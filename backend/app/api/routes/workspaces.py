from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import CurrentUser
from app.api.dependencies.authorization import (
    ActiveWorkspaceMembership,
    SystemAdministratorMembership,
)
from app.db.session import get_db_session
from app.schemas.common import ErrorResponse
from app.schemas.membership import (
    MembershipCreate,
    MembershipResponse,
    MembershipUpdate,
    WorkspaceMemberResponse,
)
from app.schemas.workspace import (
    WorkspaceCreate,
    WorkspaceListItemResponse,
    WorkspaceResponse,
)
from app.services import workspaces as workspace_service

router = APIRouter(prefix="/workspaces", tags=["workspaces"])
DatabaseSession = Annotated[Session, Depends(get_db_session)]

AUTHENTICATION_RESPONSES = {401: {"model": ErrorResponse}}
WORKSPACE_ACCESS_RESPONSES = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
}
WORKSPACE_ADMIN_WRITE_RESPONSES = {
    **WORKSPACE_ACCESS_RESPONSES,
    409: {"model": ErrorResponse},
}


@router.post(
    "",
    response_model=WorkspaceResponse,
    status_code=status.HTTP_201_CREATED,
    responses={**AUTHENTICATION_RESPONSES, 409: {"model": ErrorResponse}},
)
def create_workspace(
    payload: WorkspaceCreate,
    session: DatabaseSession,
    current_user: CurrentUser,
) -> WorkspaceResponse:
    workspace = workspace_service.create_workspace(session, payload, current_user.id)
    return WorkspaceResponse.model_validate(workspace)


@router.get(
    "",
    response_model=list[WorkspaceListItemResponse],
    responses=AUTHENTICATION_RESPONSES,
)
def list_workspaces(
    session: DatabaseSession,
    current_user: CurrentUser,
) -> list[WorkspaceListItemResponse]:
    return workspace_service.list_user_workspaces(session, current_user.id)


@router.get(
    "/{workspace_id}",
    response_model=WorkspaceResponse,
    responses=WORKSPACE_ACCESS_RESPONSES,
)
def get_workspace(
    workspace_id: UUID,
    session: DatabaseSession,
    _membership: ActiveWorkspaceMembership,
) -> WorkspaceResponse:
    workspace = workspace_service.get_workspace(session, workspace_id)
    return WorkspaceResponse.model_validate(workspace)


@router.get(
    "/{workspace_id}/members",
    response_model=list[WorkspaceMemberResponse],
    responses=WORKSPACE_ACCESS_RESPONSES,
)
def list_workspace_members(
    workspace_id: UUID,
    session: DatabaseSession,
    _administrator: SystemAdministratorMembership,
) -> list[WorkspaceMemberResponse]:
    return workspace_service.list_workspace_members(session, workspace_id)


@router.post(
    "/{workspace_id}/members",
    response_model=MembershipResponse,
    status_code=status.HTTP_201_CREATED,
    responses=WORKSPACE_ADMIN_WRITE_RESPONSES,
)
def create_membership(
    workspace_id: UUID,
    payload: MembershipCreate,
    session: DatabaseSession,
    _administrator: SystemAdministratorMembership,
) -> MembershipResponse:
    membership = workspace_service.create_membership(session, workspace_id, payload)
    return MembershipResponse.model_validate(membership)


@router.patch(
    "/{workspace_id}/members/{membership_id}",
    response_model=MembershipResponse,
    responses=WORKSPACE_ACCESS_RESPONSES,
)
def update_membership(
    workspace_id: UUID,
    membership_id: UUID,
    payload: MembershipUpdate,
    session: DatabaseSession,
    _administrator: SystemAdministratorMembership,
) -> MembershipResponse:
    membership = workspace_service.update_membership(
        session,
        workspace_id,
        membership_id,
        payload,
    )
    return MembershipResponse.model_validate(membership)
