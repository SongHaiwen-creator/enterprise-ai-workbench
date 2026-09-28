"""Shared fixtures and builders for Feature 013 Human Approval tests."""

from collections.abc import Generator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.dependencies.generation import get_generation_provider
from app.api.dependencies.routing import get_routing_provider
from app.api.dependencies.tool_selection import get_tool_selector
from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.main import app
from app.models import Agent, AgentTool, Membership, Tool, User, Workspace
from app.models.enums import (
    AgentStatus,
    MembershipRole,
    MembershipStatus,
    ToolRisk,
    ToolStatus,
    UserStatus,
    WorkspaceStatus,
)
from app.schemas.agent_routing import RoutingIntent
from app.security.tokens import create_access_token
from app.services.tool_registry import ToolDefinition
from app.services.tool_selection import (
    ToolSelection,
    ToolSelectionDecline,
    ToolSelectionProposal,
)

JWT_SECRET = "approval-api-secret-longer-than-thirty-two-bytes"
REQUEST_TEXT = "Please request read-only production database access for incident work"
ARGUMENTS: dict[str, Any] = {
    "system": "production_database",
    "access_level": "read_only",
    "business_justification": "Investigate approved production incidents.",
    "duration_days": 14,
}
INVALIDATED = "Approval is no longer valid; submit a new request"


class FakeRoutingProvider:
    def __init__(self) -> None:
        self.intent: object = RoutingIntent.TOOL_REQUEST
        self.calls: list[tuple[str, str]] = []

    def route(self, request: str, system_prompt: str) -> object:
        self.calls.append((request, system_prompt))
        return self.intent


class FakeToolSelector:
    def __init__(self) -> None:
        self.selection: ToolSelection = ToolSelectionDecline(reason="no_matching_capability")
        self.calls: list[str] = []

    def select(
        self,
        request: str,
        agent_scope: str,
        candidates: tuple[ToolDefinition, ...],
    ) -> ToolSelection:
        del agent_scope, candidates
        self.calls.append(request)
        return self.selection


class FakeGenerationProvider:
    def generate(self, question: str, evidence: object) -> None:
        del question, evidence
        raise AssertionError("Approval paths must never call a model")


@dataclass
class Scenario:
    workspace: Workspace
    requester: User
    requester_membership: Membership
    reviewer: User
    reviewer_membership: Membership
    agent: Agent
    tool: Tool

    @property
    def approvals_url(self) -> str:
        return f"/api/workspaces/{self.workspace.id}/approvals"

    @property
    def route_url(self) -> str:
        return f"/api/workspaces/{self.workspace.id}/agents/{self.agent.id}/route"

    def approval_url(self, approval_id: UUID | str) -> str:
        return f"{self.approvals_url}/{approval_id}"


def make_settings(database_urls: tuple[object, object]) -> Settings:
    database_url, test_database_url = database_urls
    return Settings(
        database_url=str(database_url),
        test_database_url=str(test_database_url),
        jwt_secret_key=JWT_SECRET,
        openai_api_key=None,
        _env_file=None,
    )


def install_overrides(
    session_dependency: Any,
    settings: Settings,
    router: FakeRoutingProvider,
    selector: FakeToolSelector,
) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_db_session] = session_dependency
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_routing_provider] = lambda: router
    app.dependency_overrides[get_tool_selector] = lambda: selector
    app.dependency_overrides[get_generation_provider] = FakeGenerationProvider
    try:
        with TestClient(app) as client:
            yield client
    finally:
        for dependency in (
            get_db_session, get_settings, get_routing_provider,
            get_tool_selector, get_generation_provider,
        ):
            app.dependency_overrides.pop(dependency, None)


def make_user(session: Session, name: str = "Approval User") -> User:
    result = User(email=f"approval-{uuid4().hex}@company.com", name=name)
    session.add(result)
    session.flush()
    return result


def make_workspace(session: Session) -> Workspace:
    result = Workspace(name="Approval Workspace", slug=f"approval-{uuid4().hex}")
    session.add(result)
    session.flush()
    return result


def make_membership(
    session: Session,
    user: User,
    workspace: Workspace,
    role: MembershipRole = MembershipRole.EMPLOYEE,
) -> Membership:
    result = Membership(
        user_id=user.id,
        workspace_id=workspace.id,
        role=role,
        status=MembershipStatus.ACTIVE,
        joined_at=datetime.now(UTC),
    )
    session.add(result)
    session.flush()
    return result


def make_scenario(
    session: Session,
    *,
    requester_role: MembershipRole = MembershipRole.EMPLOYEE,
) -> Scenario:
    workspace = make_workspace(session)
    requester = make_user(session, "Employee One")
    reviewer = make_user(session, "Admin One")
    requester_membership = make_membership(session, requester, workspace, requester_role)
    reviewer_membership = make_membership(
        session, reviewer, workspace, MembershipRole.SYSTEM_ADMIN
    )
    agent = Agent(
        workspace_id=workspace.id,
        created_by=reviewer.id,
        name="Employee Service Assistant",
        system_prompt="Route employee service requests.",
        status=AgentStatus.ACTIVE,
    )
    session.add(agent)
    session.flush()
    tool = Tool(
        workspace_id=workspace.id,
        created_by=reviewer.id,
        tool_key="create_it_access_request",
        name="Create IT access request",
        description="Submit an IT access request for approval.",
        risk_level=ToolRisk.HIGH,
        status=ToolStatus.ACTIVE,
    )
    session.add(tool)
    session.flush()
    session.add(AgentTool(workspace_id=workspace.id, agent_id=agent.id, tool_id=tool.id))
    session.flush()
    return Scenario(
        workspace=workspace,
        requester=requester,
        requester_membership=requester_membership,
        reviewer=reviewer,
        reviewer_membership=reviewer_membership,
        agent=agent,
        tool=tool,
    )


def bearer(user: User, settings: Settings) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, settings)}"}


def request_approval(
    client: TestClient,
    scenario: Scenario,
    selector: FakeToolSelector,
    settings: Settings,
    arguments: dict[str, Any] | None = None,
    requester: User | None = None,
) -> str:
    selector.selection = ToolSelectionProposal(
        "create_it_access_request", dict(arguments or ARGUMENTS)
    )
    response = client.post(
        scenario.route_url,
        headers=bearer(requester or scenario.requester, settings),
        json={"request": REQUEST_TEXT},
    )
    assert response.status_code == 200, response.text
    outcome = response.json()["outcome"]
    assert outcome["status"] == "approval_required"
    assert outcome["executed"] is False
    return str(outcome["approval"]["id"])


def decide(
    client: TestClient,
    scenario: Scenario,
    approval_id: str,
    settings: Settings,
    decision: str = "approve",
    user: User | None = None,
    note: str | None = None,
) -> Any:
    body: dict[str, Any] = {"decision": decision}
    if note is not None:
        body["note"] = note
    return client.post(
        f"{scenario.approval_url(approval_id)}/decision",
        headers=bearer(user or scenario.reviewer, settings),
        json=body,
    )


def set_status(
    session: Session,
    entity: User | Workspace | Membership | Agent | Tool,
    status: UserStatus | WorkspaceStatus | MembershipStatus | AgentStatus | ToolStatus,
) -> None:
    entity.status = status  # type: ignore[assignment]
    session.flush()
