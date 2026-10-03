"""Create immutable evaluation Run history. Revision 0012 follows 0011."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evaluation_runs",
        sa.Column("dataset_id", sa.UUID(), nullable=False),
        sa.Column("agent_id", sa.UUID(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="running", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_cases", sa.SmallInteger(), nullable=False),
        sa.Column("passed_cases", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("failed_cases", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("error_cases", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("failure_category", sa.String(length=32), nullable=True),
        sa.Column("dataset_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("agent_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("config_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("snapshot_version", sa.SmallInteger(), server_default="1", nullable=False),
        sa.Column(
            "scorer_version",
            sa.String(length=32),
            server_default="evaluation-scorer-v1",
            nullable=False,
        ),
        sa.Column("configuration_sha256", sa.CHAR(length=64), nullable=False),
        sa.Column("provider_egress_acknowledged", sa.Boolean(), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(status='failed') = (failure_category IS NOT NULL)",
            name=op.f("ck_evaluation_runs_failure_valid"),
        ),
        sa.CheckConstraint(
            "(status='running') = (completed_at IS NULL)",
            name=op.f("ck_evaluation_runs_completion_valid"),
        ),
        sa.CheckConstraint(
            "configuration_sha256 ~ '^[0-9a-f]{64}$'", name=op.f("ck_evaluation_runs_hash_valid")
        ),
        sa.CheckConstraint(
            "deadline_at = started_at + interval '120 seconds' AND (completed_at IS"
            " NULL OR completed_at >= started_at)",
            name=op.f("ck_evaluation_runs_time_valid"),
        ),
        sa.CheckConstraint(
            "failure_category IS NULL OR failure_category IN ('provider_configurati"
            "on','provider_failure','provider_contract','input_budget','resource_co"
            "nfiguration','configuration_drift','authorization_revoked','case_timeo"
            "ut','run_timeout','persistence_failure','interrupted','internal_error'"
            ")",
            name=op.f("ck_evaluation_runs_failure_values"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(agent_snapshot)='object' AND agent_snapshot <> '{}'",
            name=op.f("ck_evaluation_runs_agent_snapshot_object"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(config_snapshot)='object' AND config_snapshot <> '{}'",
            name=op.f("ck_evaluation_runs_config_snapshot_object"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(dataset_snapshot)='object' AND dataset_snapshot <> '{}'",
            name=op.f("ck_evaluation_runs_dataset_snapshot_object"),
        ),
        sa.CheckConstraint(
            "snapshot_version=1 AND scorer_version='evaluation-scorer-v1'",
            name=op.f("ck_evaluation_runs_version_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('running','completed','failed')",
            name=op.f("ck_evaluation_runs_status_values"),
        ),
        sa.CheckConstraint(
            "total_cases BETWEEN 1 AND 5 AND passed_cases >= 0 AND failed_cases >= "
            "0 AND error_cases >= 0 AND passed_cases+failed_cases+error_cases <= to"
            "tal_cases AND (status = 'running' OR passed_cases+failed_cases+error_c"
            "ases = total_cases)",
            name=op.f("ck_evaluation_runs_counts_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["agent_id", "workspace_id"],
            ["agents.id", "agents.workspace_id"],
            name="fk_evaluation_runs_agent_id_workspace",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by", "workspace_id"],
            ["memberships.user_id", "memberships.workspace_id"],
            name="fk_evaluation_runs_created_by_workspace",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id", "workspace_id"],
            ["evaluation_datasets.id", "evaluation_datasets.workspace_id"],
            name="fk_evaluation_runs_dataset_id_workspace",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_evaluation_runs_workspace_id_workspaces"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evaluation_runs")),
        sa.UniqueConstraint("id", "workspace_id", name="uq_evaluation_runs_id_workspace_id"),
    )
    op.create_index("ix_evaluation_runs_agent_id", "evaluation_runs", ["agent_id"], unique=False)
    op.create_index(
        "ix_evaluation_runs_created_by", "evaluation_runs", ["created_by"], unique=False
    )
    op.create_index(
        "ix_evaluation_runs_workspace_created",
        "evaluation_runs",
        ["workspace_id", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_evaluation_runs_workspace_dataset_created",
        "evaluation_runs",
        ["workspace_id", "dataset_id", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "uq_evaluation_runs_workspace_running",
        "evaluation_runs",
        ["workspace_id"],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
    )
    op.create_table(
        "evaluation_run_cases",
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("case_id", sa.UUID(), nullable=False),
        sa.Column("ordinal", sa.SmallInteger(), nullable=False),
        sa.Column("case_type", sa.String(length=32), nullable=False),
        sa.Column("case_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("test_input_snapshot", sa.Text(), nullable=False),
        sa.Column(
            "expected_behavior_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("context_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "actual_behavior",
            postgresql.JSONB(none_as_null=True, astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "comparison_checks",
            postgresql.JSONB(none_as_null=True, astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("result", sa.String(length=16), nullable=True),
        sa.Column("attempted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error_category", sa.String(length=32), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "((result='error' AND error_category IS NOT NULL AND comparison_checks "
            "IS NULL) OR (result IN ('passed','failed') AND error_category IS NULL "
            "AND comparison_checks IS NOT NULL AND actual_behavior IS NOT NULL) OR "
            "(result IS NULL AND error_category IS NULL AND comparison_checks IS NU"
            "LL AND actual_behavior IS NULL)) IS TRUE",
            name=op.f("ck_evaluation_run_cases_result_consistency"),
        ),
        sa.CheckConstraint(
            "actual_behavior IS NULL OR jsonb_typeof(actual_behavior)='object'",
            name=op.f("ck_evaluation_run_cases_actual_behavior_object"),
        ),
        sa.CheckConstraint(
            "attempted = (started_at IS NOT NULL) AND ((result IS NULL AND latency_"
            "ms IS NULL) OR (result IS NOT NULL AND ((attempted AND latency_ms IS N"
            "OT NULL AND latency_ms >= 0) OR (NOT attempted AND latency_ms IS NULL "
            "AND result='error'))))",
            name=op.f("ck_evaluation_run_cases_attempt_valid"),
        ),
        sa.CheckConstraint(
            "case_type IN ('knowledge_qa','tool_calling','permission_boundary','refusal_behavior')",
            name=op.f("ck_evaluation_run_cases_type_values"),
        ),
        sa.CheckConstraint(
            "comparison_checks IS NULL OR jsonb_typeof(comparison_checks)='object'",
            name=op.f("ck_evaluation_run_cases_comparison_checks_object"),
        ),
        sa.CheckConstraint(
            "error_category IS NULL OR error_category IN ('provider_configuration',"
            "'provider_failure','provider_contract','input_budget','resource_config"
            "uration','configuration_drift','authorization_revoked','case_timeout',"
            "'run_timeout','persistence_failure','interrupted','internal_error')",
            name=op.f("ck_evaluation_run_cases_error_values"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(case_snapshot)='object' AND case_snapshot <> '{}'",
            name=op.f("ck_evaluation_run_cases_case_snapshot_object"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(context_snapshot)='object' AND context_snapshot <> '{}'",
            name=op.f("ck_evaluation_run_cases_context_snapshot_object"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(expected_behavior_snapshot)='object' AND expected_behavio"
            "r_snapshot <> '{}'",
            name=op.f("ck_evaluation_run_cases_expected_behavior_snapshot_object"),
        ),
        sa.CheckConstraint(
            "result IS NULL OR result IN ('passed','failed','error')",
            name=op.f("ck_evaluation_run_cases_result_values"),
        ),
        sa.CheckConstraint(
            "(result IS NULL) = (completed_at IS NULL)",
            name=op.f("ck_evaluation_run_cases_completion_valid"),
        ),
        sa.CheckConstraint(
            "ordinal BETWEEN 1 AND 5", name=op.f("ck_evaluation_run_cases_ordinal_valid")
        ),
        sa.CheckConstraint(
            "started_at IS NULL OR completed_at IS NULL OR completed_at >= started_at",
            name=op.f("ck_evaluation_run_cases_time_valid"),
        ),
        sa.CheckConstraint(
            "test_input_snapshot=btrim(test_input_snapshot) AND length(test_input_s"
            "napshot) BETWEEN 1 AND 2000",
            name=op.f("ck_evaluation_run_cases_input_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["case_id", "workspace_id"],
            ["evaluation_cases.id", "evaluation_cases.workspace_id"],
            name="fk_evaluation_run_cases_case_id_workspace",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["run_id", "workspace_id"],
            ["evaluation_runs.id", "evaluation_runs.workspace_id"],
            name="fk_evaluation_run_cases_run_id_workspace",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_evaluation_run_cases_workspace_id_workspaces"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evaluation_run_cases")),
        sa.UniqueConstraint("id", "workspace_id", name="uq_evaluation_run_cases_id_workspace_id"),
        sa.UniqueConstraint("run_id", "case_id", name="uq_evaluation_run_cases_run_case"),
        sa.UniqueConstraint("run_id", "ordinal", name="uq_evaluation_run_cases_run_ordinal"),
    )
    op.create_index(
        "ix_evaluation_run_cases_case_id", "evaluation_run_cases", ["case_id"], unique=False
    )
    op.create_index(
        "ix_evaluation_run_cases_workspace_run_ordinal",
        "evaluation_run_cases",
        ["workspace_id", "run_id", "ordinal"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("evaluation_run_cases")
    op.drop_table("evaluation_runs")
