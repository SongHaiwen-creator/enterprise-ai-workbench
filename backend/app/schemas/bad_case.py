from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BeforeValidator, Field, StrictInt, model_validator

from app.schemas.evaluation import CaseType, StrictModel
from app.schemas.evaluation_run import CaseResult, RunCaseDetail

Category = Literal[
    "unclassified",
    "routing",
    "knowledge",
    "tool_planning",
    "permission",
    "refusal",
    "runtime",
    "other",
]
Status = Literal["open", "investigating", "resolved", "dismissed"]
Origin = Literal["behavior_failure", "execution_error", "manual_review"]


def trim(value):
    if not isinstance(value, str) or "\0" in value:
        raise ValueError("Invalid bad case request")
    return value.strip()


def optional_text(value):
    return None if value is None else trim(value) or None


Title = Annotated[str, BeforeValidator(trim), Field(min_length=1, max_length=255)]
Description = Annotated[str, BeforeValidator(trim), Field(min_length=1, max_length=5000)]
Note = Annotated[Annotated[str, Field(max_length=5000)] | None, BeforeValidator(optional_text)]
Reason = Annotated[Annotated[str, Field(max_length=1000)] | None, BeforeValidator(optional_text)]


class HumanValues(StrictModel):
    title: Title
    description: Description
    category: Category = "unclassified"
    possible_cause: Note = None
    handling_note: Note = None
    status: Status = "open"
    resolution_note: Note = None

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if (self.status in {"resolved", "dismissed"}) != (self.resolution_note is not None):
            raise ValueError("Invalid bad case request")
        return self


HUMAN_FIELDS = tuple(HumanValues.model_fields)


class BadCaseCreate(StrictModel):
    title: Title
    description: Description
    category: Category = "unclassified"
    possible_cause: Note = None


class BadCaseUpdate(StrictModel):
    expected_revision: Annotated[StrictInt, Field(ge=1)]
    title: Title | None = None
    description: Description | None = None
    category: Category | None = None
    possible_cause: Note = None
    handling_note: Note = None
    status: Status | None = None
    resolution_note: Note = None
    change_reason: Reason = None

    @model_validator(mode="after")
    def valid_patch(self) -> Self:
        if not (self.model_fields_set & set(HUMAN_FIELDS)):
            raise ValueError("Invalid bad case request")
        if any(
            getattr(self, key) is None
            for key in self.model_fields_set & {"title", "description", "category", "status"}
        ):
            raise ValueError("Invalid bad case request")
        return self


class BadCaseSummary(StrictModel):
    id: UUID
    workspace_id: UUID
    source_run_case_id: UUID
    source_run_id: UUID
    source_case_id: UUID
    dataset_id: UUID
    agent_id: UUID
    source_result: CaseResult
    source_case_type: CaseType
    origin_kind: Origin
    title: str
    category: Category
    status: Status
    created_by: UUID
    updated_by: UUID
    created_at: datetime
    updated_at: datetime
    revision: int


class BadCaseDetail(BadCaseSummary):
    description: str
    possible_cause: str | None
    handling_note: str | None
    resolution_note: str | None
    source_evidence: RunCaseDetail


class HistoryItem(StrictModel):
    id: UUID
    bad_case_id: UUID
    workspace_id: UUID
    actor_id: UUID
    revision: int
    event: Literal["created", "updated"]
    created_at: datetime
    change_reason: Reason
    before_values: dict | None
    after_values: dict

    @model_validator(mode="after")
    def allowlist(self) -> Self:
        for values in (self.before_values, self.after_values):
            if values is not None:
                # Partial diffs use the PATCH field validators without requiring revision.
                BadCaseUpdate.model_validate({"expected_revision": 1, **values})
                if not values or set(values) - set(HUMAN_FIELDS):
                    raise ValueError("Invalid bad case request")
        if self.event == "created":
            if self.before_values is not None or self.revision != 1:
                raise ValueError("Invalid bad case request")
            HumanValues.model_validate(self.after_values)
            if set(self.after_values) != set(HUMAN_FIELDS):
                raise ValueError("Invalid bad case request")
        elif (
            self.revision <= 1
            or self.before_values is None
            or set(self.before_values) != set(self.after_values)
        ):
            raise ValueError("Invalid bad case request")
        return self


class BadCaseList(StrictModel):
    items: list[BadCaseSummary]
    limit: int
    offset: int


class HistoryList(StrictModel):
    items: list[HistoryItem]
    limit: int
    offset: int
