from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.api.dependencies.auth import DatabaseSession
from app.api.dependencies.authorization import ActiveWorkspaceMembership
from app.api.dependencies.embeddings import ConfiguredEmbeddingProvider
from app.api.dependencies.generation import ConfiguredGenerationProvider
from app.schemas.answer import (
    GenerationMetadata,
    GroundedAnswerRequest,
    GroundedAnswerResponse,
    GroundedCitation,
)
from app.schemas.common import ErrorResponse
from app.services import answers as answer_service
from app.services.embeddings import EmbeddingProviderError
from app.services.generation import (
    GenerationConfigurationError,
    GenerationInputTooLargeError,
    GenerationProviderError,
)

router = APIRouter(
    prefix="/workspaces/{workspace_id}/knowledge-bases/{knowledge_base_id}",
    tags=["answers"],
)

ANSWER_RESPONSES = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
    502: {"model": ErrorResponse},
    503: {"model": ErrorResponse},
}


@router.post(
    "/answer",
    response_model=GroundedAnswerResponse,
    responses=ANSWER_RESPONSES,
)
def answer_knowledge_question(
    workspace_id: UUID,
    knowledge_base_id: UUID,
    payload: GroundedAnswerRequest,
    session: DatabaseSession,
    _membership: ActiveWorkspaceMembership,
    embedding_provider: ConfiguredEmbeddingProvider,
    generation_provider: ConfiguredGenerationProvider,
) -> GroundedAnswerResponse:
    try:
        result = answer_service.answer_question(
            session,
            workspace_id,
            knowledge_base_id,
            payload.question,
            embedding_provider,
            generation_provider,
        )
    except GenerationInputTooLargeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except GenerationConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (EmbeddingProviderError, GenerationProviderError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    usage = result.usage
    return GroundedAnswerResponse(
        question=result.question,
        status=result.status,
        answer=result.answer,
        message=result.message,
        citations=[
            GroundedCitation.model_validate(citation, from_attributes=True)
            for citation in result.citations
        ],
        generation=GenerationMetadata(
            model=generation_provider.model,
            reasoning_effort=generation_provider.reasoning_effort,
            retrieval_limit=generation_provider.retrieval_limit,
            prompt_version=generation_provider.prompt_version,
            max_input_tokens=generation_provider.max_input_tokens,
            max_output_tokens=generation_provider.max_output_tokens,
            input_tokens=usage.input_tokens if usage is not None else None,
            output_tokens=usage.output_tokens if usage is not None else None,
            total_tokens=usage.total_tokens if usage is not None else None,
        ),
    )
