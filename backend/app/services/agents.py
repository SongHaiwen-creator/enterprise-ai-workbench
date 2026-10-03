from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Agent
from app.models.enums import AgentStatus
from app.schemas.agent import AgentCreate, AgentUpdate
from app.services.authorization_policy import require_scoped_resource

AGENT_NOT_FOUND = "Agent not found"
AGENT_NOT_ACTIVE = "Agent is not active"
KNOWLEDGE_BASE_NOT_ACTIVE = "Knowledge base is not active"
KNOWLEDGE_CONTEXT_REQUIRED = "Knowledge base context is required for knowledge questions."


def get_agent(session: Session, workspace_id: UUID, agent_id: UUID) -> Agent:
    agent = session.scalar(
        select(Agent).where(
            Agent.id == agent_id,
            Agent.workspace_id == workspace_id,
        )
    )
    require_scoped_resource(agent is not None, AGENT_NOT_FOUND)
    return agent


def list_agents(
    session: Session,
    workspace_id: UUID,
    include_inactive: bool = False,
) -> list[Agent]:
    statement = select(Agent).where(Agent.workspace_id == workspace_id)
    if not include_inactive:
        statement = statement.where(Agent.status == AgentStatus.ACTIVE)
    statement = statement.order_by(Agent.name, Agent.id)
    return list(session.scalars(statement).all())


def create_agent(
    session: Session,
    workspace_id: UUID,
    creator_id: UUID,
    payload: AgentCreate,
) -> Agent:
    agent = Agent(
        workspace_id=workspace_id,
        name=payload.name,
        description=payload.description,
        system_prompt=payload.system_prompt,
        created_by=creator_id,
    )
    session.add(agent)
    session.commit()
    session.refresh(agent)
    return agent


def update_agent(
    session: Session,
    workspace_id: UUID,
    agent_id: UUID,
    payload: AgentUpdate,
) -> Agent:
    agent = get_agent(session, workspace_id, agent_id)
    for field_name, value in payload.model_dump(exclude_unset=True).items():
        setattr(agent, field_name, value)
    session.commit()
    session.refresh(agent)
    return agent
