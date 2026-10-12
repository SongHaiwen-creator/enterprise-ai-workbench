from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import DocumentFileType, DocumentStatus


class DocumentStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal[DocumentStatus.READY, DocumentStatus.DISABLED]


class DocumentIndexMetadata(BaseModel):
    chunk_count: int
    embedding_model: str
    embedding_dimensions: int
    indexed_at: datetime


class DocumentFamilyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    knowledge_base_id: UUID
    display_name: str
    current_document_id: UUID | None
    revision: int
    created_by: UUID
    created_at: datetime
    updated_at: datetime


class DocumentActivation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: UUID
    expected_revision: int = Field(strict=True, ge=1, le=2147483647)


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    family_id: UUID
    is_current: bool
    content_sha256: str | None
    indexing: DocumentIndexMetadata | None
    workspace_id: UUID
    knowledge_base_id: UUID
    file_name: str
    file_type: DocumentFileType
    status: DocumentStatus
    version: int
    processing_error: str | None
    created_by: UUID
    created_at: datetime
    updated_at: datetime
