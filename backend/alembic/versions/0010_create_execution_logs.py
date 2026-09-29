"""Create the Workspace-owned, append-only execution log.

Revision ID: 0010
Revises: 0009
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EXECUTION_LOG_CHECKS = {
    "operation_values": (
        "operation IN ('agent_route', 'knowledge_answer', 'approval_decision', "
        "'approval_cancel')"
    ),
    "routing_intent_values": (
        "routing_intent IS NULL OR routing_intent IN "
        "('knowledge_qa', 'tool_request', 'unsupported')"
    ),
    "status_values": "status IN ('succeeded', 'failed')",
    "outcome_values": (
        "outcome IS NULL OR outcome IN ('knowledge_answered', "
        "'knowledge_unsupported', 'tool_executed', 'tool_approval_required', "
        "'tool_not_executed', 'unsupported_request', "
        "'approved_execution_succeeded', 'approved_execution_failed', 'rejected', "
        "'invalidated', 'expired', 'cancelled')"
    ),
    "error_category_values": (
        "error_category IS NULL OR error_category IN ('agent_not_found', "
        "'agent_inactive', 'knowledge_base_required', 'knowledge_base_not_found', "
        "'knowledge_base_inactive', 'input_too_large', 'provider_unavailable', "
        "'provider_error', 'tool_configuration_error', 'tool_unavailable', "
        "'tool_execution_failed', 'access_denied', 'approval_not_found', "
        "'approval_not_pending', 'approval_expired', 'approval_invalidated', "
        "'approval_busy', 'approval_execution_failed', 'internal_error')"
    ),
    "http_status_range": "http_status BETWEEN 100 AND 599",
    "latency_non_negative": "latency_ms >= 0",
    "status_error_consistency": "(status = 'failed') = (error_category IS NOT NULL)",
    "status_http_consistency": (
        "(status = 'succeeded') = (http_status BETWEEN 200 AND 299)"
    ),
    "routing_intent_agent_route_only": (
        "routing_intent IS NULL OR operation = 'agent_route'"
    ),
    "tool_reference_pair": "(tool_id IS NULL) = (tool_key IS NULL)",
    "details_object": "jsonb_typeof(details) = 'object'",
}


def _uuid(name: str, *, nullable: bool = False) -> sa.Column:
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=nullable)


def _same_workspace_fk(
    column: str, table: str, key: str, name: str
) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [column, "workspace_id"],
        [f"{table}.{key}", f"{table}.workspace_id"],
        name=name,
        ondelete="RESTRICT",
    )


def upgrade() -> None:
    op.create_table(
        "execution_logs",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"), nullable=False,
        ),
        _uuid("workspace_id"),
        _uuid("user_id"),
        sa.Column("operation", sa.String(length=32), nullable=False),
        sa.Column("routing_intent", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("outcome", sa.String(length=40), nullable=True),
        sa.Column("error_category", sa.String(length=40), nullable=True),
        sa.Column("http_status", sa.SmallInteger(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        _uuid("agent_id", nullable=True),
        _uuid("tool_id", nullable=True),
        sa.Column("tool_key", sa.String(length=64), nullable=True),
        _uuid("approval_id", nullable=True),
        _uuid("knowledge_base_id", nullable=True),
        sa.Column(
            "details", postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"), nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False,
        ),
        *(
            sa.CheckConstraint(condition, name=op.f(f"ck_execution_logs_{name}"))
            for name, condition in EXECUTION_LOG_CHECKS.items()
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"],
            name=op.f("fk_execution_logs_workspace_id_workspaces"), ondelete="RESTRICT",
        ),
        _same_workspace_fk(
            "user_id", "memberships", "user_id", "fk_execution_logs_user_membership"
        ),
        _same_workspace_fk("agent_id", "agents", "id", "fk_execution_logs_agent_workspace"),
        _same_workspace_fk("tool_id", "tools", "id", "fk_execution_logs_tool_workspace"),
        _same_workspace_fk(
            "approval_id", "approvals", "id", "fk_execution_logs_approval_workspace"
        ),
        _same_workspace_fk(
            "knowledge_base_id", "knowledge_bases", "id",
            "fk_execution_logs_knowledge_base_workspace",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_execution_logs")),
    )
    op.create_index(
        "ix_execution_logs_workspace_created",
        "execution_logs",
        ["workspace_id", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_execution_logs_workspace_agent_created",
        "execution_logs",
        ["workspace_id", "agent_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_execution_logs_workspace_agent_created", table_name="execution_logs")
    op.drop_index("ix_execution_logs_workspace_created", table_name="execution_logs")
    op.drop_table("execution_logs")
