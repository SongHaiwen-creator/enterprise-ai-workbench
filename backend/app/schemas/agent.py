from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import AgentStatus


class AgentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    system_prompt: str = Field(min_length=1, max_length=8000)

    @field_validator("name", "description", "system_prompt", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value


class AgentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    system_prompt: str | None = Field(default=None, min_length=1, max_length=8000)
    status: AgentStatus | None = None

    @field_validator("name", "description", "system_prompt", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @model_validator(mode="after")
    def require_valid_update(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        for field_name in ("name", "system_prompt", "status"):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        return self


class AgentSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    name: str
    description: str | None
    status: AgentStatus
    created_by: UUID
    created_at: datetime
    updated_at: datetime


class AgentConfigurationResponse(AgentSummaryResponse):
    system_prompt: str
