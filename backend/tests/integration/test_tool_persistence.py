from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Agent, AgentTool, Tool, User, Workspace
from app.models.enums import AgentStatus, ToolRisk, ToolStatus
from app.services.tools import eligible_tools

pytestmark = pytest.mark.integration


def parents(session: Session) -> tuple[User, Workspace, Agent]:
    creator = User(email=f"tool-{uuid4()}@company.com", name="Tool Creator")
    workspace = Workspace(name="Tool Workspace", slug=f"tool-{uuid4()}")
    session.add_all([creator, workspace])
    session.flush()
    agent = Agent(
        workspace_id=workspace.id,
        created_by=creator.id,
        name="Tool Agent",
        system_prompt="Handle approved tools.",
        status=AgentStatus.ACTIVE,
    )
    session.add(agent)
    session.flush()
    return creator, workspace, agent


def test_tool_defaults_and_assignment_control_effective_capability(
    db_session: Session,
) -> None:
    creator, workspace, agent = parents(db_session)
    configured = Tool(
        workspace_id=workspace.id,
        created_by=creator.id,
        tool_key="get_reimbursement_status",
        name="Reimbursement status",
        description="Return the signed-in employee's latest mock status.",
        risk_level=ToolRisk.LOW,
    )
    db_session.add(configured)
    db_session.flush()

    assert configured.id is not None
    assert configured.status is ToolStatus.DISABLED
    assert eligible_tools(db_session, workspace.id, agent.id) == []

    configured.status = ToolStatus.ACTIVE
    db_session.flush()
    assert eligible_tools(db_session, workspace.id, agent.id) == []

    db_session.add(
        AgentTool(
            workspace_id=workspace.id, agent_id=agent.id, tool_id=configured.id
        )
    )
    db_session.flush()
    assert [item.id for item in eligible_tools(db_session, workspace.id, agent.id)] == [
        configured.id
    ]


def test_workspace_tool_key_is_unique(db_session: Session) -> None:
    creator, workspace, _ = parents(db_session)
    values = {
        "workspace_id": workspace.id,
        "created_by": creator.id,
        "tool_key": "get_employee_information",
        "name": "Employee profile",
        "description": "Read the signed-in employee profile.",
        "risk_level": ToolRisk.LOW,
    }
    db_session.add_all([Tool(**values), Tool(**values)])
    with pytest.raises(IntegrityError):
        db_session.flush()


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("tool_key", "Invalid-Key"),
        ("name", " "),
        ("description", "\t"),
        ("risk_level", "critical"),
        ("status", "draft"),
    ],
)
def test_tool_database_checks_reject_invalid_values(
    db_session: Session, column: str, value: str
) -> None:
    creator, workspace, _ = parents(db_session)
    values: dict[str, object] = {
        "workspace_id": workspace.id,
        "created_by": creator.id,
        "tool_key": "get_employee_information",
        "name": "Employee profile",
        "description": "Read own profile.",
        "risk_level": "low",
        "status": "active",
    }
    values[column] = value
    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                "INSERT INTO tools "
                "(workspace_id, tool_key, name, description, risk_level, status, created_by) "
                "VALUES (:workspace_id, :tool_key, :name, :description, :risk_level, "
                ":status, :created_by)"
            ),
            values,
        )


def test_assignment_database_rejects_cross_workspace_edges(
    db_session: Session,
) -> None:
    creator, workspace, agent = parents(db_session)
    other_workspace = Workspace(name="Other Tools", slug=f"other-tools-{uuid4()}")
    db_session.add(other_workspace)
    db_session.flush()
    foreign_tool = Tool(
        workspace_id=other_workspace.id,
        created_by=creator.id,
        tool_key="get_reimbursement_status",
        name="Foreign tool",
        description="Foreign Workspace capability.",
        risk_level=ToolRisk.LOW,
        status=ToolStatus.ACTIVE,
    )
    db_session.add(foreign_tool)
    db_session.flush()
    db_session.add(
        AgentTool(
            workspace_id=workspace.id,
            agent_id=agent.id,
            tool_id=foreign_tool.id,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
