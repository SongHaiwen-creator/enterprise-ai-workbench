from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CHAR,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

ERROR_VALUES = (
    "'provider_configuration','provider_failure','provider_contract','input_budget',"
    "'resource_configuration','configuration_drift','authorization_revoked',"
    "'case_timeout','run_timeout','persistence_failure','interrupted','internal_error'"
)


def composite_fk(table: str, column: str, target: str, target_column: str = "id"):
    return ForeignKeyConstraint(
        [column, "workspace_id"],
        [f"{target}.{target_column}", f"{target}.workspace_id"],
        name=f"fk_{table}_{column}_workspace",
        ondelete="RESTRICT",
    )


class RunIdentity:
    id: Mapped[UUID] = mapped_column(
        PGUUID, primary_key=True, server_default=text("gen_random_uuid()")
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PGUUID, ForeignKey("workspaces.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvaluationRun(RunIdentity, Base):
    __tablename__ = "evaluation_runs"
    __table_args__ = (
        UniqueConstraint("id", "workspace_id", name="uq_evaluation_runs_id_workspace_id"),
        composite_fk("evaluation_runs", "dataset_id", "evaluation_datasets"),
        composite_fk("evaluation_runs", "agent_id", "agents"),
        composite_fk("evaluation_runs", "created_by", "memberships", "user_id"),
        CheckConstraint("status IN ('running','completed','failed')", name="status_values"),
        CheckConstraint(
            "total_cases BETWEEN 1 AND 5 AND passed_cases >= 0 AND "
            "failed_cases >= 0 AND error_cases >= 0 AND "
            "passed_cases+failed_cases+error_cases <= total_cases AND "
            "(status = 'running' OR passed_cases+failed_cases+error_cases = total_cases)",
            name="counts_valid",
        ),
        CheckConstraint("(status='running') = (completed_at IS NULL)", name="completion_valid"),
        CheckConstraint("(status='failed') = (failure_category IS NOT NULL)", name="failure_valid"),
        CheckConstraint(
            f"failure_category IS NULL OR failure_category IN ({ERROR_VALUES})",
            name="failure_values",
        ),
        CheckConstraint(
            "deadline_at = started_at + interval '120 seconds' AND "
            "(completed_at IS NULL OR completed_at >= started_at)",
            name="time_valid",
        ),
        CheckConstraint(
            "snapshot_version=1 AND scorer_version='evaluation-scorer-v1'", name="version_valid"
        ),
        CheckConstraint("configuration_sha256 ~ '^[0-9a-f]{64}$'", name="hash_valid"),
        *(
            CheckConstraint(f"jsonb_typeof({c})='object' AND {c} <> '{{}}'", name=f"{c}_object")
            for c in ("dataset_snapshot", "agent_snapshot", "config_snapshot")
        ),
        Index("ix_evaluation_runs_workspace_created", "workspace_id", "created_at", "id"),
        Index(
            "ix_evaluation_runs_workspace_dataset_created",
            "workspace_id",
            "dataset_id",
            "created_at",
            "id",
        ),
        Index("ix_evaluation_runs_agent_id", "agent_id"),
        Index("ix_evaluation_runs_created_by", "created_by"),
        Index(
            "uq_evaluation_runs_workspace_running",
            "workspace_id",
            unique=True,
            postgresql_where=text("status = 'running'"),
        ),
    )
    dataset_id: Mapped[UUID] = mapped_column(PGUUID)
    agent_id: Mapped[UUID] = mapped_column(PGUUID)
    created_by: Mapped[UUID] = mapped_column(PGUUID)
    status: Mapped[str] = mapped_column(String(16), default="running", server_default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_cases: Mapped[int] = mapped_column(SmallInteger)
    passed_cases: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    failed_cases: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    error_cases: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    failure_category: Mapped[str | None] = mapped_column(String(32))
    dataset_snapshot: Mapped[dict] = mapped_column(JSONB)
    agent_snapshot: Mapped[dict] = mapped_column(JSONB)
    config_snapshot: Mapped[dict] = mapped_column(JSONB)
    snapshot_version: Mapped[int] = mapped_column(SmallInteger, default=1, server_default="1")
    scorer_version: Mapped[str] = mapped_column(
        String(32), default="evaluation-scorer-v1", server_default="evaluation-scorer-v1"
    )
    configuration_sha256: Mapped[str] = mapped_column(CHAR(64))
    provider_egress_acknowledged: Mapped[bool] = mapped_column(Boolean)


class EvaluationRunCase(RunIdentity, Base):
    __tablename__ = "evaluation_run_cases"
    __table_args__ = (
        UniqueConstraint("id", "workspace_id", name="uq_evaluation_run_cases_id_workspace_id"),
        UniqueConstraint("run_id", "ordinal", name="uq_evaluation_run_cases_run_ordinal"),
        UniqueConstraint("run_id", "case_id", name="uq_evaluation_run_cases_run_case"),
        composite_fk("evaluation_run_cases", "run_id", "evaluation_runs"),
        composite_fk("evaluation_run_cases", "case_id", "evaluation_cases"),
        CheckConstraint("ordinal BETWEEN 1 AND 5", name="ordinal_valid"),
        CheckConstraint(
            "case_type IN ('knowledge_qa','tool_calling','permission_boundary','refusal_behavior')",
            name="type_values",
        ),
        CheckConstraint(
            "result IS NULL OR result IN ('passed','failed','error')", name="result_values"
        ),
        CheckConstraint(
            f"error_category IS NULL OR error_category IN ({ERROR_VALUES})", name="error_values"
        ),
        CheckConstraint(
            "((result='error' AND error_category IS NOT NULL AND "
            "comparison_checks IS NULL) OR (result IN ('passed','failed') AND "
            "error_category IS NULL AND comparison_checks IS NOT NULL AND "
            "actual_behavior IS NOT NULL) OR (result IS NULL AND "
            "error_category IS NULL AND comparison_checks IS NULL AND "
            "actual_behavior IS NULL)) IS TRUE",
            name="result_consistency",
        ),
        CheckConstraint("(result IS NULL) = (completed_at IS NULL)", name="completion_valid"),
        CheckConstraint(
            "attempted = (started_at IS NOT NULL) AND "
            "((result IS NULL AND latency_ms IS NULL) OR "
            "(result IS NOT NULL AND ((attempted AND latency_ms IS NOT NULL "
            "AND latency_ms >= 0) OR "
            "(NOT attempted AND latency_ms IS NULL AND result='error'))))",
            name="attempt_valid",
        ),
        CheckConstraint(
            "started_at IS NULL OR completed_at IS NULL OR completed_at >= started_at",
            name="time_valid",
        ),
        CheckConstraint(
            "test_input_snapshot=btrim(test_input_snapshot) AND "
            "length(test_input_snapshot) BETWEEN 1 AND 2000",
            name="input_valid",
        ),
        *(
            CheckConstraint(f"jsonb_typeof({c})='object' AND {c} <> '{{}}'", name=f"{c}_object")
            for c in ("case_snapshot", "expected_behavior_snapshot", "context_snapshot")
        ),
        *(
            CheckConstraint(f"{c} IS NULL OR jsonb_typeof({c})='object'", name=f"{c}_object")
            for c in ("actual_behavior", "comparison_checks")
        ),
        Index("ix_evaluation_run_cases_workspace_run_ordinal", "workspace_id", "run_id", "ordinal"),
        Index("ix_evaluation_run_cases_case_id", "case_id"),
    )
    run_id: Mapped[UUID] = mapped_column(PGUUID)
    case_id: Mapped[UUID] = mapped_column(PGUUID)
    ordinal: Mapped[int] = mapped_column(SmallInteger)
    case_type: Mapped[str] = mapped_column(String(32))
    case_snapshot: Mapped[dict] = mapped_column(JSONB)
    test_input_snapshot: Mapped[str] = mapped_column(Text)
    expected_behavior_snapshot: Mapped[dict] = mapped_column(JSONB)
    context_snapshot: Mapped[dict] = mapped_column(JSONB)
    actual_behavior: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    comparison_checks: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    result: Mapped[str | None] = mapped_column(String(16))
    attempted: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    error_category: Mapped[str | None] = mapped_column(String(32))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
