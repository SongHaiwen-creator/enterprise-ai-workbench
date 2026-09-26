from collections.abc import Generator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.dependencies.generation import get_generation_provider
from app.api.dependencies.routing import get_routing_provider
from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.main import app
from app.models import Agent, KnowledgeBase, Membership, User, Workspace
from app.models.enums import (
    AgentStatus,
    KnowledgeBaseStatus,
    MembershipRole,
    MembershipStatus,
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
def client(
    db_session: Session,
    auth_settings: Settings,
    router_provider: FakeRoutingProvider,
) -> Generator[TestClient, None, None]:
    def override_db_session() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[get_settings] = lambda: auth_settings
    app.dependency_overrides[get_routing_provider] = lambda: router_provider
    app.dependency_overrides[get_generation_provider] = FakeGenerationProvider
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_settings, None)
        app.dependency_overrides.pop(get_routing_provider, None)
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
            "required_capability": "enterprise_tool",
            "message": "This request requires an enterprise tool. No action was executed.",
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
