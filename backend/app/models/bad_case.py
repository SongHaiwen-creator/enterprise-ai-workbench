from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base
from app.models.evaluation_run import RunIdentity, composite_fk


class BadCase(RunIdentity, Base):
    __tablename__ = "bad_cases"
    __table_args__ = (
        UniqueConstraint("id", "workspace_id", name="uq_bad_cases_id_workspace_id"),
        UniqueConstraint("workspace_id", "source_run_case_id", name="uq_bad_cases_source"),
        composite_fk("bad_cases", "source_run_case_id", "evaluation_run_cases"),
        composite_fk("bad_cases", "created_by", "memberships", "user_id"),
        composite_fk("bad_cases", "updated_by", "memberships", "user_id"),
        CheckConstraint(
            "origin_kind IN ('behavior_failure','execution_error','manual_review')",
            name="origin_values",
        ),
        CheckConstraint(
            "category IN ('unclassified','routing','knowledge','tool_planning',"
            "'permission','refusal','runtime','other')",
            name="category_values",
        ),
        CheckConstraint(
            "status IN ('open','investigating','resolved','dismissed')",
            name="status_values",
        ),
        CheckConstraint("revision >= 1", name="revision_valid"),
        CheckConstraint(
            "(status IN ('resolved','dismissed')) = (resolution_note IS NOT NULL)",
            name="resolution_valid",
        ),
        *(
            CheckConstraint(
                f"{column}=btrim({column}) AND length({column}) BETWEEN 1 AND {size}",
                name=f"{column}_valid",
            )
            for column, size in (("title", 255), ("description", 5000))
        ),
        *(
            CheckConstraint(
                f"{column} IS NULL OR ({column}=btrim({column}) AND "
                f"length({column}) BETWEEN 1 AND 5000)",
                name=f"{column}_valid",
            )
            for column in ("possible_cause", "handling_note", "resolution_note")
        ),
        Index("ix_bad_cases_workspace_created", "workspace_id", "created_at", "id"),
        Index(
            "ix_bad_cases_workspace_status_created", "workspace_id", "status", "created_at", "id"
        ),
        *(
            Index(f"ix_bad_cases_{c}", c)
            for c in ("source_run_case_id", "created_by", "updated_by")
        ),
    )
    source_run_case_id: Mapped[UUID] = mapped_column(PGUUID)
    origin_kind: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(
        String(32), default="unclassified", server_default="unclassified"
    )
    status: Mapped[str] = mapped_column(String(16), default="open", server_default="open")
    possible_cause: Mapped[str | None] = mapped_column(Text)
    handling_note: Mapped[str | None] = mapped_column(Text)
    resolution_note: Mapped[str | None] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    created_by: Mapped[UUID] = mapped_column(PGUUID)
    updated_by: Mapped[UUID] = mapped_column(PGUUID)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BadCaseHistory(RunIdentity, Base):
    __tablename__ = "bad_case_history"
    __table_args__ = (
        UniqueConstraint("bad_case_id", "revision", name="uq_bad_case_history_revision"),
        composite_fk("bad_case_history", "bad_case_id", "bad_cases"),
        composite_fk("bad_case_history", "actor_id", "memberships", "user_id"),
        CheckConstraint("revision >= 1", name="revision_valid"),
        CheckConstraint(
            "((event='created' AND revision=1 AND before_values IS NULL) OR "
            "(event='updated' AND revision>1 AND jsonb_typeof(before_values)='object' "
            "AND before_values <> '{}')) IS TRUE",
            name="event_valid",
        ),
        CheckConstraint(
            "jsonb_typeof(after_values)='object' AND after_values <> '{}'",
            name="after_valid",
        ),
        CheckConstraint(
            "change_reason IS NULL OR (change_reason=btrim(change_reason) AND "
            "length(change_reason) BETWEEN 1 AND 1000)",
            name="reason_valid",
        ),
        Index("ix_bad_case_history_workspace_revision", "workspace_id", "bad_case_id", "revision"),
        Index("ix_bad_case_history_actor_id", "actor_id"),
    )
    bad_case_id: Mapped[UUID] = mapped_column(PGUUID)
    actor_id: Mapped[UUID] = mapped_column(PGUUID)
    revision: Mapped[int] = mapped_column(Integer)
    event: Mapped[str] = mapped_column(String(16))
    change_reason: Mapped[str | None] = mapped_column(String(1000))
    before_values: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    after_values: Mapped[dict] = mapped_column(JSONB)
