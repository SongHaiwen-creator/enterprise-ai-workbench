import hashlib
from dataclasses import dataclass
from datetime import date, timedelta
from uuid import UUID

from app.schemas.tool_calling import (
    EmployeeInformationResult,
    GetEmployeeInformationArguments,
    GetReimbursementStatusArguments,
    ReimbursementStatusResult,
)


@dataclass(frozen=True, slots=True)
class ToolExecutionContext:
    workspace_id: UUID
    user_id: UUID
    user_name: str
    user_email: str
    agent_id: UUID


def get_reimbursement_status(
    context: object,
    arguments: GetReimbursementStatusArguments,
) -> ReimbursementStatusResult:
    del arguments
    if not isinstance(context, ToolExecutionContext):
        raise TypeError("Invalid Tool execution context")
    digest = hashlib.sha256(
        b"feature012-reimbursement-v1|"
        + context.workspace_id.bytes
        + context.user_id.bytes
    ).digest()
    statuses = ("submitted", "under_review", "approved", "rejected", "paid")
    submitted_on = date(2026, 9, 1) + timedelta(days=digest[7] % 15)
    return ReimbursementStatusResult(
        reimbursement_reference=f"REIM-{digest[0:4].hex().upper()}",
        status=statuses[digest[4] % len(statuses)],
        amount_minor=10000 + (int.from_bytes(digest[5:7], "big") % 50001),
        submitted_on=submitted_on,
        last_updated_on=submitted_on + timedelta(days=1 + digest[8] % 7),
    )


def get_employee_information(
    context: object,
    arguments: GetEmployeeInformationArguments,
) -> EmployeeInformationResult:
    del arguments
    if not isinstance(context, ToolExecutionContext):
        raise TypeError("Invalid Tool execution context")
    digest = hashlib.sha256(
        b"feature012-employee-v1|" + context.workspace_id.bytes + context.user_id.bytes
    ).digest()
    profile = (
        ("Enterprise Operations", "Operations Specialist"),
        ("Finance", "Finance Analyst"),
        ("People", "People Coordinator"),
        ("Technology", "Software Engineer"),
    )[digest[0] % 4]
    return EmployeeInformationResult(
        name=context.user_name,
        email=context.user_email,
        department=profile[0],
        job_title=profile[1],
    )
