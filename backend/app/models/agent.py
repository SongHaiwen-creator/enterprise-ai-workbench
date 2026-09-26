from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import AgentStatus, StringEnumType


class Agent(Base):
    __tablename__ = "agents"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'active', 'disabled')", name="status_values"),
        CheckConstraint("name ~ '[^[:space:]]'", name="name_not_empty"),
        CheckConstraint("system_prompt ~ '[^[:space:]]'", name="system_prompt_not_empty"),
        Index("ix_agents_workspace_id", "workspace_id"),
        Index("ix_agents_created_by", "created_by"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[AgentStatus] = mapped_column(
        StringEnumType(AgentStatus),
        nullable=False,
        default=AgentStatus.DRAFT,
        server_default=AgentStatus.DRAFT.value,
    )
    created_by: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
