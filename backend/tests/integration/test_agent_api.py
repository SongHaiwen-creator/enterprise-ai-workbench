from collections.abc import Generator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.dependencies.generation import get_generation_provider
from app.api.dependencies.routing import get_routing_provider
from app.api.dependencies.tool_selection import get_tool_selector
from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.main import app
from app.models import Agent, AgentTool, KnowledgeBase, Membership, Tool, User, Workspace
from app.models.enums import (
    AgentStatus,
    KnowledgeBaseStatus,
    MembershipRole,
    MembershipStatus,
    ToolRisk,
    ToolStatus,
    UserStatus,
    WorkspaceStatus,
)
from app.schemas.agent_routing import RoutingIntent
from app.schemas.answer import AnswerStatus
from app.security.tokens import create_access_token
from app.services.answers import AnswerCitation, AnswerResult
from app.services.generation import GenerationUsage
from app.services.routing import (
    RoutingConfigurationError,
    RoutingInputTooLargeError,
    RoutingProviderError,
)
from app.services.tool_registry import ToolDefinition
from app.services.tool_selection import (
    ToolSelection,
    ToolSelectionDecline,
    ToolSelectionProposal,
)

pytestmark = pytest.mark.integration
JWT_SECRET = "agent-api-secret-longer-than-thirty-two-bytes"
SUMMARY_KEYS = {
    "id", "workspace_id", "name", "description", "status", "created_by",
    "created_at", "updated_at",
}


class FakeRoutingProvider:
    def __init__(self) -> None:
        self.intent: object = RoutingIntent.TOOL_REQUEST
        self.error: Exception | None = None
        self.calls: list[tuple[str, str]] = []

    def route(self, request: str, system_prompt: str) -> object:
        self.calls.append((request, system_prompt))
        if self.error is not None:
            raise self.error
        return self.intent


class FakeGenerationProvider:
    model = "gpt-5.6-terra"
    reasoning_effort = "low"
    retrieval_limit = 5
    prompt_version = "grounded-answer-v1"
    max_input_tokens = 12000
    max_output_tokens = 1200

    def generate(self, question: str, evidence: object) -> None:
        del question, evidence
        raise AssertionError("generation must be mocked at the answer service boundary")


class FakeToolSelector:
    def __init__(self) -> None:
        self.selection: ToolSelection = ToolSelectionDecline(
            reason="no_matching_capability"
        )
        self.calls: list[tuple[str, str, tuple[ToolDefinition, ...]]] = []

    def select(
        self,
        request: str,
        agent_scope: str,
        candidates: tuple[ToolDefinition, ...],
    ) -> ToolSelection:
        self.calls.append((request, agent_scope, candidates))
        return self.selection


@pytest.fixture
def auth_settings(database_urls: tuple[object, object]) -> Settings:
    database_url, test_database_url = database_urls
    return Settings(
        database_url=str(database_url),
        test_database_url=str(test_database_url),
        jwt_secret_key=JWT_SECRET,
        openai_api_key=None,
        _env_file=None,
    )


@pytest.fixture
def router_provider() -> FakeRoutingProvider:
    return FakeRoutingProvider()


@pytest.fixture
def tool_selector() -> FakeToolSelector:
    return FakeToolSelector()


@pytest.fixture
def client(
    db_session: Session,
    auth_settings: Settings,
    router_provider: FakeRoutingProvider,
    tool_selector: FakeToolSelector,
) -> Generator[TestClient, None, None]:
    def override_db_session() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[get_settings] = lambda: auth_settings
    app.dependency_overrides[get_routing_provider] = lambda: router_provider
    app.dependency_overrides[get_tool_selector] = lambda: tool_selector
    app.dependency_overrides[get_generation_provider] = FakeGenerationProvider
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_settings, None)
        app.dependency_overrides.pop(get_routing_provider, None)
        app.dependency_overrides.pop(get_tool_selector, None)
        app.dependency_overrides.pop(get_generation_provider, None)


def user(session: Session, *, status: UserStatus = UserStatus.ACTIVE) -> User:
    identifier = uuid4().hex
    result = User(email=f"agent-{identifier}@company.com", name="Agent User", status=status)
    session.add(result)
    session.flush()
    return result


def workspace(
    session: Session, *, status: WorkspaceStatus = WorkspaceStatus.ACTIVE
) -> Workspace:
    identifier = uuid4().hex
    result = Workspace(name="Agent Workspace", slug=f"agent-{identifier}", status=status)
    session.add(result)
    session.flush()
    return result


def membership(
    session: Session,
    caller: User,
    scope: Workspace,
    *,
    role: MembershipRole = MembershipRole.EMPLOYEE,
    status: MembershipStatus = MembershipStatus.ACTIVE,
) -> Membership:
    result = Membership(
        user_id=caller.id,
        workspace_id=scope.id,
        role=role,
        status=status,
        joined_at=datetime.now(UTC) if status is MembershipStatus.ACTIVE else None,
    )
    session.add(result)
    session.flush()
    return result


def agent(
    session: Session,
    scope: Workspace,
    creator: User,
    *,
    status: AgentStatus = AgentStatus.ACTIVE,
    name: str = "Employee Assistant",
) -> Agent:
    result = Agent(
        workspace_id=scope.id,
        created_by=creator.id,
        name=name,
        description="Employee routing",
        system_prompt="Route approved employee requests.",
        status=status,
    )
    session.add(result)
    session.flush()
    return result


def knowledge_base(
    session: Session,
    scope: Workspace,
    creator: User,
    *,
    status: KnowledgeBaseStatus = KnowledgeBaseStatus.ACTIVE,
) -> KnowledgeBase:
    result = KnowledgeBase(
        workspace_id=scope.id,
        created_by=creator.id,
        name="Employee Policies",
        status=status,
    )
    session.add(result)
    session.flush()
    return result


def tool(
    session: Session,
    scope: Workspace,
    creator: User,
    *,
    tool_key: str = "get_reimbursement_status",
    status: ToolStatus = ToolStatus.ACTIVE,
) -> Tool:
    risks = {
        "get_reimbursement_status": "low",
        "get_employee_information": "low",
        "create_it_access_request": "high",
    }
    result = Tool(
        workspace_id=scope.id,
        created_by=creator.id,
        tool_key=tool_key,
        name=tool_key.replace("_", " ").title(),
        description=f"Administrative description for {tool_key}.",
        risk_level=ToolRisk(risks[tool_key]),
        status=status,
    )
    session.add(result)
    session.flush()
    return result


def assign(session: Session, scope: Workspace, selected: Agent, configured: Tool) -> None:
    session.add(
        AgentTool(
            workspace_id=scope.id,
            agent_id=selected.id,
            tool_id=configured.id,
        )
    )
    session.flush()


def bearer(caller: User, settings: Settings) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(caller.id, settings)}"}


def collection(scope: Workspace) -> str:
    return f"/api/workspaces/{scope.id}/agents"


def route(scope: Workspace, selected: Agent | UUID) -> str:
    agent_id = selected.id if isinstance(selected, Agent) else selected
    return f"{collection(scope)}/{agent_id}/route"


@pytest.mark.parametrize(
    ("method", "suffix", "body"),
    [
        ("get", "", None),
        ("post", "", {"name": "A", "system_prompt": "Scope"}),
        ("get", f"/{uuid4()}", None),
        ("patch", f"/{uuid4()}", {"status": "active"}),
        ("post", f"/{uuid4()}/route", {"request": "Question"}),
    ],
)
def test_every_agent_endpoint_requires_authentication(
    client: TestClient, method: str, suffix: str, body: dict[str, str] | None
) -> None:
    response = client.request(
        method, f"/api/workspaces/{uuid4()}/agents{suffix}", json=body
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}


@pytest.mark.parametrize("role", list(MembershipRole))
def test_active_roles_list_summaries_and_route_without_knowledge_base(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    router_provider: FakeRoutingProvider,
    role: MembershipRole,
) -> None:
    caller = user(db_session)
    scope = workspace(db_session)
    membership(db_session, caller, scope, role=role)
    selected = agent(db_session, scope, caller)

    listed = client.get(collection(scope), headers=bearer(caller, auth_settings))
    routed = client.post(
        route(scope, selected),
        headers=bearer(caller, auth_settings),
        json={"request": " Check my reimbursement status "},
    )

    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert set(listed.json()[0]) == SUMMARY_KEYS
    assert listed.json()[0]["id"] == str(selected.id)
    assert routed.status_code == 200
    assert routed.json() == {
        "request": "Check my reimbursement status",
        "intent": "tool_request",
        "outcome": {
            "status": "not_executed",
            "tool": None,
            "executed": False,
            "approval_required": False,
            "reason": "no_available_tool",
            "validated_arguments": None,
            "result": None,
            "message": "No permitted enterprise capability can safely handle this request.",
        },
    }
    assert router_provider.calls == [
        ("Check my reimbursement status", selected.system_prompt)
    ]


@pytest.mark.parametrize("role", [MembershipRole.AGENT_ADMIN, MembershipRole.SYSTEM_ADMIN])
def test_agent_administrators_manage_configuration(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    role: MembershipRole,
) -> None:
    caller = user(db_session)
    scope = workspace(db_session)
    membership(db_session, caller, scope, role=role)
    path = collection(scope)
    headers = bearer(caller, auth_settings)

    created = client.post(
        path,
        headers=headers,
        json={
            "name": " Employee Assistant ",
            "description": " Employee scope ",
            "system_prompt": " Route employee topics. ",
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["name"] == "Employee Assistant"
    assert body["description"] == "Employee scope"
    assert body["system_prompt"] == "Route employee topics."
    assert body["status"] == "draft"
    assert body["workspace_id"] == str(scope.id)
    assert body["created_by"] == str(caller.id)
    assert body["created_at"] and body["updated_at"]
    assert db_session.get(Agent, UUID(body["id"])) is not None
    assert client.get(path, headers=headers).json() == []
    all_summaries = client.get(f"{path}?include_inactive=true", headers=headers)
    assert all_summaries.status_code == 200
    assert set(all_summaries.json()[0]) == SUMMARY_KEYS

    item_path = f"{path}/{body['id']}"
    read = client.get(item_path, headers=headers)
    assert read.status_code == 200
    assert read.json()["system_prompt"] == "Route employee topics."
    activated = client.patch(item_path, headers=headers, json={"status": "active"})
    assert activated.status_code == 200
    assert activated.json()["status"] == "active"
    disabled = client.patch(
        item_path,
        headers=headers,
        json={"status": "disabled", "description": None},
    )
    assert disabled.status_code == 200
    assert disabled.json()["description"] is None
    assert client.get(path, headers=headers).json() == []
    enabled = client.patch(item_path, headers=headers, json={"status": "active"})
    assert enabled.status_code == 200
    assert [item["id"] for item in client.get(path, headers=headers).json()] == [body["id"]]


@pytest.mark.parametrize("role", [MembershipRole.EMPLOYEE, MembershipRole.KNOWLEDGE_ADMIN])
def test_non_agent_admin_cannot_manage_agents(
    client: TestClient, db_session: Session, auth_settings: Settings, role: MembershipRole
) -> None:
    caller = user(db_session)
    scope = workspace(db_session)
    membership(db_session, caller, scope, role=role)
    selected = agent(db_session, scope, caller)
    headers = bearer(caller, auth_settings)
    path = collection(scope)

    for method, target, body in [
        ("post", path, {"name": "New", "system_prompt": "Scope"}),
        ("get", f"{path}/{selected.id}", None),
        ("patch", f"{path}/{selected.id}", {"status": "disabled"}),
        ("get", f"{path}?include_inactive=true", None),
    ]:
        response = client.request(method, target, headers=headers, json=body)
        assert response.status_code == 403
        assert response.json() == {"detail": "Agent administrator role required"}


def test_agent_admin_does_not_gain_adjacent_administration(
    client: TestClient, db_session: Session, auth_settings: Settings
) -> None:
    caller = user(db_session)
    scope = workspace(db_session)
    membership(db_session, caller, scope, role=MembershipRole.AGENT_ADMIN)
    headers = bearer(caller, auth_settings)
    kb_response = client.post(
        f"/api/workspaces/{scope.id}/knowledge-bases",
        headers=headers,
        json={"name": "Unauthorized"},
    )
    member_response = client.post(
        f"/api/workspaces/{scope.id}/members",
        headers=headers,
        json={"user_id": str(uuid4()), "role": "employee"},
    )
    assert kb_response.status_code == 403
    assert member_response.status_code == 403


def test_role_is_resolved_per_workspace(
    client: TestClient, db_session: Session, auth_settings: Settings
) -> None:
    caller = user(db_session)
    admin_scope = workspace(db_session)
    employee_scope = workspace(db_session)
    membership(db_session, caller, admin_scope, role=MembershipRole.AGENT_ADMIN)
    membership(db_session, caller, employee_scope, role=MembershipRole.EMPLOYEE)
    admin_agent = agent(db_session, admin_scope, caller)
    employee_agent = agent(db_session, employee_scope, caller)
    headers = bearer(caller, auth_settings)

    assert client.get(
        f"{collection(admin_scope)}/{admin_agent.id}", headers=headers
    ).status_code == 200
    assert client.get(
        f"{collection(employee_scope)}/{employee_agent.id}", headers=headers
    ).status_code == 403
    assert client.post(
        route(employee_scope, employee_agent),
        headers=headers,
        json={"request": "My request status"},
    ).status_code == 200


@pytest.mark.parametrize("status", [AgentStatus.DRAFT, AgentStatus.DISABLED])
def test_inactive_agent_is_rejected_before_routing(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    router_provider: FakeRoutingProvider,
    status: AgentStatus,
) -> None:
    caller = user(db_session)
    scope = workspace(db_session)
    membership(db_session, caller, scope)
    selected = agent(db_session, scope, caller, status=status)
    result = client.post(
        route(scope, selected), headers=bearer(caller, auth_settings),
        json={"request": "Question"},
    )
    assert result.status_code == 409
    assert router_provider.calls == []


@pytest.mark.parametrize(
    "membership_status", [None, MembershipStatus.INVITED, MembershipStatus.DISABLED]
)
def test_missing_or_inactive_membership_cannot_route(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    router_provider: FakeRoutingProvider,
    membership_status: MembershipStatus | None,
) -> None:
    caller = user(db_session)
    scope = workspace(db_session)
    if membership_status is not None:
        membership(db_session, caller, scope, status=membership_status)
    selected = agent(db_session, scope, caller)
    result = client.post(
        route(scope, selected), headers=bearer(caller, auth_settings),
        json={"request": "Question"},
    )
    assert result.status_code == 403
    assert router_provider.calls == []


def test_disabled_user_or_workspace_cannot_route(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    router_provider: FakeRoutingProvider,
) -> None:
    disabled_caller = user(db_session, status=UserStatus.DISABLED)
    disabled_scope = workspace(db_session, status=WorkspaceStatus.DISABLED)
    active_caller = user(db_session)
    active_scope = workspace(db_session)
    membership(db_session, disabled_caller, active_scope)
    membership(db_session, active_caller, disabled_scope)
    first_agent = agent(db_session, active_scope, active_caller)
    second_agent = agent(db_session, disabled_scope, active_caller)
    first = client.post(
        route(active_scope, first_agent),
        headers=bearer(disabled_caller, auth_settings), json={"request": "Question"},
    )
    second = client.post(
        route(disabled_scope, second_agent),
        headers=bearer(active_caller, auth_settings), json={"request": "Question"},
    )
    assert first.status_code == 403
    assert second.status_code == 403
    assert router_provider.calls == []


def test_missing_and_foreign_agents_have_identical_scoped_404(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    router_provider: FakeRoutingProvider,
) -> None:
    caller = user(db_session)
    scope = workspace(db_session)
    foreign_scope = workspace(db_session)
    membership(db_session, caller, scope)
    foreign_agent = agent(db_session, foreign_scope, caller)
    headers = bearer(caller, auth_settings)
    missing = client.post(route(scope, uuid4()), headers=headers, json={"request": "Question"})
    foreign = client.post(
        route(scope, foreign_agent), headers=headers, json={"request": "Question"}
    )
    assert missing.status_code == foreign.status_code == 404
    assert missing.json() == foreign.json() == {"detail": "Agent not found"}
    assert router_provider.calls == []


@pytest.mark.parametrize(
    "body",
    [
        {"request": " "},
        {"request": "x" * 2001},
        {"request": "Question", "knowledge_base_id": "not-a-uuid"},
        {"request": "Question", "unknown": "value"},
    ],
)
def test_invalid_route_shape_cannot_call_provider(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    router_provider: FakeRoutingProvider,
    body: dict[str, object],
) -> None:
    caller = user(db_session)
    scope = workspace(db_session)
    membership(db_session, caller, scope)
    selected = agent(db_session, scope, caller)
    response = client.post(route(scope, selected), headers=bearer(caller, auth_settings), json=body)
    assert response.status_code == 422
    assert router_provider.calls == []


@pytest.mark.parametrize(
    "body", [{"request": "Question"}, {"request": "Question", "knowledge_base_id": None}]
)
def test_knowledge_context_required_after_routing(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    router_provider: FakeRoutingProvider,
    monkeypatch: pytest.MonkeyPatch,
    body: dict[str, object],
) -> None:
    caller = user(db_session)
    scope = workspace(db_session)
    membership(db_session, caller, scope)
    selected = agent(db_session, scope, caller)
    router_provider.intent = RoutingIntent.KNOWLEDGE_QA
    monkeypatch.setattr(
        "app.api.routes.agents.knowledge_base_service.get_knowledge_base",
        lambda *args: pytest.fail("KB lookup before context-required response"),
    )
    monkeypatch.setattr(
        "app.api.routes.agents.answer_service.answer_question",
        lambda *args: pytest.fail("Feature 009 call without context"),
    )
    result = client.post(route(scope, selected), headers=bearer(caller, auth_settings), json=body)
    assert result.status_code == 422
    assert result.json() == {
        "detail": "Knowledge base context is required for knowledge questions."
    }
    assert router_provider.calls == [("Question", selected.system_prompt)]


@pytest.mark.parametrize("intent", [RoutingIntent.TOOL_REQUEST, RoutingIntent.UNSUPPORTED])
@pytest.mark.parametrize(
    "context_kind", ["omitted", "null", "active", "missing", "foreign", "disabled"]
)
def test_nonknowledge_routes_never_resolve_knowledge_base(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    router_provider: FakeRoutingProvider,
    monkeypatch: pytest.MonkeyPatch,
    intent: RoutingIntent,
    context_kind: str,
) -> None:
    caller = user(db_session)
    scope = workspace(db_session)
    foreign_scope = workspace(db_session)
    membership(db_session, caller, scope)
    selected = agent(db_session, scope, caller)
    router_provider.intent = intent
    body: dict[str, object] = {"request": "Request"}
    if context_kind == "null":
        body["knowledge_base_id"] = None
    elif context_kind == "active":
        body["knowledge_base_id"] = str(knowledge_base(db_session, scope, caller).id)
    elif context_kind == "missing":
        body["knowledge_base_id"] = str(uuid4())
    elif context_kind == "foreign":
        body["knowledge_base_id"] = str(knowledge_base(db_session, foreign_scope, caller).id)
    elif context_kind == "disabled":
        body["knowledge_base_id"] = str(
            knowledge_base(db_session, scope, caller, status=KnowledgeBaseStatus.DISABLED).id
        )
    monkeypatch.setattr(
        "app.api.routes.agents.knowledge_base_service.get_knowledge_base",
        lambda *args: pytest.fail("nonknowledge route queried a KB"),
    )
    monkeypatch.setattr(
        "app.api.routes.agents.answer_service.answer_question",
        lambda *args: pytest.fail("nonknowledge route called Feature 009"),
    )
    monkeypatch.setattr(
        "app.api.routes.agents.create_openai_embedding_provider",
        lambda *args: pytest.fail("nonknowledge route created embedding provider"),
    )
    result = client.post(route(scope, selected), headers=bearer(caller, auth_settings), json=body)
    assert result.status_code == 200
    assert result.json()["intent"] == intent.value
    assert "knowledge_base_id" not in result.json()
    assert "knowledge_base_id" not in result.json()["outcome"]
    if intent is RoutingIntent.TOOL_REQUEST:
        assert result.json()["outcome"]["status"] == "not_executed"
    else:
        assert result.json()["outcome"] == {
            "status": "unsupported",
            "message": "This request is outside the configured Agent capabilities.",
        }


@pytest.mark.parametrize("context_kind", ["missing", "foreign", "disabled"])
def test_knowledge_context_is_scoped_and_active(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    router_provider: FakeRoutingProvider,
    monkeypatch: pytest.MonkeyPatch,
    context_kind: str,
) -> None:
    caller = user(db_session)
    scope = workspace(db_session)
    foreign_scope = workspace(db_session)
    membership(db_session, caller, scope)
    selected = agent(db_session, scope, caller)
    router_provider.intent = RoutingIntent.KNOWLEDGE_QA
    if context_kind == "missing":
        kb_id = uuid4()
    elif context_kind == "foreign":
        kb_id = knowledge_base(db_session, foreign_scope, caller).id
    else:
        kb_id = knowledge_base(
            db_session, scope, caller, status=KnowledgeBaseStatus.DISABLED
        ).id
    monkeypatch.setattr(
        "app.api.routes.agents.answer_service.answer_question",
        lambda *args: pytest.fail("Feature 009 called with unavailable KB"),
    )
    result = client.post(
        route(scope, selected), headers=bearer(caller, auth_settings),
        json={"request": "Question", "knowledge_base_id": str(kb_id)},
    )
    if context_kind == "disabled":
        assert result.status_code == 409
    else:
        assert result.status_code == 404
        assert result.json() == {"detail": "Knowledge base not found"}
    assert router_provider.calls == [("Question", selected.system_prompt)]


@pytest.mark.parametrize("answer_status", [AnswerStatus.ANSWERED, AnswerStatus.UNSUPPORTED])
def test_knowledge_route_reuses_unchanged_answer_service(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    router_provider: FakeRoutingProvider,
    monkeypatch: pytest.MonkeyPatch,
    answer_status: AnswerStatus,
) -> None:
    caller = user(db_session)
    scope = workspace(db_session)
    membership(db_session, caller, scope)
    selected = agent(db_session, scope, caller)
    kb = knowledge_base(db_session, scope, caller)
    router_provider.intent = RoutingIntent.KNOWLEDGE_QA
    embedding_provider = object()
    monkeypatch.setattr(
        "app.api.routes.agents.create_openai_embedding_provider",
        lambda settings: embedding_provider,
    )
    calls: list[tuple[object, ...]] = []
    citation = AnswerCitation(
        document_id=uuid4(), file_name="travel.txt", document_version=1,
        chunk_id=uuid4(), chunk_index=0, excerpt="Travel limit is 100.",
    )

    def answer_spy(*args: object) -> AnswerResult:
        calls.append(args)
        return AnswerResult(
            question="What is the limit?",
            status=answer_status,
            answer="The limit is 100." if answer_status is AnswerStatus.ANSWERED else None,
            message=None if answer_status is AnswerStatus.ANSWERED else "Insufficient evidence.",
            citations=[citation] if answer_status is AnswerStatus.ANSWERED else [],
            usage=GenerationUsage(input_tokens=10, output_tokens=5, total_tokens=15),
        )

    monkeypatch.setattr("app.api.routes.agents.answer_service.answer_question", answer_spy)
    result = client.post(
        route(scope, selected), headers=bearer(caller, auth_settings),
        json={"request": " What is the limit? ", "knowledge_base_id": str(kb.id)},
    )
    assert result.status_code == 200
    assert result.json()["intent"] == "knowledge_qa"
    assert result.json()["request"] == "What is the limit?"
    assert result.json()["outcome"]["status"] == answer_status.value
    assert result.json()["outcome"]["generation"]["prompt_version"] == "grounded-answer-v1"
    if answer_status is AnswerStatus.ANSWERED:
        assert result.json()["outcome"]["citations"][0]["excerpt"] == citation.excerpt
    else:
        assert result.json()["outcome"]["answer"] is None
        assert result.json()["outcome"]["citations"] == []
    assert len(calls) == 1
    assert calls[0][0] is db_session
    assert calls[0][1:4] == (scope.id, kb.id, "What is the limit?")
    assert calls[0][4] is embedding_provider
    assert calls[0][5].prompt_version == "grounded-answer-v1"
    assert selected.system_prompt not in str(calls[0][1:])


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (RoutingConfigurationError("Routing provider is not configured"), 503),
        (RoutingInputTooLargeError("Routing input exceeds configured budget"), 422),
        (RoutingProviderError("Routing provider request failed"), 502),
    ],
)
def test_routing_errors_remain_errors(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    router_provider: FakeRoutingProvider,
    error: Exception,
    expected_status: int,
) -> None:
    caller = user(db_session)
    scope = workspace(db_session)
    membership(db_session, caller, scope)
    selected = agent(db_session, scope, caller)
    router_provider.error = error
    result = client.post(
        route(scope, selected), headers=bearer(caller, auth_settings),
        json={"request": "Question"},
    )
    assert result.status_code == expected_status
    assert result.json()["detail"] == str(error)


@pytest.mark.parametrize("malformed", [None, "tool_request", {"intent": "tool_request"}])
def test_unvalidated_fake_provider_output_fails_closed(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    router_provider: FakeRoutingProvider,
    malformed: object,
) -> None:
    caller = user(db_session)
    scope = workspace(db_session)
    membership(db_session, caller, scope)
    selected = agent(db_session, scope, caller)
    router_provider.intent = malformed
    result = client.post(
        route(scope, selected), headers=bearer(caller, auth_settings),
        json={"request": "Question"},
    )
    assert result.status_code == 502
    assert result.json() == {"detail": "Routing provider request failed"}


@pytest.mark.parametrize("role", [MembershipRole.AGENT_ADMIN, MembershipRole.SYSTEM_ADMIN])
def test_tool_administrators_manage_configuration_and_assignments(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    role: MembershipRole,
) -> None:
    caller = user(db_session)
    scope = workspace(db_session)
    membership(db_session, caller, scope, role=role)
    selected = agent(db_session, scope, caller)
    headers = bearer(caller, auth_settings)
    collection_path = f"/api/workspaces/{scope.id}/tools"

    created = client.post(
        collection_path,
        headers=headers,
        json={
            "tool_key": "get_reimbursement_status",
            "name": " Reimbursement status ",
            "description": " Read the signed-in employee's latest record. ",
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body == {
        "id": body["id"],
        "workspace_id": str(scope.id),
        "tool_key": "get_reimbursement_status",
        "name": "Reimbursement status",
        "description": "Read the signed-in employee's latest record.",
        "operation_type": "read_only",
        "risk_level": "low",
        "status": "disabled",
        "created_by": str(caller.id),
        "created_at": body["created_at"],
        "updated_at": body["updated_at"],
    }
    assert client.post(
        collection_path,
        headers=headers,
        json={
            "tool_key": "get_reimbursement_status",
            "name": "Duplicate",
            "description": "Duplicate configuration.",
        },
    ).status_code == 409
    assert client.post(
        collection_path,
        headers=headers,
        json={
            "tool_key": "unknown_tool",
            "name": "Unknown",
            "description": "Unknown capability.",
        },
    ).status_code == 422

    tool_id = body["id"]
    item_path = f"{collection_path}/{tool_id}"
    updated = client.patch(
        item_path, headers=headers, json={"name": "Claim status", "status": "active"}
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Claim status"
    assert updated.json()["status"] == "active"
    assert client.patch(item_path, headers=headers, json={}).status_code == 422
    assert client.get(collection_path, headers=headers).json()[0]["id"] == tool_id

    assignment_path = f"/api/workspaces/{scope.id}/agents/{selected.id}/tools"
    assigned = client.put(f"{assignment_path}/{tool_id}", headers=headers)
    assert assigned.status_code == 200
    assert assigned.json()["id"] == tool_id
    assert client.put(f"{assignment_path}/{tool_id}", headers=headers).status_code == 200
    assert client.put(
        f"{assignment_path}/{tool_id}", headers=headers, json={"unexpected": True}
    ).status_code == 422
    assert [item["id"] for item in client.get(assignment_path, headers=headers).json()] == [
        tool_id
    ]
    assert client.delete(f"{assignment_path}/{tool_id}", headers=headers).status_code == 204
    assert client.request(
        "delete", f"{assignment_path}/{tool_id}", headers=headers,
        json={"unexpected": True},
    ).status_code == 422
    assert client.delete(f"{assignment_path}/{tool_id}", headers=headers).status_code == 204


@pytest.mark.parametrize("role", [MembershipRole.EMPLOYEE, MembershipRole.KNOWLEDGE_ADMIN])
def test_non_administrators_cannot_discover_or_manage_tools(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    role: MembershipRole,
) -> None:
    caller = user(db_session)
    scope = workspace(db_session)
    membership(db_session, caller, scope, role=role)
    selected = agent(db_session, scope, caller)
    configured = tool(db_session, scope, caller)
    headers = bearer(caller, auth_settings)

    paths = [
        ("get", f"/api/workspaces/{scope.id}/tools", None),
        ("get", f"/api/workspaces/{scope.id}/tools/{configured.id}", None),
        (
            "post",
            f"/api/workspaces/{scope.id}/tools",
            {
                "tool_key": "get_employee_information",
                "name": "Employee",
                "description": "Own profile.",
            },
        ),
        ("patch", f"/api/workspaces/{scope.id}/tools/{configured.id}", {"status": "disabled"}),
        ("get", f"/api/workspaces/{scope.id}/agents/{selected.id}/tools", None),
        ("put", f"/api/workspaces/{scope.id}/agents/{selected.id}/tools/{configured.id}", None),
        ("delete", f"/api/workspaces/{scope.id}/agents/{selected.id}/tools/{configured.id}", None),
    ]
    for method, path, body in paths:
        response = client.request(method, path, headers=headers, json=body)
        assert response.status_code == 403
        assert response.json() == {"detail": "Agent administrator role required"}


def test_assigned_read_only_tool_executes_once_with_backend_identity(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    router_provider: FakeRoutingProvider,
    tool_selector: FakeToolSelector,
) -> None:
    caller = user(db_session)
    scope = workspace(db_session)
    membership(db_session, caller, scope)
    selected = agent(db_session, scope, caller)
    configured = tool(db_session, scope, caller)
    assign(db_session, scope, selected, configured)
    tool_selector.selection = ToolSelectionProposal("get_reimbursement_status", {})

    response = client.post(
        route(scope, selected),
        headers=bearer(caller, auth_settings),
        json={"request": "Check my reimbursement"},
    )

    assert response.status_code == 200
    outcome = response.json()["outcome"]
    assert outcome["status"] == "executed"
    assert outcome["tool"] == {
        "tool_key": "get_reimbursement_status", "name": configured.name
    }
    assert outcome["executed"] is True
    assert outcome["approval_required"] is False
    assert outcome["validated_arguments"] == {}
    assert outcome["result"]["type"] == "reimbursement_status"
    assert outcome["result"]["currency"] == "CNY"
    assert len(router_provider.calls) == len(tool_selector.calls) == 1
    assert [item.tool_key for item in tool_selector.calls[0][2]] == [
        "get_reimbursement_status"
    ]


def test_employee_tool_returns_only_authenticated_profile(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    tool_selector: FakeToolSelector,
) -> None:
    caller = user(db_session)
    scope = workspace(db_session)
    membership(db_session, caller, scope)
    selected = agent(db_session, scope, caller)
    configured = tool(db_session, scope, caller, tool_key="get_employee_information")
    assign(db_session, scope, selected, configured)
    tool_selector.selection = ToolSelectionProposal(
        "get_employee_information", {"subject": "self"}
    )

    response = client.post(
        route(scope, selected), headers=bearer(caller, auth_settings),
        json={"request": "Show my employee profile"},
    )
    result = response.json()["outcome"]["result"]
    assert response.status_code == 200
    assert result["type"] == "employee_information"
    assert result["name"] == caller.name
    assert result["email"] == caller.email
    assert set(result) == {
        "type", "name", "email", "department", "job_title", "employment_status"
    }


def test_sensitive_tool_requires_approval_without_creating_or_executing(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    tool_selector: FakeToolSelector,
) -> None:
    caller = user(db_session)
    scope = workspace(db_session)
    membership(db_session, caller, scope)
    selected = agent(db_session, scope, caller)
    configured = tool(db_session, scope, caller, tool_key="create_it_access_request")
    assign(db_session, scope, selected, configured)
    arguments = {
        "system": "production_database",
        "access_level": "read_only",
        "business_justification": "Investigate approved production incidents.",
        "duration_days": 14,
    }
    tool_selector.selection = ToolSelectionProposal(
        "create_it_access_request", arguments
    )

    response = client.post(
        route(scope, selected), headers=bearer(caller, auth_settings),
        json={"request": "Request temporary production access"},
    )

    assert response.status_code == 200
    assert response.json()["outcome"] == {
        "status": "approval_required",
        "tool": {"tool_key": "create_it_access_request", "name": configured.name},
        "executed": False,
        "approval_required": True,
        "validated_arguments": arguments,
        "result": None,
        "message": "This request requires human approval and was not executed.",
    }


def test_disabled_unassigned_and_foreign_tools_are_not_effective(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    tool_selector: FakeToolSelector,
) -> None:
    caller = user(db_session)
    scope = workspace(db_session)
    foreign_scope = workspace(db_session)
    membership(db_session, caller, scope, role=MembershipRole.AGENT_ADMIN)
    selected = agent(db_session, scope, caller)
    disabled = tool(
        db_session, scope, caller, status=ToolStatus.DISABLED
    )
    assign(db_session, scope, selected, disabled)
    foreign = tool(db_session, foreign_scope, caller)
    headers = bearer(caller, auth_settings)

    response = client.post(
        route(scope, selected), headers=headers, json={"request": "Check status"}
    )
    assert response.status_code == 200
    assert response.json()["outcome"]["reason"] == "no_available_tool"
    assert tool_selector.calls == []
    foreign_assignment = client.put(
        f"/api/workspaces/{scope.id}/agents/{selected.id}/tools/{foreign.id}",
        headers=headers,
    )
    assert foreign_assignment.status_code == 404
    assert foreign_assignment.json() == {"detail": "Tool not found"}


def test_invalid_selector_arguments_are_sanitized_provider_failure(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    tool_selector: FakeToolSelector,
) -> None:
    caller = user(db_session)
    scope = workspace(db_session)
    membership(db_session, caller, scope)
    selected = agent(db_session, scope, caller)
    configured = tool(db_session, scope, caller, tool_key="get_employee_information")
    assign(db_session, scope, selected, configured)
    tool_selector.selection = ToolSelectionProposal(
        "get_employee_information", {"subject": "other", "email": "victim@example.com"}
    )
    response = client.post(
        route(scope, selected), headers=bearer(caller, auth_settings),
        json={"request": "Show another employee"},
    )
    assert response.status_code == 502
    assert response.json() == {"detail": "Tool selector request failed"}


def test_selected_tool_is_revalidated_immediately_before_dispatch(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    tool_selector: FakeToolSelector,
) -> None:
    caller = user(db_session)
    scope = workspace(db_session)
    membership(db_session, caller, scope)
    selected = agent(db_session, scope, caller)
    configured = tool(db_session, scope, caller)
    assign(db_session, scope, selected, configured)

    def revoke_during_selection(
        request: str,
        agent_scope: str,
        candidates: tuple[ToolDefinition, ...],
    ) -> ToolSelection:
        del request, agent_scope, candidates
        configured.status = ToolStatus.DISABLED
        db_session.flush()
        return ToolSelectionProposal("get_reimbursement_status", {})

    tool_selector.select = revoke_during_selection  # type: ignore[method-assign]
    response = client.post(
        route(scope, selected), headers=bearer(caller, auth_settings),
        json={"request": "Check my reimbursement"},
    )
    assert response.status_code == 409
    assert response.json() == {"detail": "Tool is no longer active or assigned"}


def test_registry_risk_mismatch_fails_closed_before_selection(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    tool_selector: FakeToolSelector,
) -> None:
    caller = user(db_session)
    scope = workspace(db_session)
    membership(db_session, caller, scope)
    selected = agent(db_session, scope, caller)
    configured = tool(db_session, scope, caller)
    configured.risk_level = ToolRisk.HIGH
    assign(db_session, scope, selected, configured)

    response = client.post(
        route(scope, selected), headers=bearer(caller, auth_settings),
        json={"request": "Check my reimbursement"},
    )
    assert response.status_code == 503
    assert response.json() == {"detail": "Tool configuration is unavailable"}
    assert tool_selector.calls == []
