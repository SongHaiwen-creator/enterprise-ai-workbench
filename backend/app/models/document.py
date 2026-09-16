from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
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
