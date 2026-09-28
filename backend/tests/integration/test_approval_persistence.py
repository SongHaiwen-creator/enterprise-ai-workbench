import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.enums import MembershipRole
from tests.integration.approval_support import (
    Scenario,
    make_membership,
    make_scenario,
    make_user,
    make_workspace,
)

pytestmark = pytest.mark.integration
HASH = "a" * 64
NOW = datetime(2026, 9, 28, 10, 0, tzinfo=UTC)
EXPIRES = NOW + timedelta(hours=72)
AUTO: Any = object()


def approval_values(scenario: Scenario, **overrides: Any) -> dict[str, Any]:
    """A legal pending row; timestamps follow the statuses unless overridden."""

    values: dict[str, Any] = {
        "id": uuid4(),
        "workspace_id": scenario.workspace.id,
        "requester_id": scenario.requester.id,
        "agent_id": scenario.agent.id,
        "tool_id": scenario.tool.id,
        "action_type": "it_access_request.create",
        "canonical_arguments": "{}",
        "canonical_arguments_sha256": HASH,
        "capability_snapshot": "{}",
        "policy_snapshot": "{}",
        "snapshot_sha256": HASH,
        "decision_status": "pending",
        "decided_by": None,
        "decided_at": AUTO,
        "decision_note": None,
        "invalidation_reason": None,
        "invalidation_triggered_by": None,
        "execution_status": "not_started",
        "executed_at": AUTO,
        "execution_failure_category": None,
        "created_at": NOW,
        "expires_at": EXPIRES,
    }
    values.update(overrides)
    if values["decided_at"] is AUTO:
        if values["decision_status"] == "pending":
            values["decided_at"] = None
        elif values["decision_status"] == "expired":
            values["decided_at"] = values["expires_at"]
        else:
            values["decided_at"] = NOW + timedelta(hours=1)
    if values["executed_at"] is AUTO:
        values["executed_at"] = (
            None if values["execution_status"] == "not_started" else NOW + timedelta(hours=1)
        )
    return values


def terminal(scenario: Scenario, status: str, **overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"decision_status": status}
    if status in {"approved", "rejected"}:
        base["decided_by"] = scenario.reviewer.id
    if status == "cancelled":
        base["decided_by"] = scenario.requester.id
    if status == "invalidated":
        base["invalidation_reason"] = "configuration_drift"
        base["invalidation_triggered_by"] = scenario.reviewer.id
    if status == "approved":
        base["execution_status"] = "succeeded"
    base.update(overrides)
    return base


def insert_approval(session: Session, values: dict[str, Any]) -> UUID:
    columns = ", ".join(values)
    placeholders = ", ".join(
        f"CAST(:{name} AS jsonb)"
        if name in {"canonical_arguments", "capability_snapshot", "policy_snapshot"}
        else f":{name}"
        for name in values
    )
    session.execute(text(f"INSERT INTO approvals ({columns}) VALUES ({placeholders})"), values)
    return values["id"]


def insert_mock(
    session: Session, scenario: Scenario, approval_id: UUID, **overrides: Any
) -> None:
    values: dict[str, Any] = {
        "workspace_id": scenario.workspace.id,
        "approval_id": approval_id,
        "requester_id": scenario.requester.id,
        "reference": f"ITAR-{uuid4().hex[:12].upper()}",
        "system": "production_database",
        "access_level": "read_only",
        "duration_days": 14,
        "status": "recorded",
    }
    values.update(overrides)
    session.execute(
        text(
            "INSERT INTO mock_it_access_requests (workspace_id, approval_id, requester_id, "
            "reference, system, access_level, duration_days, status) VALUES "
            "(:workspace_id, :approval_id, :requester_id, :reference, :system, "
            ":access_level, :duration_days, :status)"
        ),
        values,
    )


def rejected(session: Session, action: Callable[[], object]) -> None:
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            action()


def test_every_legal_status_pair_is_accepted(db_session: Session) -> None:
    scenario = make_scenario(db_session)
    rows = [
        {},
        terminal(scenario, "rejected", decision_note="Not justified."),
        terminal(scenario, "cancelled"),
        terminal(scenario, "expired"),
        terminal(scenario, "invalidated"),
        terminal(
            scenario, "approved", execution_status="failed",
            execution_failure_category="adapter_error",
        ),
        terminal(scenario, "approved", decision_note="ok"),
    ]
    approval_id = None
    for index, overrides in enumerate(rows):
        values = approval_values(scenario, snapshot_sha256=f"{index:064x}", **overrides)
        approval_id = insert_approval(db_session, values)
    assert approval_id is not None
    insert_mock(db_session, scenario, approval_id)
    db_session.flush()


ILLEGAL_ROWS: dict[str, Callable[[Scenario], dict[str, Any]]] = {
    "unknown_decision": lambda s: {"decision_status": "done", "decided_at": NOW},
    "unknown_execution": lambda s: {"execution_status": "running"},
    "pending_succeeded": lambda s: {"execution_status": "succeeded"},
    "approved_not_started": lambda s: terminal(s, "approved", execution_status="not_started"),
    "rejected_failed": lambda s: terminal(
        s, "rejected", execution_status="failed", execution_failure_category="adapter_error"
    ),
    "self_approval": lambda s: terminal(s, "approved", decided_by=s.requester.id),
    "self_rejection": lambda s: terminal(s, "rejected", decided_by=s.requester.id),
    "non_requester_cancel": lambda s: terminal(s, "cancelled", decided_by=s.reviewer.id),
    "expired_with_decider": lambda s: terminal(s, "expired", decided_by=s.reviewer.id),
    "failed_without_category": lambda s: terminal(s, "approved", execution_status="failed"),
    "category_without_failure": lambda s: terminal(
        s, "approved", execution_failure_category="adapter_error"
    ),
    "unknown_category": lambda s: terminal(
        s, "approved", execution_status="failed", execution_failure_category="timeout"
    ),
    "invalidated_without_reason": lambda s: terminal(
        s, "invalidated", invalidation_reason=None
    ),
    "invalidated_without_trigger": lambda s: terminal(
        s, "invalidated", invalidation_triggered_by=None
    ),
    "invalidated_by_requester": lambda s: terminal(
        s, "invalidated", invalidation_triggered_by=s.requester.id
    ),
    "unknown_invalidation_reason": lambda s: terminal(
        s, "invalidated", invalidation_reason="timeout"
    ),
    "reason_on_rejected": lambda s: terminal(
        s, "rejected", invalidation_reason="configuration_drift"
    ),
    "note_on_pending": lambda s: {"decision_note": "note"},
    "note_on_cancelled": lambda s: terminal(s, "cancelled", decision_note="note"),
    "note_on_invalidated": lambda s: terminal(s, "invalidated", decision_note="note"),
    "empty_note": lambda s: terminal(s, "rejected", decision_note=""),
    "long_note": lambda s: terminal(s, "rejected", decision_note="n" * 1001),
    "malformed_arguments_hash": lambda s: {"canonical_arguments_sha256": "A" * 64},
    "malformed_snapshot_hash": lambda s: {"snapshot_sha256": "xyz"},
    "arguments_not_object": lambda s: {"canonical_arguments": "[]"},
    "capability_not_object": lambda s: {"capability_snapshot": "1"},
    "policy_not_object": lambda s: {"policy_snapshot": "\"policy\""},
    "unknown_action": lambda s: {"action_type": "payroll.change"},
    "terminal_without_decided_at": lambda s: terminal(s, "rejected", decided_at=None),
    "pending_with_decided_at": lambda s: {"decided_at": NOW},
    "expired_decided_at_not_expiry": lambda s: terminal(
        s, "expired", decided_at=NOW + timedelta(hours=1)
    ),
    "expiry_not_after_creation": lambda s: {"expires_at": NOW},
    "attempt_without_executed_at": lambda s: terminal(s, "approved", executed_at=None),
    "unstarted_with_executed_at": lambda s: {"executed_at": NOW},
}


@pytest.mark.parametrize("case", sorted(ILLEGAL_ROWS))
def test_database_rejects_illegal_approval_rows(db_session: Session, case: str) -> None:
    scenario = make_scenario(db_session)
    values = approval_values(scenario, **ILLEGAL_ROWS[case](scenario))

    rejected(db_session, lambda: insert_approval(db_session, values))


def test_composite_foreign_keys_bind_rows_to_the_workspace(db_session: Session) -> None:
    scenario = make_scenario(db_session)
    outsider = make_user(db_session, "Outsider")
    other_workspace = make_workspace(db_session)
    make_membership(db_session, outsider, other_workspace, MembershipRole.SYSTEM_ADMIN)
    foreign = make_scenario(db_session)

    for overrides in (
        {"requester_id": outsider.id},
        terminal(scenario, "rejected", decided_by=outsider.id),
        terminal(scenario, "invalidated", invalidation_triggered_by=outsider.id),
        {"agent_id": foreign.agent.id},
        {"tool_id": foreign.tool.id},
        {"workspace_id": foreign.workspace.id},
    ):
        values = approval_values(scenario, **overrides)
        rejected(db_session, lambda v=values: insert_approval(db_session, v))


def test_pending_dedupe_is_partial_and_mock_rows_are_unique(db_session: Session) -> None:
    scenario = make_scenario(db_session)
    insert_approval(db_session, approval_values(scenario))
    rejected(db_session, lambda: insert_approval(db_session, approval_values(scenario)))
    for status in ("cancelled", "rejected", "expired", "invalidated"):
        insert_approval(db_session, approval_values(scenario, **terminal(scenario, status)))
    other_requester = make_user(db_session, "Second Requester")
    make_membership(db_session, other_requester, scenario.workspace)
    insert_approval(db_session, approval_values(scenario, requester_id=other_requester.id))

    approved = insert_approval(
        db_session, approval_values(scenario, **terminal(scenario, "approved"))
    )
    insert_mock(db_session, scenario, approved)
    rejected(db_session, lambda: insert_mock(db_session, scenario, approved))

    foreign = make_scenario(db_session)
    rejected(db_session, lambda: insert_mock(
        db_session, foreign, approved, requester_id=foreign.requester.id
    ))
    for overrides in (
        {"access_level": "standard"},
        {"system": "payroll"},
        {"duration_days": 91},
        {"status": "pending"},
        {"reference": "ITAR-lowercase00"},
    ):
        values = approval_values(
            scenario, snapshot_sha256=uuid4().hex * 2, **terminal(scenario, "approved")
        )
        insert_approval(db_session, values)
        rejected(
            db_session,
            lambda o=overrides, v=values: insert_mock(db_session, scenario, v["id"], **o),
        )


def test_approval_json_columns_round_trip(db_session: Session) -> None:
    scenario = make_scenario(db_session)
    approval_id = insert_approval(
        db_session,
        approval_values(scenario, canonical_arguments=json.dumps({"b": 1, "a": "季"})),
    )
    stored = db_session.scalar(
        text("SELECT canonical_arguments FROM approvals WHERE id = :id"), {"id": approval_id}
    )
    assert stored == {"a": "季", "b": 1}
