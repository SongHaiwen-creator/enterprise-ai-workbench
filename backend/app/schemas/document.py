from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.enums import DocumentFileType, DocumentStatus


class DocumentStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal[DocumentStatus.READY, DocumentStatus.DISABLED]


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
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
