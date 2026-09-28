"""Create human Approvals and the local Mock IT access request records.

Revision ID: 0009
Revises: 0008
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APPROVAL_CHECKS = {
    "decision_status_values": (
        "decision_status IN ('pending', 'approved', 'rejected', 'cancelled', "
        "'expired', 'invalidated')"
    ),
    "execution_status_values": (
        "execution_status IN ('not_started', 'succeeded', 'failed')"
    ),
    "failure_category_values": (
        "execution_failure_category IS NULL "
        "OR execution_failure_category IN ('adapter_error')"
    ),
    "invalidation_reason_values": (
        "invalidation_reason IS NULL OR invalidation_reason IN "
        "('requester_ineligible', 'capability_unavailable', 'configuration_drift')"
    ),
    "action_type_values": "action_type IN ('it_access_request.create')",
    "canonical_arguments_object": "jsonb_typeof(canonical_arguments) = 'object'",
    "capability_snapshot_object": "jsonb_typeof(capability_snapshot) = 'object'",
    "policy_snapshot_object": "jsonb_typeof(policy_snapshot) = 'object'",
    "arguments_sha256_format": "canonical_arguments_sha256 ~ '^[0-9a-f]{64}$'",
    "snapshot_sha256_format": "snapshot_sha256 ~ '^[0-9a-f]{64}$'",
    "decision_note_length": (
        "decision_note IS NULL OR char_length(decision_note) BETWEEN 1 AND 1000"
    ),
    "decision_note_decided_only": (
        "decision_note IS NULL OR decision_status IN ('approved', 'rejected')"
    ),
    "status_pair_legal": (
        "(decision_status = 'approved' "
        "AND execution_status IN ('succeeded', 'failed')) "
        "OR (decision_status <> 'approved' AND execution_status = 'not_started')"
    ),
    "decided_at_presence": "(decision_status = 'pending') = (decided_at IS NULL)",
    "decided_by_presence": (
        "(decision_status IN ('approved', 'rejected', 'cancelled')) "
        "= (decided_by IS NOT NULL)"
    ),
    "no_self_decision": (
        "decision_status NOT IN ('approved', 'rejected') "
        "OR decided_by <> requester_id"
    ),
    "cancel_by_requester": (
        "decision_status <> 'cancelled' OR decided_by = requester_id"
    ),
    "executed_at_presence": (
        "(execution_status = 'not_started') = (executed_at IS NULL)"
    ),
    "failure_category_presence": (
        "(execution_status = 'failed') = (execution_failure_category IS NOT NULL)"
    ),
    "invalidation_reason_presence": (
        "(decision_status = 'invalidated') = (invalidation_reason IS NOT NULL)"
    ),
    "invalidation_trigger_presence": (
        "(decision_status = 'invalidated') "
        "= (invalidation_triggered_by IS NOT NULL)"
    ),
    "invalidation_not_requester": (
        "decision_status <> 'invalidated' "
        "OR invalidation_triggered_by <> requester_id"
    ),
    "expired_decided_at": "decision_status <> 'expired' OR decided_at = expires_at",
    "expires_after_created": "expires_at > created_at",
}

MOCK_CHECKS = {
    "reference_format": "reference ~ '^ITAR-[0-9A-F]{12}$'",
    "system_values": (
        "system IN ('production_database', 'analytics_warehouse', 'source_control')"
    ),
    "access_level_values": "access_level IN ('read_only', 'standard')",
    "production_read_only": (
        "system <> 'production_database' OR access_level = 'read_only'"
    ),
    "duration_days_range": "duration_days BETWEEN 1 AND 90",
    "status_values": "status IN ('recorded')",
}


def _uuid(name: str, *, nullable: bool = False) -> sa.Column:
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=nullable)


def _timestamp(name: str, *, nullable: bool = False, default: bool = False) -> sa.Column:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        server_default=sa.text("CURRENT_TIMESTAMP") if default else None,
        nullable=nullable,
    )


def _membership_fk(column: str, name: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [column, "workspace_id"],
        ["memberships.user_id", "memberships.workspace_id"],
        name=name,
        ondelete="RESTRICT",
    )


def upgrade() -> None:
    op.create_table(
        "approvals",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"), nullable=False,
        ),
        _uuid("workspace_id"),
        _uuid("requester_id"),
        _uuid("agent_id"),
        _uuid("tool_id"),
        sa.Column("action_type", sa.String(length=64), nullable=False),
        sa.Column(
            "canonical_arguments", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("canonical_arguments_sha256", sa.CHAR(length=64), nullable=False),
        sa.Column(
            "capability_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "policy_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("snapshot_sha256", sa.CHAR(length=64), nullable=False),
        sa.Column(
            "decision_status", sa.String(length=16),
            server_default="pending", nullable=False,
        ),
        _uuid("decided_by", nullable=True),
        _timestamp("decided_at", nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("invalidation_reason", sa.String(length=32), nullable=True),
        _uuid("invalidation_triggered_by", nullable=True),
        sa.Column(
            "execution_status", sa.String(length=16),
            server_default="not_started", nullable=False,
        ),
        _timestamp("executed_at", nullable=True),
        sa.Column("execution_failure_category", sa.String(length=32), nullable=True),
        _timestamp("expires_at"),
        _timestamp("created_at", default=True),
        _timestamp("updated_at", default=True),
        *(
            sa.CheckConstraint(condition, name=op.f(f"ck_approvals_{name}"))
            for name, condition in APPROVAL_CHECKS.items()
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"],
            name=op.f("fk_approvals_workspace_id_workspaces"), ondelete="RESTRICT",
        ),
        _membership_fk("requester_id", "fk_approvals_requester_membership"),
        sa.ForeignKeyConstraint(
            ["agent_id", "workspace_id"], ["agents.id", "agents.workspace_id"],
            name="fk_approvals_agent_workspace", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tool_id", "workspace_id"], ["tools.id", "tools.workspace_id"],
            name="fk_approvals_tool_workspace", ondelete="RESTRICT",
        ),
        _membership_fk("decided_by", "fk_approvals_decider_membership"),
        _membership_fk(
            "invalidation_triggered_by", "fk_approvals_invalidation_trigger_membership"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_approvals")),
        sa.UniqueConstraint("id", "workspace_id", name="uq_approvals_id_workspace_id"),
    )
    op.create_index(
        "uq_approvals_pending_dedupe",
        "approvals",
        ["workspace_id", "requester_id", "snapshot_sha256"],
        unique=True,
        postgresql_where=sa.text("decision_status = 'pending'"),
    )
    op.create_index(
        "ix_approvals_ws_decision_created",
        "approvals",
        ["workspace_id", "decision_status", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_approvals_ws_requester_created",
        "approvals",
        ["workspace_id", "requester_id", "created_at"],
        unique=False,
    )
    op.create_index("ix_approvals_agent_id", "approvals", ["agent_id"], unique=False)
    op.create_index("ix_approvals_tool_id", "approvals", ["tool_id"], unique=False)
    op.create_index("ix_approvals_decided_by", "approvals", ["decided_by"], unique=False)

    op.create_table(
        "mock_it_access_requests",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"), nullable=False,
        ),
        _uuid("workspace_id"),
        _uuid("approval_id"),
        _uuid("requester_id"),
        sa.Column("reference", sa.String(length=32), nullable=False),
        sa.Column("system", sa.String(length=32), nullable=False),
        sa.Column("access_level", sa.String(length=16), nullable=False),
        sa.Column("duration_days", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        _timestamp("created_at", default=True),
        *(
            sa.CheckConstraint(
                condition, name=op.f(f"ck_mock_it_access_requests_{name}")
            )
            for name, condition in MOCK_CHECKS.items()
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"],
            name=op.f("fk_mock_it_access_requests_workspace_id_workspaces"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["approval_id", "workspace_id"], ["approvals.id", "approvals.workspace_id"],
            name="fk_mock_it_access_requests_approval_workspace", ondelete="RESTRICT",
        ),
        _membership_fk(
            "requester_id", "fk_mock_it_access_requests_requester_membership"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mock_it_access_requests")),
        sa.UniqueConstraint(
            "approval_id", name="uq_mock_it_access_requests_approval_id"
        ),
        sa.UniqueConstraint("reference", name="uq_mock_it_access_requests_reference"),
    )


def downgrade() -> None:
    op.drop_table("mock_it_access_requests")
    op.drop_index("ix_approvals_decided_by", table_name="approvals")
    op.drop_index("ix_approvals_tool_id", table_name="approvals")
    op.drop_index("ix_approvals_agent_id", table_name="approvals")
    op.drop_index("ix_approvals_ws_requester_created", table_name="approvals")
    op.drop_index("ix_approvals_ws_decision_created", table_name="approvals")
    op.drop_index("uq_approvals_pending_dedupe", table_name="approvals")
    op.drop_table("approvals")
