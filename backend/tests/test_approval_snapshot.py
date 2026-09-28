import hashlib
from uuid import UUID

import pytest
from pydantic import BaseModel

from app.models.enums import ToolRisk
from app.schemas.tool_calling import CreateITAccessRequestArguments
from app.services.approval_execution import (
    WRITE_EXECUTORS,
    ApprovalExecutionContext,
    execute_mock_it_access_request,
    mock_it_access_reference,
)
from app.services.approval_snapshot import (
    SnapshotCanonicalizationError,
    arguments_sha256,
    canonical_arguments,
    canonical_json_bytes,
    capability_snapshot,
    policy_snapshot,
    snapshot_sha256,
)
from app.services.tool_registry import TOOL_REGISTRY, get_tool_definition

PINNED_BYTES = (
    b'{"access_level":"standard","business_justification":'
    b'"Quarterly revenue review \xe2\x80\x93 \xe5\xad\xa3\xe5\xba\xa6",'
    b'"duration_days":30,"system":"analytics_warehouse"}'
)
PINNED_ARGUMENTS_SHA256 = "a510c650f9acc2fc83bfe339d515f5fcf54455cdf0dc7c875c4779b711f6d198"
PINNED_SNAPSHOT_SHA256 = "732a63503ff966e62cc1509b2e6bc385c19d5d032d37249921ee43369e33f840"


def fixed_arguments() -> CreateITAccessRequestArguments:
    return CreateITAccessRequestArguments(
        system="analytics_warehouse",
        access_level="standard",
        business_justification="  Quarterly revenue review – 季度 ",
        duration_days=30,
    )


def fixed_capability(arguments_hash: str) -> dict[str, object]:
    definition = get_tool_definition("create_it_access_request")
    assert definition is not None
    return capability_snapshot(
        workspace_id=UUID(int=1),
        requester_id=UUID(int=2),
        requester_membership_id=UUID(int=3),
        agent_id=UUID(int=4),
        tool_id=UUID(int=5),
        tool_key=definition.tool_key,
        tool_risk_level=ToolRisk.HIGH,
        definition=definition,
        canonical_arguments_sha256=arguments_hash,
    )


def test_fixed_input_produces_pinned_canonical_bytes_and_hashes() -> None:
    value = canonical_arguments(fixed_arguments())

    assert canonical_json_bytes(value) == PINNED_BYTES
    assert arguments_sha256(value) == PINNED_ARGUMENTS_SHA256
    assert PINNED_ARGUMENTS_SHA256 == hashlib.sha256(
        b"eaw.approval.arguments.v1\n" + PINNED_BYTES
    ).hexdigest()
    definition = get_tool_definition("create_it_access_request")
    assert definition is not None and definition.approval is not None
    assert snapshot_sha256(
        canonical_arguments_sha256=PINNED_ARGUMENTS_SHA256,
        capability=fixed_capability(PINNED_ARGUMENTS_SHA256),
        policy=policy_snapshot(definition.approval.policy),
    ) == PINNED_SNAPSHOT_SHA256


def test_key_order_and_whitespace_do_not_change_canonical_bytes() -> None:
    first = {"b": 1, "a": {"y": True, "x": None}}
    second = {"a": {"x": None, "y": True}, "b": 1}

    assert canonical_json_bytes(first) == canonical_json_bytes(second)
    assert canonical_json_bytes(first) == b'{"a":{"x":null,"y":true},"b":1}'


def test_types_are_preserved_and_unicode_is_literal_utf8() -> None:
    assert canonical_json_bytes({"i": 1, "t": True, "n": None, "s": "é"}) == (
        b'{"i":1,"n":null,"s":"\xc3\xa9","t":true}'
    )
    # No Unicode normalization: composed and decomposed forms hash differently.
    assert arguments_sha256({"s": "é"}) != arguments_sha256({"s": "é"})


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_numbers_are_rejected(value: float) -> None:
    with pytest.raises(SnapshotCanonicalizationError):
        canonical_json_bytes({"value": value})


def test_lone_surrogate_fails_closed() -> None:
    with pytest.raises(SnapshotCanonicalizationError):
        canonical_json_bytes({"value": "\ud800"})


def test_arguments_round_trip_through_json_reproduces_hash() -> None:
    value = canonical_arguments(fixed_arguments())
    reparsed = CreateITAccessRequestArguments.model_validate(dict(reversed(value.items())))

    assert arguments_sha256(canonical_arguments(reparsed)) == PINNED_ARGUMENTS_SHA256


def test_snapshot_contains_execution_critical_fields_only() -> None:
    capability = fixed_capability(PINNED_ARGUMENTS_SHA256)

    assert capability == {
        "workspace_id": str(UUID(int=1)),
        "requester_id": str(UUID(int=2)),
        "requester_membership_id": str(UUID(int=3)),
        "agent_id": str(UUID(int=4)),
        "tool_id": str(UUID(int=5)),
        "tool_key": "create_it_access_request",
        "tool_risk_level": "high",
        "assignment": {"agent_id": str(UUID(int=4)), "tool_id": str(UUID(int=5))},
        "action_type": "it_access_request.create",
        "operation_type": "write_sensitive",
        "tool_definition_version": "create_it_access_request.v1",
        "executor_key": "mock_it_access_request.v1",
        "executor_type": "local_mock",
        "canonical_arguments_sha256": PINNED_ARGUMENTS_SHA256,
    }
    definition = get_tool_definition("create_it_access_request")
    assert definition is not None and definition.approval is not None
    assert policy_snapshot(definition.approval.policy) == {
        "approval_policy_version": "it-access-approval-v1",
        "required_reviewer_roles": ["system_admin"],
        "self_approval_allowed": False,
        "ttl_hours": 72,
    }


def test_registry_keeps_write_tool_off_the_immediate_branch() -> None:
    definition = get_tool_definition("create_it_access_request")

    assert definition is not None
    assert definition.immediate_execution is False
    assert definition.adapter is None
    assert definition.risk is ToolRisk.HIGH
    assert [key for key, item in TOOL_REGISTRY.items() if item.approval is not None] == [
        "create_it_access_request"
    ]
    assert dict(WRITE_EXECUTORS) == {
        "mock_it_access_request.v1": execute_mock_it_access_request
    }


def test_mock_reference_is_deterministic() -> None:
    assert mock_it_access_reference(UUID(int=7)) == "ITAR-549E14F97087"
    assert mock_it_access_reference(UUID(int=8)) != mock_it_access_reference(UUID(int=7))


def test_mock_executor_rejects_foreign_context_and_arguments() -> None:
    class Other(BaseModel):
        pass

    context = ApprovalExecutionContext(*(UUID(int=index) for index in range(6)))
    with pytest.raises(TypeError):
        execute_mock_it_access_request(object(), object(), fixed_arguments())  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        execute_mock_it_access_request(object(), context, Other())  # type: ignore[arg-type]
