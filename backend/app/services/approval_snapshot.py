"""Server-only canonicalization and hashing of Approval execution snapshots.

Rules (Feature 013 Section 10): standard-library JSON with sorted keys,
compact separators, literal non-ASCII encoded as UTF-8, and NaN/Infinity
rejected. Every hash input carries a versioned domain prefix.
"""

import hashlib
import json
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import ToolRisk
from app.services.tool_registry import ApprovalPolicy, ToolDefinition

ARGUMENTS_HASH_PREFIX = b"eaw.approval.arguments.v1\n"
SNAPSHOT_HASH_PREFIX = b"eaw.approval.snapshot.v1\n"


class SnapshotCanonicalizationError(ValueError):
    """A value cannot be represented in the canonical snapshot form."""


def canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise SnapshotCanonicalizationError("Value is not canonicalizable") from exc


def canonical_arguments(arguments: BaseModel) -> dict[str, Any]:
    value = arguments.model_dump(mode="json")
    if not isinstance(value, dict):
        raise SnapshotCanonicalizationError("Arguments must be an object")
    return value


def arguments_sha256(value: dict[str, Any]) -> str:
    return hashlib.sha256(ARGUMENTS_HASH_PREFIX + canonical_json_bytes(value)).hexdigest()


def policy_snapshot(policy: ApprovalPolicy) -> dict[str, Any]:
    return {
        "approval_policy_version": policy.policy_version,
        "required_reviewer_roles": [role.value for role in policy.required_reviewer_roles],
        "self_approval_allowed": policy.self_approval_allowed,
        "ttl_hours": policy.ttl_hours,
    }


def capability_snapshot(
    *,
    workspace_id: UUID,
    requester_id: UUID,
    requester_membership_id: UUID,
    agent_id: UUID,
    tool_id: UUID,
    tool_key: str,
    tool_risk_level: ToolRisk,
    definition: ToolDefinition,
    canonical_arguments_sha256: str,
) -> dict[str, Any]:
    requirement = definition.approval
    if requirement is None:
        raise SnapshotCanonicalizationError("Tool has no approval requirement")
    return {
        "workspace_id": str(workspace_id),
        "requester_id": str(requester_id),
        "requester_membership_id": str(requester_membership_id),
        "agent_id": str(agent_id),
        "tool_id": str(tool_id),
        "tool_key": tool_key,
        "tool_risk_level": tool_risk_level.value,
        "assignment": {"agent_id": str(agent_id), "tool_id": str(tool_id)},
        "action_type": requirement.action_type,
        "operation_type": definition.operation_type.value,
        "tool_definition_version": requirement.tool_definition_version,
        "executor_key": requirement.executor_key,
        "executor_type": requirement.executor_type,
        "canonical_arguments_sha256": canonical_arguments_sha256,
    }


def snapshot_sha256(
    *,
    canonical_arguments_sha256: str,
    capability: dict[str, Any],
    policy: dict[str, Any],
) -> str:
    digest_input = {
        "arguments_sha256": canonical_arguments_sha256,
        "capability": capability,
        "policy": policy,
    }
    return hashlib.sha256(
        SNAPSHOT_HASH_PREFIX + canonical_json_bytes(digest_input)
    ).hexdigest()
