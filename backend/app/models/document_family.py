from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DocumentFamily(Base):
    __tablename__ = "document_families"
    __table_args__ = (
        CheckConstraint("length(btrim(display_name)) > 0", name="display_name_nonblank"),
        CheckConstraint("next_version > 0 AND revision > 0", name="counters_positive"),
        UniqueConstraint(
            "id", "workspace_id", "knowledge_base_id", name="uq_document_families_scope"
        ),
        ForeignKeyConstraint(
            ["knowledge_base_id", "workspace_id"],
            ["knowledge_bases.id", "knowledge_bases.workspace_id"],
            name="fk_document_families_knowledge_base_workspace",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["current_document_id", "id", "workspace_id", "knowledge_base_id"],
            [
                "documents.id",
                "documents.family_id",
                "documents.workspace_id",
                "documents.knowledge_base_id",
            ],
            name="fk_document_families_current_version",
            ondelete="RESTRICT",
            use_alter=True,
        ),
        Index(
            "ix_document_families_list", "workspace_id", "knowledge_base_id", "display_name", "id"
        ),
        Index("ix_document_families_created_by", "created_by"),
    )
    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="RESTRICT")
    )
    knowledge_base_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True))
    display_name: Mapped[str] = mapped_column(String(255))
    current_document_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True))
    next_version: Mapped[int] = mapped_column(Integer, default=2, server_default="2")
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    legacy_backfill: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    created_by: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
