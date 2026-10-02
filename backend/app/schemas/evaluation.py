from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    field_validator,
    model_validator,
)

Status = Literal["active", "disabled"]
CaseType = Literal["knowledge_qa", "tool_calling", "permission_boundary", "refusal_behavior"]
ToolKey = Literal[
    "get_reimbursement_status", "get_employee_information", "create_it_access_request"
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class KnowledgeExpectation(StrictModel):
    routing_intent: Literal["knowledge_qa"]
    answer_status: Literal["answered", "unsupported"]
    citation_requirement: Literal["present", "none"]

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if (self.answer_status == "answered") != (self.citation_requirement == "present"):
            raise ValueError("Invalid expectation")
        return self


class ToolExpectation(StrictModel):
    routing_intent: Literal["tool_request"]
    outcome: Literal["executed", "approval_required", "not_executed"]
    tool_key: ToolKey | None
    approval_required: StrictBool
    non_execution_reason: (
        Literal["no_available_tool", "no_matching_tool", "missing_required_arguments"] | None
    )

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if self.outcome == "not_executed":
            valid = (
                self.tool_key is None
                and not self.approval_required
                and self.non_execution_reason is not None
            )
        else:
            approval = self.outcome == "approval_required"
            valid = (
                self.tool_key is not None
                and self.approval_required == approval
                and self.non_execution_reason is None
                and (self.tool_key == "create_it_access_request") == approval
            )
        if not valid:
            raise ValueError("Invalid expectation")
        return self


class PermissionExpectation(StrictModel):
    actor_role: Literal["employee", "knowledge_admin", "agent_admin", "system_admin"]
    actor_membership_status: Literal["active", "invited", "disabled", "absent"]
    target_context: Literal["same_workspace", "other_workspace", "nonexistent"]
    operation: Literal[
        "agent_route",
        "knowledge_answer",
        "agent_configuration_read",
        "tool_configuration_read",
        "evaluation_dataset_read",
    ]
    expected_http_status: StrictInt
    result_category: Literal["forbidden", "not_found"]
    access_denied: StrictBool

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if (
            not self.access_denied
            or self.expected_http_status not in (403, 404)
            or (self.expected_http_status == 403) != (self.result_category == "forbidden")
        ):
            raise ValueError("Invalid expectation")
        return self


class RefusalExpectation(StrictModel):
    routing_intent: Literal["unsupported", "knowledge_qa"]
    response_category: Literal["unsupported_request", "knowledge_unsupported"]
    safe_response_required: StrictBool

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if not self.safe_response_required or (self.routing_intent == "unsupported") != (
            self.response_category == "unsupported_request"
        ):
            raise ValueError("Invalid expectation")
        return self


Expectation = KnowledgeExpectation | ToolExpectation | PermissionExpectation | RefusalExpectation
EXPECTATION_MODELS = {
    "knowledge_qa": KnowledgeExpectation,
    "tool_calling": ToolExpectation,
    "permission_boundary": PermissionExpectation,
    "refusal_behavior": RefusalExpectation,
}


class TextFields(StrictModel):
    @field_validator("name", "description", "test_input", mode="before", check_fields=False)
    @classmethod
    def normalize(cls, value: object) -> object:
        if isinstance(value, str):
            if "\x00" in value:
                raise ValueError("Invalid text")
            return value.strip()
        return value

    @field_validator("description", check_fields=False)
    @classmethod
    def blank_description(cls, value: str | None) -> str | None:
        return value or None


class DatasetCreate(TextFields):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)


class DatasetUpdate(TextFields):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    status: Status | None = None

    @model_validator(mode="after")
    def valid_patch(self) -> Self:
        if not self.model_fields_set or any(
            name in self.model_fields_set and getattr(self, name) is None
            for name in ("name", "status", "test_input", "expected_behavior")
        ):
            raise ValueError("Invalid update")
        return self


class CaseCreate(DatasetCreate):
    case_type: CaseType
    test_input: str = Field(min_length=1, max_length=2000)
    expected_behavior: Expectation
    agent_id: UUID | None = None
    knowledge_base_id: UUID | None = None
    tool_id: UUID | None = None

    @model_validator(mode="before")
    @classmethod
    def select_expectation(cls, value: object) -> object:
        if (
            isinstance(value, dict)
            and isinstance(value.get("case_type"), str)
            and value["case_type"] in EXPECTATION_MODELS
        ):
            value = dict(value)
            value["expected_behavior"] = EXPECTATION_MODELS[value["case_type"]].model_validate(
                value.get("expected_behavior")
            )
        return value

    @model_validator(mode="after")
    def valid_references(self) -> Self:
        if not isinstance(self.expected_behavior, EXPECTATION_MODELS[self.case_type]):
            raise ValueError("Invalid expectation category")
        expected = self.expected_behavior
        if isinstance(expected, KnowledgeExpectation):
            valid = self.knowledge_base_id is not None and self.tool_id is None
        elif isinstance(expected, ToolExpectation):
            valid = self.knowledge_base_id is None and (self.tool_id is None) == (
                expected.outcome == "not_executed"
            )
        elif isinstance(expected, RefusalExpectation):
            valid = self.tool_id is None and (self.knowledge_base_id is not None) == (
                expected.routing_intent == "knowledge_qa"
            )
        else:
            allowed = (
                {
                    "agent_route": "agent_id",
                    "agent_configuration_read": "agent_id",
                    "knowledge_answer": "knowledge_base_id",
                    "tool_configuration_read": "tool_id",
                }.get(expected.operation)
                if expected.target_context == "same_workspace"
                else None
            )
            valid = all(
                getattr(self, key) is None or key == allowed
                for key in ("agent_id", "knowledge_base_id", "tool_id")
            )
        if not valid:
            raise ValueError("Invalid references")
        return self


class CaseUpdate(DatasetUpdate):
    test_input: str | None = Field(default=None, min_length=1, max_length=2000)
    expected_behavior: Expectation | None = None
    agent_id: UUID | None = None
    knowledge_base_id: UUID | None = None
    tool_id: UUID | None = None


class DatasetResponse(DatasetCreate):
    id: UUID
    workspace_id: UUID
    status: Status
    created_by: UUID
    created_at: datetime
    updated_at: datetime


class CaseSummary(DatasetResponse):
    dataset_id: UUID
    case_type: CaseType
    schema_version: Literal[1]
    agent_id: UUID | None
    knowledge_base_id: UUID | None
    tool_id: UUID | None


class CaseResponse(CaseSummary):
    test_input: str
    expected_behavior: Expectation


class DatasetListResponse(StrictModel):
    items: list[DatasetResponse]
    limit: int
    offset: int


class CaseListResponse(StrictModel):
    items: list[CaseSummary]
    limit: int
    offset: int
