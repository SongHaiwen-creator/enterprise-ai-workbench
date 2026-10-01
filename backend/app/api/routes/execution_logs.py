from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import AwareDatetime

from app.api.dependencies.auth import DatabaseSession
from app.api.dependencies.authorization import AgentAdministratorMembership
from app.models.enums import ExecutionLogOperation, ExecutionLogStatus
from app.schemas.common import ErrorResponse
from app.schemas.execution_log import ExecutionLogListResponse, ExecutionLogResponse
from app.services import execution_logs as execution_log_service

EXECUTION_LOG_RESPONSES = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}

router = APIRouter(
    prefix="/workspaces/{workspace_id}/execution-logs", tags=["execution-logs"]
)


@router.get(
    "",
    response_model=ExecutionLogListResponse,
    response_model_exclude_unset=True,
    responses=EXECUTION_LOG_RESPONSES,
)
def list_execution_logs(
    workspace_id: UUID,
    session: DatabaseSession,
    _administrator: AgentAdministratorMembership,
    operation: ExecutionLogOperation | None = None,
    status: ExecutionLogStatus | None = None,
    agent_id: UUID | None = None,
    user_id: UUID | None = None,
    tool_key: Literal[
        "get_reimbursement_status",
        "get_employee_information",
        "create_it_access_request",
    ] | None = None,
    created_after: AwareDatetime | None = None,
    created_before: AwareDatetime | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ExecutionLogListResponse:
    rows = execution_log_service.list_execution_logs(
        session,
        workspace_id=workspace_id,
        operation=operation,
        status=status,
        agent_id=agent_id,
        user_id=user_id,
        tool_key=tool_key,
        created_after=created_after,
        created_before=created_before,
        limit=limit,
        offset=offset,
    )
    return ExecutionLogListResponse(
        items=[execution_log_service.to_response(row) for row in rows],
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{log_id}",
    response_model=ExecutionLogResponse,
    response_model_exclude_unset=True,
    responses=EXECUTION_LOG_RESPONSES,
)
def get_execution_log(
    workspace_id: UUID,
    log_id: UUID,
    session: DatabaseSession,
    _administrator: AgentAdministratorMembership,
) -> ExecutionLogResponse:
    row = execution_log_service.get_execution_log(session, workspace_id, log_id)
    return execution_log_service.to_response(row)
