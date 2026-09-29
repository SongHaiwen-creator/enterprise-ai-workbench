from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CHAR,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import (
    ApprovalDecisionStatus,
    ApprovalExecutionFailure,
    ApprovalExecutionStatus,
    ApprovalInvalidationReason,
    StringEnumType,
)


class Approval(Base):
    __tablename__ = "approvals"
    __table_args__ = (
        CheckConstraint(
            "decision_status IN ('pending', 'approved', 'rejected', 'cancelled', "
            "'expired', 'invalidated')",
            name="decision_status_values",
        ),
        CheckConstraint(
            "execution_status IN ('not_started', 'succeeded', 'failed')",
            name="execution_status_values",
        ),
        CheckConstraint(
            "execution_failure_category IS NULL "
            "OR execution_failure_category IN ('adapter_error')",
            name="failure_category_values",
        ),
        CheckConstraint(
            "invalidation_reason IS NULL OR invalidation_reason IN "
            "('requester_ineligible', 'capability_unavailable', 'configuration_drift')",
            name="invalidation_reason_values",
        ),
        CheckConstraint(
            "action_type IN ('it_access_request.create')", name="action_type_values"
        ),
        CheckConstraint(
            "jsonb_typeof(canonical_arguments) = 'object'",
            name="canonical_arguments_object",
        ),
        CheckConstraint(
            "jsonb_typeof(capability_snapshot) = 'object'",
            name="capability_snapshot_object",
        ),
        CheckConstraint(
            "jsonb_typeof(policy_snapshot) = 'object'", name="policy_snapshot_object"
        ),
        CheckConstraint(
            "canonical_arguments_sha256 ~ '^[0-9a-f]{64}$'",
            name="arguments_sha256_format",
        ),
        CheckConstraint(
            "snapshot_sha256 ~ '^[0-9a-f]{64}$'", name="snapshot_sha256_format"
        ),
        CheckConstraint(
            "decision_note IS NULL OR char_length(decision_note) BETWEEN 1 AND 1000",
            name="decision_note_length",
        ),
        CheckConstraint(
            "decision_note IS NULL OR decision_status IN ('approved', 'rejected')",
            name="decision_note_decided_only",
        ),
        CheckConstraint(
            "(decision_status = 'approved' "
            "AND execution_status IN ('succeeded', 'failed')) "
            "OR (decision_status <> 'approved' AND execution_status = 'not_started')",
            name="status_pair_legal",
        ),
        CheckConstraint(
            "(decision_status = 'pending') = (decided_at IS NULL)",
            name="decided_at_presence",
        ),
        CheckConstraint(
            "(decision_status IN ('approved', 'rejected', 'cancelled')) "
            "= (decided_by IS NOT NULL)",
            name="decided_by_presence",
        ),
        CheckConstraint(
            "decision_status NOT IN ('approved', 'rejected') "
            "OR decided_by <> requester_id",
            name="no_self_decision",
        ),
        CheckConstraint(
            "decision_status <> 'cancelled' OR decided_by = requester_id",
            name="cancel_by_requester",
        ),
        CheckConstraint(
            "(execution_status = 'not_started') = (executed_at IS NULL)",
            name="executed_at_presence",
        ),
        CheckConstraint(
            "(execution_status = 'failed') = (execution_failure_category IS NOT NULL)",
            name="failure_category_presence",
        ),
        CheckConstraint(
            "(decision_status = 'invalidated') = (invalidation_reason IS NOT NULL)",
            name="invalidation_reason_presence",
        ),
        CheckConstraint(
            "(decision_status = 'invalidated') "
            "= (invalidation_triggered_by IS NOT NULL)",
            name="invalidation_trigger_presence",
        ),
        CheckConstraint(
            "decision_status <> 'invalidated' "
            "OR invalidation_triggered_by <> requester_id",
            name="invalidation_not_requester",
        ),
        CheckConstraint(
            "decision_status <> 'expired' OR decided_at = expires_at",
            name="expired_decided_at",
        ),
        CheckConstraint("expires_at > created_at", name="expires_after_created"),
        ForeignKeyConstraint(
            ["requester_id", "workspace_id"],
            ["memberships.user_id", "memberships.workspace_id"],
            name="fk_approvals_requester_membership",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["agent_id", "workspace_id"],
            ["agents.id", "agents.workspace_id"],
            name="fk_approvals_agent_workspace",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tool_id", "workspace_id"],
            ["tools.id", "tools.workspace_id"],
            name="fk_approvals_tool_workspace",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["decided_by", "workspace_id"],
            ["memberships.user_id", "memberships.workspace_id"],
            name="fk_approvals_decider_membership",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["invalidation_triggered_by", "workspace_id"],
            ["memberships.user_id", "memberships.workspace_id"],
            name="fk_approvals_invalidation_trigger_membership",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("id", "workspace_id", name="uq_approvals_id_workspace_id"),
        Index(
            "uq_approvals_pending_dedupe",
            "workspace_id",
            "requester_id",
            "snapshot_sha256",
            unique=True,
            postgresql_where=text("decision_status = 'pending'"),
        ),
        Index(
            "ix_approvals_ws_decision_created",
            "workspace_id",
            "decision_status",
            "created_at",
        ),
        Index(
            "ix_approvals_ws_requester_created",
            "workspace_id",
            "requester_id",
            "created_at",
        ),
        Index("ix_approvals_agent_id", "agent_id"),
        Index("ix_approvals_tool_id", "tool_id"),
        Index("ix_approvals_decided_by", "decided_by"),
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
    requester_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    agent_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    tool_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    canonical_arguments: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    canonical_arguments_sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    capability_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    policy_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    snapshot_sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    decision_status: Mapped[ApprovalDecisionStatus] = mapped_column(
        StringEnumType(ApprovalDecisionStatus, length=16),
        nullable=False,
        default=ApprovalDecisionStatus.PENDING,
        server_default=ApprovalDecisionStatus.PENDING.value,
    )
    decided_by: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    invalidation_reason: Mapped[ApprovalInvalidationReason | None] = mapped_column(
        StringEnumType(ApprovalInvalidationReason), nullable=True
    )
    invalidation_triggered_by: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True), nullable=True
    )
    execution_status: Mapped[ApprovalExecutionStatus] = mapped_column(
        StringEnumType(ApprovalExecutionStatus, length=16),
        nullable=False,
        default=ApprovalExecutionStatus.NOT_STARTED,
        server_default=ApprovalExecutionStatus.NOT_STARTED.value,
    )
    executed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    execution_failure_category: Mapped[ApprovalExecutionFailure | None] = mapped_column(
        StringEnumType(ApprovalExecutionFailure), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class MockITAccessRequest(Base):
    """Record in the local Mock IT access system; never a Workbench permission."""

    __tablename__ = "mock_it_access_requests"
    __table_args__ = (
        CheckConstraint("reference ~ '^ITAR-[0-9A-F]{12}$'", name="reference_format"),
        CheckConstraint(
            "system IN ('production_database', 'analytics_warehouse', 'source_control')",
            name="system_values",
        ),
        CheckConstraint(
            "access_level IN ('read_only', 'standard')", name="access_level_values"
        ),
        CheckConstraint(
            "system <> 'production_database' OR access_level = 'read_only'",
            name="production_read_only",
        ),
        CheckConstraint("duration_days BETWEEN 1 AND 90", name="duration_days_range"),
        CheckConstraint("status IN ('recorded')", name="status_values"),
        ForeignKeyConstraint(
            ["approval_id", "workspace_id"],
            ["approvals.id", "approvals.workspace_id"],
            name="fk_mock_it_access_requests_approval_workspace",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["requester_id", "workspace_id"],
            ["memberships.user_id", "memberships.workspace_id"],
            name="fk_mock_it_access_requests_requester_membership",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("approval_id", name="uq_mock_it_access_requests_approval_id"),
        UniqueConstraint("reference", name="uq_mock_it_access_requests_reference"),
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
    approval_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    requester_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    reference: Mapped[str] = mapped_column(String(32), nullable=False)
    system: Mapped[str] = mapped_column(String(32), nullable=False)
    access_level: Mapped[str] = mapped_column(String(16), nullable=False)
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
