from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AnswerStatus(StrEnum):
    ANSWERED = "answered"
    UNSUPPORTED = "unsupported"


class GroundedAnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=2000)

    @field_validator("question", mode="before")
    @classmethod
    def strip_question(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value


class GroundedCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: UUID
    file_name: str
    document_version: int
    chunk_id: UUID
    chunk_index: int
    excerpt: str = Field(min_length=1, max_length=500)


class GenerationMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str
    reasoning_effort: Literal["low"]
    retrieval_limit: Literal[5]
    prompt_version: str
    max_input_tokens: int
    max_output_tokens: int
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None


class GroundedAnswerResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str
    status: AnswerStatus
    answer: str | None
    message: str | None
    citations: list[GroundedCitation]
    generation: GenerationMetadata


class ModelCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_ref: str = Field(pattern=r"^E[1-5]$")
    excerpt: str = Field(min_length=1, max_length=500)

    @field_validator("excerpt")
    @classmethod
    def reject_blank_excerpt(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("citation excerpt must not be blank")
        return value


class ModelGenerationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: AnswerStatus
    answer: str | None = Field(max_length=8000)
    citations: list[ModelCitation] = Field(max_length=5)

    @field_validator("answer")
    @classmethod
    def normalize_answer(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_result_shape(self) -> "ModelGenerationOutput":
        references = [citation.evidence_ref for citation in self.citations]
        if len(references) != len(set(references)):
            raise ValueError("citation evidence references must be unique")
        if self.status is AnswerStatus.ANSWERED:
            if self.answer is None or not self.citations:
                raise ValueError("answered output requires an answer and citations")
        elif self.answer is not None or self.citations:
            raise ValueError("unsupported output cannot contain an answer or citations")
        return self
