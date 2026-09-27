from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import StringEnumType, ToolRisk, ToolStatus


class Tool(Base):
    __tablename__ = "tools"
    __table_args__ = (
        UniqueConstraint("workspace_id", "tool_key", name="uq_tools_workspace_tool_key"),
        UniqueConstraint("id", "workspace_id", name="uq_tools_id_workspace_id"),
        CheckConstraint("tool_key ~ '^[a-z][a-z0-9_]{0,63}$'", name="tool_key_format"),
        CheckConstraint("name ~ '[^[:space:]]'", name="name_not_empty"),
        CheckConstraint("description ~ '[^[:space:]]'", name="description_not_empty"),
        CheckConstraint(
            "risk_level IN ('low', 'medium', 'high')", name="risk_level_values"
        ),
        CheckConstraint("status IN ('active', 'disabled')", name="status_values"),
        Index("ix_tools_workspace_id", "workspace_id"),
        Index("ix_tools_created_by", "created_by"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False,
    )
    tool_key: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    risk_level: Mapped[ToolRisk] = mapped_column(
        StringEnumType(ToolRisk, length=16), nullable=False
    )
    status: Mapped[ToolStatus] = mapped_column(
        StringEnumType(ToolStatus), nullable=False,
        default=ToolStatus.DISABLED, server_default=ToolStatus.DISABLED.value,
    )
    created_by: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now(),
    )
