import json
from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import KnowledgeBase
from app.models.enums import (
    ExecutionLogErrorCategory,
    ExecutionLogOperation,
    ExecutionLogOutcome,
)
from tests.integration.approval_support import Scenario, make_scenario, make_user
from tests.integration.test_approval_persistence import approval_values, insert_approval

pytestmark = pytest.mark.integration


def knowledge_base(session: Session, scenario: Scenario) -> KnowledgeBase:
    result = KnowledgeBase(
        workspace_id=scenario.workspace.id,
        name="Policies",
        created_by=scenario.reviewer.id,
    )
    session.add(result)
    session.flush()
    return result


def log_values(scenario: Scenario, **overrides: Any) -> dict[str, Any]:
    """A legal succeeded agent_route row."""

    values: dict[str, Any] = {
        "workspace_id": scenario.workspace.id,
        "user_id": scenario.requester.id,
        "operation": "agent_route",
        "routing_intent": "tool_request",
        "status": "succeeded",
        "outcome": "tool_executed",
        "error_category": None,
        "http_status": 200,
        "latency_ms": 12,
        "agent_id": scenario.agent.id,
        "tool_id": scenario.tool.id,
        "tool_key": scenario.tool.tool_key,
        "approval_id": None,
        "knowledge_base_id": None,
        "details": "{}",
    }
    values.update(overrides)
    return values


def insert_log(session: Session, values: dict[str, Any]) -> UUID:
    return session.execute(
        text(
            "INSERT INTO execution_logs (workspace_id, user_id, operation, routing_intent, "
            "status, outcome, error_category, http_status, latency_ms, agent_id, tool_id, "
            "tool_key, approval_id, knowledge_base_id, details) VALUES (:workspace_id, "
            ":user_id, :operation, :routing_intent, :status, :outcome, :error_category, "
            ":http_status, :latency_ms, :agent_id, :tool_id, :tool_key, :approval_id, "
            ":knowledge_base_id, CAST(:details AS jsonb)) RETURNING id"
        ),
        values,
    ).scalar_one()


def rejected(session: Session, action: Callable[[], object]) -> None:
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            action()


FAILED = {"status": "failed", "error_category": "provider_error", "http_status": 502}

ILLEGAL_ROWS: dict[str, dict[str, Any]] = {
    "unknown_operation": {"operation": "approval_create"},
    "unknown_status": {"status": "success"},
    "unknown_outcome": {"outcome": "done"},
    "unknown_error_category": {**FAILED, "error_category": "boom"},
    "unknown_routing_intent": {"routing_intent": "chat"},
    "failed_without_category": {**FAILED, "error_category": None},
    "succeeded_with_category": {"error_category": "provider_error"},
    "succeeded_with_error_status": {"http_status": 409},
    "failed_with_success_status": {**FAILED, "http_status": 200},
    "http_status_out_of_range": {**FAILED, "http_status": 600},
    "negative_latency": {"latency_ms": -1},
    "routing_intent_outside_agent_route": {
        "operation": "knowledge_answer", "outcome": "knowledge_answered",
        "tool_id": None, "tool_key": None,
    },
    "tool_id_without_key": {"tool_key": None},
    "tool_key_without_id": {"tool_id": None},
    "details_array": {"details": "[]"},
    "details_string": {"details": json.dumps("request text")},
}


@pytest.mark.parametrize("case", sorted(ILLEGAL_ROWS))
def test_database_rejects_illegal_execution_log_rows(db_session: Session, case: str) -> None:
    scenario = make_scenario(db_session)
    values = log_values(scenario, **ILLEGAL_ROWS[case])

    rejected(db_session, lambda: insert_log(db_session, values))


def test_every_enumerated_value_is_accepted(db_session: Session) -> None:
    scenario = make_scenario(db_session)
    for operation in ExecutionLogOperation:
        insert_log(
            db_session,
            log_values(
                scenario,
                operation=operation.value,
                routing_intent="tool_request" if operation.value == "agent_route" else None,
            ),
        )
    for outcome in ExecutionLogOutcome:
        insert_log(db_session, log_values(scenario, outcome=outcome.value))
    for category in ExecutionLogErrorCategory:
        insert_log(
            db_session,
            log_values(scenario, status="failed", error_category=category.value, http_status=500),
        )
    for intent in ("knowledge_qa", "tool_request", "unsupported"):
        insert_log(db_session, log_values(scenario, routing_intent=intent))
    minimal = log_values(
        scenario, routing_intent=None, outcome=None, agent_id=None, tool_id=None, tool_key=None,
        status="failed", error_category="agent_not_found", http_status=404,
    )
    insert_log(db_session, minimal)


def test_composite_foreign_keys_bind_references_to_the_workspace(db_session: Session) -> None:
    scenario = make_scenario(db_session)
    foreign = make_scenario(db_session)
    outsider = make_user(db_session, "Outsider")
    foreign_approval = approval_values(foreign)
    insert_approval(db_session, foreign_approval)
    foreign_knowledge_base = knowledge_base(db_session, foreign)

    for overrides in (
        {"user_id": outsider.id},
        {"user_id": foreign.requester.id},
        {"agent_id": foreign.agent.id},
        {"tool_id": foreign.tool.id},
        {"approval_id": foreign_approval["id"]},
        {"knowledge_base_id": foreign_knowledge_base.id},
        {"agent_id": uuid4()},
    ):
        values = log_values(scenario, **overrides)
        rejected(db_session, lambda v=values: insert_log(db_session, v))

    own_approval = approval_values(scenario)
    insert_approval(db_session, own_approval)
    insert_log(
        db_session,
        log_values(
            scenario,
            approval_id=own_approval["id"],
            knowledge_base_id=knowledge_base(db_session, scenario).id,
        ),
    )


def test_details_default_to_an_empty_object(db_session: Session) -> None:
    scenario = make_scenario(db_session)
    log_id = db_session.execute(
        text(
            "INSERT INTO execution_logs (workspace_id, user_id, operation, status, "
            "http_status, latency_ms) VALUES (:workspace_id, :user_id, 'approval_cancel', "
            "'succeeded', 200, 0) RETURNING id"
        ),
        {"workspace_id": scenario.workspace.id, "user_id": scenario.requester.id},
    ).scalar_one()

    row = db_session.execute(
        text("SELECT details, created_at FROM execution_logs WHERE id = :id"), {"id": log_id}
    ).one()
    assert row.details == {}
    assert row.created_at.tzinfo is not None
