from uuid import UUID

import pytest
from pydantic import TypeAdapter, ValidationError

from app.schemas.tool_calling import (
    CreateITAccessRequestArguments,
    GetEmployeeInformationArguments,
    GetReimbursementStatusArguments,
    ToolOutcome,
)
from app.services.tool_execution import (
    ToolExecutionContext,
    get_employee_information,
    get_reimbursement_status,
)


def context() -> ToolExecutionContext:
    return ToolExecutionContext(
        workspace_id=UUID("11111111-1111-1111-1111-111111111111"),
        user_id=UUID("22222222-2222-2222-2222-222222222222"),
        user_name="Signed In User",
        user_email="signed.in@example.com",
        agent_id=UUID("33333333-3333-3333-3333-333333333333"),
    )


def test_mock_adapters_are_deterministic_and_backend_identity_owned() -> None:
    first = get_reimbursement_status(context(), GetReimbursementStatusArguments())
    second = get_reimbursement_status(context(), GetReimbursementStatusArguments())
    employee = get_employee_information(
        context(), GetEmployeeInformationArguments(subject="self")
    )

    assert first == second
    assert first.reimbursement_reference.startswith("REIM-")
    assert first.currency == "CNY"
    assert first.last_updated_on >= first.submitted_on
    assert employee.name == "Signed In User"
    assert employee.email == "signed.in@example.com"
    assert employee.employment_status == "active"


@pytest.mark.parametrize(
    "payload",
    [
        {
            "system": "production_database", "access_level": "standard",
            "business_justification": "Valid business reason", "duration_days": 14,
        },
        {
            "system": "source_control", "access_level": "standard",
            "business_justification": "short", "duration_days": 14,
        },
        {
            "system": "source_control", "access_level": "standard",
            "business_justification": "Valid\nreason", "duration_days": 14,
        },
        {
            "system": "source_control", "access_level": "standard",
            "business_justification": "Valid business reason", "duration_days": 1.0,
        },
        {
            "system": "source_control", "access_level": "standard",
            "business_justification": "Valid business reason", "duration_days": 14,
            "requester": "other",
        },
    ],
)
def test_it_access_arguments_fail_closed(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        CreateITAccessRequestArguments.model_validate(payload)


def test_public_tool_outcome_rejects_cross_tool_result() -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(ToolOutcome).validate_python(
            {
                "status": "executed",
                "tool": {
                    "tool_key": "get_employee_information",
                    "name": "Employee",
                },
                "executed": True,
                "approval_required": False,
                "validated_arguments": {"subject": "self"},
                "result": {
                    "type": "reimbursement_status",
                    "reimbursement_reference": "REIM-1234ABCD",
                    "status": "paid",
                    "amount_minor": 10000,
                    "currency": "CNY",
                    "submitted_on": "2026-09-01",
                    "last_updated_on": "2026-09-02",
                },
                "message": "Completed",
            }
        )
