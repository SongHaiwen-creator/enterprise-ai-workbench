from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from app.models.enums import (
    ExecutionLogErrorCategory,
    ExecutionLogOperation,
    ExecutionLogOutcome,
    ExecutionLogStatus,
)
from app.schemas.agent_routing import RoutingIntent
from app.schemas.approval import ApprovalPartyReference
from app.schemas.tool_calling import PublicToolReference

SERVER_IDENTIFIER_PATTERN = r"^[A-Za-z0-9._:-]{1,64}$"


class ExecutionLogDetails(BaseModel):
    """The only keys an execution log may carry in ``details`` (spec 8.2)."""

    model_config = ConfigDict(extra="forbid", strict=True)

    tool_not_executed_reason: (
        Literal["no_available_tool", "no_matching_tool", "missing_required_arguments"]
        | None
    ) = None
    citation_count: StrictInt | None = Field(default=None, ge=0, le=100)
    generation_model: str | None = Field(default=None, pattern=SERVER_IDENTIFIER_PATTERN)
    prompt_version: str | None = Field(default=None, pattern=SERVER_IDENTIFIER_PATTERN)
    input_tokens: StrictInt | None = Field(default=None, ge=0)
    output_tokens: StrictInt | None = Field(default=None, ge=0)
    total_tokens: StrictInt | None = Field(default=None, ge=0)
    decision: Literal["approve", "reject"] | None = None


class ExecutionLogResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    workspace_id: UUID
    operation: ExecutionLogOperation
    routing_intent: RoutingIntent | None
    status: ExecutionLogStatus
    outcome: ExecutionLogOutcome | None
    error_category: ExecutionLogErrorCategory | None
    http_status: int = Field(ge=100, le=599)
    latency_ms: int = Field(ge=0)
    user: ApprovalPartyReference
    agent: ApprovalPartyReference | None
    tool: PublicToolReference | None
    approval_id: UUID | None
    knowledge_base: ApprovalPartyReference | None
    details: ExecutionLogDetails
    created_at: datetime

    @model_validator(mode="after")
    def enforce_status_consistency(self) -> Self:
        failed = self.status is ExecutionLogStatus.FAILED
        if failed != (self.error_category is not None):
            raise ValueError("error_category must be set exactly for failed records")
        if (not failed) != (200 <= self.http_status <= 299):
            raise ValueError("http_status does not match status")
        if (
            self.routing_intent is not None
            and self.operation is not ExecutionLogOperation.AGENT_ROUTE
        ):
            raise ValueError("routing_intent is only recorded for agent_route")
        return self


class ExecutionLogListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ExecutionLogResponse]
    limit: int
    offset: int
