import json
import traceback
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.main import app
from app.models import (
    Agent,
    Approval,
    EvaluationCase,
    ExecutionLog,
    KnowledgeBase,
    MockITAccessRequest,
    Tool,
)
from app.models.enums import MembershipRole, MembershipStatus, UserStatus, WorkspaceStatus
from app.schemas.evaluation import CaseCreate, DatasetCreate
from app.services import evaluation
from tests.evaluation_support import case_body
from tests.integration.test_knowledge_base_api import (
    add_membership,
    bearer,
    create_user,
    create_workspace,
)

pytestmark = pytest.mark.integration
SENTINEL = "EVALUATION-SECRET-SENTINEL-9e72"


@pytest.fixture
def settings(database_urls):
    runtime, test = database_urls
    assert test.database == "enterprise_ai_workbench_test"
    return Settings(
        database_url=str(runtime),
        test_database_url=str(test),
        jwt_secret_key="evaluation-test-secret-longer-than-thirty-two-bytes",
        _env_file=None,
    )


@pytest.fixture
def client(db_session, settings) -> Generator[TestClient, None, None]:
    def session_override():
        try:
            yield db_session
        except Exception:
            db_session.rollback()
            raise

    app.dependency_overrides[get_db_session] = session_override
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as result:
            yield result
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def scenario(db_session, settings):
    user = create_user(db_session, email=f"eval-{uuid4()}@example.test")
    workspace = create_workspace(db_session, slug=f"eval-{uuid4()}")
    membership = add_membership(db_session, user, workspace, role=MembershipRole.AGENT_ADMIN)
    parent = evaluation.create_dataset(
        db_session, workspace.id, user.id, DatasetCreate(name="Synthetic")
    )
    child = evaluation.create_case(
        db_session, workspace.id, parent.id, user.id, CaseCreate.model_validate(case_body())
    )
    return user, workspace, membership, parent, child, bearer(user, settings)


def paths(workspace, parent, child):
    root = f"/api/workspaces/{workspace.id}/evaluation-datasets"
    detail = f"{root}/{parent.id}"
    return root, detail, f"{detail}/cases", f"{detail}/cases/{child.id}"


OPERATIONS = [
    ("get", 0, None),
    ("post", 0, {"name": "New dataset"}),
    ("get", 1, None),
    ("patch", 1, {"name": "Edited dataset"}),
    ("get", 2, None),
    ("post", 2, case_body()),
    ("get", 3, None),
    ("patch", 3, {"description": "Edited case"}),
]


@pytest.mark.parametrize("role", list(MembershipRole))
@pytest.mark.parametrize("method,path_index,body", OPERATIONS)
def test_authorization_matrix(client, db_session, scenario, role, method, path_index, body):
    _, workspace, membership, parent, child, headers = scenario
    membership.role = role
    db_session.commit()
    response = client.request(
        method, paths(workspace, parent, child)[path_index], json=body, headers=headers
    )
    allowed = role in (MembershipRole.AGENT_ADMIN, MembershipRole.SYSTEM_ADMIN)
    assert (
        response.status_code == (201 if method == "post" else 200)
        if allowed
        else response.status_code == 403
    )


@pytest.mark.parametrize("method,path_index,body", OPERATIONS)
def test_all_routes_require_auth(client, scenario, method, path_index, body):
    _, workspace, _, parent, child, _ = scenario
    response = client.request(method, paths(workspace, parent, child)[path_index], json=body)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("ineligible", ["user", "workspace", "disabled", "invited", "absent"])
def test_inactive_access(client, db_session, scenario, ineligible):
    user, workspace, membership, parent, child, headers = scenario
    if ineligible == "user":
        user.status = UserStatus.DISABLED
    elif ineligible == "workspace":
        workspace.status = WorkspaceStatus.DISABLED
    elif ineligible == "absent":
        other = create_user(db_session, email=f"absent-{uuid4()}@example.test")
        headers = bearer(other, app.dependency_overrides[get_settings]())
    else:
        membership.status = MembershipStatus(ineligible)
    db_session.commit()
    response = client.get(paths(workspace, parent, child)[0], headers=headers)
    assert response.status_code == 403


def test_crud_lifecycle_and_summary(client, scenario):
    user, workspace, _, parent, child, headers = scenario
    root, detail, collection, case = paths(workspace, parent, child)
    response = client.get(case, headers=headers).json()
    assert response["created_by"] == str(user.id)
    assert response["workspace_id"] == str(workspace.id)
    assert response["schema_version"] == 1
    summary = client.get(collection, headers=headers).json()["items"][0]
    assert "test_input" not in summary and "expected_behavior" not in summary
    assert client.patch(detail, json={"status": "disabled"}, headers=headers).status_code == 200
    assert client.post(collection, json=case_body(), headers=headers).status_code == 409
    assert client.get(case, headers=headers).json()["status"] == "active"
    changed = client.patch(
        case, json={"status": "disabled", "description": "changed"}, headers=headers
    )
    assert changed.status_code == 200
    assert changed.json()["description"] == "changed"
    assert (
        client.patch(case, json={"description": None}, headers=headers).json()["description"]
        is None
    )
    assert client.get(collection, params={"status": "disabled"}, headers=headers).json()["items"]
    assert client.patch(detail, json={"status": "active"}, headers=headers).status_code == 200
    assert client.post(collection, json=case_body(), headers=headers).status_code == 201
    assert client.patch(case, json={"status": "active"}, headers=headers).status_code == 200
    assert client.delete(case, headers=headers).status_code == 405
    assert client.post(f"{detail}/run", headers=headers).status_code == 404
    assert client.get(root, params={"status": "disabled"}, headers=headers).json()["items"] == []


def test_foreign_missing_and_wrong_parent_ids(client, db_session, scenario):
    user, workspace, _, parent, child, headers = scenario
    foreign = create_workspace(db_session, slug=f"foreign-{uuid4()}")
    add_membership(db_session, user, foreign, role=MembershipRole.SYSTEM_ADMIN)
    other_parent = evaluation.create_dataset(
        db_session, foreign.id, user.id, DatasetCreate(name="Other")
    )
    local_parent = evaluation.create_dataset(
        db_session, workspace.id, user.id, DatasetCreate(name="Local")
    )
    root, _, _, _ = paths(workspace, parent, child)
    for suffix in ("", "/cases", f"/cases/{child.id}"):
        for method in ("get", "patch" if suffix != "/cases" else "post"):
            body = case_body() if suffix == "/cases" else {"name": "Updated"}
            foreign_response = client.request(
                method, f"{root}/{other_parent.id}{suffix}", json=body, headers=headers
            )
            missing_response = client.request(
                method, f"{root}/{uuid4()}{suffix}", json=body, headers=headers
            )
            assert foreign_response.status_code == missing_response.status_code == 404
            assert foreign_response.json() == missing_response.json()
    wrong = client.get(f"{root}/{local_parent.id}/cases/{child.id}", headers=headers)
    missing = client.get(f"{root}/{local_parent.id}/cases/{uuid4()}", headers=headers)
    assert wrong.status_code == missing.status_code == 404
    assert wrong.json() == missing.json()
    listed = client.get(root, headers=headers).json()["items"]
    assert str(other_parent.id) not in {row["id"] for row in listed}


@pytest.mark.parametrize(
    "column,model", [("agent_id", Agent), ("knowledge_base_id", KnowledgeBase), ("tool_id", Tool)]
)
def test_foreign_and_missing_references(client, db_session, scenario, column, model):
    user, workspace, _, parent, child, headers = scenario
    foreign = create_workspace(db_session, slug=f"ref-{uuid4()}")
    kwargs = {"workspace_id": foreign.id, "created_by": user.id, "name": "Foreign"}
    if model is Agent:
        kwargs["system_prompt"] = "Synthetic scope"
    if model is Tool:
        kwargs.update(
            tool_key="get_reimbursement_status", risk_level="low", description="Synthetic"
        )
    target = model(**kwargs)
    db_session.add(target)
    db_session.commit()
    collection = paths(workspace, parent, child)[2]
    body = case_body(
        "knowledge_qa"
        if model is KnowledgeBase
        else "tool_calling"
        if model is Tool
        else "refusal_behavior"
    )
    if model is Tool:
        body["expected_behavior"].update(
            outcome="executed", tool_key="get_reimbursement_status", non_execution_reason=None
        )
    responses = []
    for identifier in (target.id, uuid4()):
        body[column] = str(identifier)
        responses.append(client.post(collection, json=body, headers=headers))
    assert [r.status_code for r in responses] == [404, 404]
    assert (
        responses[0].json() == responses[1].json() == {"detail": "Evaluation reference not found"}
    )
    # A failed reference write left the existing child intact.
    assert client.get(paths(workspace, parent, child)[3], headers=headers).status_code == 200


def test_all_categories_and_atomic_merged_patch(client, db_session, scenario):
    user, workspace, _, parent, child, headers = scenario
    kb = KnowledgeBase(
        workspace_id=workspace.id, created_by=user.id, name="Synthetic KB", status="disabled"
    )
    tool = Tool(
        workspace_id=workspace.id,
        created_by=user.id,
        name="Synthetic Tool",
        description="Synthetic",
        tool_key="get_reimbursement_status",
        risk_level="low",
        status="disabled",
    )
    agent = Agent(
        workspace_id=workspace.id,
        created_by=user.id,
        name="Synthetic Agent",
        system_prompt="Synthetic",
    )
    db_session.add_all([kb, tool, agent])
    db_session.commit()
    collection = paths(workspace, parent, child)[2]
    for category in ("knowledge_qa", "tool_calling", "permission_boundary", "refusal_behavior"):
        body = case_body(category)
        if category == "knowledge_qa":
            body["knowledge_base_id"] = str(kb.id)
        if category == "tool_calling":
            body["tool_id"] = str(tool.id)
            body["expected_behavior"].update(
                outcome="executed", tool_key="get_reimbursement_status", non_execution_reason=None
            )
        result = client.post(collection, json=body, headers=headers)
        assert result.status_code == 201, result.text
        url = f"{collection}/{result.json()['id']}"
        if category == "knowledge_qa":
            invalid = client.patch(
                url, json={"name": "must rollback", "knowledge_base_id": None}, headers=headers
            )
            assert invalid.status_code == 422
            assert client.get(url, headers=headers).json()["name"] == "Synthetic case"
        if category == "tool_calling":
            mismatch = dict(result.json()["expected_behavior"], tool_key="get_employee_information")
            assert (
                client.patch(url, json={"expected_behavior": mismatch}, headers=headers).status_code
                == 422
            )
            updated = client.patch(
                url,
                json={
                    "expected_behavior": case_body(category)["expected_behavior"],
                    "tool_id": None,
                    "agent_id": str(agent.id),
                },
                headers=headers,
            )
            assert updated.status_code == 200
            assert updated.json()["tool_id"] is None
        assert client.patch(url, json={"case_type": "other"}, headers=headers).status_code == 422


@pytest.mark.parametrize(
    "invalid", ["malformed_json", "missing", "extra", "nested", "path", "query", "patch"]
)
def test_validation_boundary_sentinel(client, db_session, scenario, caplog, capsys, invalid):
    _, workspace, _, parent, child, headers = scenario
    root, _, collection, case = paths(workspace, parent, child)
    body = case_body()
    body["test_input"] = SENTINEL
    try:
        if invalid == "malformed_json":
            response = client.post(
                collection,
                content='{"test_input":"' + SENTINEL + '",',
                headers={**headers, "Content-Type": "application/json"},
            )
        elif invalid == "path":
            response = client.get(f"{root}/{SENTINEL}", headers=headers)
        elif invalid == "query":
            response = client.get(collection, params={"case_type": SENTINEL}, headers=headers)
        elif invalid == "patch":
            response = client.patch(
                case, json={"expected_behavior": {"routing_intent": SENTINEL}}, headers=headers
            )
        else:
            if invalid == "missing":
                del body["name"]
            elif invalid == "extra":
                body["creator"] = SENTINEL
            else:
                body["expected_behavior"]["safe_response_required"] = SENTINEL
            response = client.post(collection, json=body, headers=headers)
    except Exception:
        assert SENTINEL not in traceback.format_exc()
        raise
    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid evaluation request"}
    assert SENTINEL not in response.text
    # HTTP access logs contain paths; prohibit content in application logger records.
    application = "\n".join(
        record.getMessage()
        for record in caplog.records
        if record.name.startswith(("app", "sqlalchemy", "uvicorn.error"))
    )
    assert SENTINEL not in application
    output = capsys.readouterr()
    assert SENTINEL not in output.out + output.err
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(ExecutionLog)
            .where(ExecutionLog.workspace_id == workspace.id)
        )
        == 0
    )
    assert SENTINEL not in json.dumps(
        [row.details for row in db_session.scalars(select(ExecutionLog))]
    )


def test_no_execution_and_safe_storage(client, db_session, scenario, monkeypatch, caplog):
    from app.api.routes import agents as agent_routes
    from app.services import (
        answers,
        approvals,
        embeddings,
        generation,
        routing,
        tool_execution,
        tool_selection,
        tools,
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("Evaluation CRUD must never execute")

    for module, name in [
        (agent_routes, "_route_agent_request"),
        (answers, "answer_question"),
        (approvals, "create_pending_approval"),
        (tool_execution, "get_reimbursement_status"),
    ]:
        monkeypatch.setattr(module, name, forbidden)
    monkeypatch.setattr(tools, "handle_tool_request", forbidden)
    for module in (routing, tool_selection, embeddings, generation):
        monkeypatch.setattr(module, "OpenAI", forbidden)
    monkeypatch.setattr(routing, "create_openai_routing_provider", forbidden)
    monkeypatch.setattr(tool_selection, "create_openai_tool_selector", forbidden)
    _, workspace, _, parent, child, headers = scenario
    body = case_body()
    body["test_input"] = SENTINEL
    result = client.post(paths(workspace, parent, child)[2], json=body, headers=headers)
    assert result.status_code == 201
    assert result.json()["test_input"] == SENTINEL
    for model in (ExecutionLog, Approval, MockITAccessRequest):
        assert (
            db_session.scalar(
                select(func.count()).select_from(model).where(model.workspace_id == workspace.id)
            )
            == 0
        )
    assert SENTINEL not in caplog.text


def test_pagination_filters(client, db_session, scenario):
    _, workspace, _, parent, child, headers = scenario
    collection = paths(workspace, parent, child)[2]
    base = datetime(2026, 1, 1, tzinfo=UTC)
    child.created_at = base
    db_session.commit()
    for index, name in enumerate(("A", "B", "C"), start=1):
        response = client.post(collection, json={**case_body(), "name": name}, headers=headers)
        assert response.status_code == 201
        stored = db_session.get(EvaluationCase, UUID(response.json()["id"]))
        stored.created_at = base + timedelta(seconds=index)
        db_session.commit()
    first = client.get(collection, params={"limit": 2}, headers=headers).json()
    second = client.get(collection, params={"limit": 2, "offset": 2}, headers=headers).json()
    assert [row["name"] for row in first["items"]] == ["C", "B"]
    assert [row["name"] for row in second["items"]] == ["A", "Synthetic case"]
    assert (
        client.get(collection, params={"case_type": "knowledge_qa"}, headers=headers).json()[
            "items"
        ]
        == []
    )
    for query in ({"limit": 0}, {"limit": 101}, {"offset": -1}, {"status": "future"}):
        assert client.get(collection, params=query, headers=headers).status_code == 422
