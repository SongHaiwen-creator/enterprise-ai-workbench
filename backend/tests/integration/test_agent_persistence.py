from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Agent, User, Workspace
from app.models.enums import AgentStatus
from app.schemas.agent import AgentCreate, AgentUpdate
from app.services.agents import create_agent, get_agent, list_agents, update_agent
from app.services.exceptions import NotFoundError

pytestmark = pytest.mark.integration


def test_agent_service_persists_configuration_and_scopes_all_lookups(db_session: Session) -> None:
    creator = User(email="agent-creator@company.com", name="Creator")
    workspace = Workspace(name="Agent Workspace", slug="agent-workspace")
    foreign_workspace = Workspace(name="Foreign Workspace", slug="foreign-agent-workspace")
    db_session.add_all([creator, workspace, foreign_workspace])
    db_session.flush()

    agent = create_agent(
        db_session,
        workspace.id,
        creator.id,
        AgentCreate(name="Assistant", system_prompt="Route employee services."),
    )
    assert agent.id is not None
    assert agent.workspace_id == workspace.id
    assert agent.created_by == creator.id
    assert agent.system_prompt == "Route employee services."
    assert agent.status is AgentStatus.DRAFT
    assert agent.created_at is not None
    assert agent.updated_at is not None
    assert list_agents(db_session, workspace.id) == []
    assert [listed.id for listed in list_agents(db_session, workspace.id, True)] == [agent.id]
    assert list_agents(db_session, foreign_workspace.id, True) == []

    with pytest.raises(NotFoundError, match="Agent not found"):
        get_agent(db_session, foreign_workspace.id, agent.id)
    with pytest.raises(NotFoundError, match="Agent not found"):
        get_agent(db_session, workspace.id, uuid4())
    with pytest.raises(NotFoundError, match="Agent not found"):
        update_agent(
            db_session,
            foreign_workspace.id,
            agent.id,
            AgentUpdate(status=AgentStatus.ACTIVE),
        )

    active = update_agent(
        db_session,
        workspace.id,
        agent.id,
        AgentUpdate(name="Updated Assistant", status=AgentStatus.ACTIVE),
    )
    assert active.name == "Updated Assistant"
    assert active.status is AgentStatus.ACTIVE
    assert [listed.id for listed in list_agents(db_session, workspace.id)] == [agent.id]

    disabled = update_agent(
        db_session,
        workspace.id,
        agent.id,
        AgentUpdate(status=AgentStatus.DISABLED),
    )
    assert disabled.status is AgentStatus.DISABLED
    assert list_agents(db_session, workspace.id) == []


@pytest.mark.parametrize(
    ("name", "system_prompt", "status"),
    [
        (" ", "Valid", "draft"),
        ("\t\n", "Valid", "draft"),
        ("Valid", " ", "draft"),
        ("Valid", "\t\n", "draft"),
        ("Valid", "Valid", "unknown"),
    ],
)
def test_agent_database_checks_reject_invalid_values(
    db_session: Session,
    name: str,
    system_prompt: str,
    status: str,
) -> None:
    creator = User(email="agent-checks@company.com", name="Creator")
    workspace = Workspace(name="Agent Checks", slug="agent-checks")
    db_session.add_all([creator, workspace])
    db_session.flush()

    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                "INSERT INTO agents (workspace_id, name, system_prompt, status, created_by) "
                "VALUES (:workspace_id, :name, :system_prompt, :status, :created_by)"
            ),
            {
                "workspace_id": workspace.id,
                "name": name,
                "system_prompt": system_prompt,
                "status": status,
                "created_by": creator.id,
            },
        )


def test_agent_database_foreign_keys_reject_orphan(db_session: Session) -> None:
    db_session.add(
        Agent(
            workspace_id=uuid4(),
            name="Orphan",
            system_prompt="Route requests.",
            created_by=uuid4(),
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
