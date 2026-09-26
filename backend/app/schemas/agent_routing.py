from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.answer import GroundedAnswerResponse


class RoutingIntent(StrEnum):
    KNOWLEDGE_QA = "knowledge_qa"
    TOOL_REQUEST = "tool_request"
    UNSUPPORTED = "unsupported"


class AgentRouteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request: str = Field(min_length=1, max_length=2000)
    knowledge_base_id: UUID | None = None

    @field_validator("request", mode="before")
    @classmethod
    def strip_request(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value


class ModelRoutingOutput(BaseModel):
    """The entire model-owned output; public outcomes remain server-owned."""

    model_config = ConfigDict(extra="forbid")

    intent: RoutingIntent


class ToolNotExecutedOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["not_executed"]
    required_capability: Literal["enterprise_tool"]
    message: str


class UnsupportedOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["unsupported"]
    message: str


class KnowledgeRouteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request: str
    intent: Literal[RoutingIntent.KNOWLEDGE_QA]
    outcome: GroundedAnswerResponse


class ToolRouteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request: str
    intent: Literal[RoutingIntent.TOOL_REQUEST]
    outcome: ToolNotExecutedOutcome


class UnsupportedRouteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request: str
    intent: Literal[RoutingIntent.UNSUPPORTED]
    outcome: UnsupportedOutcome


AgentRouteResponse = Annotated[
    KnowledgeRouteResponse | ToolRouteResponse | UnsupportedRouteResponse,
    Field(discriminator="intent"),
]
