from datetime import date
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class GetReimbursementStatusArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GetEmployeeInformationArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: Literal["self"]


class CreateITAccessRequestArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    system: Literal[
        "production_database", "analytics_warehouse", "source_control"
    ]
    access_level: Literal["read_only", "standard"]
    business_justification: str = Field(min_length=10, max_length=500)
    duration_days: int = Field(strict=True, ge=1, le=90)

    @field_validator("business_justification", mode="before")
    @classmethod
    def normalize_justification(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        if any(ord(character) < 32 or ord(character) == 127 for character in value):
            raise ValueError("Control characters are not allowed")
        return value.strip()

    @model_validator(mode="after")
    def restrict_production_access(self) -> Self:
        if self.system == "production_database" and self.access_level != "read_only":
            raise ValueError("Production database access must be read_only")
        return self


class ReimbursementStatusResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["reimbursement_status"] = "reimbursement_status"
    reimbursement_reference: str = Field(pattern=r"^REIM-[0-9A-F]{8}$")
    status: Literal["submitted", "under_review", "approved", "rejected", "paid"]
    amount_minor: int = Field(strict=True, ge=0)
    currency: Literal["CNY"] = "CNY"
    submitted_on: date
    last_updated_on: date

    @model_validator(mode="after")
    def validate_dates(self) -> Self:
        if self.last_updated_on < self.submitted_on:
            raise ValueError("last_updated_on cannot precede submitted_on")
        return self


class EmployeeInformationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["employee_information"] = "employee_information"
    name: str = Field(min_length=1, max_length=255)
    email: str = Field(min_length=3, max_length=320)
    department: str = Field(min_length=1, max_length=255)
    job_title: str = Field(min_length=1, max_length=255)
    employment_status: Literal["active"] = "active"


ToolArguments = (
    GetReimbursementStatusArguments
    | GetEmployeeInformationArguments
    | CreateITAccessRequestArguments
)
ToolResult = Annotated[
    ReimbursementStatusResult | EmployeeInformationResult,
    Field(discriminator="type"),
]


class PublicToolReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_key: Literal[
        "get_reimbursement_status",
        "get_employee_information",
        "create_it_access_request",
    ]
    name: str


class ToolExecutedOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["executed"] = "executed"
    tool: PublicToolReference
    executed: Literal[True] = True
    approval_required: Literal[False] = False
    validated_arguments: GetReimbursementStatusArguments | GetEmployeeInformationArguments
    result: ToolResult
    message: str

    @model_validator(mode="after")
    def require_matching_contract(self) -> Self:
        expected = {
            "get_reimbursement_status": (
                GetReimbursementStatusArguments, "reimbursement_status"
            ),
            "get_employee_information": (
                GetEmployeeInformationArguments, "employee_information"
            ),
        }.get(self.tool.tool_key)
        if expected is None:
            raise ValueError("This Tool cannot execute immediately")
        argument_type, result_type = expected
        if not isinstance(self.validated_arguments, argument_type):
            raise ValueError("Tool arguments do not match the selected Tool")
        if self.result.type != result_type:
            raise ValueError("Tool result does not match the selected Tool")
        return self


class ToolApprovalRequiredOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["approval_required"] = "approval_required"
    tool: PublicToolReference
    executed: Literal[False] = False
    approval_required: Literal[True] = True
    validated_arguments: CreateITAccessRequestArguments
    result: None = None
    message: str

    @model_validator(mode="after")
    def require_sensitive_tool(self) -> Self:
        if self.tool.tool_key != "create_it_access_request":
            raise ValueError("Approval-required arguments do not match the Tool")
        return self


class ToolNotExecutedOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["not_executed"] = "not_executed"
    tool: None = None
    executed: Literal[False] = False
    approval_required: Literal[False] = False
    reason: Literal[
        "no_available_tool", "no_matching_tool", "missing_required_arguments"
    ]
    validated_arguments: None = None
    result: None = None
    message: str


ToolOutcome = Annotated[
    ToolExecutedOutcome | ToolApprovalRequiredOutcome | ToolNotExecutedOutcome,
    Field(discriminator="status"),
]
