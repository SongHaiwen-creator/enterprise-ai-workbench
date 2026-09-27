from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import ToolStatus


class ToolCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=5000)

    @field_validator("name", "description", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class ToolUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, min_length=1, max_length=5000)
    status: ToolStatus | None = None

    @field_validator("name", "description", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def require_non_null_update(self) -> Self:
        supplied = self.model_fields_set
        if not supplied:
            raise ValueError("At least one field must be provided")
        if any(getattr(self, field) is None for field in supplied):
            raise ValueError("Updated fields cannot be null")
        return self


class ToolConfigurationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    workspace_id: UUID
    tool_key: str
    name: str
    description: str
    operation_type: Literal["read_only", "write_sensitive"]
    risk_level: Literal["low", "medium", "high"]
    status: ToolStatus
    created_by: UUID
    created_at: datetime
    updated_at: datetime
