from itertools import product
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.schemas.evaluation_run import RunCreate
from app.services.authorization_policy import permission_observation
from app.services.evaluation_execution import CaseBudget, EvaluationFailure, PhaseProviders
from app.services.evaluation_scoring import compare, metrics
from tests.evaluation_support import case_body


@pytest.mark.parametrize(
    "role,status,context,operation",
    list(
        product(
            ["employee", "knowledge_admin", "agent_admin", "system_admin"],
            ["active", "invited", "disabled", "absent"],
            ["same_workspace", "other_workspace", "nonexistent"],
            [
                "agent_route",
                "knowledge_answer",
                "agent_configuration_read",
                "tool_configuration_read",
                "evaluation_dataset_read",
            ],
        )
    ),
)
def test_policy_matrix(role, status, context, operation):
    observed = permission_observation(
        role=role,
        membership_status=status,
        operation=operation,
        present=context == "same_workspace",
        active=True,
    )
    blocked = status != "active" or (
        operation.endswith("_read") and role not in {"agent_admin", "system_admin"}
    )
    expected = 403 if blocked else 200 if context == "same_workspace" else 404
    assert observed["http_status"] == expected
    assert observed["access_denied"] == (expected != 200)


@pytest.mark.parametrize(
    "category,actual,refs",
    [
        (
            "knowledge_qa",
            {
                "routing_intent": "knowledge_qa",
                "answer_status": "answered",
                "citation_count": 1,
                "knowledge_base_id": "12345678-1234-1234-1234-123456789abc",
            },
            {"knowledge_base_id": "12345678-1234-1234-1234-123456789abc"},
        ),
        (
            "tool_calling",
            {
                "routing_intent": "tool_request",
                "would_outcome": "not_executed",
                "approval_required": False,
                "non_execution_reason": "no_available_tool",
            },
            {"tool_id": None},
        ),
        (
            "permission_boundary",
            {"http_status": 404, "result_category": "not_found", "access_denied": True},
            {},
        ),
        (
            "refusal_behavior",
            {
                "routing_intent": "unsupported",
                "response_category": "unsupported_request",
                "safe_response": True,
            },
            {},
        ),
    ],
)
def test_exact_scoring(category, actual, refs):
    expected = case_body(category)["expected_behavior"]
    checks = compare(category, expected, actual, refs)
    assert all(checks.values())
    # A normal observed behavior difference is scorable, not an execution error.
    if category == "permission_boundary":
        actual.update(http_status=200, result_category="allowed", access_denied=False)
    else:
        actual["routing_intent"] = (
            "unsupported" if category != "refusal_behavior" else "knowledge_qa"
        )
    assert not all(compare(category, expected, actual, refs).values())


def row(category, result, latency=None, checks=None):
    return SimpleNamespace(
        case_type=category,
        result=result,
        attempted=latency is not None,
        latency_ms=latency,
        comparison_checks=checks,
    )


def test_metric_denominators_errors_partial_and_even_median():
    rows = [
        row("refusal_behavior", "passed", 10, {"routing_intent": True}),
        row("knowledge_qa", "failed", 30, {"routing_intent": False, "citation_requirement": False}),
        row("tool_calling", "error", 100),
        row("permission_boundary", "error"),
        row("refusal_behavior", None),
    ]
    result = metrics(rows)
    assert result["overall_pass_rate"] == {"matched": 1, "eligible": 2, "value": 0.5}
    assert result["routing_match_rate"]["eligible"] == 2
    assert result["evaluation_coverage"]["value"] == 0.4
    assert result["error_rate"]["value"] == 0.5
    assert result["tool_selection_match_rate"]["value"] is None
    assert result["citation_requirement_compliance"]["value"] == 0
    assert result["latency_ms"] == {
        "count": 3,
        "error_count": 1,
        "min": 10,
        "max": 100,
        "mean": 140 / 3,
        "median": 30,
    }
    assert metrics(rows[:2])["latency_ms"]["median"] == 20
    assert metrics([row("tool_calling", "error")])["overall_pass_rate"]["value"] is None


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"agent_id": "bad", "provider_egress_acknowledged": True},
        {
            "agent_id": "12345678-1234-1234-1234-123456789abc",
            "provider_egress_acknowledged": "true",
        },
        {
            "agent_id": "12345678-1234-1234-1234-123456789abc",
            "provider_egress_acknowledged": True,
            "actor_role": "system_admin",
        },
    ],
)
def test_strict_run_input(payload):
    with pytest.raises(ValidationError):
        RunCreate.model_validate(payload)


def test_clock_budgets_and_deadline_clients(monkeypatch):
    from app.core.config import Settings
    from app.services import evaluation_execution

    now = [0.0]
    monkeypatch.setattr(evaluation_execution.time, "monotonic", lambda: now[0])
    budget = CaseBudget(120)
    calls = []
    settings = Settings(
        database_url="postgresql://local/example",
        jwt_secret_key="x" * 32,
        openai_timeout_seconds=90,
        _env_file=None,
    )

    class Providers:
        def routing(self, bounded):
            calls.append(bounded.openai_timeout_seconds)
            return SimpleNamespace(route=lambda *_: "observation")

    phases = PhaseProviders(
        settings,
        Providers(),
        budget,
        lambda: calls.append("guard"),
        lambda: calls.append("release"),
    )
    now[0] = 50
    assert phases.call("routing", "route", "synthetic", "scope") == "observation"
    assert calls == ["guard", "release", 10, "guard"]
    now[0] = 61
    with pytest.raises(EvaluationFailure, match="case_timeout"):
        budget.remaining()
    now[0] = 121
    with pytest.raises(EvaluationFailure, match="run_timeout"):
        budget.remaining()
