from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

from app.models.enums import MembershipRole, MembershipStatus


class MembershipCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: UUID
    role: MembershipRole = MembershipRole.EMPLOYEE


class MembershipUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: MembershipRole | None = None
    status: MembershipStatus | None = None

    @model_validator(mode="after")
    def require_non_null_update(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("at least one of role or status must be provided")
        if any(getattr(self, field_name) is None for field_name in self.model_fields_set):
            raise ValueError("role and status cannot be null")
        return self


class MembershipResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    workspace_id: UUID
    role: MembershipRole
    status: MembershipStatus
    joined_at: datetime | None


class WorkspaceMemberResponse(BaseModel):
    id: UUID
    user_id: UUID
    email: str
    name: str
    role: MembershipRole
    status: MembershipStatus
    joined_at: datetime | None
