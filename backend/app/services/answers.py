from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from app.schemas.answer import AnswerStatus
from app.services import retrieval as retrieval_service
from app.services.embeddings import EmbeddingProvider
from app.services.generation import (
    EvidenceItem,
    GenerationProvider,
    GenerationProviderError,
    GenerationUsage,
)

UNSUPPORTED_MESSAGE = (
    "The retrieved knowledge does not contain enough evidence to answer this question."
)
ANSWER_RETRIEVAL_LIMIT = 5


@dataclass(frozen=True)
class AnswerCitation:
    document_id: UUID
    file_name: str
    document_version: int
    chunk_id: UUID
    chunk_index: int
    excerpt: str


@dataclass(frozen=True)
class AnswerResult:
    question: str
    status: AnswerStatus
    answer: str | None
    message: str | None
    citations: list[AnswerCitation]
    usage: GenerationUsage | None


def answer_question(
    session: Session,
    workspace_id: UUID,
    knowledge_base_id: UUID,
    question: str,
    embedding_provider: EmbeddingProvider,
    generation_provider: GenerationProvider,
) -> AnswerResult:
    results = retrieval_service.search_knowledge_base(
        session,
        workspace_id,
        knowledge_base_id,
        question,
        ANSWER_RETRIEVAL_LIMIT,
        embedding_provider,
    )
    if not results:
        return AnswerResult(
            question=question,
            status=AnswerStatus.UNSUPPORTED,
            answer=None,
            message=UNSUPPORTED_MESSAGE,
            citations=[],
            usage=None,
        )

    evidence = [
        EvidenceItem(reference=f"E{index}", content=result.content)
        for index, result in enumerate(results, start=1)
    ]
    generated = generation_provider.generate(question, evidence)
    output = generated.output
    if output.status is AnswerStatus.UNSUPPORTED:
        if output.answer is not None or output.citations:
            raise GenerationProviderError("Generation provider request failed")
        return AnswerResult(
            question=question,
            status=AnswerStatus.UNSUPPORTED,
            answer=None,
            message=UNSUPPORTED_MESSAGE,
            citations=[],
            usage=generated.usage,
        )

    if output.status is not AnswerStatus.ANSWERED or output.answer is None:
        raise GenerationProviderError("Generation provider request failed")
    if not output.citations:
        raise GenerationProviderError("Generation provider request failed")

    results_by_reference = {
        item.reference: result for item, result in zip(evidence, results, strict=True)
    }
    seen: set[str] = set()
    citations: list[AnswerCitation] = []
    for citation in output.citations:
        if citation.evidence_ref in seen:
            raise GenerationProviderError("Generation provider request failed")
        seen.add(citation.evidence_ref)
        result = results_by_reference.get(citation.evidence_ref)
        if (
            result is None
            or not 1 <= len(citation.excerpt) <= 500
            or not citation.excerpt.strip()
            or citation.excerpt not in result.content
        ):
            raise GenerationProviderError("Generation provider request failed")
        citations.append(
            AnswerCitation(
                document_id=result.document_id,
                file_name=result.file_name,
                document_version=result.document_version,
                chunk_id=result.chunk_id,
                chunk_index=result.chunk_index,
                excerpt=citation.excerpt,
            )
        )

    return AnswerResult(
        question=question,
        status=AnswerStatus.ANSWERED,
        answer=output.answer,
        message=None,
        citations=citations,
        usage=generated.usage,
    )
