from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from pydantic import BaseModel

from app.models.enums import MembershipRole, ToolRisk
from app.schemas.tool_calling import (
    CreateITAccessRequestArguments,
    EmployeeInformationResult,
    GetEmployeeInformationArguments,
    GetReimbursementStatusArguments,
    ReimbursementStatusResult,
)


class ToolOperationType(StrEnum):
    READ_ONLY = "read_only"
    WRITE_SENSITIVE = "write_sensitive"


ToolAdapter = Callable[[object, BaseModel], BaseModel | Mapping[str, Any]]


@dataclass(frozen=True, slots=True)
class ApprovalPolicy:
    """Code-owned reviewer policy copied into every Approval snapshot."""

    policy_version: str
    required_reviewer_roles: tuple[MembershipRole, ...]
    self_approval_allowed: bool
    ttl_hours: int


@dataclass(frozen=True, slots=True)
class ApprovalRequirement:
    """Execution-critical constants for a Tool that runs only after approval.

    Any change to the argument model, business validation, write executor, or
    result model must bump ``tool_definition_version`` or ``executor_key``.
    """

    action_type: str
    tool_definition_version: str
    executor_key: str
    executor_type: str
    policy: ApprovalPolicy


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    tool_key: str
    selector_name: str
    selector_description: str
    argument_model: type[BaseModel]
    result_model: type[BaseModel] | None
    operation_type: ToolOperationType
    risk: ToolRisk
    immediate_execution: bool
    adapter: ToolAdapter | None
    approval: ApprovalRequirement | None = None


IT_ACCESS_APPROVAL_POLICY = ApprovalPolicy(
    policy_version="it-access-approval-v1",
    required_reviewer_roles=(MembershipRole.SYSTEM_ADMIN,),
    self_approval_allowed=False,
    ttl_hours=72,
)


def _reimbursement_adapter(context: object, arguments: BaseModel) -> BaseModel:
    from app.services.tool_execution import get_reimbursement_status

    assert isinstance(arguments, GetReimbursementStatusArguments)
    return get_reimbursement_status(context, arguments)


def _employee_adapter(context: object, arguments: BaseModel) -> BaseModel:
    from app.services.tool_execution import get_employee_information

    assert isinstance(arguments, GetEmployeeInformationArguments)
    return get_employee_information(context, arguments)


TOOL_REGISTRY: Mapping[str, ToolDefinition] = MappingProxyType(
    {
        "get_reimbursement_status": ToolDefinition(
            tool_key="get_reimbursement_status",
            selector_name="Get reimbursement status",
            selector_description=(
                "Return only the signed-in employee's own latest reimbursement "
                "status. Use no identity or reference arguments."
            ),
            argument_model=GetReimbursementStatusArguments,
            result_model=ReimbursementStatusResult,
            operation_type=ToolOperationType.READ_ONLY,
            risk=ToolRisk.LOW,
            immediate_execution=True,
            adapter=_reimbursement_adapter,
        ),
        "get_employee_information": ToolDefinition(
            tool_key="get_employee_information",
            selector_name="Get employee information",
            selector_description=(
                "Return only the signed-in employee's own profile. Pass subject=self. "
                "Decline requests about any other person."
            ),
            argument_model=GetEmployeeInformationArguments,
            result_model=EmployeeInformationResult,
            operation_type=ToolOperationType.READ_ONLY,
            risk=ToolRisk.LOW,
            immediate_execution=True,
            adapter=_employee_adapter,
        ),
        "create_it_access_request": ToolDefinition(
            tool_key="create_it_access_request",
            selector_name="Create IT access request",
            selector_description=(
                "Validate a request for the signed-in employee's IT access. This "
                "capability requires human approval and will not execute. Decline "
                "when required arguments are absent."
            ),
            argument_model=CreateITAccessRequestArguments,
            result_model=None,
            operation_type=ToolOperationType.WRITE_SENSITIVE,
            risk=ToolRisk.HIGH,
            immediate_execution=False,
            adapter=None,
            approval=ApprovalRequirement(
                action_type="it_access_request.create",
                tool_definition_version="create_it_access_request.v1",
                executor_key="mock_it_access_request.v1",
                executor_type="local_mock",
                policy=IT_ACCESS_APPROVAL_POLICY,
            ),
        ),
    }
)

RESERVED_SELECTOR_TOOL = "decline_tool_selection"


def get_tool_definition(tool_key: str) -> ToolDefinition | None:
    return TOOL_REGISTRY.get(tool_key)
