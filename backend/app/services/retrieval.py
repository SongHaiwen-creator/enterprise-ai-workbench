from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Chunk, Document
from app.models.enums import DocumentStatus, KnowledgeBaseStatus
from app.services.chunking import split_document_text
from app.services.documents import get_document
from app.services.embeddings import (
    EmbeddingProvider,
    EmbeddingProviderError,
    is_valid_embedding,
)
from app.services.exceptions import ConflictError
from app.services.knowledge_bases import get_knowledge_base


@dataclass(frozen=True)
class DocumentIndexResult:
    document_id: UUID
    chunk_count: int
    embedding_model: str
    embedding_dimensions: int
    indexed_at: datetime


@dataclass(frozen=True)
class SearchResult:
    chunk_id: UUID
    document_id: UUID
    file_name: str
    document_version: int
    chunk_index: int
    content: str
    cosine_distance: float


def _validated_embeddings(
    provider: EmbeddingProvider,
    texts: list[str],
) -> list[list[float]]:
    embeddings = provider.embed_texts(texts)
    if len(embeddings) != len(texts):
        raise EmbeddingProviderError("Embedding provider request failed")
    if any(not is_valid_embedding(embedding, provider.dimensions) for embedding in embeddings):
        raise EmbeddingProviderError("Embedding provider request failed")
    return embeddings


def index_document(
    session: Session,
    workspace_id: UUID,
    knowledge_base_id: UUID,
    document_id: UUID,
    provider: EmbeddingProvider,
) -> DocumentIndexResult:
    knowledge_base = get_knowledge_base(session, workspace_id, knowledge_base_id)
    if knowledge_base.status is KnowledgeBaseStatus.DISABLED:
        raise ConflictError("Cannot index a disabled knowledge base")

    document = get_document(session, workspace_id, knowledge_base_id, document_id)
    if document.status is not DocumentStatus.READY or not document.extracted_text:
        raise ConflictError("Document is not ready for indexing")

    contents = split_document_text(document.extracted_text)
    if not contents:
        raise ConflictError("Document is not ready for indexing")
    embeddings = _validated_embeddings(provider, contents)

    session.execute(
        delete(Chunk).where(
            Chunk.workspace_id == workspace_id,
            Chunk.document_id == document_id,
        )
    )
    chunks = [
        Chunk(
            workspace_id=workspace_id,
            document_id=document_id,
            content=content,
            chunk_index=index,
            embedding_model=provider.model,
            embedding=embedding,
        )
        for index, (content, embedding) in enumerate(zip(contents, embeddings, strict=True))
    ]
    session.add_all(chunks)
    session.flush()
    indexed_at = max(chunk.created_at for chunk in chunks)
    session.commit()

    return DocumentIndexResult(
        document_id=document_id,
        chunk_count=len(chunks),
        embedding_model=provider.model,
        embedding_dimensions=provider.dimensions,
        indexed_at=indexed_at,
    )


def search_knowledge_base(
    session: Session,
    workspace_id: UUID,
    knowledge_base_id: UUID,
    query: str,
    limit: int,
    provider: EmbeddingProvider,
) -> list[SearchResult]:
    knowledge_base = get_knowledge_base(session, workspace_id, knowledge_base_id)
    if knowledge_base.status is KnowledgeBaseStatus.DISABLED:
        raise ConflictError("Cannot search a disabled knowledge base")

    query_embedding = _validated_embeddings(provider, [query])[0]
    distance = Chunk.embedding.cosine_distance(query_embedding).label("cosine_distance")
    statement = (
        select(Chunk, Document, distance)
        .join(
            Document,
            (Document.id == Chunk.document_id)
            & (Document.workspace_id == Chunk.workspace_id),
        )
        .where(
            Chunk.workspace_id == workspace_id,
            Chunk.embedding_model == provider.model,
            Document.workspace_id == workspace_id,
            Document.knowledge_base_id == knowledge_base_id,
            Document.status == DocumentStatus.READY,
        )
        .order_by(distance, Chunk.document_id, Chunk.chunk_index)
        .limit(limit)
    )
    rows = session.execute(statement).all()
    return [
        SearchResult(
            chunk_id=chunk.id,
            document_id=document.id,
            file_name=document.file_name,
            document_version=document.version,
            chunk_index=chunk.chunk_index,
            content=chunk.content,
            cosine_distance=float(cosine_distance),
        )
        for chunk, document, cosine_distance in rows
    ]
