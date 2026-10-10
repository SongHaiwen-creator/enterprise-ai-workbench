"""Keep the UI's read-only help aligned with code-owned capability contracts."""

import json
from pathlib import Path

import pytest

from app.schemas.tool_calling import CreateITAccessRequestArguments
from app.services.tool_registry import TOOL_REGISTRY

HELP_PATH = Path(__file__).resolve().parents[2] / "frontend/utils/registered-tool-help.json"
HELP = json.loads(HELP_PATH.read_text(encoding="utf-8"))


def test_help_covers_exactly_registered_capabilities() -> None:
    keys = [entry["tool_key"] for entry in HELP]
    assert len(keys) == len(set(keys))
    assert set(keys) == set(TOOL_REGISTRY)


@pytest.mark.parametrize("help_entry", HELP, ids=lambda entry: entry["tool_key"])
def test_help_matches_registry_and_argument_schema(help_entry: dict[str, object]) -> None:
    definition = TOOL_REGISTRY[help_entry["tool_key"]]
    assert help_entry["operation_type"] == definition.operation_type.value
    assert help_entry["risk_level"] == definition.risk.value
    arguments = definition.argument_model.model_json_schema()["properties"]
    assert set(help_entry["arguments"]) == set(arguments)
    for field, limits in help_entry["arguments"].items():
        assert all(arguments[field][key] == value for key, value in limits.items())
    if definition.approval:
        policy = definition.approval.policy
        assert help_entry["approval"] == {
            "reviewer_roles": [role.value for role in policy.required_reviewer_roles],
            "self_approval_allowed": policy.self_approval_allowed,
            "ttl_hours": policy.ttl_hours,
        }
    else:
        assert "approval" not in help_entry


def test_documented_production_access_and_text_constraints() -> None:
    valid = {
        "system": "production_database",
        "access_level": "read_only",
        "business_justification": "  Synthetic test request  ",
        "duration_days": 1,
    }
    parsed = CreateITAccessRequestArguments(**valid)
    assert parsed.business_justification == "Synthetic test request"
    for override in (
        {"access_level": "standard"}, {"duration_days": True},
        {"business_justification": "Synthetic\nrequest"},
    ):
        with pytest.raises(ValueError):
            CreateITAccessRequestArguments(**(valid | override))
