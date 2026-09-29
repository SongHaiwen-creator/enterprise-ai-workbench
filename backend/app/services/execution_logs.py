"""Feature 014 execution log recorder and reads.

The recorder writes one allow-listed record per handled in-scope request after
the business outcome is known. It never stores request content, never commits
business work that its owning service did not commit, and never changes the
response: recording is best-effort (spec Section 10).
"""

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import Select, event, select, text
from sqlalchemy.orm import ORMExecuteState, Session, SessionTransaction, aliased

from app.models import Agent, Approval, ExecutionLog, KnowledgeBase, Tool, User
from app.models.enums import (
    ApprovalDecisionStatus,
    ApprovalExecutionStatus,
    ExecutionLogErrorCategory,
    ExecutionLogOperation,
    ExecutionLogOutcome,
    ExecutionLogStatus,
)
from app.schemas.agent_routing import RoutingIntent
from app.schemas.answer import AnswerStatus, GroundedAnswerResponse
from app.schemas.approval import ApprovalPartyReference
from app.schemas.execution_log import ExecutionLogDetails, ExecutionLogResponse
from app.schemas.tool_calling import PublicToolReference
from app.services import approvals as approval_service
from app.services.agents import (
    AGENT_NOT_ACTIVE,
    AGENT_NOT_FOUND,
    KNOWLEDGE_BASE_NOT_ACTIVE,
    KNOWLEDGE_CONTEXT_REQUIRED,
)
from app.services.embeddings import EmbeddingConfigurationError, EmbeddingProviderError
from app.services.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.services.generation import (
    GenerationConfigurationError,
    GenerationInputTooLargeError,
    GenerationProviderError,
)
from app.services.knowledge_bases import KNOWLEDGE_BASE_NOT_FOUND
from app.services.retrieval import KNOWLEDGE_BASE_SEARCH_DISABLED
from app.services.routing import (
    ROUTING_PROVIDER_FAILURE,
    RoutingConfigurationError,
    RoutingInputTooLargeError,
    RoutingProviderError,
)
from app.services.tool_selection import (
    ToolSelectionConfigurationError,
    ToolSelectionInputTooLargeError,
    ToolSelectionProviderError,
)
from app.services.tools import (
    TOOL_ADAPTER_FAILURE,
    TOOL_PROVIDER_FAILURE,
    ToolAdapterError,
    ToolRegistryConfigurationError,
)

logger = logging.getLogger(__name__)

EXECUTION_LOG_NOT_FOUND = "Execution log not found"
WRITE_FAILED_EVENT = "execution_log_write_failed"
LOG_LOCK_TIMEOUT = "5s"
SUCCESS_STATUS = 200

Category = ExecutionLogErrorCategory
Outcome = ExecutionLogOutcome
Operation = ExecutionLogOperation

# --- Details allow-list (spec Section 8.2) -----------------------------------

_GENERATION_KEYS = frozenset(
    {
        "citation_count", "generation_model", "prompt_version",
        "input_tokens", "output_tokens", "total_tokens",
    }
)
ALLOWED_DETAIL_KEYS: dict[ExecutionLogOperation, frozenset[str]] = {
    Operation.AGENT_ROUTE: _GENERATION_KEYS | {"tool_not_executed_reason"},
    Operation.KNOWLEDGE_ANSWER: _GENERATION_KEYS,
    Operation.APPROVAL_DECISION: frozenset({"decision"}),
    Operation.APPROVAL_CANCEL: frozenset(),
}


class DisallowedDetailError(ValueError):
    """A details key is not permitted for the operation."""


def validate_details(
    operation: ExecutionLogOperation, details: dict[str, Any]
) -> dict[str, Any]:
    disallowed = set(details) - ALLOWED_DETAIL_KEYS[operation]
    if disallowed:
        raise DisallowedDetailError("details key not permitted for operation")
    validated = ExecutionLogDetails.model_validate(details)
    return validated.model_dump(exclude_unset=True)


# --- Classification (spec Section 9.2) ---------------------------------------

_INPUT_TOO_LARGE = (
    RoutingInputTooLargeError, ToolSelectionInputTooLargeError, GenerationInputTooLargeError,
)
_PROVIDER_UNAVAILABLE = (
    RoutingConfigurationError, ToolSelectionConfigurationError,
    EmbeddingConfigurationError, GenerationConfigurationError,
)
_PROVIDER_ERROR = (
    RoutingProviderError, ToolSelectionProviderError,
    EmbeddingProviderError, GenerationProviderError,
)
_NOT_FOUND = {
    AGENT_NOT_FOUND: Category.AGENT_NOT_FOUND,
    KNOWLEDGE_BASE_NOT_FOUND: Category.KNOWLEDGE_BASE_NOT_FOUND,
    approval_service.APPROVAL_NOT_FOUND: Category.APPROVAL_NOT_FOUND,
}
_CONFLICT = {
    AGENT_NOT_ACTIVE: Category.AGENT_INACTIVE,
    KNOWLEDGE_BASE_NOT_ACTIVE: Category.KNOWLEDGE_BASE_INACTIVE,
    KNOWLEDGE_BASE_SEARCH_DISABLED: Category.KNOWLEDGE_BASE_INACTIVE,
    approval_service.CAPABILITY_UNAVAILABLE: Category.TOOL_UNAVAILABLE,
    approval_service.APPROVAL_NOT_PENDING: Category.APPROVAL_NOT_PENDING,
    approval_service.APPROVAL_EXPIRED: Category.APPROVAL_EXPIRED,
    approval_service.APPROVAL_BUSY: Category.APPROVAL_BUSY,
}
_TOOL_ADAPTER = {
    TOOL_PROVIDER_FAILURE: Category.PROVIDER_ERROR,
    TOOL_ADAPTER_FAILURE: Category.TOOL_EXECUTION_FAILED,
}
_HTTP_DETAIL = {
    KNOWLEDGE_CONTEXT_REQUIRED: Category.KNOWLEDGE_BASE_REQUIRED,
    ROUTING_PROVIDER_FAILURE: Category.PROVIDER_ERROR,
}


def _classify_cause(cause: BaseException) -> ExecutionLogErrorCategory:
    if isinstance(cause, _INPUT_TOO_LARGE):
        return Category.INPUT_TOO_LARGE
    if isinstance(cause, _PROVIDER_UNAVAILABLE):
        return Category.PROVIDER_UNAVAILABLE
    if isinstance(cause, _PROVIDER_ERROR):
        return Category.PROVIDER_ERROR
    if isinstance(cause, ToolAdapterError):
        return _TOOL_ADAPTER.get(str(cause), Category.INTERNAL_ERROR)
    if isinstance(
        cause, (ToolRegistryConfigurationError, approval_service.ApprovalConfigurationError)
    ):
        return Category.TOOL_CONFIGURATION_ERROR
    return Category.INTERNAL_ERROR


def classify_exception(exc: BaseException) -> tuple[int, ExecutionLogErrorCategory]:
    """Map a handler exception to ``(http_status, error_category)``.

    Uses only exception types and existing module constants; the exception
    message itself is never stored.
    """

    if isinstance(exc, approval_service.ApprovalOutcomeError):
        if exc.status_code == 409:
            return 409, Category.APPROVAL_INVALIDATED
        return exc.status_code, Category.APPROVAL_EXECUTION_FAILED
    if isinstance(exc, NotFoundError):
        return 404, _NOT_FOUND.get(exc.detail, Category.INTERNAL_ERROR)
    if isinstance(exc, ConflictError):
        return 409, _CONFLICT.get(exc.detail, Category.INTERNAL_ERROR)
    if isinstance(exc, ForbiddenError):
        return 403, Category.ACCESS_DENIED
    if isinstance(exc, HTTPException):
        if exc.__cause__ is not None:
            return exc.status_code, _classify_cause(exc.__cause__)
        return exc.status_code, _HTTP_DETAIL.get(str(exc.detail), Category.INTERNAL_ERROR)
    return 500, Category.INTERNAL_ERROR


def approval_outcome(
    decision_status: ApprovalDecisionStatus,
    execution_status: ApprovalExecutionStatus,
) -> ExecutionLogOutcome | None:
    if decision_status is ApprovalDecisionStatus.APPROVED:
        if execution_status is ApprovalExecutionStatus.SUCCEEDED:
            return Outcome.APPROVED_EXECUTION_SUCCEEDED
        return Outcome.APPROVED_EXECUTION_FAILED
    return {
        ApprovalDecisionStatus.REJECTED: Outcome.REJECTED,
        ApprovalDecisionStatus.CANCELLED: Outcome.CANCELLED,
        ApprovalDecisionStatus.EXPIRED: Outcome.EXPIRED,
        ApprovalDecisionStatus.INVALIDATED: Outcome.INVALIDATED,
    }.get(decision_status)


# Failures whose business state change was committed by this request, so the
# Approval's committed state is the operation outcome (spec BR-06).
_APPROVAL_STATE_CHANGING_FAILURES = frozenset(
    {
        Category.APPROVAL_INVALIDATED,
        Category.APPROVAL_EXPIRED,
        Category.APPROVAL_EXECUTION_FAILED,
    }
)

# --- Recorder ---------------------------------------------------------------


@dataclass
class ExecutionTrace:
    """Values a route handler reports while it runs; plain data only."""

    workspace_id: UUID
    user_id: UUID
    operation: ExecutionLogOperation
    routing_intent: RoutingIntent | None = None
    outcome: ExecutionLogOutcome | None = None
    agent_id: UUID | None = None
    tool_key: str | None = None
    approval_id: UUID | None = None
    knowledge_base_id: UUID | None = None
    details: dict[str, Any] = field(default_factory=dict)


class _UncommittedWriteTracker:
    """Detect business writes the handler left uncommitted on the session."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.pending = False

    def _flushed(self, *_: object) -> None:
        self.pending = True

    def _executed(self, state: ORMExecuteState) -> None:
        if state.is_insert or state.is_update or state.is_delete:
            self.pending = True

    def _ended(self, *_: object) -> None:
        self.pending = False

    def __enter__(self) -> "_UncommittedWriteTracker":
        event.listen(self.session, "after_flush", self._flushed)
        event.listen(self.session, "do_orm_execute", self._executed)
        event.listen(self.session, "after_commit", self._ended)
        event.listen(self.session, "after_rollback", self._ended)
        return self

    def __exit__(self, *_: object) -> None:
        event.remove(self.session, "after_flush", self._flushed)
        event.remove(self.session, "do_orm_execute", self._executed)
        event.remove(self.session, "after_commit", self._ended)
        event.remove(self.session, "after_rollback", self._ended)

    @property
    def has_uncommitted_writes(self) -> bool:
        session = self.session
        return self.pending or bool(session.new or session.dirty or session.deleted)


def record_grounded_answer(trace: ExecutionTrace, answer: GroundedAnswerResponse) -> None:
    """Record the outcome and allow-listed metrics of a grounded answer."""

    trace.outcome = (
        Outcome.KNOWLEDGE_ANSWERED
        if answer.status is AnswerStatus.ANSWERED
        else Outcome.KNOWLEDGE_UNSUPPORTED
    )
    generation = answer.generation
    trace.details.update(
        citation_count=len(answer.citations),
        generation_model=generation.model,
        prompt_version=generation.prompt_version,
        input_tokens=generation.input_tokens,
        output_tokens=generation.output_tokens,
        total_tokens=generation.total_tokens,
    )


@contextmanager
def execution_log(
    session: Session,
    *,
    workspace_id: UUID,
    user_id: UUID,
    operation: ExecutionLogOperation,
) -> Iterator[ExecutionTrace]:
    """Record one execution log for the wrapped route handler body.

    Used as ``with execution_log(...) as trace:`` around the whole handler
    body, including the ``return`` of the already-built response.
    """

    trace = ExecutionTrace(workspace_id=workspace_id, user_id=user_id, operation=operation)
    started = time.perf_counter()
    with _UncommittedWriteTracker(session) as tracker:
        # Marks handler entry. Services still commit or roll back the
        # outermost transaction (SQLAlchemy 2.0), which also ends this
        # savepoint, so their transaction ownership is unchanged.
        handler_savepoint = session.begin_nested()
        try:
            yield trace
        except Exception as exc:
            latency_ms = _elapsed_ms(started)
            http_status, category = classify_exception(exc)
            _record(
                session, handler_savepoint, tracker, trace, latency_ms, http_status, category
            )
            raise
        latency_ms = _elapsed_ms(started)
        _record(
            session, handler_savepoint, tracker, trace, latency_ms, SUCCESS_STATUS, None
        )


def _elapsed_ms(started: float) -> int:
    return max(0, int((time.perf_counter() - started) * 1000))


def _record(
    session: Session,
    handler_savepoint: SessionTransaction,
    tracker: _UncommittedWriteTracker,
    trace: ExecutionTrace,
    latency_ms: int,
    http_status: int,
    category: ExecutionLogErrorCategory | None,
) -> None:
    """Write the record; never raises and never commits business work."""

    try:
        # Work its owning service did not commit is not part of the outcome;
        # discard it before the log commit (spec 10.1).
        if handler_savepoint.is_active:
            # No service ended the transaction since handler entry: discard
            # everything the handler did, keep what preceded it.
            handler_savepoint.rollback()
        elif tracker.has_uncommitted_writes:
            session.rollback()
        with session.no_autoflush:
            row = _build_row(session, trace, latency_ms, http_status, category)
        session.execute(text(f"SET LOCAL lock_timeout = '{LOG_LOCK_TIMEOUT}'"))
        session.add(row)
        session.commit()
    except Exception:
        try:
            session.rollback()
        except Exception:  # pragma: no cover - connection already unusable
            pass
        logger.warning(
            "%s workspace_id=%s operation=%s",
            WRITE_FAILED_EVENT,
            trace.workspace_id,
            trace.operation.value,
        )


def _build_row(
    session: Session,
    trace: ExecutionTrace,
    latency_ms: int,
    http_status: int,
    category: ExecutionLogErrorCategory | None,
) -> ExecutionLog:
    workspace_id = trace.workspace_id
    agent_id = _resolve(session, Agent, trace.agent_id, workspace_id)
    knowledge_base_id = None
    if category is not Category.KNOWLEDGE_BASE_NOT_FOUND:
        knowledge_base_id = _resolve(
            session, KnowledgeBase, trace.knowledge_base_id, workspace_id
        )
    tool_id: UUID | None = None
    tool_key: str | None = None
    if trace.tool_key is not None:
        tool_id = session.scalar(
            select(Tool.id).where(
                Tool.workspace_id == workspace_id, Tool.tool_key == trace.tool_key
            )
        )
        tool_key = trace.tool_key if tool_id is not None else None

    outcome = trace.outcome
    approval_id: UUID | None = None
    if trace.approval_id is not None and category is not Category.APPROVAL_NOT_FOUND:
        approval = session.execute(
            select(
                Approval.id,
                Approval.agent_id,
                Approval.tool_id,
                Tool.tool_key,
                Approval.decision_status,
                Approval.execution_status,
            )
            .join(
                Tool,
                (Tool.id == Approval.tool_id) & (Tool.workspace_id == Approval.workspace_id),
            )
            .where(Approval.id == trace.approval_id, Approval.workspace_id == workspace_id)
        ).one_or_none()
        if approval is not None:
            approval_id = approval.id
            agent_id = agent_id or approval.agent_id
            tool_id, tool_key = approval.tool_id, approval.tool_key
            if trace.operation in {Operation.APPROVAL_DECISION, Operation.APPROVAL_CANCEL} and (
                category is None or category in _APPROVAL_STATE_CHANGING_FAILURES
            ):
                outcome = approval_outcome(approval.decision_status, approval.execution_status)

    return ExecutionLog(
        workspace_id=workspace_id,
        user_id=trace.user_id,
        operation=trace.operation,
        routing_intent=trace.routing_intent.value if trace.routing_intent else None,
        status=ExecutionLogStatus.FAILED if category else ExecutionLogStatus.SUCCEEDED,
        outcome=outcome,
        error_category=category,
        http_status=http_status,
        latency_ms=latency_ms,
        agent_id=agent_id,
        tool_id=tool_id,
        tool_key=tool_key,
        approval_id=approval_id,
        knowledge_base_id=knowledge_base_id,
        details=validate_details(trace.operation, trace.details),
    )


def _resolve(
    session: Session,
    model: type[Agent] | type[KnowledgeBase],
    object_id: UUID | None,
    workspace_id: UUID,
) -> UUID | None:
    if object_id is None:
        return None
    return session.scalar(
        select(model.id).where(model.id == object_id, model.workspace_id == workspace_id)
    )


# --- Reads ------------------------------------------------------------------


def _read_statement() -> Select[Any]:
    agent = aliased(Agent)
    tool = aliased(Tool)
    knowledge_base = aliased(KnowledgeBase)
    return (
        select(
            ExecutionLog,
            User.name.label("user_name"),
            agent.name.label("agent_name"),
            tool.name.label("tool_name"),
            knowledge_base.name.label("knowledge_base_name"),
        )
        .join(User, User.id == ExecutionLog.user_id)
        .outerjoin(
            agent,
            (agent.id == ExecutionLog.agent_id)
            & (agent.workspace_id == ExecutionLog.workspace_id),
        )
        .outerjoin(
            tool,
            (tool.id == ExecutionLog.tool_id) & (tool.workspace_id == ExecutionLog.workspace_id),
        )
        .outerjoin(
            knowledge_base,
            (knowledge_base.id == ExecutionLog.knowledge_base_id)
            & (knowledge_base.workspace_id == ExecutionLog.workspace_id),
        )
    )


def list_execution_logs(
    session: Session,
    *,
    workspace_id: UUID,
    operation: ExecutionLogOperation | None,
    status: ExecutionLogStatus | None,
    agent_id: UUID | None,
    user_id: UUID | None,
    tool_key: str | None,
    created_after: datetime | None,
    created_before: datetime | None,
    limit: int,
    offset: int,
) -> list[Any]:
    statement = _read_statement().where(ExecutionLog.workspace_id == workspace_id)
    if operation is not None:
        statement = statement.where(ExecutionLog.operation == operation)
    if status is not None:
        statement = statement.where(ExecutionLog.status == status)
    if agent_id is not None:
        statement = statement.where(ExecutionLog.agent_id == agent_id)
    if user_id is not None:
        statement = statement.where(ExecutionLog.user_id == user_id)
    if tool_key is not None:
        statement = statement.where(ExecutionLog.tool_key == tool_key)
    if created_after is not None:
        statement = statement.where(ExecutionLog.created_at >= created_after)
    if created_before is not None:
        statement = statement.where(ExecutionLog.created_at < created_before)
    statement = (
        statement.order_by(ExecutionLog.created_at.desc(), ExecutionLog.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(session.execute(statement).all())


def get_execution_log(session: Session, workspace_id: UUID, log_id: UUID) -> Any:
    row = session.execute(
        _read_statement().where(
            ExecutionLog.id == log_id, ExecutionLog.workspace_id == workspace_id
        )
    ).one_or_none()
    if row is None:
        raise NotFoundError(EXECUTION_LOG_NOT_FOUND)
    return row


def to_response(row: Any) -> ExecutionLogResponse:
    log: ExecutionLog = row.ExecutionLog

    def party(object_id: UUID | None, name: str | None) -> ApprovalPartyReference | None:
        if object_id is None or name is None:
            return None
        return ApprovalPartyReference(id=object_id, name=name)

    return ExecutionLogResponse(
        id=log.id,
        workspace_id=log.workspace_id,
        operation=log.operation,
        routing_intent=RoutingIntent(log.routing_intent) if log.routing_intent else None,
        status=log.status,
        outcome=log.outcome,
        error_category=log.error_category,
        http_status=log.http_status,
        latency_ms=log.latency_ms,
        user=ApprovalPartyReference(id=log.user_id, name=row.user_name),
        agent=party(log.agent_id, row.agent_name),
        tool=(
            PublicToolReference(tool_key=log.tool_key, name=row.tool_name)
            if log.tool_key is not None and row.tool_name is not None
            else None
        ),
        approval_id=log.approval_id,
        knowledge_base=party(log.knowledge_base_id, row.knowledge_base_name),
        details=ExecutionLogDetails.model_validate(log.details),
        created_at=log.created_at,
    )
