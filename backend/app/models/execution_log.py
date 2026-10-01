from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import (
    ExecutionLogErrorCategory,
    ExecutionLogOperation,
    ExecutionLogOutcome,
    ExecutionLogStatus,
    StringEnumType,
)


def _values(enum_type: type[StrEnum]) -> str:
    return ", ".join(f"'{member.value}'" for member in enum_type)


class ExecutionLog(Base):
    """Append-only, allow-listed record of one handled AI operation (Feature 014)."""

    __tablename__ = "execution_logs"
    __table_args__ = (
        CheckConstraint(
            f"operation IN ({_values(ExecutionLogOperation)})", name="operation_values"
        ),
        CheckConstraint(
            "routing_intent IS NULL OR routing_intent IN "
            "('knowledge_qa', 'tool_request', 'unsupported')",
            name="routing_intent_values",
        ),
        CheckConstraint(
            f"status IN ({_values(ExecutionLogStatus)})", name="status_values"
        ),
        CheckConstraint(
            f"outcome IS NULL OR outcome IN ({_values(ExecutionLogOutcome)})",
            name="outcome_values",
        ),
        CheckConstraint(
            "error_category IS NULL OR error_category IN "
            f"({_values(ExecutionLogErrorCategory)})",
            name="error_category_values",
        ),
        CheckConstraint("http_status BETWEEN 100 AND 599", name="http_status_range"),
        CheckConstraint("latency_ms >= 0", name="latency_non_negative"),
        CheckConstraint(
            "(status = 'failed') = (error_category IS NOT NULL)",
            name="status_error_consistency",
        ),
        CheckConstraint(
            "(status = 'succeeded') = (http_status BETWEEN 200 AND 299)",
            name="status_http_consistency",
        ),
        CheckConstraint(
            "routing_intent IS NULL OR operation = 'agent_route'",
            name="routing_intent_agent_route_only",
        ),
        CheckConstraint(
            "(tool_id IS NULL) = (tool_key IS NULL)", name="tool_reference_pair"
        ),
        CheckConstraint("jsonb_typeof(details) = 'object'", name="details_object"),
        ForeignKeyConstraint(
            ["user_id", "workspace_id"],
            ["memberships.user_id", "memberships.workspace_id"],
            name="fk_execution_logs_user_membership",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["agent_id", "workspace_id"],
            ["agents.id", "agents.workspace_id"],
            name="fk_execution_logs_agent_workspace",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tool_id", "workspace_id"],
            ["tools.id", "tools.workspace_id"],
            name="fk_execution_logs_tool_workspace",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["approval_id", "workspace_id"],
            ["approvals.id", "approvals.workspace_id"],
            name="fk_execution_logs_approval_workspace",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["knowledge_base_id", "workspace_id"],
            ["knowledge_bases.id", "knowledge_bases.workspace_id"],
            name="fk_execution_logs_knowledge_base_workspace",
            ondelete="RESTRICT",
        ),
        # Ascending btree indexes serve the newest-first list by backward scan.
        Index("ix_execution_logs_workspace_created", "workspace_id", "created_at", "id"),
        Index(
            "ix_execution_logs_workspace_agent_created",
            "workspace_id",
            "agent_id",
            "created_at",
        ),
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
    user_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    operation: Mapped[ExecutionLogOperation] = mapped_column(
        StringEnumType(ExecutionLogOperation), nullable=False
    )
    routing_intent: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[ExecutionLogStatus] = mapped_column(
        StringEnumType(ExecutionLogStatus, length=16), nullable=False
    )
    outcome: Mapped[ExecutionLogOutcome | None] = mapped_column(
        StringEnumType(ExecutionLogOutcome, length=40), nullable=True
    )
    error_category: Mapped[ExecutionLogErrorCategory | None] = mapped_column(
        StringEnumType(ExecutionLogErrorCategory, length=40), nullable=True
    )
    http_status: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    agent_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=True
    )
    tool_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=True
    )
    tool_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approval_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=True
    )
    knowledge_base_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=True
    )
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
