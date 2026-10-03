from typing import Annotated
from uuid import UUID

from fastapi import Depends
from sqlalchemy import select

from app.api.dependencies.auth import CurrentUser, DatabaseSession
from app.models import Membership, Workspace
from app.models.enums import MembershipRole, WorkspaceStatus
from app.services.authorization_policy import active_membership, agent_administrator
from app.services.exceptions import (
    WORKSPACE_ACCESS_DENIED,
    ForbiddenError,
    NotFoundError,
)

SYSTEM_ADMIN_REQUIRED = "System administrator role required"
KNOWLEDGE_ADMIN_REQUIRED = "Knowledge administrator role required"
AGENT_ADMIN_REQUIRED = "Agent administrator role required"


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
    if membership is None or not active_membership(membership.status.value):
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


def require_knowledge_administrator(
    membership: ActiveWorkspaceMembership,
) -> Membership:
    allowed_roles = {
        MembershipRole.KNOWLEDGE_ADMIN,
        MembershipRole.SYSTEM_ADMIN,
    }
    if membership.role not in allowed_roles:
        raise ForbiddenError(KNOWLEDGE_ADMIN_REQUIRED)
    return membership


KnowledgeAdministratorMembership = Annotated[
    Membership,
    Depends(require_knowledge_administrator),
]


def require_agent_administrator(
    membership: ActiveWorkspaceMembership,
) -> Membership:
    if not agent_administrator(membership.role.value):
        raise ForbiddenError(AGENT_ADMIN_REQUIRED)
    return membership


AgentAdministratorMembership = Annotated[
    Membership,
    Depends(require_agent_administrator),
]
