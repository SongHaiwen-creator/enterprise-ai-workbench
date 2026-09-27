"""Create workspace Tool configurations and Agent allowlist assignments.

Revision ID: 0008
Revises: 0007
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_agents_id_workspace_id", "agents", ["id", "workspace_id"]
    )
    op.create_table(
        "tools",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"), nullable=False,
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tool_key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("risk_level", sa.String(length=16), nullable=False),
        sa.Column(
            "status", sa.String(length=32), server_default="disabled", nullable=False,
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False,
        ),
        sa.CheckConstraint(
            "tool_key ~ '^[a-z][a-z0-9_]{0,63}$'",
            name=op.f("ck_tools_tool_key_format"),
        ),
        sa.CheckConstraint(
            "name ~ '[^[:space:]]'", name=op.f("ck_tools_name_not_empty"),
        ),
        sa.CheckConstraint(
            "description ~ '[^[:space:]]'",
            name=op.f("ck_tools_description_not_empty"),
        ),
        sa.CheckConstraint(
            "risk_level IN ('low', 'medium', 'high')",
            name=op.f("ck_tools_risk_level_values"),
        ),
        sa.CheckConstraint(
            "status IN ('active', 'disabled')",
            name=op.f("ck_tools_status_values"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"],
            name=op.f("fk_tools_created_by_users"), ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"],
            name=op.f("fk_tools_workspace_id_workspaces"), ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tools")),
        sa.UniqueConstraint(
            "workspace_id", "tool_key", name="uq_tools_workspace_tool_key",
        ),
        sa.UniqueConstraint("id", "workspace_id", name="uq_tools_id_workspace_id"),
    )
    op.create_index("ix_tools_workspace_id", "tools", ["workspace_id"], unique=False)
    op.create_index("ix_tools_created_by", "tools", ["created_by"], unique=False)
    op.create_table(
        "agent_tools",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tool_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"],
            name=op.f("fk_agent_tools_workspace_id_workspaces"), ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["agent_id", "workspace_id"], ["agents.id", "agents.workspace_id"],
            name=op.f("fk_agent_tools_agent_id_workspace_id_agents"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tool_id", "workspace_id"], ["tools.id", "tools.workspace_id"],
            name=op.f("fk_agent_tools_tool_id_workspace_id_tools"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("agent_id", "tool_id", name=op.f("pk_agent_tools")),
    )
    op.create_index(
        "ix_agent_tools_workspace_id", "agent_tools", ["workspace_id"], unique=False,
    )
    op.create_index(
        "ix_agent_tools_tool_id", "agent_tools", ["tool_id"], unique=False,
    )


def downgrade() -> None:
    op.drop_table("agent_tools")
    op.drop_table("tools")
    op.drop_constraint("uq_agents_id_workspace_id", "agents", type_="unique")
