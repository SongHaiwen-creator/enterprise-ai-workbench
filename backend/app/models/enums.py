from enum import StrEnum
from typing import TypeVar

from sqlalchemy import String
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.types import TypeDecorator


class UserStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class WorkspaceStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class KnowledgeBaseStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class AgentStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    DISABLED = "disabled"


class DocumentFileType(StrEnum):
    PDF = "pdf"
    TXT = "txt"
    MARKDOWN = "md"


class DocumentStatus(StrEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"
    DISABLED = "disabled"


class MembershipRole(StrEnum):
    EMPLOYEE = "employee"
    KNOWLEDGE_ADMIN = "knowledge_admin"
    AGENT_ADMIN = "agent_admin"
    SYSTEM_ADMIN = "system_admin"


class MembershipStatus(StrEnum):
    ACTIVE = "active"
    INVITED = "invited"
    DISABLED = "disabled"


EnumType = TypeVar("EnumType", bound=StrEnum)


class StringEnumType(TypeDecorator[EnumType]):
    """Persist a StrEnum's explicit value in a VARCHAR column."""

    impl = String
    cache_ok = True

    def __init__(self, enum_type: type[EnumType], *, length: int = 32) -> None:
        self.enum_type = enum_type
        super().__init__(length=length)

    def process_bind_param(
        self,
        value: EnumType | str | None,
        dialect: Dialect,
    ) -> str | None:
        del dialect
        if value is None:
            return None
        return self.enum_type(value).value

    def process_result_value(
        self,
        value: str | None,
        dialect: Dialect,
    ) -> EnumType | None:
        del dialect
        if value is None:
            return None
        return self.enum_type(value)
