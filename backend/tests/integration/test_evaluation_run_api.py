from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api.routes.evaluation_runs import evaluation_providers, evaluation_session
from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.main import app
from app.models import (
    Agent,
    AgentTool,
    Approval,
    Chunk,
    Document,
    EvaluationRun,
    ExecutionLog,
    KnowledgeBase,
    MockITAccessRequest,
    Tool,
)
from app.models.enums import (
    AgentStatus,
    DocumentStatus,
    MembershipRole,
    MembershipStatus,
    ToolStatus,
)
from app.schemas.agent_routing import RoutingIntent
from app.schemas.answer import AnswerStatus, ModelGenerationOutput
from app.schemas.evaluation import CaseCreate, DatasetCreate
from app.schemas.evaluation_run import RunCreate
from app.services import evaluation, evaluation_runs
from app.services.generation import GeneratedAnswer
from app.services.routing import RoutingProviderError
from app.services.tool_selection import ToolSelectionProposal
from tests.evaluation_support import case_body
from tests.integration.test_knowledge_base_api import (
    add_membership,
    bearer,
    create_user,
    create_workspace,
)

pytestmark = pytest.mark.integration


class FakeProviders:
    def __init__(self):
        self.intent = RoutingIntent.UNSUPPORTED
        self.calls = []
        self.callback = None
        self.error = None
        self.selection = ToolSelectionProposal("get_employee_information", {"subject": "self"})

    def routing(self, settings):
        def route(request, scope):
            self.calls.append(("routing", request, scope, settings.openai_timeout_seconds))
            if self.callback:
                self.callback()
            if self.error:
                raise self.error
            return self.intent

        return SimpleNamespace(route=route)

    def selector(self, settings):
        def select_tool(request, scope, candidates):
            self.calls.append(("selector", request, [c.tool_key for c in candidates]))
            return self.selection

        return SimpleNamespace(select=select_tool)

    def embedding(self, settings):
        self.calls.append(("embedding", settings.openai_timeout_seconds))
        return SimpleNamespace(embed_texts=lambda texts: [[1.0] + [0.0] * 1535 for _ in texts])

    def generation(self, settings):
        def generate(question, evidence):
            self.calls.append(("generation", question, len(evidence)))
            return GeneratedAnswer(
                output=ModelGenerationOutput(
                    status=AnswerStatus.ANSWERED,
                    answer="Synthetic answer",
                    citations=[{"evidence_ref": "E1", "excerpt": "Synthetic evidence"}],
                ),
                usage=None,
            )

        return SimpleNamespace(generate=generate)


@pytest.fixture
def scenario(db_session, database_urls):
    runtime, test = database_urls
    assert test.database == "enterprise_ai_workbench_test"
    settings = Settings(
        database_url=str(runtime),
        test_database_url=str(test),
        jwt_secret_key="feature016-test-secret-more-than-32-bytes",
        _env_file=None,
    )
    user = create_user(db_session, email=f"run-{uuid4()}@example.test")
    workspace = create_workspace(db_session, slug=f"run-{uuid4()}")
    member = add_membership(db_session, user, workspace, role=MembershipRole.AGENT_ADMIN)
    agent = Agent(
        workspace_id=workspace.id,
        created_by=user.id,
        name="Captured Agent",
        system_prompt="Synthetic evaluation scope",
        status=AgentStatus.ACTIVE,
    )
    kb = KnowledgeBase(workspace_id=workspace.id, created_by=user.id, name="Synthetic KB")
    db_session.add_all([agent, kb])
    db_session.commit()
    dataset = evaluation.create_dataset(
        db_session, workspace.id, user.id, DatasetCreate(name="Captured Dataset")
    )
    providers = FakeProviders()
    return SimpleNamespace(
        user=user,
        workspace=workspace,
        member=member,
        agent=agent,
        kb=kb,
        dataset=dataset,
        providers=providers,
        settings=settings,
        headers=bearer(user, settings),
    )


@pytest.fixture
def client(db_session, scenario):
    def session_override():
        yield db_session

    app.dependency_overrides[get_db_session] = session_override
    app.dependency_overrides[evaluation_session] = session_override
    app.dependency_overrides[get_settings] = lambda: scenario.settings
    app.dependency_overrides[evaluation_providers] = lambda: scenario.providers
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def add_case(db_session, s, category="refusal_behavior", **overrides):
    body = case_body(category)
    if category == "knowledge_qa":
        body["knowledge_base_id"] = str(s.kb.id)
    body.update(overrides)
    return evaluation.create_case(
        db_session, s.workspace.id, s.dataset.id, s.user.id, CaseCreate.model_validate(body)
    )


def root(s):
    return f"/api/workspaces/{s.workspace.id}"


def post(client, s, **overrides):
    return client.post(
        f"{root(s)}/evaluation-datasets/{s.dataset.id}/runs",
        json={"agent_id": str(s.agent.id), "provider_egress_acknowledged": True, **overrides},
        headers=s.headers,
    )


def forbid_side_effects(monkeypatch):
    from app.services import approval_execution, approvals, tool_execution, tools

    def forbidden(*args, **kwargs):
        pytest.fail("Evaluation reached a production side effect")

    monkeypatch.setattr(tools, "create_pending_approval", forbidden)
    monkeypatch.setattr(approvals, "create_pending_approval", forbidden)
    monkeypatch.setattr(tool_execution, "get_employee_information", forbidden)
    monkeypatch.setattr(tool_execution, "get_reimbursement_status", forbidden)
    monkeypatch.setattr(
        approval_execution, "execute_mock_it_access_request", forbidden, raising=False
    )


def test_run_history_routes_and_immutable_snapshots(client, scenario, db_session, monkeypatch):
    s = scenario
    forbid_side_effects(monkeypatch)
    case = add_case(db_session, s)
    first = post(client, s)
    assert first.status_code == 201, first.text
    data = first.json()
    run_id = data["id"]
    assert data["status"] == "completed" and data["passed_cases"] == 1
    assert data["metrics"]["overall_pass_rate"]["value"] == 1
    detail = client.get(f"{root(s)}/evaluation-runs/{run_id}", headers=s.headers).json()
    assert detail["agent_snapshot"]["system_prompt"] == "Synthetic evaluation scope"
    case.test_input = "Edited later"
    case.name = "Edited name"
    s.agent.name = "Edited Agent"
    s.dataset.name = "Edited Dataset"
    db_session.commit()
    cases = client.get(f"{root(s)}/evaluation-runs/{run_id}/cases", headers=s.headers).json()
    assert cases["items"][0]["name"] == "Synthetic case"
    assert "test_input_snapshot" not in cases["items"][0]
    result = client.get(
        f"{root(s)}/evaluation-runs/{run_id}/cases/{cases['items'][0]['id']}", headers=s.headers
    ).json()
    assert result["test_input_snapshot"] == "Synthetic input"
    assert result["actual_behavior"]["response_category"] == "unsupported_request"
    history = client.get(f"{root(s)}/evaluation-runs?limit=1&offset=0", headers=s.headers).json()
    assert history["items"][0]["dataset_name"] == "Captured Dataset"
    assert history["items"][0]["agent_name"] == "Captured Agent"
    assert "agent_snapshot" not in history["items"][0]
    assert post(client, s).json()["id"] != run_id
    for model in (Approval, MockITAccessRequest, ExecutionLog):
        assert (
            db_session.scalar(
                select(func.count()).select_from(model).where(model.workspace_id == s.workspace.id)
            )
            == 0
        )


@pytest.mark.parametrize(
    "key,args,expected",
    [
        ("get_employee_information", {"subject": "self"}, "executed"),
        ("get_reimbursement_status", {}, "executed"),
        (
            "create_it_access_request",
            {
                "system": "production_database",
                "access_level": "read_only",
                "duration_days": 3,
                "business_justification": "Synthetic test",
            },
            "approval_required",
        ),
    ],
)
def test_tool_dry_run_never_dispatches(
    client, scenario, db_session, monkeypatch, key, args, expected
):
    s = scenario
    forbid_side_effects(monkeypatch)
    from app.services.tool_registry import TOOL_REGISTRY

    definition = TOOL_REGISTRY[key]
    tool = Tool(
        workspace_id=s.workspace.id,
        created_by=s.user.id,
        name="Synthetic Tool",
        description="Synthetic",
        tool_key=key,
        risk_level=definition.risk,
        status=ToolStatus.ACTIVE,
    )
    db_session.add(tool)
    db_session.commit()
    db_session.add(AgentTool(workspace_id=s.workspace.id, agent_id=s.agent.id, tool_id=tool.id))
    db_session.commit()
    add_case(
        db_session,
        s,
        "tool_calling",
        tool_id=str(tool.id),
        expected_behavior={
            "routing_intent": "tool_request",
            "outcome": expected,
            "tool_key": key,
            "approval_required": expected == "approval_required",
            "non_execution_reason": None,
        },
    )
    s.providers.intent = RoutingIntent.TOOL_REQUEST
    s.providers.selection = ToolSelectionProposal(key, args)
    response = post(client, s)
    assert response.status_code == 201, response.text
    assert response.json()["passed_cases"] == 1
    assert [c[0] for c in s.providers.calls] == ["routing", "selector"]
    run_id = response.json()["id"]
    row = evaluation_runs.case_rows(db_session, s.workspace.id, run_id)[0]
    assert row.actual_behavior["adapter_executed"] is False
    assert row.actual_behavior["would_outcome"] == expected
    assert "arguments" not in str(row.actual_behavior)
    for model in (Approval, MockITAccessRequest, ExecutionLog):
        assert (
            db_session.scalar(
                select(func.count()).select_from(model).where(model.workspace_id == s.workspace.id)
            )
            == 0
        )


def test_permission_is_local_and_wrong_denial_is_fail(client, scenario, db_session):
    s = scenario
    add_case(db_session, s, "permission_boundary")
    response = post(client, s, provider_egress_acknowledged=False)
    assert response.status_code == 201, response.text
    assert response.json()["passed_cases"] == 1
    assert s.providers.calls == []
    add_case(
        db_session,
        s,
        "permission_boundary",
        expected_behavior={
            **case_body("permission_boundary")["expected_behavior"],
            "target_context": "same_workspace",
        },
    )
    response = post(client, s, provider_egress_acknowledged=False)
    assert response.json()["failed_cases"] == 1
    assert response.json()["error_cases"] == 0


def test_real_read_only_rag_and_citation_presence(client, scenario, db_session, monkeypatch):
    s = scenario
    forbid_side_effects(monkeypatch)
    doc = Document(
        workspace_id=s.workspace.id,
        knowledge_base_id=s.kb.id,
        created_by=s.user.id,
        file_name="synthetic.txt",
        file_type="txt",
        status=DocumentStatus.READY,
        extracted_text="Synthetic evidence",
        version=1,
    )
    db_session.add(doc)
    db_session.commit()
    db_session.add(
        Chunk(
            workspace_id=s.workspace.id,
            document_id=doc.id,
            content="Synthetic evidence",
            chunk_index=0,
            embedding_model=s.settings.embedding_model,
            embedding=[1.0] + [0.0] * 1535,
        )
    )
    db_session.commit()
    add_case(db_session, s, "knowledge_qa")
    s.providers.intent = RoutingIntent.KNOWLEDGE_QA
    response = post(client, s)
    assert response.status_code == 201, response.text
    assert response.json()["passed_cases"] == 1
    row = evaluation_runs.case_rows(db_session, s.workspace.id, response.json()["id"])[0]
    assert row.actual_behavior["citation_count"] == 1
    assert row.actual_behavior["evidence"][0]["cited"] == 1
    assert "Synthetic evidence" not in str(row.actual_behavior)
    assert [c[0] for c in s.providers.calls] == ["routing", "embedding", "generation"]


@pytest.mark.parametrize("count", [0, 6])
def test_case_limit_before_provider(client, scenario, db_session, count):
    for _ in range(count):
        add_case(db_session, scenario)
    assert post(client, scenario).status_code == 409
    assert scenario.providers.calls == []


def test_consent_and_provider_error_denominators(client, scenario, db_session):
    s = scenario
    add_case(db_session, s)
    assert post(client, s, provider_egress_acknowledged=False).status_code == 422
    assert s.providers.calls == []
    s.providers.error = RoutingProviderError("SECRET-SENTINEL")
    response = post(client, s)
    assert response.status_code == 201, response.text
    assert "SECRET-SENTINEL" not in response.text
    assert response.json()["error_cases"] == 1
    assert response.json()["failed_cases"] == 0
    assert response.json()["metrics"]["overall_pass_rate"]["value"] is None


@pytest.mark.parametrize("change", ["prompt", "membership"])
def test_drift_and_revocation_fail_run(client, scenario, db_session, change):
    s = scenario
    add_case(db_session, s)
    add_case(db_session, s)

    def mutate():
        if change == "prompt":
            s.agent.system_prompt = "Changed scope"
        else:
            s.member.status = MembershipStatus.DISABLED
        db_session.commit()

    s.providers.callback = mutate
    response = post(client, s)
    assert response.status_code == (201 if change == "prompt" else 403), response.text
    run = db_session.scalar(select(EvaluationRun))
    assert run.status == "failed" and run.error_cases == 2
    assert run.failure_category == (
        "configuration_drift" if change == "prompt" else "authorization_revoked"
    )
    assert len(s.providers.calls) == 1


@pytest.mark.parametrize("role", list(MembershipRole))
def test_all_routes_role_matrix(client, scenario, db_session, role):
    s = scenario
    add_case(db_session, s, "permission_boundary")
    data = post(client, s).json()
    row = evaluation_runs.case_rows(db_session, s.workspace.id, data["id"])[0]
    s.member.role = role
    db_session.commit()
    allowed = role in {MembershipRole.AGENT_ADMIN, MembershipRole.SYSTEM_ADMIN}
    urls = [
        f"{root(s)}/evaluation-runs",
        f"{root(s)}/evaluation-runs/{data['id']}",
        f"{root(s)}/evaluation-runs/{data['id']}/cases",
        f"{root(s)}/evaluation-runs/{data['id']}/cases/{row.id}",
    ]
    for url in urls:
        assert client.get(url, headers=s.headers).status_code == (200 if allowed else 403)
    assert post(client, s).status_code == (201 if allowed else 403)


def test_missing_foreign_nested_and_validation(client, scenario, db_session):
    s = scenario
    add_case(db_session, s, "permission_boundary")
    data = post(client, s).json()
    run_id = data["id"]
    for suffix in [f"evaluation-runs/{uuid4()}", f"evaluation-runs/{run_id}/cases/{uuid4()}"]:
        assert client.get(f"{root(s)}/{suffix}", headers=s.headers).status_code == 404
    for query in ["limit=0", "limit=101", "offset=-1", "status=SECRET-SENTINEL"]:
        response = client.get(f"{root(s)}/evaluation-runs?{query}", headers=s.headers)
        assert response.status_code == 422 and "SECRET-SENTINEL" not in response.text
    assert post(client, s, actor_role="system_admin").status_code == 422
    assert client.get(f"{root(s)}/evaluation-runs").status_code == 401


def test_stale_reconciliation_fences_late_executor(client, scenario, db_session):
    s = scenario
    add_case(db_session, s, "permission_boundary")
    run_id = evaluation_runs.capture(
        db_session,
        s.workspace.id,
        s.dataset.id,
        s.user.id,
        RunCreate(agent_id=s.agent.id, provider_egress_acknowledged=False),
        s.settings,
    )
    row = evaluation_runs.run_row(db_session, s.workspace.id, run_id)
    row.started_at -= timedelta(seconds=140)
    row.deadline_at -= timedelta(seconds=140)
    db_session.commit()
    response = client.get(f"{root(s)}/evaluation-runs/{run_id}", headers=s.headers)
    assert response.status_code == 200, response.text
    assert response.json()["failure_category"] == "interrupted"
    assert response.json()["error_cases"] == 1
    evaluation_runs.execute_run(
        db_session, s.workspace.id, run_id, s.user.id, s.settings, s.providers
    )
    row = evaluation_runs.case_rows(db_session, s.workspace.id, run_id)[0]
    assert row.result == "error" and row.attempted is False and row.latency_ms is None


@pytest.mark.parametrize("fatal_store", [False, True])
def test_monotonic_latency_excludes_persistence_even_on_fatal_store(
    client, scenario, db_session, monkeypatch, fatal_store
):
    from app.services import evaluation_execution

    s = scenario
    add_case(db_session, s)
    clock = [0.0]
    timer = SimpleNamespace(monotonic=lambda: clock[0])
    monkeypatch.setattr(evaluation_runs, "time", timer)
    monkeypatch.setattr(evaluation_execution, "time", timer)
    original_attempt, original_store = evaluation_runs._attempt, evaluation_runs._store

    def attempt(*args):
        clock[0] += 10
        return original_attempt(*args)

    def store(*args):
        clock[0] += 40
        if fatal_store:
            raise evaluation_execution.EvaluationFailure("run_timeout")
        return original_store(*args)

    monkeypatch.setattr(evaluation_runs, "_attempt", attempt)
    monkeypatch.setattr(evaluation_runs, "_store", store)
    s.providers.callback = lambda: clock.__setitem__(0, clock[0] + 20)
    response = post(client, s)
    assert response.status_code == 201, response.text
    row = evaluation_runs.case_rows(db_session, s.workspace.id, response.json()["id"])[0]
    assert row.latency_ms == 20000 and row.attempted is True
    assert row.result == ("error" if fatal_store else "passed")


@pytest.mark.parametrize("seconds,expected_status", [(61, "completed"), (121, "failed")])
def test_clock_controlled_case_and_run_timeouts(
    client, scenario, db_session, monkeypatch, seconds, expected_status
):
    from app.services import evaluation_execution

    s = scenario
    first = add_case(db_session, s)
    second = add_case(db_session, s, "permission_boundary")
    second.created_at = first.created_at + timedelta(seconds=1)
    db_session.commit()
    clock = [0.0]
    timer = SimpleNamespace(monotonic=lambda: clock[0])
    monkeypatch.setattr(evaluation_runs, "time", timer)
    monkeypatch.setattr(evaluation_execution, "time", timer)
    s.providers.callback = lambda: clock.__setitem__(0, seconds)
    response = post(client, s)
    assert response.status_code == 201, response.text
    assert response.json()["status"] == expected_status
    rows = evaluation_runs.case_rows(db_session, s.workspace.id, response.json()["id"])
    assert rows[0].error_category == ("case_timeout" if seconds == 61 else "run_timeout")
    assert rows[1].attempted == (seconds == 61)


def test_case_listing_rechecks_authority_after_query(client, scenario, db_session, monkeypatch):
    s = scenario
    add_case(db_session, s, "permission_boundary")
    run = post(client, s).json()
    original = evaluation_runs.case_rows
    calls = [0]

    def query(*args):
        rows = original(*args)
        calls[0] += 1
        if calls[0] == 2:
            s.member.status = MembershipStatus.DISABLED
            db_session.commit()
        return rows

    monkeypatch.setattr(evaluation_runs, "case_rows", query)
    response = client.get(f"{root(s)}/evaluation-runs/{run['id']}/cases", headers=s.headers)
    assert response.status_code == 403
    assert "Synthetic case" not in response.text


def test_partial_persistence_failure_preserves_prior_terminal_results(
    client, scenario, db_session, monkeypatch
):
    from sqlalchemy.exc import StatementError

    s = scenario
    add_case(db_session, s, "permission_boundary")
    add_case(db_session, s, "permission_boundary")
    original = evaluation_runs._store
    calls = [0]

    def store(*args):
        calls[0] += 1
        if calls[0] == 2:
            raise StatementError("SECRET-SENTINEL", "SQL", {}, ValueError("SECRET-SENTINEL"))
        return original(*args)

    monkeypatch.setattr(evaluation_runs, "_store", store)
    response = post(client, s)
    assert response.status_code == 201, response.text
    assert "SECRET-SENTINEL" not in response.text
    assert response.json()["status"] == "failed"
    assert response.json()["passed_cases"] == response.json()["error_cases"] == 1
    rows = evaluation_runs.case_rows(db_session, s.workspace.id, response.json()["id"])
    assert rows[0].result == "passed" and rows[1].error_category == "persistence_failure"


def test_foreign_run_case_filters_and_composite_fks(client, scenario, db_session):
    from sqlalchemy.exc import IntegrityError

    from app.models import EvaluationRunCase

    s = scenario
    add_case(db_session, s, "permission_boundary")
    local_run = post(client, s).json()
    foreign_workspace = create_workspace(db_session, slug=f"foreign-run-{uuid4()}")
    add_membership(db_session, s.user, foreign_workspace, role=MembershipRole.AGENT_ADMIN)
    foreign_agent = Agent(
        workspace_id=foreign_workspace.id,
        created_by=s.user.id,
        name="Foreign",
        system_prompt="Synthetic",
        status=AgentStatus.ACTIVE,
    )
    db_session.add(foreign_agent)
    db_session.commit()
    foreign_dataset = evaluation.create_dataset(
        db_session, foreign_workspace.id, s.user.id, DatasetCreate(name="Foreign")
    )
    foreign_case = evaluation.create_case(
        db_session,
        foreign_workspace.id,
        foreign_dataset.id,
        s.user.id,
        CaseCreate.model_validate(case_body("permission_boundary")),
    )
    foreign_id = evaluation_runs.create_run(
        db_session,
        foreign_workspace.id,
        foreign_dataset.id,
        s.user.id,
        RunCreate(agent_id=foreign_agent.id, provider_egress_acknowledged=False),
        s.settings,
        s.providers,
    ).id
    foreign_result = evaluation_runs.case_rows(db_session, foreign_workspace.id, foreign_id)[0]
    for path in [
        f"evaluation-runs/{foreign_id}",
        f"evaluation-runs/{local_run['id']}/cases/{foreign_result.id}",
        f"evaluation-runs?dataset_id={foreign_dataset.id}",
        f"evaluation-runs?agent_id={foreign_agent.id}",
    ]:
        response = client.get(f"{root(s)}/{path}", headers=s.headers)
        assert response.status_code == 404
        assert "Foreign" not in response.text
    assert post(client, s, agent_id=str(foreign_agent.id)).status_code == 404
    # The database also rejects Workspace spoofing, even without the service loader.
    row = evaluation_runs.case_rows(db_session, s.workspace.id, local_run["id"])[0]
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(
            EvaluationRunCase(
                workspace_id=s.workspace.id,
                run_id=foreign_id,
                case_id=row.case_id,
                ordinal=1,
                case_type=row.case_type,
                case_snapshot=row.case_snapshot,
                test_input_snapshot=row.test_input_snapshot,
                expected_behavior_snapshot=row.expected_behavior_snapshot,
                context_snapshot=row.context_snapshot,
            )
        )
        db_session.flush()
    with pytest.raises(IntegrityError), db_session.begin_nested():
        row.case_id = foreign_case.id
        db_session.flush()


def test_knowledge_configuration_and_corpus_drift(client, scenario, db_session):
    s = scenario
    add_case(db_session, s, "knowledge_qa")
    s.providers.intent = RoutingIntent.KNOWLEDGE_QA

    def mutate():
        s.kb.name = "Changed KB"
        db_session.commit()

    s.providers.callback = mutate
    response = post(client, s)
    assert response.status_code == 201, response.text
    assert response.json()["failure_category"] == "configuration_drift"
    assert [c[0] for c in s.providers.calls] == ["routing"]


def test_disabled_kb_is_error_and_unexpected_tool_route_never_dispatches(
    client, scenario, db_session, monkeypatch
):
    s = scenario
    forbid_side_effects(monkeypatch)
    add_case(db_session, s, "knowledge_qa")
    s.kb.status = "disabled"
    db_session.commit()
    s.providers.intent = RoutingIntent.KNOWLEDGE_QA
    response = post(client, s)
    assert response.json()["error_cases"] == 1 and response.json()["status"] == "completed"
    s.providers.intent = RoutingIntent.TOOL_REQUEST
    response = post(client, s)
    assert response.json()["failed_cases"] == 1 and response.json()["error_cases"] == 0
    assert "selector" not in [c[0] for c in s.providers.calls]


def test_unavailable_persistence_is_fixed_500(client, scenario, db_session, monkeypatch):
    from sqlalchemy.exc import StatementError

    s = scenario
    add_case(db_session, s)

    def unavailable(*args, **kwargs):
        raise StatementError("SECRET-SENTINEL", "SQL", {}, ValueError("SECRET-SENTINEL"))

    monkeypatch.setattr(evaluation_runs, "capture", unavailable)
    response = post(client, s)
    assert response.status_code == 500 and response.json() == {
        "detail": "Evaluation persistence unavailable"
    }
    assert s.providers.calls == []


def test_malformed_tool_arguments_are_error_without_side_effects(
    client, scenario, db_session, monkeypatch
):
    s = scenario
    forbid_side_effects(monkeypatch)
    from app.services.tool_registry import TOOL_REGISTRY

    key = "get_employee_information"
    tool = Tool(
        workspace_id=s.workspace.id,
        created_by=s.user.id,
        name="Synthetic",
        description="Synthetic",
        tool_key=key,
        risk_level=TOOL_REGISTRY[key].risk,
        status=ToolStatus.ACTIVE,
    )
    db_session.add(tool)
    db_session.commit()
    db_session.add(AgentTool(workspace_id=s.workspace.id, agent_id=s.agent.id, tool_id=tool.id))
    db_session.commit()
    add_case(
        db_session,
        s,
        "tool_calling",
        tool_id=str(tool.id),
        expected_behavior={
            "routing_intent": "tool_request",
            "outcome": "executed",
            "tool_key": key,
            "approval_required": False,
            "non_execution_reason": None,
        },
    )
    s.providers.intent = RoutingIntent.TOOL_REQUEST
    s.providers.selection = ToolSelectionProposal(
        key, {"subject": "other", "secret": "SECRET-SENTINEL"}
    )
    response = post(client, s)
    assert response.status_code == 201, response.text
    assert response.json()["error_cases"] == 1 and response.json()["failed_cases"] == 0
    row = evaluation_runs.case_rows(db_session, s.workspace.id, response.json()["id"])[0]
    assert row.error_category == "provider_contract"
    assert "SECRET-SENTINEL" not in str(row.actual_behavior) + response.text


def test_invalid_citation_is_error_not_semantic_failure(client, scenario, db_session, monkeypatch):
    s = scenario
    add_case(db_session, s, "knowledge_qa")
    doc = Document(
        workspace_id=s.workspace.id,
        knowledge_base_id=s.kb.id,
        created_by=s.user.id,
        file_name="synthetic.txt",
        file_type="txt",
        status=DocumentStatus.READY,
        extracted_text="Synthetic evidence",
        version=1,
    )
    db_session.add(doc)
    db_session.commit()
    db_session.add(
        Chunk(
            workspace_id=s.workspace.id,
            document_id=doc.id,
            content="Synthetic evidence",
            chunk_index=0,
            embedding_model=s.settings.embedding_model,
            embedding=[1.0] + [0.0] * 1535,
        )
    )
    db_session.commit()
    s.providers.intent = RoutingIntent.KNOWLEDGE_QA
    monkeypatch.setattr(
        s.providers,
        "generation",
        lambda settings: SimpleNamespace(
            generate=lambda *_: GeneratedAnswer(
                output=ModelGenerationOutput(
                    status="answered",
                    answer="Synthetic answer",
                    citations=[{"evidence_ref": "E1", "excerpt": "SECRET-SENTINEL"}],
                ),
                usage=None,
            )
        ),
    )
    response = post(client, s)
    assert response.status_code == 201, response.text
    assert response.json()["error_cases"] == 1 and response.json()["failed_cases"] == 0
    row = evaluation_runs.case_rows(db_session, s.workspace.id, response.json()["id"])[0]
    assert row.error_category == "provider_contract"
    assert "SECRET-SENTINEL" not in response.text + str(row.actual_behavior)


def test_snapshot_allowlist_and_oversize_capture(client, scenario, db_session, monkeypatch):
    from app.services import evaluation_snapshot

    s = scenario
    add_case(db_session, s, "permission_boundary")
    response = post(client, s)
    detail = evaluation_runs.read_run(db_session, s.workspace.id, response.json()["id"], s.user.id)
    serialized = str(detail.config_snapshot)
    assert "database_url" not in serialized and "jwt_secret_key" not in serialized
    assert s.settings.jwt_secret_key.get_secret_value() not in serialized

    def oversized(*args):
        raise evaluation_snapshot.SnapshotTooLarge()

    monkeypatch.setattr(evaluation_runs, "_context", oversized)
    response = post(client, s)
    assert response.status_code == 409
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(EvaluationRun)
            .where(EvaluationRun.workspace_id == s.workspace.id)
        )
        == 1
    )


def test_create_rechecks_authority_after_final_summary(client, scenario, db_session, monkeypatch):
    s = scenario
    add_case(db_session, s, "permission_boundary")
    original = evaluation_runs.summary

    def summarize(*args, **kwargs):
        result = original(*args, **kwargs)
        s.member.status = MembershipStatus.DISABLED
        db_session.commit()
        return result

    monkeypatch.setattr(evaluation_runs, "summary", summarize)
    response = post(client, s)
    assert response.status_code == 403
    assert "Synthetic" not in response.text
