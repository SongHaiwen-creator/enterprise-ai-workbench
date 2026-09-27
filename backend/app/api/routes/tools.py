from uuid import UUID

from fastapi import APIRouter, Body, HTTPException, Response, status

from app.api.dependencies.auth import CurrentUser, DatabaseSession
from app.api.dependencies.authorization import AgentAdministratorMembership
from app.models import Tool
from app.schemas.common import ErrorResponse
from app.schemas.tool import ToolConfigurationResponse, ToolCreate, ToolUpdate
from app.services import tools as tool_service

TOOL_RESPONSES = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
    503: {"model": ErrorResponse},
}

router = APIRouter(prefix="/workspaces/{workspace_id}/tools", tags=["tools"])
assignment_router = APIRouter(
    prefix="/workspaces/{workspace_id}/agents/{agent_id}/tools",
    tags=["tools"],
)


def _response(tool: Tool) -> ToolConfigurationResponse:
    try:
        return tool_service.to_configuration_response(tool)
    except tool_service.ToolRegistryConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post(
    "",
    response_model=ToolConfigurationResponse,
    status_code=status.HTTP_201_CREATED,
    responses=TOOL_RESPONSES,
)
def create_tool(
    workspace_id: UUID,
    payload: ToolCreate,
    session: DatabaseSession,
    current_user: CurrentUser,
    _administrator: AgentAdministratorMembership,
) -> ToolConfigurationResponse:
    try:
        tool = tool_service.create_tool(session, workspace_id, current_user.id, payload)
    except tool_service.UnknownToolKeyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _response(tool)


@router.get(
    "", response_model=list[ToolConfigurationResponse], responses=TOOL_RESPONSES
)
def list_tools(
    workspace_id: UUID,
    session: DatabaseSession,
    _administrator: AgentAdministratorMembership,
) -> list[ToolConfigurationResponse]:
    return [_response(tool) for tool in tool_service.list_tools(session, workspace_id)]


@router.get(
    "/{tool_id}", response_model=ToolConfigurationResponse, responses=TOOL_RESPONSES
)
def get_tool(
    workspace_id: UUID,
    tool_id: UUID,
    session: DatabaseSession,
    _administrator: AgentAdministratorMembership,
) -> ToolConfigurationResponse:
    return _response(tool_service.get_tool(session, workspace_id, tool_id))


@router.patch(
    "/{tool_id}", response_model=ToolConfigurationResponse, responses=TOOL_RESPONSES
)
def update_tool(
    workspace_id: UUID,
    tool_id: UUID,
    payload: ToolUpdate,
    session: DatabaseSession,
    _administrator: AgentAdministratorMembership,
) -> ToolConfigurationResponse:
    tool = tool_service.update_tool(session, workspace_id, tool_id, payload)
    return _response(tool)


@assignment_router.get(
    "", response_model=list[ToolConfigurationResponse], responses=TOOL_RESPONSES
)
def list_agent_tools(
    workspace_id: UUID,
    agent_id: UUID,
    session: DatabaseSession,
    _administrator: AgentAdministratorMembership,
) -> list[ToolConfigurationResponse]:
    return [
        _response(tool)
        for tool in tool_service.list_agent_tools(session, workspace_id, agent_id)
    ]


@assignment_router.put(
    "/{tool_id}", response_model=ToolConfigurationResponse, responses=TOOL_RESPONSES
)
def assign_tool(
    workspace_id: UUID,
    agent_id: UUID,
    tool_id: UUID,
    session: DatabaseSession,
    _administrator: AgentAdministratorMembership,
    payload: None = Body(default=None),
) -> ToolConfigurationResponse:
    del payload
    try:
        tool = tool_service.assign_tool(session, workspace_id, agent_id, tool_id)
    except tool_service.ToolRegistryConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return _response(tool)


@assignment_router.delete(
    "/{tool_id}", status_code=status.HTTP_204_NO_CONTENT, responses=TOOL_RESPONSES
)
def unassign_tool(
    workspace_id: UUID,
    agent_id: UUID,
    tool_id: UUID,
    session: DatabaseSession,
    _administrator: AgentAdministratorMembership,
    payload: None = Body(default=None),
) -> Response:
    del payload
    try:
        tool_service.unassign_tool(session, workspace_id, agent_id, tool_id)
    except tool_service.ToolRegistryConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
