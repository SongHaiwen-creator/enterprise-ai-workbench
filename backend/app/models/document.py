from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CHAR,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import DocumentFileType, DocumentStatus, StringEnumType


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "file_type IN ('pdf', 'txt', 'md')",
            name="file_type_values",
        ),
        CheckConstraint(
            "status IN ('uploaded', 'processing', 'ready', 'failed', 'disabled')",
            name="status_values",
        ),
        CheckConstraint("version > 0", name="version_positive"),
        CheckConstraint(
            "content_sha256 IS NULL OR content_sha256 ~ '^[0-9a-f]{64}$'",
            name="content_hash_valid",
        ),
        CheckConstraint(
            "(indexed_at IS NULL AND indexed_model IS NULL AND indexed_dimensions IS NULL "
            "AND indexed_chunk_count IS NULL) OR (indexed_at IS NOT NULL AND indexed_model "
            "IS NOT NULL AND length(btrim(indexed_model)) > 0 AND indexed_dimensions IS NOT NULL "
            "AND indexed_dimensions = 1536 AND indexed_chunk_count IS NOT NULL "
            "AND indexed_chunk_count > 0 AND content_sha256 IS NOT NULL "
            "AND status IN ('ready', 'disabled'))",
            name="index_complete",
        ),
        CheckConstraint(
            "status NOT IN ('ready', 'disabled') OR (extracted_text IS NOT NULL "
            "AND length(btrim(extracted_text)) > 0 AND content_sha256 IS NOT NULL)",
            name="ready_content_valid",
        ),
        CheckConstraint(
            "status <> 'failed' OR (extracted_text IS NULL AND content_sha256 IS NULL "
            "AND indexed_at IS NULL)",
            name="failed_content_empty",
        ),
        ForeignKeyConstraint(
            ["family_id", "workspace_id", "knowledge_base_id"],
            [
                "document_families.id",
                "document_families.workspace_id",
                "document_families.knowledge_base_id",
            ],
            name="fk_documents_family_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("family_id", "version", name="uq_documents_family_version"),
        UniqueConstraint(
            "id",
            "family_id",
            "workspace_id",
            "knowledge_base_id",
            name="uq_documents_version_scope",
        ),
        Index(
            "ix_documents_family_versions",
            "workspace_id",
            "knowledge_base_id",
            "family_id",
            "version",
            "id",
        ),
        ForeignKeyConstraint(
            ["knowledge_base_id", "workspace_id"],
            ["knowledge_bases.id", "knowledge_bases.workspace_id"],
            name="fk_documents_knowledge_base_workspace_knowledge_bases",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("id", "workspace_id", name="uq_documents_id_workspace_id"),
        Index("ix_documents_workspace_id", "workspace_id"),
        Index("ix_documents_knowledge_base_id", "knowledge_base_id"),
        Index("ix_documents_created_by", "created_by"),
        Index(
            "ix_documents_knowledge_base_status",
            "knowledge_base_id",
            "status",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        nullable=False,
    )
    knowledge_base_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("knowledge_bases.id", ondelete="RESTRICT"),
        nullable=False,
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    family_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    content_sha256: Mapped[str | None] = mapped_column(CHAR(64), nullable=True)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    indexed_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    indexed_dimensions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    indexed_chunk_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_type: Mapped[DocumentFileType] = mapped_column(
        StringEnumType(DocumentFileType, length=16),
        nullable=False,
    )
    status: Mapped[DocumentStatus] = mapped_column(
        StringEnumType(DocumentStatus),
        nullable=False,
        default=DocumentStatus.UPLOADED,
        server_default=DocumentStatus.UPLOADED.value,
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
    )
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    processing_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
