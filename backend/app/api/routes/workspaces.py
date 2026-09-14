from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.schemas.common import ErrorResponse
from app.schemas.membership import (
    MembershipCreate,
    MembershipResponse,
    MembershipUpdate,
    WorkspaceMemberResponse,
)
from app.schemas.workspace import WorkspaceCreate, WorkspaceResponse
from app.services import workspaces as workspace_service

router = APIRouter(prefix="/workspaces", tags=["workspaces"])
DatabaseSession = Annotated[Session, Depends(get_db_session)]

NOT_FOUND_RESPONSE = {404: {"model": ErrorResponse}}
NOT_FOUND_OR_CONFLICT_RESPONSES = {
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
}


@router.post(
    "",
    response_model=WorkspaceResponse,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"model": ErrorResponse}},
)
def create_workspace(payload: WorkspaceCreate, session: DatabaseSession) -> WorkspaceResponse:
    workspace = workspace_service.create_workspace(session, payload)
    return WorkspaceResponse.model_validate(workspace)


@router.get(
    "/{workspace_id}",
    response_model=WorkspaceResponse,
    responses=NOT_FOUND_RESPONSE,
)
def get_workspace(workspace_id: UUID, session: DatabaseSession) -> WorkspaceResponse:
    workspace = workspace_service.get_workspace(session, workspace_id)
    return WorkspaceResponse.model_validate(workspace)


@router.get(
    "/{workspace_id}/members",
    response_model=list[WorkspaceMemberResponse],
    responses=NOT_FOUND_RESPONSE,
)
def list_workspace_members(
    workspace_id: UUID,
    session: DatabaseSession,
) -> list[WorkspaceMemberResponse]:
    return workspace_service.list_workspace_members(session, workspace_id)


@router.post(
    "/{workspace_id}/members",
    response_model=MembershipResponse,
    status_code=status.HTTP_201_CREATED,
    responses=NOT_FOUND_OR_CONFLICT_RESPONSES,
)
def create_membership(
    workspace_id: UUID,
    payload: MembershipCreate,
    session: DatabaseSession,
) -> MembershipResponse:
    membership = workspace_service.create_membership(session, workspace_id, payload)
    return MembershipResponse.model_validate(membership)


@router.patch(
    "/{workspace_id}/members/{membership_id}",
    response_model=MembershipResponse,
    responses=NOT_FOUND_RESPONSE,
)
def update_membership(
    workspace_id: UUID,
    membership_id: UUID,
    payload: MembershipUpdate,
    session: DatabaseSession,
) -> MembershipResponse:
    membership = workspace_service.update_membership(
        session,
        workspace_id,
        membership_id,
        payload,
    )
    return MembershipResponse.model_validate(membership)
