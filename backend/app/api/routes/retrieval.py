from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.api.dependencies.auth import DatabaseSession
from app.api.dependencies.authorization import (
    ActiveWorkspaceMembership,
    KnowledgeAdministratorMembership,
)
from app.api.dependencies.embeddings import ConfiguredEmbeddingProvider
from app.schemas.common import ErrorResponse
from app.schemas.retrieval import (
    DocumentIndexResponse,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    KnowledgeSearchResult,
)
from app.services import retrieval as retrieval_service
from app.services.embeddings import EmbeddingProviderError

router = APIRouter(
    prefix="/workspaces/{workspace_id}/knowledge-bases/{knowledge_base_id}",
    tags=["retrieval"],
)

RETRIEVAL_RESPONSES = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    502: {"model": ErrorResponse},
    503: {"model": ErrorResponse},
}


@router.post(
    "/documents/{document_id}/index",
    response_model=DocumentIndexResponse,
    responses=RETRIEVAL_RESPONSES,
)
def index_document(
    workspace_id: UUID,
    knowledge_base_id: UUID,
    document_id: UUID,
    session: DatabaseSession,
    _administrator: KnowledgeAdministratorMembership,
    provider: ConfiguredEmbeddingProvider,
) -> DocumentIndexResponse:
    try:
        result = retrieval_service.index_document(
            session,
            workspace_id,
            knowledge_base_id,
            document_id,
            provider,
        )
    except EmbeddingProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return DocumentIndexResponse.model_validate(result, from_attributes=True)


@router.post(
    "/search",
    response_model=KnowledgeSearchResponse,
    responses=RETRIEVAL_RESPONSES,
)
def search_knowledge_base(
    workspace_id: UUID,
    knowledge_base_id: UUID,
    payload: KnowledgeSearchRequest,
    session: DatabaseSession,
    _membership: ActiveWorkspaceMembership,
    provider: ConfiguredEmbeddingProvider,
) -> KnowledgeSearchResponse:
    try:
        results = retrieval_service.search_knowledge_base(
            session,
            workspace_id,
            knowledge_base_id,
            payload.query,
            payload.limit,
            provider,
        )
    except EmbeddingProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return KnowledgeSearchResponse(
        query=payload.query,
        results=[
            KnowledgeSearchResult.model_validate(result, from_attributes=True)
            for result in results
        ],
    )
