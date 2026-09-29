from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Body, HTTPException, Query

from app.api.dependencies.auth import CurrentUser, DatabaseSession
from app.api.dependencies.authorization import ActiveWorkspaceMembership
from app.models.enums import ApprovalDecisionStatus, ApprovalExecutionStatus
from app.schemas.approval import (
    ApprovalCancelRequest,
    ApprovalDecisionRequest,
    ApprovalListResponse,
    ApprovalResponse,
)
from app.schemas.common import ErrorResponse
from app.services import approvals as approval_service

APPROVAL_RESPONSES = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
    502: {"model": ErrorResponse},
    503: {"model": ErrorResponse},
}

router = APIRouter(prefix="/workspaces/{workspace_id}/approvals", tags=["approvals"])


def _unavailable(exc: approval_service.ApprovalConfigurationError) -> HTTPException:
    return HTTPException(status_code=503, detail=str(exc))


@router.get("", response_model=ApprovalListResponse, responses=APPROVAL_RESPONSES)
def list_approvals(
    workspace_id: UUID,
    session: DatabaseSession,
    membership: ActiveWorkspaceMembership,
    current_user: CurrentUser,
    scope: Literal["mine", "review"] = "mine",
    decision_status: ApprovalDecisionStatus | None = None,
    execution_status: ApprovalExecutionStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ApprovalListResponse:
    try:
        items = approval_service.list_approvals(
            session,
            workspace_id=workspace_id,
            user_id=current_user.id,
            role=membership.role,
            scope=scope,
            decision_status=decision_status,
            execution_status=execution_status,
            limit=limit,
            offset=offset,
        )
    except approval_service.ApprovalConfigurationError as exc:
        raise _unavailable(exc) from exc
    return ApprovalListResponse(items=items, limit=limit, offset=offset)


@router.get(
    "/{approval_id}", response_model=ApprovalResponse, responses=APPROVAL_RESPONSES
)
def get_approval(
    workspace_id: UUID,
    approval_id: UUID,
    session: DatabaseSession,
    membership: ActiveWorkspaceMembership,
    current_user: CurrentUser,
) -> ApprovalResponse:
    try:
        return approval_service.read_approval(
            session,
            workspace_id=workspace_id,
            approval_id=approval_id,
            user_id=current_user.id,
            role=membership.role,
        )
    except approval_service.ApprovalConfigurationError as exc:
        raise _unavailable(exc) from exc


@router.post(
    "/{approval_id}/decision",
    response_model=ApprovalResponse,
    responses=APPROVAL_RESPONSES,
)
def decide_approval(
    workspace_id: UUID,
    approval_id: UUID,
    payload: ApprovalDecisionRequest,
    session: DatabaseSession,
    _membership: ActiveWorkspaceMembership,
    current_user: CurrentUser,
) -> ApprovalResponse:
    approval_service.decide_approval(
        session,
        workspace_id=workspace_id,
        approval_id=approval_id,
        user_id=current_user.id,
        decision=payload.decision,
        note=payload.note,
    )
    try:
        return approval_service.get_approval_response(session, workspace_id, approval_id)
    except approval_service.ApprovalConfigurationError as exc:
        raise _unavailable(exc) from exc


@router.post(
    "/{approval_id}/cancel",
    response_model=ApprovalResponse,
    responses=APPROVAL_RESPONSES,
)
def cancel_approval(
    workspace_id: UUID,
    approval_id: UUID,
    session: DatabaseSession,
    _membership: ActiveWorkspaceMembership,
    current_user: CurrentUser,
    payload: Annotated[ApprovalCancelRequest | None, Body()] = None,
) -> ApprovalResponse:
    del payload
    approval_service.cancel_approval(
        session,
        workspace_id=workspace_id,
        approval_id=approval_id,
        user_id=current_user.id,
    )
    try:
        return approval_service.get_approval_response(session, workspace_id, approval_id)
    except approval_service.ApprovalConfigurationError as exc:
        raise _unavailable(exc) from exc
