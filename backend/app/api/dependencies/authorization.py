from typing import Annotated
from uuid import UUID

from fastapi import Depends
from sqlalchemy import select

from app.api.dependencies.auth import CurrentUser, DatabaseSession
from app.models import Membership, Workspace
from app.models.enums import MembershipRole, MembershipStatus, WorkspaceStatus
from app.services.exceptions import ForbiddenError, NotFoundError

WORKSPACE_ACCESS_DENIED = "Not authorized for this workspace"
SYSTEM_ADMIN_REQUIRED = "System administrator role required"


def get_active_workspace_membership(
    workspace_id: UUID,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> Membership:
    workspace = session.get(Workspace, workspace_id)
    if workspace is None:
        raise NotFoundError("Workspace not found")
    if workspace.status is not WorkspaceStatus.ACTIVE:
        raise ForbiddenError(WORKSPACE_ACCESS_DENIED)

    membership = session.scalar(
        select(Membership).where(
            Membership.workspace_id == workspace_id,
            Membership.user_id == current_user.id,
        )
    )
    if membership is None or membership.status is not MembershipStatus.ACTIVE:
        raise ForbiddenError(WORKSPACE_ACCESS_DENIED)
    return membership


ActiveWorkspaceMembership = Annotated[
    Membership,
    Depends(get_active_workspace_membership),
]


def require_system_administrator(
    membership: ActiveWorkspaceMembership,
) -> Membership:
    if membership.role is not MembershipRole.SYSTEM_ADMIN:
        raise ForbiddenError(SYSTEM_ADMIN_REQUIRED)
    return membership


SystemAdministratorMembership = Annotated[
    Membership,
    Depends(require_system_administrator),
]
