from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    SmallInteger,
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


def _common_constraints(table: str) -> tuple:
    return (
        CheckConstraint("status IN ('active', 'disabled')", name="status_values"),
        CheckConstraint("name = btrim(name) AND length(name) BETWEEN 1 AND 255", name="name_valid"),
        CheckConstraint(
            "description IS NULL OR length(description) <= 5000", name="description_length"
        ),
        ForeignKeyConstraint(
            ["created_by", "workspace_id"],
            ["memberships.user_id", "memberships.workspace_id"],
            name=f"fk_{table}_creator_membership",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("id", "workspace_id", name=f"uq_{table}_id_workspace_id"),
        Index(f"ix_{table}_created_by", "created_by"),
    )


class EvaluationFields:
    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
    )
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active")
    created_by: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class EvaluationDataset(EvaluationFields, Base):
    __tablename__ = "evaluation_datasets"
    __table_args__ = (
        *_common_constraints("evaluation_datasets"),
        Index("ix_evaluation_datasets_workspace_created", "workspace_id", "created_at", "id"),
    )


class EvaluationCase(EvaluationFields, Base):
    __tablename__ = "evaluation_cases"
    __table_args__ = (
        *_common_constraints("evaluation_cases"),
        CheckConstraint(
            "case_type IN ('knowledge_qa', 'tool_calling', "
            "'permission_boundary', 'refusal_behavior')",
            name="case_type_values",
        ),
        CheckConstraint(
            "test_input = btrim(test_input) AND length(test_input) BETWEEN 1 AND 2000",
            name="input_valid",
        ),
        CheckConstraint("schema_version = 1", name="schema_version_valid"),
        CheckConstraint(
            "jsonb_typeof(expected_behavior) = 'object' AND expected_behavior <> '{}'",
            name="expectation_object",
        ),
        *(
            ForeignKeyConstraint(
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
        Index(
            "ix_evaluation_cases_workspace_dataset_created",
            "workspace_id",
            "dataset_id",
            "created_at",
            "id",
        ),
        *(
            Index(f"ix_evaluation_cases_{column}", column)
            for column in ("agent_id", "knowledge_base_id", "tool_id")
        ),
    )

    dataset_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True))
    case_type: Mapped[str] = mapped_column(String(32))
    test_input: Mapped[str] = mapped_column(Text)
    expected_behavior: Mapped[dict] = mapped_column(JSONB)
    schema_version: Mapped[int] = mapped_column(SmallInteger, default=1, server_default="1")
    agent_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True))
    knowledge_base_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True))
    tool_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True))
