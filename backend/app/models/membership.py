from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import MembershipRole, MembershipStatus, StringEnumType

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.workspace import Workspace


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "workspace_id", name="uq_memberships_user_workspace"),
        CheckConstraint(
            "role IN ('employee', 'knowledge_admin', 'agent_admin', 'system_admin')",
            name="role_values",
        ),
        CheckConstraint(
            "status IN ('active', 'invited', 'disabled')",
            name="status_values",
        ),
        Index("ix_memberships_workspace_id", "workspace_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        nullable=False,
    )
    role: Mapped[MembershipRole] = mapped_column(
        StringEnumType(MembershipRole),
        nullable=False,
        default=MembershipRole.EMPLOYEE,
        server_default=MembershipRole.EMPLOYEE.value,
    )
    status: Mapped[MembershipStatus] = mapped_column(
        StringEnumType(MembershipStatus),
        nullable=False,
        default=MembershipStatus.INVITED,
        server_default=MembershipStatus.INVITED.value,
    )
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="memberships")
    workspace: Mapped[Workspace] = relationship(back_populates="memberships")
