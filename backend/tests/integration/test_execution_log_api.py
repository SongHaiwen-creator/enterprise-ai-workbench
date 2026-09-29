"""Feature 014 execution log recording and read API tests."""

import time
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.dependencies.embeddings import get_embedding_provider
from app.api.dependencies.generation import get_generation_provider
from app.core.config import Settings
from app.main import app
from app.models import Agent, Approval, ExecutionLog, KnowledgeBase, Tool
from app.models.enums import (
    AgentStatus,
    KnowledgeBaseStatus,
    MembershipRole,
    MembershipStatus,
    ToolRisk,
    ToolStatus,
    WorkspaceStatus,
)
from app.schemas.agent_routing import RoutingIntent
from app.schemas.answer import AnswerStatus
from app.services import approvals as approval_service
from app.services import execution_logs
from app.services.answers import AnswerCitation, AnswerResult
from app.services.generation import GenerationUsage
from app.services.routing import RoutingInputTooLargeError, RoutingProviderError
from app.services.tool_selection import ToolSelectionDecline, ToolSelectionProposal
from tests.integration.approval_support import (
    ARGUMENTS,
    FakeRoutingProvider,
    FakeToolSelector,
    Scenario,
    bearer,
    decide,
    install_overrides,
    make_membership,
    make_scenario,
    make_settings,
    make_user,
    request_approval,
    set_status,
)

pytestmark = pytest.mark.integration

REQUEST_SENTINEL = "SENTINEL-request-text-7f3a"
ANSWER_SENTINEL = "SENTINEL-answer-text-91bc"
NOTE_SENTINEL = "SENTINEL-decision-note-55de"
SYSTEM_PROMPT_SENTINEL = "SENTINEL-system-prompt-0c2e"


class KnowledgeGenerationProvider:
    model = "gpt-5.6-terra"
    reasoning_effort = "low"
    prompt_version = "grounded-answer-v1"
    retrieval_limit = 5
    max_input_tokens = 12_000
    max_output_tokens = 1_200

    def generate(self, question: str, evidence: object) -> None:
        del question, evidence
        raise AssertionError("answer_question is replaced in these tests")


class UnusedEmbeddingProvider:
    model = "text-embedding-3-small"
    dimensions = 1536

    def embed_texts(self, texts: object) -> list[list[float]]:
        del texts
        raise AssertionError("embedding must not be reached in these tests")


@pytest.fixture
def settings(database_urls: tuple[object, object]) -> Settings:
    return make_settings(database_urls)


@pytest.fixture
def router_provider() -> FakeRoutingProvider:
    return FakeRoutingProvider()


@pytest.fixture
def selector() -> FakeToolSelector:
    return FakeToolSelector()


@pytest.fixture
def client(
    db_session: Session,
    settings: Settings,
    router_provider: FakeRoutingProvider,
    selector: FakeToolSelector,
) -> Generator[TestClient, None, None]:
    def override_db_session() -> Generator[Session, None, None]:
        # Release fixture setup into the test connection's outer transaction
        # before the request starts.  The production recorder may then roll
        # back the request Session unconditionally without erasing setup.
        db_session.commit()
        yield db_session

    try:
        yield from install_overrides(override_db_session, settings, router_provider, selector)
    finally:
        app.dependency_overrides.pop(get_embedding_provider, None)


@pytest.fixture
def scenario(db_session: Session) -> Scenario:
    result = make_scenario(db_session)
    result.agent.system_prompt = SYSTEM_PROMPT_SENTINEL
    db_session.flush()
    return result


def use_knowledge_fakes(monkeypatch: pytest.MonkeyPatch, status: AnswerStatus) -> None:
    app.dependency_overrides[get_generation_provider] = KnowledgeGenerationProvider
    app.dependency_overrides[get_embedding_provider] = UnusedEmbeddingProvider
    monkeypatch.setattr(
        "app.api.routes.agents.create_openai_embedding_provider",
        lambda settings: UnusedEmbeddingProvider(),
    )

    def answer_question(
        session: Session, workspace_id: UUID, knowledge_base_id: UUID, question: str,
        embedding_provider: object, generation_provider: object,
    ) -> AnswerResult:
        del session, workspace_id, knowledge_base_id, embedding_provider, generation_provider
        answered = status is AnswerStatus.ANSWERED
        return AnswerResult(
            question=question,
            status=status,
            answer=ANSWER_SENTINEL if answered else None,
            message=None if answered else "Not enough evidence.",
            citations=[
                AnswerCitation(
                    document_id=uuid4(), file_name="SENTINEL-file.md", document_version=1,
                    chunk_id=uuid4(), chunk_index=0, excerpt=ANSWER_SENTINEL,
                )
            ] if answered else [],
            usage=GenerationUsage(input_tokens=120, output_tokens=30, total_tokens=150),
        )

    monkeypatch.setattr("app.services.answers.answer_question", answer_question)


def add_tool(session: Session, scenario: Scenario, tool_key: str) -> Tool:
    tool = Tool(
        workspace_id=scenario.workspace.id,
        created_by=scenario.reviewer.id,
        tool_key=tool_key,
        name=f"{tool_key} tool",
        description="Read-only enterprise capability.",
        risk_level=ToolRisk.LOW,
        status=ToolStatus.ACTIVE,
    )
    session.add(tool)
    session.flush()
    session.execute(
        text(
            "INSERT INTO agent_tools (workspace_id, agent_id, tool_id) "
            "VALUES (:workspace_id, :agent_id, :tool_id)"
        ),
        {"workspace_id": scenario.workspace.id, "agent_id": scenario.agent.id, "tool_id": tool.id},
    )
    session.flush()
    return tool


def add_knowledge_base(
    session: Session, scenario: Scenario, status: KnowledgeBaseStatus = KnowledgeBaseStatus.ACTIVE
) -> KnowledgeBase:
    result = KnowledgeBase(
        workspace_id=scenario.workspace.id, name="Travel Policies",
        created_by=scenario.reviewer.id, status=status,
    )
    session.add(result)
    session.flush()
    return result


def logs(session: Session, scenario: Scenario, operation: str | None = None) -> list[ExecutionLog]:
    statement = select(ExecutionLog).where(ExecutionLog.workspace_id == scenario.workspace.id)
    if operation is not None:
        statement = statement.where(ExecutionLog.operation == operation)
    return list(
        session.scalars(
            statement.order_by(ExecutionLog.created_at, ExecutionLog.id)
            .execution_options(populate_existing=True)
        ).all()
    )


def only_log(session: Session, scenario: Scenario, operation: str) -> ExecutionLog:
    rows = logs(session, scenario, operation)
    assert len(rows) == 1, rows
    return rows[0]


def route(client: TestClient, scenario: Scenario, settings: Settings, **body: Any) -> Any:
    return client.post(
        scenario.route_url,
        headers=bearer(scenario.requester, settings),
        json={"request": REQUEST_SENTINEL, **body},
    )


def row_text(session: Session, scenario: Scenario) -> str:
    return "\n".join(
        session.scalars(
            text("SELECT row_to_json(l)::text FROM execution_logs l WHERE workspace_id = :ws"),
            {"ws": scenario.workspace.id},
        ).all()
    )


# --- agent_route outcomes -----------------------------------------------------


def test_read_only_tool_execution_is_recorded(
    client: TestClient, db_session: Session, scenario: Scenario,
    selector: FakeToolSelector, settings: Settings,
) -> None:
    tool = add_tool(db_session, scenario, "get_employee_information")
    selector.selection = ToolSelectionProposal("get_employee_information", {"subject": "self"})

    response = route(client, scenario, settings)

    assert response.status_code == 200, response.text
    log = only_log(db_session, scenario, "agent_route")
    assert log.status.value == "succeeded"
    assert log.http_status == 200
    assert log.routing_intent == "tool_request"
    assert log.outcome.value == "tool_executed"
    assert (log.tool_id, log.tool_key) == (tool.id, "get_employee_information")
    assert log.agent_id == scenario.agent.id
    assert log.user_id == scenario.requester.id
    assert log.error_category is None
    assert log.approval_id is None and log.knowledge_base_id is None
    assert log.details == {}
    assert log.latency_ms >= 0
    # The Tool result carries the caller's name and email; neither is stored.
    stored = row_text(db_session, scenario)
    assert scenario.requester.name not in stored
    assert scenario.requester.email not in stored


def test_approval_creation_is_the_agent_route_approval_required_outcome(
    client: TestClient, db_session: Session, scenario: Scenario,
    selector: FakeToolSelector, settings: Settings,
) -> None:
    approval_id = request_approval(client, scenario, selector, settings)

    log = only_log(db_session, scenario, "agent_route")
    assert log.outcome.value == "tool_approval_required"
    assert str(log.approval_id) == approval_id
    assert (log.tool_id, log.tool_key) == (scenario.tool.id, "create_it_access_request")
    assert logs(db_session, scenario) == [log]
    stored = row_text(db_session, scenario)
    for secret in (
        ARGUMENTS["business_justification"], "production_database",
        REQUEST_SENTINEL, SYSTEM_PROMPT_SENTINEL,
    ):
        assert secret not in stored


def test_not_executed_and_unsupported_outcomes(
    client: TestClient, db_session: Session, scenario: Scenario,
    router_provider: FakeRoutingProvider, selector: FakeToolSelector, settings: Settings,
) -> None:
    selector.selection = ToolSelectionDecline(reason="missing_required_arguments")
    assert route(client, scenario, settings).status_code == 200
    router_provider.intent = RoutingIntent.UNSUPPORTED
    assert route(client, scenario, settings).status_code == 200

    rows = logs(db_session, scenario, "agent_route")
    assert len(rows) == 2
    by_outcome = {row.outcome.value: row for row in rows}
    declined = by_outcome["tool_not_executed"]
    assert declined.details == {"tool_not_executed_reason": "missing_required_arguments"}
    assert declined.tool_id is None and declined.tool_key is None
    unsupported = by_outcome["unsupported_request"]
    assert unsupported.routing_intent == "unsupported"
    assert unsupported.details == {}


@pytest.mark.parametrize(
    ("status", "outcome", "citations"),
    [(AnswerStatus.ANSWERED, "knowledge_answered", 1),
     (AnswerStatus.UNSUPPORTED, "knowledge_unsupported", 0)],
)
def test_knowledge_route_records_generation_metrics_only(
    client: TestClient, db_session: Session, scenario: Scenario,
    router_provider: FakeRoutingProvider, settings: Settings,
    monkeypatch: pytest.MonkeyPatch, status: AnswerStatus, outcome: str, citations: int,
) -> None:
    router_provider.intent = RoutingIntent.KNOWLEDGE_QA
    knowledge_base = add_knowledge_base(db_session, scenario)
    use_knowledge_fakes(monkeypatch, status)

    response = route(client, scenario, settings, knowledge_base_id=str(knowledge_base.id))

    assert response.status_code == 200, response.text
    log = only_log(db_session, scenario, "agent_route")
    assert log.routing_intent == "knowledge_qa"
    assert log.outcome.value == outcome
    assert log.knowledge_base_id == knowledge_base.id
    assert log.details == {
        "citation_count": citations, "generation_model": "gpt-5.6-terra",
        "prompt_version": "grounded-answer-v1", "input_tokens": 120,
        "output_tokens": 30, "total_tokens": 150,
    }
    stored = row_text(db_session, scenario)
    for secret in (ANSWER_SENTINEL, REQUEST_SENTINEL, "SENTINEL-file.md"):
        assert secret not in stored


# --- agent_route failures -----------------------------------------------------


def test_agent_failures_record_category_and_resolved_references_only(
    client: TestClient, db_session: Session, scenario: Scenario,
    router_provider: FakeRoutingProvider, selector: FakeToolSelector, settings: Settings,
) -> None:
    missing = client.post(
        f"/api/workspaces/{scenario.workspace.id}/agents/{uuid4()}/route",
        headers=bearer(scenario.requester, settings),
        json={"request": REQUEST_SENTINEL},
    )
    assert missing.status_code == 404
    set_status(db_session, scenario.agent, AgentStatus.DISABLED)
    assert route(client, scenario, settings).status_code == 409
    set_status(db_session, scenario.agent, AgentStatus.ACTIVE)
    router_provider.intent = RoutingIntent.KNOWLEDGE_QA
    assert route(client, scenario, settings).status_code == 422
    foreign_knowledge_base = add_knowledge_base(db_session, make_scenario(db_session))
    assert route(
        client, scenario, settings, knowledge_base_id=str(foreign_knowledge_base.id)
    ).status_code == 404
    disabled = add_knowledge_base(db_session, scenario, KnowledgeBaseStatus.DISABLED)
    assert route(
        client, scenario, settings, knowledge_base_id=str(disabled.id)
    ).status_code == 409
    active = add_knowledge_base(db_session, scenario)
    # No OpenAI key configured: the in-handler embedding provider is unavailable.
    assert route(client, scenario, settings, knowledge_base_id=str(active.id)).status_code == 503
    router_provider.intent = RoutingIntent.TOOL_REQUEST
    selector.selection = ToolSelectionProposal("get_reimbursement_status", {})
    assert route(client, scenario, settings).status_code == 409

    rows = logs(db_session, scenario, "agent_route")
    observed = sorted(
        (row.error_category.value, row.http_status, str(row.agent_id),
         str(row.knowledge_base_id), str(row.routing_intent), row.status.value, row.outcome)
        for row in rows
    )
    agent_id = str(scenario.agent.id)
    assert observed == sorted([
        ("agent_not_found", 404, "None", "None", "None", "failed", None),
        ("agent_inactive", 409, agent_id, "None", "None", "failed", None),
        ("knowledge_base_required", 422, agent_id, "None", "knowledge_qa", "failed", None),
        ("knowledge_base_not_found", 404, agent_id, "None", "knowledge_qa", "failed", None),
        ("knowledge_base_inactive", 409, agent_id, str(disabled.id), "knowledge_qa",
         "failed", None),
        ("provider_unavailable", 503, agent_id, str(active.id), "knowledge_qa", "failed", None),
        ("tool_unavailable", 409, agent_id, "None", "tool_request", "failed", None),
    ])


@pytest.mark.parametrize(
    ("error", "status", "category"),
    [(RoutingProviderError("provider said SENTINEL-provider-detail"), 502, "provider_error"),
     (RoutingInputTooLargeError("SENTINEL-provider-detail"), 422, "input_too_large")],
)
def test_routing_provider_failures_never_store_messages(
    client: TestClient, db_session: Session, scenario: Scenario,
    router_provider: FakeRoutingProvider, settings: Settings,
    error: Exception, status: int, category: str,
) -> None:
    def fail(request: str, system_prompt: str) -> object:
        del request, system_prompt
        raise error

    router_provider.route = fail  # type: ignore[method-assign]

    assert route(client, scenario, settings).status_code == status
    log = only_log(db_session, scenario, "agent_route")
    assert (log.error_category.value, log.http_status) == (category, status)
    assert log.routing_intent is None
    assert "SENTINEL-provider-detail" not in row_text(db_session, scenario)


def test_tool_adapter_failure_and_revoked_caller_are_recorded(
    client: TestClient, db_session: Session, scenario: Scenario,
    selector: FakeToolSelector, settings: Settings, monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = add_tool(db_session, scenario, "get_reimbursement_status")
    selector.selection = ToolSelectionProposal("get_reimbursement_status", {})

    def broken(context: object, arguments: object) -> object:
        raise RuntimeError("SENTINEL-adapter-internal")

    monkeypatch.setattr("app.services.tool_execution.get_reimbursement_status", broken)
    assert route(client, scenario, settings).status_code == 502

    def revoke(request: str, agent_scope: str, candidates: object) -> Any:
        del request, agent_scope, candidates
        scenario.requester_membership.status = MembershipStatus.DISABLED
        db_session.flush()
        return ToolSelectionProposal("get_reimbursement_status", {})

    selector.select = revoke  # type: ignore[method-assign]
    assert route(client, scenario, settings).status_code == 403

    categories = sorted(
        row.error_category.value for row in logs(db_session, scenario, "agent_route")
    )
    assert categories == ["access_denied", "tool_execution_failed"]
    failed = next(
        row for row in logs(db_session, scenario, "agent_route")
        if row.error_category.value == "tool_execution_failed"
    )
    assert (failed.tool_id, failed.tool_key) == (tool.id, tool.tool_key)
    assert "SENTINEL-adapter-internal" not in row_text(db_session, scenario)


def test_tool_result_validation_failure_keeps_only_resolved_tool_identity(
    client: TestClient, db_session: Session, scenario: Scenario,
    selector: FakeToolSelector, settings: Settings, monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = add_tool(db_session, scenario, "get_reimbursement_status")
    selector.selection = ToolSelectionProposal("get_reimbursement_status", {})
    monkeypatch.setattr(
        "app.services.tool_execution.get_reimbursement_status",
        lambda context, arguments: {"SENTINEL-result": "never store this"},
    )

    assert route(client, scenario, settings).status_code == 502
    row = only_log(db_session, scenario, "agent_route")
    assert (row.error_category.value, row.tool_id, row.tool_key) == (
        "tool_execution_failed", tool.id, tool.tool_key,
    )
    assert "SENTINEL-result" not in row_text(db_session, scenario)


# --- knowledge_answer ---------------------------------------------------------


def answer_url(scenario: Scenario, knowledge_base_id: UUID) -> str:
    return f"/api/workspaces/{scenario.workspace.id}/knowledge-bases/{knowledge_base_id}/answer"


def test_knowledge_answer_route_is_recorded(
    client: TestClient, db_session: Session, scenario: Scenario,
    settings: Settings, monkeypatch: pytest.MonkeyPatch,
) -> None:
    knowledge_base = add_knowledge_base(db_session, scenario)
    use_knowledge_fakes(monkeypatch, AnswerStatus.ANSWERED)

    response = client.post(
        answer_url(scenario, knowledge_base.id),
        headers=bearer(scenario.requester, settings),
        json={"question": REQUEST_SENTINEL},
    )

    assert response.status_code == 200, response.text
    log = only_log(db_session, scenario, "knowledge_answer")
    assert log.outcome.value == "knowledge_answered"
    assert log.knowledge_base_id == knowledge_base.id
    assert log.agent_id is None and log.routing_intent is None
    assert log.details["citation_count"] == 1
    assert ANSWER_SENTINEL not in row_text(db_session, scenario)


def test_knowledge_answer_failures_resolve_only_owned_knowledge_bases(
    client: TestClient, db_session: Session, scenario: Scenario, settings: Settings,
) -> None:
    app.dependency_overrides[get_embedding_provider] = UnusedEmbeddingProvider
    foreign = add_knowledge_base(db_session, make_scenario(db_session))
    disabled = add_knowledge_base(db_session, scenario, KnowledgeBaseStatus.DISABLED)
    headers = bearer(scenario.requester, settings)

    assert client.post(
        answer_url(scenario, foreign.id), headers=headers, json={"question": "q"}
    ).status_code == 404
    assert client.post(
        answer_url(scenario, disabled.id), headers=headers, json={"question": "q"}
    ).status_code == 409

    observed = sorted(
        (row.error_category.value, str(row.knowledge_base_id))
        for row in logs(db_session, scenario, "knowledge_answer")
    )
    assert observed == [
        ("knowledge_base_inactive", str(disabled.id)), ("knowledge_base_not_found", "None"),
    ]


# --- Recording boundary (spec Section 6.1) -----------------------------------


def test_pre_handler_rejections_write_no_record(
    client: TestClient, db_session: Session, scenario: Scenario, settings: Settings,
) -> None:
    knowledge_base = add_knowledge_base(db_session, scenario)
    outsider = make_user(db_session, "Outsider")
    member_headers = bearer(scenario.requester, settings)

    assert client.post(scenario.route_url, json={"request": "x"}).status_code == 401
    assert client.post(
        scenario.route_url, headers=bearer(outsider, settings), json={"request": "x"}
    ).status_code == 403
    assert client.post(scenario.route_url, headers=member_headers, json={}).status_code == 422
    assert client.post(
        f"{scenario.approval_url(uuid4())}/decision",
        headers=member_headers, json={"decision": "maybe"},
    ).status_code == 422
    # Embedding configuration is resolved by a dependency on this route.
    response = client.post(
        answer_url(scenario, knowledge_base.id), headers=member_headers,
        json={"question": "q"},
    )
    assert response.status_code == 503
    assert response.json() == {"detail": "Embedding provider is not configured"}
    set_status(db_session, scenario.workspace, WorkspaceStatus.DISABLED)
    assert client.post(
        scenario.route_url, headers=member_headers, json={"request": "x"}
    ).status_code == 403

    assert logs(db_session, scenario) == []


# --- Approval decision and cancel --------------------------------------------


def test_approval_decisions_record_committed_state(
    client: TestClient, db_session: Session, scenario: Scenario,
    selector: FakeToolSelector, settings: Settings,
) -> None:
    approved = request_approval(client, scenario, selector, settings)
    assert decide(client, scenario, approved, settings, note=NOTE_SENTINEL).status_code == 200
    assert decide(client, scenario, approved, settings).status_code == 200  # replay
    assert decide(client, scenario, approved, settings, "reject").status_code == 409
    rejected = request_approval(
        client, scenario, selector, settings,
        arguments={**ARGUMENTS, "duration_days": 7},
    )
    assert decide(client, scenario, rejected, settings, "reject").status_code == 200

    rows = logs(db_session, scenario, "approval_decision")
    observed = sorted(
        (str(row.approval_id), row.status.value, row.http_status,
         row.outcome.value if row.outcome else "None",
         row.error_category.value if row.error_category else "None",
         row.details["decision"])
        for row in rows
    )
    assert observed == sorted([
        (approved, "succeeded", 200, "approved_execution_succeeded", "None", "approve"),
        (approved, "succeeded", 200, "approved_execution_succeeded", "None", "approve"),
        (approved, "failed", 409, "approved_execution_succeeded", "approval_not_pending", "reject"),
        (rejected, "succeeded", 200, "rejected", "None", "reject"),
    ])
    for row in rows:
        assert (row.agent_id, row.tool_id, row.tool_key) == (
            scenario.agent.id, scenario.tool.id, "create_it_access_request"
        )
        assert row.user_id == scenario.reviewer.id
    assert NOTE_SENTINEL not in row_text(db_session, scenario)


def test_approval_failures_that_change_state_record_the_outcome(
    client: TestClient, db_session: Session, scenario: Scenario,
    selector: FakeToolSelector, settings: Settings, monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalidated = request_approval(client, scenario, selector, settings)
    set_status(db_session, scenario.tool, ToolStatus.DISABLED)
    assert decide(client, scenario, invalidated, settings).status_code == 409
    set_status(db_session, scenario.tool, ToolStatus.ACTIVE)

    expired = request_approval(
        client, scenario, selector, settings, arguments={**ARGUMENTS, "duration_days": 3}
    )
    db_session.execute(
        text(
            "UPDATE approvals SET created_at = now() - interval '80 hours', "
            "expires_at = now() - interval '8 hours' WHERE id = :id"
        ),
        {"id": expired},
    )
    db_session.flush()
    assert decide(client, scenario, expired, settings).status_code == 409

    failed = request_approval(
        client, scenario, selector, settings, arguments={**ARGUMENTS, "duration_days": 5}
    )

    def failing_executor(session: Session, context: Any, arguments: Any) -> Any:
        raise RuntimeError("SENTINEL-executor-detail")

    monkeypatch.setattr(
        "app.services.approvals.WRITE_EXECUTORS",
        {"mock_it_access_request.v1": failing_executor},
    )
    assert decide(client, scenario, failed, settings).status_code == 502

    observed = {
        str(row.approval_id): (row.outcome.value, row.error_category.value, row.http_status)
        for row in logs(db_session, scenario, "approval_decision")
    }
    assert observed == {
        invalidated: ("invalidated", "approval_invalidated", 409),
        expired: ("expired", "approval_expired", 409),
        failed: ("approved_execution_failed", "approval_execution_failed", 502),
    }
    assert "SENTINEL-executor-detail" not in row_text(db_session, scenario)


@pytest.mark.parametrize(
    ("operation", "decision", "expected_outcome"),
    [
        ("approval_decision", "reject", "rejected"),
        ("approval_decision", "approve", "approved_execution_succeeded"),
        ("approval_cancel", None, "cancelled"),
    ],
)
def test_projection_failure_after_committed_approval_state_keeps_outcome(
    client: TestClient, db_session: Session, scenario: Scenario,
    selector: FakeToolSelector, settings: Settings, monkeypatch: pytest.MonkeyPatch,
    operation: str, decision: str | None, expected_outcome: str,
) -> None:
    approval_id = request_approval(client, scenario, selector, settings)

    def broken_projection(*_: object, **__: object) -> object:
        raise approval_service.ApprovalConfigurationError(
            approval_service.APPROVAL_CONFIGURATION_UNAVAILABLE
        )

    monkeypatch.setattr(approval_service, "get_approval_response", broken_projection)
    if operation == "approval_decision":
        response = decide(client, scenario, approval_id, settings, decision or "reject")
    else:
        response = client.post(
            f"{scenario.approval_url(approval_id)}/cancel",
            headers=bearer(scenario.requester, settings),
        )

    assert response.status_code == 503
    row = only_log(db_session, scenario, operation)
    assert (row.status.value, row.error_category.value, row.outcome.value) == (
        "failed", "tool_configuration_error", expected_outcome,
    )


def test_approval_visibility_failures_and_cancel(
    client: TestClient, db_session: Session, scenario: Scenario,
    selector: FakeToolSelector, settings: Settings,
) -> None:
    approval_id = request_approval(client, scenario, selector, settings)
    assert decide(client, scenario, str(uuid4()), settings).status_code == 404
    # The requester can see but not decide their own Approval.
    assert decide(
        client, scenario, approval_id, settings, user=scenario.requester
    ).status_code == 403
    cancel_url = f"{scenario.approval_url(approval_id)}/cancel"
    requester_headers = bearer(scenario.requester, settings)
    assert client.post(cancel_url, headers=requester_headers).status_code == 200
    assert client.post(cancel_url, headers=requester_headers).status_code == 200  # replay

    decisions = sorted(
        (row.error_category.value, str(row.approval_id))
        for row in logs(db_session, scenario, "approval_decision")
    )
    assert decisions == [("access_denied", approval_id), ("approval_not_found", "None")]
    cancels = logs(db_session, scenario, "approval_cancel")
    assert [(row.outcome.value, row.status.value, str(row.approval_id)) for row in cancels] == [
        ("cancelled", "succeeded", approval_id), ("cancelled", "succeeded", approval_id),
    ]
    assert all(row.details == {} for row in cancels)


# --- Write semantics ------------------------------------------------------------


def test_log_write_failure_never_changes_the_response_or_business_state(
    client: TestClient, db_session: Session, scenario: Scenario,
    selector: FakeToolSelector, settings: Settings, monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def broken_build(*args: object, **kwargs: object) -> ExecutionLog:
        raise RuntimeError("SENTINEL-log-failure")

    monkeypatch.setattr(execution_logs, "_build_row", broken_build)
    # Alembic's fileConfig in the migration fixture disables pre-existing loggers.
    monkeypatch.setattr(execution_logs.logger, "disabled", False)
    approval_id = request_approval(client, scenario, selector, settings)
    response = decide(client, scenario, approval_id, settings)

    assert response.status_code == 200
    assert response.json()["decision_status"] == "approved"
    approval = db_session.get(Approval, UUID(approval_id), populate_existing=True)
    assert approval is not None
    assert approval.decision_status.value == "approved"
    assert logs(db_session, scenario) == []
    messages = [record.getMessage() for record in caplog.records]
    assert any(message.startswith("execution_log_write_failed") for message in messages)
    assert not any("SENTINEL-log-failure" in message for message in messages)


def test_invalid_details_drop_only_the_record(
    client: TestClient, db_session: Session, scenario: Scenario,
    router_provider: FakeRoutingProvider, settings: Settings, monkeypatch: pytest.MonkeyPatch,
) -> None:
    router_provider.intent = RoutingIntent.KNOWLEDGE_QA
    knowledge_base = add_knowledge_base(db_session, scenario)
    use_knowledge_fakes(monkeypatch, AnswerStatus.ANSWERED)
    monkeypatch.setattr(KnowledgeGenerationProvider, "model", "model with spaces")

    response = route(client, scenario, settings, knowledge_base_id=str(knowledge_base.id))

    assert response.status_code == 200
    assert response.json()["outcome"]["generation"]["model"] == "model with spaces"
    assert logs(db_session, scenario) == []


def test_recorder_discards_uncommitted_handler_writes_but_not_prior_state(
    client: TestClient, db_session: Session, scenario: Scenario,
    selector: FakeToolSelector, settings: Settings,
) -> None:
    original_name = scenario.agent.name

    def write_without_commit(request: str, agent_scope: str, candidates: object) -> Any:
        del request, agent_scope, candidates
        db_session.execute(
            text("UPDATE agents SET name = 'uncommitted rename' WHERE id = :id"),
            {"id": scenario.agent.id},
        )
        return ToolSelectionDecline(reason="no_matching_capability")

    selector.select = write_without_commit  # type: ignore[method-assign]
    assert route(client, scenario, settings).status_code == 200

    agent = db_session.get(Agent, scenario.agent.id, populate_existing=True)
    assert agent is not None and agent.name == original_name
    assert only_log(db_session, scenario, "agent_route").outcome.value == "tool_not_executed"


def test_latency_reflects_handler_duration(
    client: TestClient, db_session: Session, scenario: Scenario,
    router_provider: FakeRoutingProvider, settings: Settings,
) -> None:
    def slow(request: str, system_prompt: str) -> RoutingIntent:
        del request, system_prompt
        time.sleep(0.06)
        return RoutingIntent.UNSUPPORTED

    router_provider.route = slow  # type: ignore[method-assign]
    assert route(client, scenario, settings).status_code == 200
    assert only_log(db_session, scenario, "agent_route").latency_ms >= 60


# --- Read API -------------------------------------------------------------------


def logs_url(scenario: Scenario) -> str:
    return f"/api/workspaces/{scenario.workspace.id}/execution-logs"


def seed_log(session: Session, scenario: Scenario, created_at: datetime, **values: Any) -> UUID:
    row = ExecutionLog(
        workspace_id=scenario.workspace.id,
        user_id=values.pop("user_id", scenario.requester.id),
        operation=values.pop("operation", "agent_route"),
        status=values.pop("status", "succeeded"),
        http_status=values.pop("http_status", 200),
        latency_ms=values.pop("latency_ms", 5),
        details=values.pop("details", {}),
        created_at=created_at,
        **values,
    )
    session.add(row)
    session.flush()
    return row.id


@pytest.mark.parametrize(
    ("role", "allowed"),
    [(MembershipRole.SYSTEM_ADMIN, True), (MembershipRole.AGENT_ADMIN, True),
     (MembershipRole.KNOWLEDGE_ADMIN, False), (MembershipRole.EMPLOYEE, False)],
)
def test_read_authorization_matrix(
    client: TestClient, db_session: Session, scenario: Scenario, settings: Settings,
    role: MembershipRole, allowed: bool,
) -> None:
    log_id = seed_log(db_session, scenario, datetime.now(UTC))
    caller = make_user(db_session, "Reader")
    make_membership(db_session, caller, scenario.workspace, role)
    headers = bearer(caller, settings)

    listed = client.get(logs_url(scenario), headers=headers)
    read = client.get(f"{logs_url(scenario)}/{log_id}", headers=headers)

    if allowed:
        assert listed.status_code == 200 and read.status_code == 200
        assert [item["id"] for item in listed.json()["items"]] == [str(log_id)]
    else:
        assert listed.status_code == 403 and read.status_code == 403
        assert listed.json() == {"detail": "Agent administrator role required"}


def test_read_is_workspace_isolated(
    client: TestClient, db_session: Session, scenario: Scenario, settings: Settings,
) -> None:
    foreign = make_scenario(db_session)
    foreign_log = seed_log(db_session, foreign, datetime.now(UTC))
    own_log = seed_log(db_session, scenario, datetime.now(UTC))
    headers = bearer(scenario.reviewer, settings)

    listed = client.get(logs_url(scenario), headers=headers).json()["items"]
    assert [item["id"] for item in listed] == [str(own_log)]
    for log_id in (foreign_log, uuid4()):
        response = client.get(f"{logs_url(scenario)}/{log_id}", headers=headers)
        assert response.status_code == 404
        assert response.json() == {"detail": "Execution log not found"}
    foreign_filter = client.get(
        logs_url(scenario), headers=headers, params={"user_id": str(foreign.requester.id)}
    )
    assert foreign_filter.json()["items"] == []
    # The foreign Workspace's reviewer is not a member here.
    assert client.get(
        logs_url(scenario), headers=bearer(foreign.reviewer, settings)
    ).status_code == 403


def test_read_response_shape_filters_ordering_and_pagination(
    client: TestClient, db_session: Session, scenario: Scenario, settings: Settings,
) -> None:
    base = datetime(2026, 9, 29, 8, 0, tzinfo=UTC)
    knowledge_base = add_knowledge_base(db_session, scenario)
    first = seed_log(
        db_session, scenario, base, operation="knowledge_answer",
        outcome="knowledge_answered", knowledge_base_id=knowledge_base.id,
        details={"citation_count": 2, "generation_model": "gpt-5.6-terra"},
    )
    second = seed_log(
        db_session, scenario, base + timedelta(minutes=1), routing_intent="tool_request",
        outcome="tool_approval_required", agent_id=scenario.agent.id,
        tool_id=scenario.tool.id, tool_key="create_it_access_request",
    )
    third = seed_log(
        db_session, scenario, base + timedelta(minutes=2), status="failed",
        error_category="provider_error", http_status=502, agent_id=scenario.agent.id,
        user_id=scenario.reviewer.id,
    )
    headers = bearer(scenario.reviewer, settings)

    def ids(**params: Any) -> list[str]:
        response = client.get(logs_url(scenario), headers=headers, params=params)
        assert response.status_code == 200, response.text
        return [item["id"] for item in response.json()["items"]]

    assert ids() == [str(third), str(second), str(first)]
    assert ids(limit=1, offset=1) == [str(second)]
    assert ids(status="failed") == [str(third)]
    assert ids(operation="knowledge_answer") == [str(first)]
    assert ids(agent_id=str(scenario.agent.id)) == [str(third), str(second)]
    assert ids(user_id=str(scenario.reviewer.id)) == [str(third)]
    assert ids(tool_key="create_it_access_request") == [str(second)]
    assert ids(
        created_after=(base + timedelta(minutes=1)).isoformat(),
        created_before=(base + timedelta(minutes=2)).isoformat(),
    ) == [str(second)]

    detail = client.get(f"{logs_url(scenario)}/{second}", headers=headers).json()
    assert detail == {
        "id": str(second),
        "workspace_id": str(scenario.workspace.id),
        "operation": "agent_route",
        "routing_intent": "tool_request",
        "status": "succeeded",
        "outcome": "tool_approval_required",
        "error_category": None,
        "http_status": 200,
        "latency_ms": 5,
        "user": {"id": str(scenario.requester.id), "name": scenario.requester.name},
        "agent": {"id": str(scenario.agent.id), "name": scenario.agent.name},
        "tool": {"tool_key": "create_it_access_request", "name": scenario.tool.name},
        "approval_id": None,
        "knowledge_base": None,
        "details": {},
        "created_at": detail["created_at"],
    }
    first_detail = client.get(f"{logs_url(scenario)}/{first}", headers=headers).json()
    assert first_detail["knowledge_base"] == {
        "id": str(knowledge_base.id), "name": knowledge_base.name,
    }
    assert first_detail["details"] == {"citation_count": 2, "generation_model": "gpt-5.6-terra"}


@pytest.mark.parametrize(
    "params",
    [{"status": "success"}, {"operation": "approval_create"}, {"limit": 0},
     {"limit": 101}, {"offset": -1}, {"created_after": "2026-09-29T08:00:00"},
     {"tool_key": "drop_tables"}],
)
def test_invalid_list_parameters_are_422(
    client: TestClient, scenario: Scenario, settings: Settings, params: dict[str, Any],
) -> None:
    response = client.get(
        logs_url(scenario), headers=bearer(scenario.reviewer, settings), params=params
    )
    assert response.status_code == 422


def test_execution_logs_have_no_write_methods(
    client: TestClient, db_session: Session, scenario: Scenario, settings: Settings,
) -> None:
    log_id = seed_log(db_session, scenario, datetime.now(UTC))
    headers = bearer(scenario.reviewer, settings)
    assert client.post(logs_url(scenario), headers=headers, json={}).status_code == 405
    for method in ("put", "patch", "delete"):
        response = client.request(method, f"{logs_url(scenario)}/{log_id}", headers=headers)
        assert response.status_code == 405
