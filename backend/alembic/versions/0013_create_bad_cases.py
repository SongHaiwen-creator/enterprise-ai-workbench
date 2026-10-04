"""Create manual Bad Case records and atomic history.

Revision ID: 0013
Revises: 0012
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def uuid(name):
    return sa.Column(name, pg.UUID(), nullable=False)


def common():
    return [
        sa.Column("id", pg.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "workspace_id",
            pg.UUID(),
            sa.ForeignKey("workspaces.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    ]


def fk(table, column, target, target_column="id"):
    return sa.ForeignKeyConstraint(
        [column, "workspace_id"],
        [f"{target}.{target_column}", f"{target}.workspace_id"],
        name=f"fk_{table}_{column}_workspace",
        ondelete="RESTRICT",
    )


def check(table, sql, name):
    return sa.CheckConstraint(sql, name=op.f(f"ck_{table}_{name}"))


def upgrade():
    table = "bad_cases"
    op.create_table(
        table,
        *common(),
        uuid("source_run_case_id"),
        uuid("created_by"),
        uuid("updated_by"),
        sa.Column("origin_kind", sa.String(32), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.String(32), nullable=False, server_default="unclassified"),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        *(
            sa.Column(c, sa.Text(), nullable=True)
            for c in ("possible_cause", "handling_note", "resolution_note")
        ),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("id", "workspace_id", name="uq_bad_cases_id_workspace_id"),
        sa.UniqueConstraint("workspace_id", "source_run_case_id", name="uq_bad_cases_source"),
        fk(table, "source_run_case_id", "evaluation_run_cases"),
        fk(table, "created_by", "memberships", "user_id"),
        fk(table, "updated_by", "memberships", "user_id"),
        check(
            table,
            "origin_kind IN ('behavior_failure','execution_error','manual_review')",
            "origin_values",
        ),
        check(
            table,
            "category IN ('unclassified','routing','knowledge','tool_planning',"
            "'permission','refusal','runtime','other')",
            "category_values",
        ),
        check(table, "status IN ('open','investigating','resolved','dismissed')", "status_values"),
        check(table, "revision >= 1", "revision_valid"),
        check(
            table,
            "(status IN ('resolved','dismissed')) = (resolution_note IS NOT NULL)",
            "resolution_valid",
        ),
        *(
            check(table, f"{c}=btrim({c}) AND length({c}) BETWEEN 1 AND {n}", f"{c}_valid")
            for c, n in (("title", 255), ("description", 5000))
        ),
        *(
            check(
                table,
                f"{c} IS NULL OR ({c}=btrim({c}) AND length({c}) BETWEEN 1 AND 5000)",
                f"{c}_valid",
            )
            for c in ("possible_cause", "handling_note", "resolution_note")
        ),
    )
    op.create_index("ix_bad_cases_workspace_created", table, ["workspace_id", "created_at", "id"])
    op.create_index(
        "ix_bad_cases_workspace_status_created",
        table,
        ["workspace_id", "status", "created_at", "id"],
    )
    for c in ("source_run_case_id", "created_by", "updated_by"):
        op.create_index(f"ix_bad_cases_{c}", table, [c])
    table = "bad_case_history"
    op.create_table(
        table,
        *common(),
        uuid("bad_case_id"),
        uuid("actor_id"),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("event", sa.String(16), nullable=False),
        sa.Column("change_reason", sa.String(1000), nullable=True),
        sa.Column("before_values", pg.JSONB(none_as_null=True), nullable=True),
        sa.Column("after_values", pg.JSONB(), nullable=False),
        sa.UniqueConstraint("bad_case_id", "revision", name="uq_bad_case_history_revision"),
        fk(table, "bad_case_id", "bad_cases"),
        fk(table, "actor_id", "memberships", "user_id"),
        check(table, "revision >= 1", "revision_valid"),
        check(
            table,
            "((event='created' AND revision=1 AND before_values IS NULL) OR "
            "(event='updated' AND revision>1 AND jsonb_typeof(before_values)='object' "
            "AND before_values <> '{}')) IS TRUE",
            "event_valid",
        ),
        check(table, "jsonb_typeof(after_values)='object' AND after_values <> '{}'", "after_valid"),
        check(
            table,
            "change_reason IS NULL OR (change_reason=btrim(change_reason) AND "
            "length(change_reason) BETWEEN 1 AND 1000)",
            "reason_valid",
        ),
    )
    op.create_index(
        "ix_bad_case_history_workspace_revision", table, ["workspace_id", "bad_case_id", "revision"]
    )
    op.create_index("ix_bad_case_history_actor_id", table, ["actor_id"])


def downgrade():
    op.drop_table("bad_case_history")
    op.drop_table("bad_cases")
