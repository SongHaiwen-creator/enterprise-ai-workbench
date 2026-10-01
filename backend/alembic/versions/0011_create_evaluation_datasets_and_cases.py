"""Create Workspace-owned evaluation definitions only.

Revision ID: 0011
Revises: 0010
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=nullable)


def _common(table: str) -> list:
    return [
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        _uuid("workspace_id"),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        _uuid("created_by"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{table}")),
        sa.UniqueConstraint("id", "workspace_id", name=f"uq_{table}_id_workspace_id"),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f(f"fk_{table}_workspace_id_workspaces"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by", "workspace_id"],
            ["memberships.user_id", "memberships.workspace_id"],
            name=f"fk_{table}_creator_membership",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'disabled')", name=op.f(f"ck_{table}_status_values")
        ),
        sa.CheckConstraint(
            "name = btrim(name) AND length(name) BETWEEN 1 AND 255",
            name=op.f(f"ck_{table}_name_valid"),
        ),
        sa.CheckConstraint(
            "description IS NULL OR length(description) <= 5000",
            name=op.f(f"ck_{table}_description_length"),
        ),
    ]


def upgrade() -> None:
    op.create_table("evaluation_datasets", *_common("evaluation_datasets"))
    op.create_table(
        "evaluation_cases",
        *_common("evaluation_cases"),
        _uuid("dataset_id"),
        sa.Column("case_type", sa.String(32), nullable=False),
        sa.Column("test_input", sa.Text(), nullable=False),
        sa.Column("expected_behavior", postgresql.JSONB(), nullable=False),
        sa.Column("schema_version", sa.SmallInteger(), nullable=False, server_default="1"),
        _uuid("agent_id", True),
        _uuid("knowledge_base_id", True),
        _uuid("tool_id", True),
        *(
            sa.ForeignKeyConstraint(
                [column, "workspace_id"],
                [f"{table}.id", f"{table}.workspace_id"],
                name=f"fk_evaluation_cases_{column}_workspace",
                ondelete="RESTRICT",
            )
            for column, table in (
                ("dataset_id", "evaluation_datasets"),
                ("agent_id", "agents"),
                ("knowledge_base_id", "knowledge_bases"),
                ("tool_id", "tools"),
            )
        ),
        sa.CheckConstraint(
            "case_type IN ('knowledge_qa', 'tool_calling', "
            "'permission_boundary', 'refusal_behavior')",
            name=op.f("ck_evaluation_cases_case_type_values"),
        ),
        sa.CheckConstraint(
            "test_input = btrim(test_input) AND length(test_input) BETWEEN 1 AND 2000",
            name=op.f("ck_evaluation_cases_input_valid"),
        ),
        sa.CheckConstraint(
            "schema_version = 1", name=op.f("ck_evaluation_cases_schema_version_valid")
        ),
        sa.CheckConstraint(
            "jsonb_typeof(expected_behavior) = 'object' AND expected_behavior <> '{}'",
            name=op.f("ck_evaluation_cases_expectation_object"),
        ),
    )
    for table, columns in (
        ("evaluation_datasets", ["workspace_id", "created_at", "id"]),
        ("evaluation_cases", ["workspace_id", "dataset_id", "created_at", "id"]),
    ):
        suffix = (
            "workspace_created" if table == "evaluation_datasets" else "workspace_dataset_created"
        )
        op.create_index(f"ix_{table}_{suffix}", table, columns)
        op.create_index(f"ix_{table}_created_by", table, ["created_by"])
    for column in ("agent_id", "knowledge_base_id", "tool_id"):
        op.create_index(f"ix_evaluation_cases_{column}", "evaluation_cases", [column])


def downgrade() -> None:
    op.drop_table("evaluation_cases")
    op.drop_table("evaluation_datasets")
