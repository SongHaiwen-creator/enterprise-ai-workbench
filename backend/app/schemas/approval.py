from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import (
    ApprovalDecisionStatus,
    ApprovalExecutionFailure,
    ApprovalExecutionStatus,
    ApprovalInvalidationReason,
)
from app.schemas.tool_calling import CreateITAccessRequestArguments, PublicToolReference

LEGAL_STATUS_PAIRS = frozenset(
    {
        (ApprovalDecisionStatus.PENDING, ApprovalExecutionStatus.NOT_STARTED),
        (ApprovalDecisionStatus.REJECTED, ApprovalExecutionStatus.NOT_STARTED),
        (ApprovalDecisionStatus.CANCELLED, ApprovalExecutionStatus.NOT_STARTED),
        (ApprovalDecisionStatus.EXPIRED, ApprovalExecutionStatus.NOT_STARTED),
        (ApprovalDecisionStatus.INVALIDATED, ApprovalExecutionStatus.NOT_STARTED),
        (ApprovalDecisionStatus.APPROVED, ApprovalExecutionStatus.SUCCEEDED),
        (ApprovalDecisionStatus.APPROVED, ApprovalExecutionStatus.FAILED),
    }
)


class ApprovalDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approve", "reject"]
    note: str | None = None

    @field_validator("note", mode="before")
    @classmethod
    def normalize_note(cls, value: object) -> object:
        if value is None or not isinstance(value, str):
            return value
        if any(
            (ord(character) < 32 and character not in "\n\t") or ord(character) == 127
            for character in value
        ):
            raise ValueError("Control characters are not allowed")
        value = value.strip()
        if not 1 <= len(value) <= 1000:
            raise ValueError("Note must contain 1 to 1000 characters")
        return value


class ApprovalCancelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ApprovalPartyReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: str


class ApprovalDecisionDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decided_by: ApprovalPartyReference | None
    decided_at: datetime
    note: str | None
    invalidation_reason: ApprovalInvalidationReason | None


class ITAccessRequestExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["it_access_request"] = "it_access_request"
    reference: str = Field(pattern=r"^ITAR-[0-9A-F]{12}$")
    system: Literal["production_database", "analytics_warehouse", "source_control"]
    access_level: Literal["read_only", "standard"]
    duration_days: int = Field(strict=True, ge=1, le=90)
    status: Literal["recorded"] = "recorded"


class ApprovalExecutionDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    executed_at: datetime
    failure_category: ApprovalExecutionFailure | None
    result: ITAccessRequestExecutionResult | None


class ApprovalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    workspace_id: UUID
    decision_status: ApprovalDecisionStatus
    execution_status: ApprovalExecutionStatus
    action_type: Literal["it_access_request.create"]
    tool: PublicToolReference
    agent: ApprovalPartyReference
    requester: ApprovalPartyReference
    arguments: CreateITAccessRequestArguments
    created_at: datetime
    expires_at: datetime
    decision: ApprovalDecisionDetail | None
    execution: ApprovalExecutionDetail | None

    @model_validator(mode="after")
    def enforce_invariants(self) -> Self:
        decision_status = self.decision_status
        execution_status = self.execution_status
        if (decision_status, execution_status) not in LEGAL_STATUS_PAIRS:
            raise ValueError("Illegal decision and execution status pair")
        if self.tool.tool_key != "create_it_access_request":
            raise ValueError("Approval arguments do not match the Tool")

        decision = self.decision
        if decision_status is ApprovalDecisionStatus.PENDING:
            if decision is not None:
                raise ValueError("Pending Approvals have no decision")
        else:
            if decision is None:
                raise ValueError("Terminal Approvals require a decision")
            system_closed = decision_status in {
                ApprovalDecisionStatus.EXPIRED,
                ApprovalDecisionStatus.INVALIDATED,
            }
            if system_closed and (decision.decided_by is not None or decision.note is not None):
                raise ValueError("System-closed Approvals have no human decider or note")
            if not system_closed and decision.decided_by is None:
                raise ValueError("Human decisions require a decider")
            if decision_status is ApprovalDecisionStatus.CANCELLED and decision.note is not None:
                raise ValueError("Cancellations have no note")
            if (decision_status is ApprovalDecisionStatus.INVALIDATED) != (
                decision.invalidation_reason is not None
            ):
                raise ValueError("Invalidation reason is required only for invalidated")
            if (
                decision_status is ApprovalDecisionStatus.EXPIRED
                and decision.decided_at != self.expires_at
            ):
                raise ValueError("Expiry time must equal expires_at")

        execution = self.execution
        if execution_status is ApprovalExecutionStatus.NOT_STARTED:
            if execution is not None:
                raise ValueError("Unstarted executions have no execution detail")
        elif execution is None:
            raise ValueError("Attempted executions require execution detail")
        elif execution_status is ApprovalExecutionStatus.SUCCEEDED:
            if execution.result is None or execution.failure_category is not None:
                raise ValueError("Succeeded executions require a result only")
        elif (
            execution.result is not None
            or execution.failure_category is not ApprovalExecutionFailure.ADAPTER_ERROR
        ):
            raise ValueError("Failed executions require adapter_error only")
        return self


class ApprovalListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ApprovalResponse]
    limit: int
    offset: int
