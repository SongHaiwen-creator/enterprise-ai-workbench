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


class ToolRisk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ToolStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class ApprovalDecisionStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    INVALIDATED = "invalidated"


class ApprovalExecutionStatus(StrEnum):
    NOT_STARTED = "not_started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ApprovalInvalidationReason(StrEnum):
    REQUESTER_INELIGIBLE = "requester_ineligible"
    CAPABILITY_UNAVAILABLE = "capability_unavailable"
    CONFIGURATION_DRIFT = "configuration_drift"


class ApprovalExecutionFailure(StrEnum):
    ADAPTER_ERROR = "adapter_error"


class ExecutionLogOperation(StrEnum):
    AGENT_ROUTE = "agent_route"
    KNOWLEDGE_ANSWER = "knowledge_answer"
    APPROVAL_DECISION = "approval_decision"
    APPROVAL_CANCEL = "approval_cancel"


class ExecutionLogStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ExecutionLogOutcome(StrEnum):
    KNOWLEDGE_ANSWERED = "knowledge_answered"
    KNOWLEDGE_UNSUPPORTED = "knowledge_unsupported"
    TOOL_EXECUTED = "tool_executed"
    TOOL_APPROVAL_REQUIRED = "tool_approval_required"
    TOOL_NOT_EXECUTED = "tool_not_executed"
    UNSUPPORTED_REQUEST = "unsupported_request"
    APPROVED_EXECUTION_SUCCEEDED = "approved_execution_succeeded"
    APPROVED_EXECUTION_FAILED = "approved_execution_failed"
    REJECTED = "rejected"
    INVALIDATED = "invalidated"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class ExecutionLogErrorCategory(StrEnum):
    AGENT_NOT_FOUND = "agent_not_found"
    AGENT_INACTIVE = "agent_inactive"
    KNOWLEDGE_BASE_REQUIRED = "knowledge_base_required"
    KNOWLEDGE_BASE_NOT_FOUND = "knowledge_base_not_found"
    KNOWLEDGE_BASE_INACTIVE = "knowledge_base_inactive"
    INPUT_TOO_LARGE = "input_too_large"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_ERROR = "provider_error"
    TOOL_CONFIGURATION_ERROR = "tool_configuration_error"
    TOOL_UNAVAILABLE = "tool_unavailable"
    TOOL_EXECUTION_FAILED = "tool_execution_failed"
    ACCESS_DENIED = "access_denied"
    APPROVAL_NOT_FOUND = "approval_not_found"
    APPROVAL_NOT_PENDING = "approval_not_pending"
    APPROVAL_EXPIRED = "approval_expired"
    APPROVAL_INVALIDATED = "approval_invalidated"
    APPROVAL_BUSY = "approval_busy"
    APPROVAL_EXECUTION_FAILED = "approval_execution_failed"
    INTERNAL_ERROR = "internal_error"


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
