from typing import Literal
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Agent, AgentTool, Membership, Tool, User, Workspace
from app.models.enums import (
    AgentStatus,
    MembershipStatus,
    ToolRisk,
    ToolStatus,
    UserStatus,
    WorkspaceStatus,
)
from app.schemas.tool import ToolConfigurationResponse, ToolCreate, ToolUpdate
from app.schemas.tool_calling import (
    ApprovalReference,
    ToolApprovalRequiredOutcome,
    ToolExecutedOutcome,
    ToolNotExecutedOutcome,
)
from app.services.approvals import ApprovalConfigurationError, create_pending_approval
from app.services.exceptions import (
    WORKSPACE_ACCESS_DENIED,
    ConflictError,
    ForbiddenError,
    NotFoundError,
)
from app.services.tool_execution import ToolExecutionContext
from app.services.tool_registry import (
    ToolDefinition,
    ToolOperationType,
    get_tool_definition,
)
from app.services.tool_selection import (
    ToolSelectionDecline,
    ToolSelectionProposal,
    ToolSelector,
)

NO_PERMITTED_TOOL_MESSAGE = (
    "No permitted enterprise capability can safely handle this request."
)
EXECUTED_MESSAGE = "The read-only enterprise capability completed successfully."
APPROVAL_REQUIRED_MESSAGE = (
    "An approval request was submitted for human review. Nothing was executed."
)
TOOL_PROVIDER_FAILURE = "Tool selector request failed"
TOOL_ADAPTER_FAILURE = "Enterprise Tool request failed"
TOOL_REGISTRY_FAILURE = "Tool configuration is unavailable"


class UnknownToolKeyError(Exception):
    """An administrative request named an unknown or reserved Tool key."""


class ToolRegistryConfigurationError(Exception):
    """Persisted Tool configuration conflicts with the application registry."""


class ToolAdapterError(Exception):
    """A backend-owned Tool adapter failed or returned invalid output."""


def _definition_for(tool: Tool) -> ToolDefinition:
    definition = get_tool_definition(tool.tool_key)
    if definition is None or tool.risk_level is not definition.risk:
        raise ToolRegistryConfigurationError(TOOL_REGISTRY_FAILURE)
    return definition


def to_configuration_response(tool: Tool) -> ToolConfigurationResponse:
    definition = _definition_for(tool)
    return ToolConfigurationResponse(
        id=tool.id,
        workspace_id=tool.workspace_id,
        tool_key=tool.tool_key,
        name=tool.name,
        description=tool.description,
        operation_type=definition.operation_type.value,
        risk_level=tool.risk_level.value,
        status=tool.status,
        created_by=tool.created_by,
        created_at=tool.created_at,
        updated_at=tool.updated_at,
    )


def create_tool(
    session: Session,
    workspace_id: UUID,
    creator_id: UUID,
    payload: ToolCreate,
) -> Tool:
    definition = get_tool_definition(payload.tool_key)
    if definition is None:
        raise UnknownToolKeyError("Unknown tool_key")
    tool = Tool(
        workspace_id=workspace_id,
        tool_key=payload.tool_key,
        name=payload.name,
        description=payload.description,
        risk_level=definition.risk,
        created_by=creator_id,
    )
    session.add(tool)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ConflictError("Tool configuration already exists") from exc
    session.refresh(tool)
    return tool


def get_tool(session: Session, workspace_id: UUID, tool_id: UUID) -> Tool:
    tool = session.scalar(
        select(Tool).where(Tool.id == tool_id, Tool.workspace_id == workspace_id)
    )
    if tool is None:
        raise NotFoundError("Tool not found")
    return tool


def list_tools(session: Session, workspace_id: UUID) -> list[Tool]:
    return list(
        session.scalars(
            select(Tool)
            .where(Tool.workspace_id == workspace_id)
            .order_by(Tool.name, Tool.id)
        ).all()
    )


def update_tool(
    session: Session,
    workspace_id: UUID,
    tool_id: UUID,
    payload: ToolUpdate,
) -> Tool:
    tool = get_tool(session, workspace_id, tool_id)
    for field_name, value in payload.model_dump(exclude_unset=True).items():
        setattr(tool, field_name, value)
    session.commit()
    session.refresh(tool)
    return tool


def _get_scoped_agent(session: Session, workspace_id: UUID, agent_id: UUID) -> Agent:
    agent = session.scalar(
        select(Agent).where(Agent.id == agent_id, Agent.workspace_id == workspace_id)
    )
    if agent is None:
        raise NotFoundError("Agent not found")
    return agent


def list_agent_tools(
    session: Session, workspace_id: UUID, agent_id: UUID
) -> list[Tool]:
    _get_scoped_agent(session, workspace_id, agent_id)
    return list(
        session.scalars(
            select(Tool)
            .join(
                AgentTool,
                (AgentTool.tool_id == Tool.id)
                & (AgentTool.workspace_id == Tool.workspace_id),
            )
            .where(
                AgentTool.workspace_id == workspace_id,
                AgentTool.agent_id == agent_id,
            )
            .order_by(Tool.name, Tool.id)
        ).all()
    )


def assign_tool(
    session: Session, workspace_id: UUID, agent_id: UUID, tool_id: UUID
) -> Tool:
    _get_scoped_agent(session, workspace_id, agent_id)
    tool = get_tool(session, workspace_id, tool_id)
    _definition_for(tool)
    session.execute(
        insert(AgentTool)
        .values(workspace_id=workspace_id, agent_id=agent_id, tool_id=tool_id)
        .on_conflict_do_nothing(index_elements=["agent_id", "tool_id"])
    )
    session.commit()
    return tool


def unassign_tool(
    session: Session, workspace_id: UUID, agent_id: UUID, tool_id: UUID
) -> None:
    _get_scoped_agent(session, workspace_id, agent_id)
    tool = get_tool(session, workspace_id, tool_id)
    _definition_for(tool)
    edge = session.get(AgentTool, (agent_id, tool_id))
    if edge is not None:
        session.delete(edge)
        session.commit()


def eligible_tools(
    session: Session, workspace_id: UUID, agent_id: UUID
) -> list[Tool]:
    return list(
        session.scalars(
            select(Tool)
            .join(
                AgentTool,
                (AgentTool.tool_id == Tool.id)
                & (AgentTool.workspace_id == Tool.workspace_id),
            )
            .join(
                Agent,
                (Agent.id == AgentTool.agent_id)
                & (Agent.workspace_id == AgentTool.workspace_id),
            )
            .where(
                Tool.workspace_id == workspace_id,
                Tool.status == ToolStatus.ACTIVE,
                Agent.status == AgentStatus.ACTIVE,
                AgentTool.workspace_id == workspace_id,
                AgentTool.agent_id == agent_id,
            )
            .order_by(Tool.tool_key)
        ).all()
    )


def _fresh_effective_tool(
    session: Session,
    workspace_id: UUID,
    agent_id: UUID,
    tool_key: str,
) -> Tool:
    tool = session.scalar(
        select(Tool)
        .join(
            AgentTool,
            (AgentTool.tool_id == Tool.id)
            & (AgentTool.workspace_id == Tool.workspace_id),
        )
        .join(
            Agent,
            (Agent.id == AgentTool.agent_id)
            & (Agent.workspace_id == AgentTool.workspace_id),
        )
        .where(
            Tool.workspace_id == workspace_id,
            Tool.tool_key == tool_key,
            Tool.status == ToolStatus.ACTIVE,
            Agent.status == AgentStatus.ACTIVE,
            AgentTool.workspace_id == workspace_id,
            AgentTool.agent_id == agent_id,
        )
    )
    if tool is None:
        raise ConflictError("Tool is no longer active or assigned")
    return tool


def _fresh_authorized_caller_identity(
    session: Session,
    workspace_id: UUID,
    user_id: UUID,
) -> tuple[str, str]:
    authorization = session.execute(
        select(
            User.name.label("user_name"),
            User.email.label("user_email"),
            User.status.label("user_status"),
            Workspace.status.label("workspace_status"),
            Membership.status.label("membership_status"),
        )
        .select_from(User)
        .join(Membership, Membership.user_id == User.id)
        .join(Workspace, Workspace.id == Membership.workspace_id)
        .where(
            User.id == user_id,
            Workspace.id == workspace_id,
            Membership.workspace_id == workspace_id,
        )
    ).one_or_none()
    if (
        authorization is None
        or authorization.user_status is not UserStatus.ACTIVE
        or authorization.workspace_status is not WorkspaceStatus.ACTIVE
        or authorization.membership_status is not MembershipStatus.ACTIVE
    ):
        raise ForbiddenError(WORKSPACE_ACCESS_DENIED)
    return authorization.user_name, authorization.user_email


def _not_executed(
    reason: Literal[
        "no_available_tool", "no_matching_tool", "missing_required_arguments"
    ],
) -> ToolNotExecutedOutcome:
    return ToolNotExecutedOutcome(
        reason=reason,
        message=NO_PERMITTED_TOOL_MESSAGE,
    )


def handle_tool_request(
    session: Session,
    *,
    workspace_id: UUID,
    agent_id: UUID,
    request: str,
    agent_scope: str,
    user_id: UUID,
    selector: ToolSelector,
) -> ToolExecutedOutcome | ToolApprovalRequiredOutcome | ToolNotExecutedOutcome:
    configured = eligible_tools(session, workspace_id, agent_id)
    if not configured:
        return _not_executed("no_available_tool")
    definitions = tuple(_definition_for(tool) for tool in configured)
    selection = selector.select(request, agent_scope, definitions)
    if isinstance(selection, ToolSelectionDecline):
        reason: Literal["no_matching_tool", "missing_required_arguments"] = (
            "missing_required_arguments"
            if selection.reason == "missing_required_arguments"
            else "no_matching_tool"
        )
        return _not_executed(reason)
    if not isinstance(selection, ToolSelectionProposal):
        raise ToolAdapterError(TOOL_PROVIDER_FAILURE)

    user_name, user_email = _fresh_authorized_caller_identity(
        session, workspace_id, user_id
    )
    tool = _fresh_effective_tool(
        session, workspace_id, agent_id, selection.tool_key
    )
    definition = _definition_for(tool)
    try:
        arguments = definition.argument_model.model_validate(selection.arguments)
    except ValidationError as exc:
        raise ToolAdapterError(TOOL_PROVIDER_FAILURE) from exc

    reference = {"tool_key": tool.tool_key, "name": tool.name}
    if not definition.immediate_execution:
        try:
            approval = create_pending_approval(
                session,
                workspace_id=workspace_id,
                requester_id=user_id,
                agent_id=agent_id,
                tool_id=tool.id,
                definition=definition,
                arguments=arguments,
            )
        except ApprovalConfigurationError as exc:
            raise ToolRegistryConfigurationError(TOOL_REGISTRY_FAILURE) from exc
        return ToolApprovalRequiredOutcome(
            tool=reference,
            validated_arguments=arguments,
            approval=ApprovalReference(
                id=approval.id,
                decision_status=approval.decision_status,
                execution_status=approval.execution_status,
                created_at=approval.created_at,
                expires_at=approval.expires_at,
            ),
            message=APPROVAL_REQUIRED_MESSAGE,
        )
    if (
        definition.risk is not ToolRisk.LOW
        or definition.operation_type is not ToolOperationType.READ_ONLY
        or definition.adapter is None
        or definition.result_model is None
    ):
        raise ToolRegistryConfigurationError(TOOL_REGISTRY_FAILURE)

    context = ToolExecutionContext(
        workspace_id=workspace_id,
        user_id=user_id,
        user_name=user_name,
        user_email=user_email,
        agent_id=agent_id,
    )
    try:
        raw_result = definition.adapter(context, arguments)
        result = definition.result_model.model_validate(raw_result)
        return ToolExecutedOutcome(
            tool=reference,
            validated_arguments=arguments,
            result=result,
            message=EXECUTED_MESSAGE,
        )
    except Exception as exc:
        raise ToolAdapterError(TOOL_ADAPTER_FAILURE) from exc
