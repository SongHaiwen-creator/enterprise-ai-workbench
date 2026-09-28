from copy import deepcopy
from typing import Any

import pytest
from pydantic import ValidationError

from app.schemas.approval import (
    LEGAL_STATUS_PAIRS,
    ApprovalCancelRequest,
    ApprovalDecisionRequest,
    ApprovalResponse,
)

EXPIRES_AT = "2026-10-01T10:00:00Z"
ARGUMENTS = {
    "system": "production_database",
    "access_level": "read_only",
    "business_justification": "Investigate approved production incidents.",
    "duration_days": 14,
}
RESULT = {
    "type": "it_access_request",
    "reference": "ITAR-3FA91C07B2D4",
    "system": "production_database",
    "access_level": "read_only",
    "duration_days": 14,
    "status": "recorded",
}
REVIEWER = {"id": "00000000-0000-0000-0000-000000000009", "name": "Admin One"}


def response(decision_status: str, execution_status: str) -> dict[str, Any]:
    decision: dict[str, Any] | None = {
        "decided_by": REVIEWER,
        "decided_at": "2026-09-28T11:00:00Z",
        "note": None,
        "invalidation_reason": None,
    }
    if decision_status == "pending":
        decision = None
    elif decision_status == "expired":
        decision = {**decision, "decided_by": None, "decided_at": EXPIRES_AT}
    elif decision_status == "invalidated":
        decision = {
            **decision, "decided_by": None, "invalidation_reason": "configuration_drift"
        }
    execution: dict[str, Any] | None = None
    if execution_status == "succeeded":
        execution = {
            "executed_at": "2026-09-28T11:00:00Z", "failure_category": None, "result": RESULT
        }
    elif execution_status == "failed":
        execution = {
            "executed_at": "2026-09-28T11:00:00Z",
            "failure_category": "adapter_error",
            "result": None,
        }
    return {
        "id": "00000000-0000-0000-0000-000000000001",
        "workspace_id": "00000000-0000-0000-0000-000000000002",
        "decision_status": decision_status,
        "execution_status": execution_status,
        "action_type": "it_access_request.create",
        "tool": {"tool_key": "create_it_access_request", "name": "Create IT access request"},
        "agent": {"id": "00000000-0000-0000-0000-000000000003", "name": "Assistant"},
        "requester": {"id": "00000000-0000-0000-0000-000000000004", "name": "Employee"},
        "arguments": ARGUMENTS,
        "created_at": "2026-09-28T10:00:00Z",
        "expires_at": EXPIRES_AT,
        "decision": decision,
        "execution": execution,
    }


@pytest.mark.parametrize(
    ("decision_status", "execution_status"),
    sorted((decision.value, execution.value) for decision, execution in LEGAL_STATUS_PAIRS),
)
def test_every_legal_pair_validates(decision_status: str, execution_status: str) -> None:
    ApprovalResponse.model_validate(response(decision_status, execution_status))


@pytest.mark.parametrize(
    ("decision_status", "execution_status"),
    [
        ("approved", "not_started"),
        ("pending", "succeeded"),
        ("rejected", "failed"),
        ("invalidated", "failed"),
        ("expired", "succeeded"),
    ],
)
def test_illegal_pairs_are_rejected(decision_status: str, execution_status: str) -> None:
    payload = response(decision_status, "not_started")
    payload["execution_status"] = execution_status
    with pytest.raises(ValidationError):
        ApprovalResponse.model_validate(payload)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda item: item.update(decision=response("rejected", "not_started")["decision"]),
        lambda item: item["decision"].update(decided_by=REVIEWER),
        lambda item: item["decision"].update(invalidation_reason=None),
        lambda item: item["decision"].update(note="Stored note"),
        lambda item: item.update(tool={"tool_key": "get_reimbursement_status", "name": "X"}),
        lambda item: item.update(arguments={**ARGUMENTS, "extra": 1}),
        lambda item: item.update(tool_id="00000000-0000-0000-0000-000000000005"),
    ],
)
def test_invalidated_representation_invariants(mutate: Any) -> None:
    payload = deepcopy(response("invalidated", "not_started"))
    mutate(payload)
    with pytest.raises(ValidationError):
        ApprovalResponse.model_validate(payload)


def test_pending_requires_no_decision_and_expired_uses_expires_at() -> None:
    pending = response("pending", "not_started")
    pending["decision"] = response("rejected", "not_started")["decision"]
    with pytest.raises(ValidationError):
        ApprovalResponse.model_validate(pending)

    expired = response("expired", "not_started")
    expired["decision"]["decided_at"] = "2026-09-30T10:00:00Z"
    with pytest.raises(ValidationError):
        ApprovalResponse.model_validate(expired)


def test_execution_detail_invariants() -> None:
    succeeded = response("approved", "succeeded")
    succeeded["execution"]["result"] = None
    with pytest.raises(ValidationError):
        ApprovalResponse.model_validate(succeeded)

    failed = response("approved", "failed")
    failed["execution"]["result"] = RESULT
    with pytest.raises(ValidationError):
        ApprovalResponse.model_validate(failed)

    unstarted = response("rejected", "not_started")
    unstarted["execution"] = response("approved", "failed")["execution"]
    with pytest.raises(ValidationError):
        ApprovalResponse.model_validate(unstarted)


@pytest.mark.parametrize(
    "field",
    [
        {"validated_arguments": ARGUMENTS},
        {"tool_id": "00000000-0000-0000-0000-000000000005"},
        {"agent_id": "00000000-0000-0000-0000-000000000003"},
        {"risk_level": "low"},
        {"policy": {"required_reviewer_roles": ["employee"]}},
        {"executor_key": "http"},
        {"requester_id": "00000000-0000-0000-0000-000000000004"},
    ],
)
def test_decision_body_rejects_any_execution_field(field: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        ApprovalDecisionRequest.model_validate({"decision": "approve", **field})


def test_decision_note_rules() -> None:
    assert ApprovalDecisionRequest(decision="approve").note is None
    assert ApprovalDecisionRequest(decision="reject", note=None).note is None
    assert ApprovalDecisionRequest(
        decision="approve", note="  Line one\n\tLine two  "
    ).note == "Line one\n\tLine two"
    for invalid in ["", "   ", "a" * 1001, "bad\x00note", "bad\x1bnote", "bad\x7fnote"]:
        with pytest.raises(ValidationError):
            ApprovalDecisionRequest(decision="approve", note=invalid)
    for decision in ["cancel", "APPROVE", "approved", ""]:
        with pytest.raises(ValidationError):
            ApprovalDecisionRequest.model_validate({"decision": decision})


def test_cancel_body_accepts_only_empty_object() -> None:
    ApprovalCancelRequest.model_validate({})
    with pytest.raises(ValidationError):
        ApprovalCancelRequest.model_validate({"note": "withdraw"})
