from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Chunk, Document, DocumentFamily, KnowledgeBase
from app.models.enums import DocumentStatus, KnowledgeBaseStatus
from app.services import documents as versions
from app.services.chunking import split_document_text
from app.services.documents import get_document
from app.services.embeddings import (
    EmbeddingProvider,
    EmbeddingProviderError,
    normalize_embedding,
)
from app.services.exceptions import ConflictError
from app.services.knowledge_bases import get_knowledge_base

KNOWLEDGE_BASE_SEARCH_DISABLED = "Cannot search a disabled knowledge base"


@dataclass(frozen=True)
class DocumentIndexResult:
    document_id: UUID
    chunk_count: int
    embedding_model: str
    embedding_dimensions: int
    indexed_at: datetime


@dataclass(frozen=True)
class SearchResult:
    family_id: UUID
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
    try:
        embeddings = provider.embed_texts(texts)
    except EmbeddingProviderError:
        raise
    except (AttributeError, TypeError, ValueError) as exc:
        raise EmbeddingProviderError("Embedding provider request failed") from exc
    if not isinstance(embeddings, list) or len(embeddings) != len(texts):
        raise EmbeddingProviderError("Embedding provider request failed")

    normalized: list[list[float]] = []
    for embedding in embeddings:
        vector = normalize_embedding(embedding, provider.dimensions)
        if vector is None:
            raise EmbeddingProviderError("Embedding provider request failed")
        normalized.append(vector)
    return normalized


def cached_index(document, model, dimensions):
    if document.indexed_at is None:
        return None
    if document.indexed_model != model or document.indexed_dimensions != dimensions:
        raise ConflictError("Document index configuration is incompatible")
    return DocumentIndexResult(
        document_id=document.id,
        chunk_count=document.indexed_chunk_count,
        embedding_model=document.indexed_model,
        embedding_dimensions=document.indexed_dimensions,
        indexed_at=document.indexed_at,
    )


def index_document(session, workspace_id, knowledge_base_id, document_id, provider, *, actor_id):
    base = get_knowledge_base(session, workspace_id, knowledge_base_id)
    versions.current_authority(session, workspace_id, actor_id)
    if base.status is not KnowledgeBaseStatus.ACTIVE:
        raise ConflictError("Cannot index a disabled knowledge base")
    document = get_document(session, workspace_id, knowledge_base_id, document_id)
    if document.status is not DocumentStatus.READY or not document.extracted_text:
        raise ConflictError("Document is not ready for indexing")
    existing = cached_index(document, provider.model, provider.dimensions)
    if existing is not None:
        return existing
    content, expected_hash, family_id = (
        document.extracted_text,
        document.content_sha256,
        document.family_id,
    )
    # No database transaction/lock spans the provider phase.
    session.commit()
    contents = split_document_text(content)
    if not contents:
        raise ConflictError("Document is not ready for indexing")
    embeddings = _validated_embeddings(provider, contents)
    with versions.write_boundary(session):
        versions.locked_base(session, workspace_id, knowledge_base_id, actor_id)
        family = versions.get_family(session, workspace_id, knowledge_base_id, family_id, lock=True)
        document = get_document(session, workspace_id, knowledge_base_id, document_id, lock=True)
        if document.status is not DocumentStatus.READY or document.content_sha256 != expected_hash:
            raise ConflictError("Document version operation conflict")
        existing = cached_index(document, provider.model, provider.dimensions)
        if existing is not None:
            session.commit()
            return existing
        chunks = [
            Chunk(
                workspace_id=workspace_id,
                document_id=document_id,
                content=text,
                chunk_index=index,
                embedding_model=provider.model,
                embedding=embedding,
            )
            for index, (text, embedding) in enumerate(zip(contents, embeddings, strict=True))
        ]
        session.add_all(chunks)
        session.flush()
        document.indexed_at = max(chunk.created_at for chunk in chunks)
        document.indexed_model = provider.model
        document.indexed_dimensions = provider.dimensions
        document.indexed_chunk_count = len(chunks)
        versions.changed(family)
        result = cached_index(document, provider.model, provider.dimensions)
        session.commit()
        return result


def effective_documents(workspace_id, knowledge_base_id, model, dimensions):
    """One shared SQL eligibility predicate for retrieval and corpus snapshots."""
    return (
        select(Document)
        .join(
            DocumentFamily,
            (DocumentFamily.id == Document.family_id)
            & (DocumentFamily.workspace_id == Document.workspace_id)
            & (DocumentFamily.knowledge_base_id == Document.knowledge_base_id)
            & (DocumentFamily.current_document_id == Document.id),
        )
        .join(
            KnowledgeBase,
            (KnowledgeBase.id == Document.knowledge_base_id)
            & (KnowledgeBase.workspace_id == Document.workspace_id),
        )
        .where(
            Document.workspace_id == workspace_id,
            Document.knowledge_base_id == knowledge_base_id,
            Document.status == DocumentStatus.READY,
            Document.indexed_at.is_not(None),
            Document.indexed_model == model,
            Document.indexed_dimensions == dimensions,
            KnowledgeBase.status == KnowledgeBaseStatus.ACTIVE,
        )
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
        raise ConflictError(KNOWLEDGE_BASE_SEARCH_DISABLED)

    query_embedding = _validated_embeddings(provider, [query])[0]
    distance = Chunk.embedding.cosine_distance(query_embedding).label("cosine_distance")
    statement = (
        effective_documents(workspace_id, knowledge_base_id, provider.model, provider.dimensions)
        .add_columns(Chunk, distance)
        .join(
            Chunk,
            (Chunk.document_id == Document.id) & (Chunk.workspace_id == Document.workspace_id),
        )
        .where(Chunk.workspace_id == workspace_id, Chunk.embedding_model == provider.model)
        .order_by(distance, Chunk.document_id, Chunk.chunk_index)
        .limit(limit)
    )
    rows = session.execute(statement).all()
    return [
        SearchResult(
            family_id=document.family_id,
            chunk_id=chunk.id,
            document_id=document.id,
            file_name=document.file_name,
            document_version=document.version,
            chunk_index=chunk.chunk_index,
            content=chunk.content,
            cosine_distance=float(cosine_distance),
        )
        for document, chunk, cosine_distance in rows
    ]
