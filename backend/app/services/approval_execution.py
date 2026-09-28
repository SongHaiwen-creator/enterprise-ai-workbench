"""The single local Mock write executor used after a committed human approval.

It writes one ``mock_it_access_requests`` row in the caller's transaction.
It performs no network, file, subprocess, or dynamic-import call and never
changes Workbench identity, authorization, or configuration tables.
"""

import hashlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models import MockITAccessRequest
from app.schemas.approval import ITAccessRequestExecutionResult
from app.schemas.tool_calling import CreateITAccessRequestArguments

MOCK_IT_ACCESS_EXECUTOR_KEY = "mock_it_access_request.v1"
_REFERENCE_PREFIX = b"eaw.mock-it-access.v1\n"


@dataclass(frozen=True, slots=True)
class ApprovalExecutionContext:
    """Identifiers read fresh under lock by execution authorization."""

    workspace_id: UUID
    approval_id: UUID
    requester_id: UUID
    reviewer_id: UUID
    agent_id: UUID
    tool_id: UUID


WriteExecutor = Callable[[Session, ApprovalExecutionContext, BaseModel], BaseModel]


def mock_it_access_reference(approval_id: UUID) -> str:
    digest = hashlib.sha256(_REFERENCE_PREFIX + approval_id.bytes).digest()
    return f"ITAR-{digest[:6].hex().upper()}"


def execute_mock_it_access_request(
    session: Session,
    context: ApprovalExecutionContext,
    arguments: BaseModel,
) -> ITAccessRequestExecutionResult:
    if not isinstance(context, ApprovalExecutionContext):
        raise TypeError("Invalid approval execution context")
    if not isinstance(arguments, CreateITAccessRequestArguments):
        raise TypeError("Invalid IT access request arguments")
    record = MockITAccessRequest(
        workspace_id=context.workspace_id,
        approval_id=context.approval_id,
        requester_id=context.requester_id,
        reference=mock_it_access_reference(context.approval_id),
        system=arguments.system,
        access_level=arguments.access_level,
        duration_days=arguments.duration_days,
        status="recorded",
    )
    session.add(record)
    session.flush()
    return ITAccessRequestExecutionResult(
        reference=record.reference,
        system=arguments.system,
        access_level=arguments.access_level,
        duration_days=arguments.duration_days,
    )


WRITE_EXECUTORS: Mapping[str, WriteExecutor] = MappingProxyType(
    {MOCK_IT_ACCESS_EXECUTOR_KEY: execute_mock_it_access_request}
)
