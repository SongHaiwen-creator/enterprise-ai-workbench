from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class KnowledgeSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=5, ge=1, le=20)

    @field_validator("query", mode="before")
    @classmethod
    def strip_query(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value


class DocumentIndexResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: UUID
    chunk_count: int
    embedding_model: str
    embedding_dimensions: int
    indexed_at: datetime


class KnowledgeSearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: UUID
    document_id: UUID
    file_name: str
    document_version: int
    chunk_index: int
    content: str
    cosine_distance: float


class KnowledgeSearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    results: list[KnowledgeSearchResult]
