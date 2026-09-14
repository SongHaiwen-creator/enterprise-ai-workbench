from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Membership, User, Workspace
from app.models.enums import MembershipStatus
from app.schemas.membership import (
    MembershipCreate,
    MembershipUpdate,
    WorkspaceMemberResponse,
)
from app.schemas.workspace import WorkspaceCreate
from app.services.exceptions import ConflictError, NotFoundError

WORKSPACE_SLUG_CONSTRAINT = "uq_workspaces_slug"
MEMBERSHIP_UNIQUE_CONSTRAINT = "uq_memberships_user_workspace"
MEMBERSHIP_USER_FOREIGN_KEY = "fk_memberships_user_id_users"
MEMBERSHIP_WORKSPACE_FOREIGN_KEY = "fk_memberships_workspace_id_workspaces"


def _constraint_name(error: IntegrityError) -> str | None:
    diagnostics = getattr(error.orig, "diag", None)
    return getattr(diagnostics, "constraint_name", None)


def get_workspace(session: Session, workspace_id: UUID) -> Workspace:
    workspace = session.get(Workspace, workspace_id)
    if workspace is None:
        raise NotFoundError("Workspace not found")
    return workspace


def create_workspace(session: Session, payload: WorkspaceCreate) -> Workspace:
    workspace = Workspace(name=payload.name, slug=payload.slug)
    session.add(workspace)

    try:
        session.commit()
    except IntegrityError as error:
        constraint_name = _constraint_name(error)
        session.rollback()
        if constraint_name == WORKSPACE_SLUG_CONSTRAINT:
            raise ConflictError("Workspace slug already exists") from error
        raise

    session.refresh(workspace)
    return workspace


def list_workspace_members(
    session: Session,
    workspace_id: UUID,
) -> list[WorkspaceMemberResponse]:
    get_workspace(session, workspace_id)

    statement = (
        select(
            Membership.id,
            Membership.user_id,
            User.email,
            User.name,
            Membership.role,
            Membership.status,
            Membership.joined_at,
        )
        .join(User, User.id == Membership.user_id)
        .where(Membership.workspace_id == workspace_id)
        .order_by(User.name, User.email, Membership.id)
    )
    rows = session.execute(statement).all()

    return [
        WorkspaceMemberResponse(
            id=row.id,
            user_id=row.user_id,
            email=row.email,
            name=row.name,
            role=row.role,
            status=row.status,
            joined_at=row.joined_at,
        )
        for row in rows
    ]


def create_membership(
    session: Session,
    workspace_id: UUID,
    payload: MembershipCreate,
) -> Membership:
    get_workspace(session, workspace_id)
    if session.get(User, payload.user_id) is None:
        raise NotFoundError("User not found")

    membership = Membership(
        user_id=payload.user_id,
        workspace_id=workspace_id,
        role=payload.role,
    )
    session.add(membership)

    try:
        session.commit()
    except IntegrityError as error:
        constraint_name = _constraint_name(error)
        session.rollback()
        if constraint_name == MEMBERSHIP_UNIQUE_CONSTRAINT:
            raise ConflictError("User is already a member of this workspace") from error
        if constraint_name == MEMBERSHIP_USER_FOREIGN_KEY:
            raise NotFoundError("User not found") from error
        if constraint_name == MEMBERSHIP_WORKSPACE_FOREIGN_KEY:
            raise NotFoundError("Workspace not found") from error
        raise

    session.refresh(membership)
    return membership


def update_membership(
    session: Session,
    workspace_id: UUID,
    membership_id: UUID,
    payload: MembershipUpdate,
) -> Membership:
    get_workspace(session, workspace_id)
    membership = session.scalar(
        select(Membership).where(
            Membership.id == membership_id,
            Membership.workspace_id == workspace_id,
        )
    )
    if membership is None:
        raise NotFoundError("Membership not found")

    if payload.role is not None:
        membership.role = payload.role
    if payload.status is not None:
        membership.status = payload.status
        if payload.status is MembershipStatus.ACTIVE and membership.joined_at is None:
            membership.joined_at = datetime.now(UTC)

    session.commit()
    session.refresh(membership)
    return membership
