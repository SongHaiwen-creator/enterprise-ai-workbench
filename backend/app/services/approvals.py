"""Feature 013 Human Approval: creation, decision, and execution boundaries.

Each boundary re-reads current persisted state (Section 15). Workspace
authority always comes from the caller's Membership in the route Workspace.
Fresh checks select columns, not ORM entities, so values cached in the
session identity map by earlier request dependencies are never trusted.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ValidationError
from sqlalchemy import ColumnElement, Select, and_, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, aliased

from app.models import Agent, AgentTool, Approval, Membership, MockITAccessRequest, Tool, User
from app.models import Workspace as WorkspaceModel
from app.models.enums import (
    AgentStatus,
    ApprovalDecisionStatus,
    ApprovalExecutionFailure,
    ApprovalExecutionStatus,
    ApprovalInvalidationReason,
    MembershipRole,
    MembershipStatus,
    ToolRisk,
    ToolStatus,
    UserStatus,
    WorkspaceStatus,
)
from app.schemas.approval import (
    ApprovalDecisionDetail,
    ApprovalPartyReference,
    ApprovalResponse,
    ITAccessRequestExecutionResult,
)
from app.services.approval_execution import (
    WRITE_EXECUTORS,
    ApprovalExecutionContext,
)
from app.services.approval_snapshot import (
    SnapshotCanonicalizationError,
    arguments_sha256,
    canonical_arguments,
    capability_snapshot,
    policy_snapshot,
    snapshot_sha256,
)
from app.services.exceptions import (
    WORKSPACE_ACCESS_DENIED,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ServiceError,
)
from app.services.tool_registry import (
    TOOL_REGISTRY,
    ApprovalRequirement,
    ToolDefinition,
    get_tool_definition,
)

APPROVAL_NOT_FOUND = "Approval not found"
APPROVAL_ACTION_NOT_PERMITTED = "Approval action not permitted"
APPROVAL_REVIEW_NOT_PERMITTED = "Approval review not permitted"
APPROVAL_NOT_PENDING = "Approval is no longer pending"
APPROVAL_EXPIRED = "Approval has expired"
APPROVAL_INVALIDATED = "Approval is no longer valid; submit a new request"
APPROVAL_BUSY = "Approval is being processed; retry"
APPROVAL_EXECUTION_FAILED = "Enterprise Tool request failed"
APPROVAL_CONFIGURATION_UNAVAILABLE = "Tool configuration is unavailable"
CAPABILITY_UNAVAILABLE = "Tool is no longer active or assigned"
LOCK_TIMEOUT = "5s"
LOCK_NOT_AVAILABLE = "55P03"
PENDING_PREDICATE = text("decision_status = 'pending'")

# Every role any registered approval policy accepts; used only as a
# visibility hint for the review list. Decisions check the exact policy.
REVIEWER_ROLES = frozenset(
    role
    for definition in TOOL_REGISTRY.values()
    if definition.approval is not None
    for role in definition.approval.policy.required_reviewer_roles
)


class ApprovalConfigurationError(Exception):
    """The registry or approval policy cannot safely support this Approval."""


class ApprovalOutcomeError(ServiceError):
    """A decision committed a terminal fact but the request did not succeed."""

    def __init__(self, detail: str, *, status_code: int, approval_id: UUID) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.approval_id = approval_id


@dataclass(frozen=True, slots=True)
class CallerAuthority:
    membership_id: UUID
    role: MembershipRole


@dataclass(frozen=True, slots=True)
class ExecutionAuthorization:
    """Result of the execution boundary; ``reason`` is set when it failed."""

    reason: ApprovalInvalidationReason | None
    requirement: ApprovalRequirement | None = None
    arguments: BaseModel | None = None

    @property
    def authorized(self) -> bool:
        return self.reason is None


def _denied(reason: ApprovalInvalidationReason) -> ExecutionAuthorization:
    return ExecutionAuthorization(reason=reason)


def _shared(statement: Select[Any], lock: bool) -> Select[Any]:
    return statement.with_for_update(read=True) if lock else statement


def _db_now(session: Session) -> datetime:
    """Current database wall-clock time, not the transaction start (``now()``)."""

    return session.scalar(select(func.clock_timestamp()))


def _fresh_caller(session: Session, workspace_id: UUID, user_id: UUID) -> CallerAuthority:
    row = session.execute(
        select(
            Membership.id,
            Membership.role,
            Membership.status.label("membership_status"),
            User.status.label("user_status"),
            WorkspaceModel.status.label("workspace_status"),
        )
        .select_from(Membership)
        .join(User, User.id == Membership.user_id)
        .join(WorkspaceModel, WorkspaceModel.id == Membership.workspace_id)
        .where(Membership.user_id == user_id, Membership.workspace_id == workspace_id)
    ).one_or_none()
    if (
        row is None
        or row.user_status is not UserStatus.ACTIVE
        or row.workspace_status is not WorkspaceStatus.ACTIVE
        or row.membership_status is not MembershipStatus.ACTIVE
    ):
        raise ForbiddenError(WORKSPACE_ACCESS_DENIED)
    return CallerAuthority(membership_id=row.id, role=row.role)


@dataclass(frozen=True, slots=True)
class _CapabilityState:
    agent_active: bool
    tool_active: bool
    tool_key: str | None
    tool_risk: ToolRisk | None
    assigned: bool

    @property
    def available(self) -> bool:
        return self.agent_active and self.tool_active and self.assigned


def _capability_state(
    session: Session,
    workspace_id: UUID,
    agent_id: UUID,
    tool_id: UUID,
    *,
    lock: bool,
) -> _CapabilityState:
    # Lock order (Section 26): Agent, Tool, then the assignment edge.
    agent_status = session.scalar(
        _shared(
            select(Agent.status).where(
                Agent.id == agent_id, Agent.workspace_id == workspace_id
            ),
            lock,
        )
    )
    tool = session.execute(
        _shared(
            select(Tool.status, Tool.tool_key, Tool.risk_level).where(
                Tool.id == tool_id, Tool.workspace_id == workspace_id
            ),
            lock,
        )
    ).one_or_none()
    assigned = session.scalar(
        _shared(
            select(AgentTool.agent_id).where(
                AgentTool.agent_id == agent_id,
                AgentTool.tool_id == tool_id,
                AgentTool.workspace_id == workspace_id,
            ),
            lock,
        )
    )
    return _CapabilityState(
        agent_active=agent_status is AgentStatus.ACTIVE,
        tool_active=tool is not None and tool.status is ToolStatus.ACTIVE,
        tool_key=None if tool is None else tool.tool_key,
        tool_risk=None if tool is None else tool.risk_level,
        assigned=assigned is not None,
    )


# --- Creation boundary (Section 15.1) --------------------------------------


def create_pending_approval(
    session: Session,
    *,
    workspace_id: UUID,
    requester_id: UUID,
    agent_id: UUID,
    tool_id: UUID,
    definition: ToolDefinition,
    arguments: BaseModel,
) -> Approval:
    """Persist (or return the identical pending) Approval and commit it."""

    requirement = definition.approval
    if definition.immediate_execution or requirement is None:
        raise ApprovalConfigurationError(APPROVAL_CONFIGURATION_UNAVAILABLE)
    requester = _fresh_caller(session, workspace_id, requester_id)
    capability = _capability_state(session, workspace_id, agent_id, tool_id, lock=False)
    if not capability.available:
        raise ConflictError(CAPABILITY_UNAVAILABLE)
    if capability.tool_key != definition.tool_key or capability.tool_risk is not definition.risk:
        raise ApprovalConfigurationError(APPROVAL_CONFIGURATION_UNAVAILABLE)

    try:
        arguments_value = canonical_arguments(arguments)
        arguments_hash = arguments_sha256(arguments_value)
        capability_value = capability_snapshot(
            workspace_id=workspace_id,
            requester_id=requester_id,
            requester_membership_id=requester.membership_id,
            agent_id=agent_id,
            tool_id=tool_id,
            tool_key=definition.tool_key,
            tool_risk_level=definition.risk,
            definition=definition,
            canonical_arguments_sha256=arguments_hash,
        )
        policy_value = policy_snapshot(requirement.policy)
        digest = snapshot_sha256(
            canonical_arguments_sha256=arguments_hash,
            capability=capability_value,
            policy=policy_value,
        )
    except SnapshotCanonicalizationError as exc:
        raise ApprovalConfigurationError(APPROVAL_CONFIGURATION_UNAVAILABLE) from exc

    identity = (
        Approval.workspace_id == workspace_id,
        Approval.requester_id == requester_id,
        Approval.snapshot_sha256 == digest,
    )
    created_at = _db_now(session)
    # A past-expiry pending duplicate is expired first so it never blocks.
    session.execute(
        update(Approval)
        .where(
            *identity,
            Approval.decision_status == ApprovalDecisionStatus.PENDING,
            Approval.expires_at <= created_at,
        )
        .values(
            decision_status=ApprovalDecisionStatus.EXPIRED,
            decided_at=Approval.expires_at,
            updated_at=created_at,
        )
        .execution_options(synchronize_session=False)
    )
    inserted_id = session.scalar(
        insert(Approval)
        .values(
            workspace_id=workspace_id,
            requester_id=requester_id,
            agent_id=agent_id,
            tool_id=tool_id,
            action_type=requirement.action_type,
            canonical_arguments=arguments_value,
            canonical_arguments_sha256=arguments_hash,
            capability_snapshot=capability_value,
            policy_snapshot=policy_value,
            snapshot_sha256=digest,
            created_at=created_at,
            updated_at=created_at,
            expires_at=created_at + timedelta(hours=requirement.policy.ttl_hours),
        )
        .on_conflict_do_nothing(
            index_elements=["workspace_id", "requester_id", "snapshot_sha256"],
            index_where=PENDING_PREDICATE,
        )
        .returning(Approval.id)
    )
    approval = session.scalar(
        select(Approval)
        .where(
            *identity,
            Approval.decision_status == ApprovalDecisionStatus.PENDING,
            *(() if inserted_id is None else (Approval.id == inserted_id,)),
        )
        .execution_options(populate_existing=True)
    )
    if approval is None:
        session.rollback()
        raise ConflictError(APPROVAL_BUSY)
    session.commit()
    return approval


# --- Execution boundary (Section 15.3) -------------------------------------


def authorize_execution(
    session: Session,
    approval: Approval,
    *,
    workspace_id: UUID,
    lock: bool = True,
) -> ExecutionAuthorization:
    """Re-establish execution authority for a locked pending Approval.

    Raises ``ForbiddenError`` only when the route Workspace itself is no
    longer active (the reviewer's own access). Every other failure is
    returned as an invalidation reason; nothing is written here.
    """

    if (
        approval.decision_status is not ApprovalDecisionStatus.PENDING
        or approval.execution_status is not ApprovalExecutionStatus.NOT_STARTED
    ):
        raise ConflictError(APPROVAL_NOT_PENDING)

    workspace_status = session.scalar(
        _shared(select(WorkspaceModel.status).where(WorkspaceModel.id == workspace_id), lock)
    )
    if workspace_status is not WorkspaceStatus.ACTIVE:
        raise ForbiddenError(WORKSPACE_ACCESS_DENIED)

    drift = _denied(ApprovalInvalidationReason.CONFIGURATION_DRIFT)
    capability = approval.capability_snapshot
    policy = approval.policy_snapshot
    if not isinstance(capability, dict) or not isinstance(policy, dict):
        return drift
    assignment = capability.get("assignment")
    if (
        approval.workspace_id != workspace_id
        or capability.get("workspace_id") != str(workspace_id)
        or capability.get("requester_id") != str(approval.requester_id)
        or capability.get("agent_id") != str(approval.agent_id)
        or capability.get("tool_id") != str(approval.tool_id)
        or assignment
        != {"agent_id": str(approval.agent_id), "tool_id": str(approval.tool_id)}
        or capability.get("action_type") != approval.action_type
    ):
        return drift

    user_status = session.scalar(
        _shared(select(User.status).where(User.id == approval.requester_id), lock)
    )
    membership = session.execute(
        _shared(
            select(Membership.id, Membership.status).where(
                Membership.user_id == approval.requester_id,
                Membership.workspace_id == workspace_id,
            ),
            lock,
        )
    ).one_or_none()
    if (
        user_status is not UserStatus.ACTIVE
        or membership is None
        or membership.status is not MembershipStatus.ACTIVE
        or str(membership.id) != capability.get("requester_membership_id")
    ):
        return _denied(ApprovalInvalidationReason.REQUESTER_INELIGIBLE)

    state = _capability_state(
        session, workspace_id, approval.agent_id, approval.tool_id, lock=lock
    )
    if not state.available:
        return _denied(ApprovalInvalidationReason.CAPABILITY_UNAVAILABLE)

    definition = get_tool_definition(str(capability.get("tool_key")))
    requirement = None if definition is None else definition.approval
    if (
        definition is None
        or requirement is None
        or definition.immediate_execution
        or state.tool_key != capability.get("tool_key")
        or state.tool_risk is None
        or state.tool_risk.value != capability.get("tool_risk_level")
        or state.tool_risk is not definition.risk
        or capability.get("operation_type") != definition.operation_type.value
        or capability.get("action_type") != requirement.action_type
        or capability.get("tool_definition_version") != requirement.tool_definition_version
        or capability.get("executor_key") != requirement.executor_key
        or capability.get("executor_type") != requirement.executor_type
        or requirement.executor_key not in WRITE_EXECUTORS
        or policy.get("approval_policy_version") != requirement.policy.policy_version
    ):
        return drift

    try:
        arguments = definition.argument_model.model_validate(approval.canonical_arguments)
        recomputed_arguments = arguments_sha256(canonical_arguments(arguments))
        recomputed_snapshot = snapshot_sha256(
            canonical_arguments_sha256=approval.canonical_arguments_sha256,
            capability=capability,
            policy=policy,
        )
    except (ValidationError, SnapshotCanonicalizationError):
        return drift
    if (
        recomputed_arguments != approval.canonical_arguments_sha256
        or recomputed_arguments != capability.get("canonical_arguments_sha256")
        or recomputed_snapshot != approval.snapshot_sha256
    ):
        return drift

    return ExecutionAuthorization(reason=None, requirement=requirement, arguments=arguments)


# --- Decision boundary (Section 15.2) --------------------------------------
#
# Lock order (Section 26), shared by decide and cancel:
#   1. Approval row            FOR UPDATE   (serializes decisions)
#   2. route Workspace row     FOR SHARE
#   3. User rows, by id        FOR SHARE    (caller and, for decisions, requester)
#   4. Membership rows, by user_id FOR SHARE
#   5. Agent, Tool, agent_tools FOR SHARE   (execution authorization only)
# Expiry is checked after step 4 and, for approve, again after step 5, using
# wall-clock time read once the relevant locks are held.
# Authority is decided only from rows read after they are locked, so a
# revocation committed while the request waited is always observed, and a
# revocation attempted during the protected transaction waits for its commit.
# Before any blocking lock, a non-locking precheck returns the uniform 404/403
# so a caller who cannot see an Approval never waits on, or holds, its lock.


def _is_lock_timeout(exc: OperationalError) -> bool:
    return getattr(exc.orig, "sqlstate", None) == LOCK_NOT_AVAILABLE


def _read_approval(session: Session, workspace_id: UUID, approval_id: UUID) -> Approval:
    approval = session.scalar(
        select(Approval)
        .where(Approval.id == approval_id, Approval.workspace_id == workspace_id)
        .execution_options(populate_existing=True)
    )
    if approval is None:
        raise NotFoundError(APPROVAL_NOT_FOUND)
    return approval


def _lock_approval(session: Session, workspace_id: UUID, approval_id: UUID) -> Approval:
    approval = session.scalar(
        select(Approval)
        .where(Approval.id == approval_id, Approval.workspace_id == workspace_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if approval is None:
        raise NotFoundError(APPROVAL_NOT_FOUND)
    return approval


def _lock_caller_authority(
    session: Session,
    workspace_id: UUID,
    caller_id: UUID,
    *related_user_ids: UUID,
) -> CallerAuthority:
    """Share-lock Workspace, Users, and Memberships in order; return caller authority."""

    workspace_status = session.scalar(
        select(WorkspaceModel.status)
        .where(WorkspaceModel.id == workspace_id)
        .with_for_update(read=True)
    )
    user_ids = {caller_id, *related_user_ids}
    user_status = dict(
        session.execute(
            select(User.id, User.status)
            .where(User.id.in_(user_ids))
            .order_by(User.id)
            .with_for_update(read=True)
        ).all()
    )
    memberships = {
        row.user_id: row
        for row in session.execute(
            select(Membership.user_id, Membership.id, Membership.role, Membership.status)
            .where(Membership.workspace_id == workspace_id, Membership.user_id.in_(user_ids))
            .order_by(Membership.user_id)
            .with_for_update(read=True)
        )
    }
    membership = memberships.get(caller_id)
    if (
        workspace_status is not WorkspaceStatus.ACTIVE
        or user_status.get(caller_id) is not UserStatus.ACTIVE
        or membership is None
        or membership.status is not MembershipStatus.ACTIVE
    ):
        raise ForbiddenError(WORKSPACE_ACCESS_DENIED)
    return CallerAuthority(membership_id=membership.id, role=membership.role)


def _current_reviewer_roles(approval: Approval) -> frozenset[MembershipRole]:
    snapshot = approval.capability_snapshot
    tool_key = snapshot.get("tool_key") if isinstance(snapshot, dict) else None
    definition = get_tool_definition(str(tool_key))
    if definition is None or definition.approval is None:
        return frozenset()
    return frozenset(definition.approval.policy.required_reviewer_roles)


def _snapshot_reviewer_roles(approval: Approval) -> frozenset[str]:
    policy = approval.policy_snapshot
    roles = policy.get("required_reviewer_roles") if isinstance(policy, dict) else None
    if not isinstance(roles, list):
        return frozenset()
    return frozenset(role for role in roles if isinstance(role, str))


def _is_visible(approval: Approval, user_id: UUID, role: MembershipRole) -> bool:
    return approval.requester_id == user_id or role in _current_reviewer_roles(approval)


def _may_decide(approval: Approval, user_id: UUID, role: MembershipRole) -> bool:
    return (
        approval.requester_id != user_id
        and role in _current_reviewer_roles(approval)
        and role.value in _snapshot_reviewer_roles(approval)
    )


def _require_decider(approval: Approval, user_id: UUID, role: MembershipRole) -> None:
    if not _is_visible(approval, user_id, role):
        raise NotFoundError(APPROVAL_NOT_FOUND)
    if not _may_decide(approval, user_id, role):
        raise ForbiddenError(APPROVAL_ACTION_NOT_PERMITTED)


def _require_canceller(approval: Approval, user_id: UUID, role: MembershipRole) -> None:
    if not _is_visible(approval, user_id, role):
        raise NotFoundError(APPROVAL_NOT_FOUND)
    if approval.requester_id != user_id:
        raise ForbiddenError(APPROVAL_ACTION_NOT_PERMITTED)


def _transition(
    session: Session,
    approval: Approval,
    **values: object,
) -> None:
    result = session.execute(
        update(Approval)
        .where(
            Approval.id == approval.id,
            Approval.workspace_id == approval.workspace_id,
            Approval.decision_status == ApprovalDecisionStatus.PENDING,
        )
        .values(updated_at=func.clock_timestamp(), **values)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        raise ConflictError(APPROVAL_NOT_PENDING)


def _decision_time(session: Session, approval: Approval) -> datetime:
    """Wall-clock time read after the lock; expires the Approval when due."""

    decided_at = _db_now(session)
    if decided_at < approval.expires_at:
        return decided_at
    _transition(
        session,
        approval,
        decision_status=ApprovalDecisionStatus.EXPIRED,
        decided_at=Approval.expires_at,
    )
    session.commit()
    raise ConflictError(APPROVAL_EXPIRED)


def _run_locked(session: Session, operation: Callable[[], None]) -> None:
    session.execute(text(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'"))
    try:
        operation()
    except OperationalError as exc:
        if not _is_lock_timeout(exc):
            raise
        session.rollback()
        raise ConflictError(APPROVAL_BUSY) from exc


def decide_approval(
    session: Session,
    *,
    workspace_id: UUID,
    approval_id: UUID,
    user_id: UUID,
    decision: Literal["approve", "reject"],
    note: str | None,
) -> None:
    """Approve or reject; commits every state change before any error."""

    def operation() -> None:
        # Non-locking precheck: invisible callers get the uniform 404 here.
        precheck = _fresh_caller(session, workspace_id, user_id)
        _require_decider(
            _read_approval(session, workspace_id, approval_id), user_id, precheck.role
        )

        approval = _lock_approval(session, workspace_id, approval_id)
        caller = _lock_caller_authority(
            session, workspace_id, user_id, approval.requester_id
        )
        _require_decider(approval, user_id, caller.role)

        if approval.decision_status is not ApprovalDecisionStatus.PENDING:
            replay = approval.decided_by == user_id and (
                (decision == "approve"
                 and approval.decision_status is ApprovalDecisionStatus.APPROVED)
                or (decision == "reject"
                    and approval.decision_status is ApprovalDecisionStatus.REJECTED)
            )
            if replay:
                session.commit()
                return
            raise ConflictError(APPROVAL_NOT_PENDING)
        decided_at = _decision_time(session, approval)

        if decision == "reject":
            _transition(
                session,
                approval,
                decision_status=ApprovalDecisionStatus.REJECTED,
                decided_by=user_id,
                decided_at=decided_at,
                decision_note=note,
            )
            session.commit()
            return

        _approve(session, approval, workspace_id=workspace_id, reviewer_id=user_id, note=note)

    _run_locked(session, operation)


def _approve(
    session: Session,
    approval: Approval,
    *,
    workspace_id: UUID,
    reviewer_id: UUID,
    note: str | None,
) -> None:
    authorization = authorize_execution(session, approval, workspace_id=workspace_id)
    # Execution authorization may wait on Agent, Tool, and assignment locks, so
    # expiry is evaluated again once every blocking lock is held. Nothing after
    # this point waits on a lock, so an Approval never becomes approved (or
    # invalidated) after expires_at.
    decided_at = _decision_time(session, approval)
    if not authorization.authorized:
        # H3: nothing is approved or executed; the snapshot is never refreshed.
        _transition(
            session,
            approval,
            decision_status=ApprovalDecisionStatus.INVALIDATED,
            decided_at=decided_at,
            invalidation_reason=authorization.reason,
            invalidation_triggered_by=reviewer_id,
        )
        session.commit()
        raise ApprovalOutcomeError(
            APPROVAL_INVALIDATED, status_code=409, approval_id=approval.id
        )

    assert authorization.requirement is not None
    assert authorization.arguments is not None
    executor = WRITE_EXECUTORS[authorization.requirement.executor_key]
    context = ApprovalExecutionContext(
        workspace_id=workspace_id,
        approval_id=approval.id,
        requester_id=approval.requester_id,
        reviewer_id=reviewer_id,
        agent_id=approval.agent_id,
        tool_id=approval.tool_id,
    )
    succeeded = True
    try:
        # The Mock row and its validated result commit only together with
        # approved/succeeded; any adapter error rolls the savepoint back.
        with session.begin_nested():
            raw_result = executor(session, context, authorization.arguments)
            ITAccessRequestExecutionResult.model_validate(
                raw_result.model_dump() if isinstance(raw_result, BaseModel) else raw_result
            )
    except Exception:  # noqa: BLE001 - any adapter failure is adapter_error
        succeeded = False

    # The legal-pair CHECK forbids approved/not_started, so the decision and
    # the execution outcome are written by one statement.
    _transition(
        session,
        approval,
        decision_status=ApprovalDecisionStatus.APPROVED,
        decided_by=reviewer_id,
        decided_at=decided_at,
        decision_note=note,
        execution_status=(
            ApprovalExecutionStatus.SUCCEEDED if succeeded else ApprovalExecutionStatus.FAILED
        ),
        executed_at=func.clock_timestamp(),
        execution_failure_category=(
            None if succeeded else ApprovalExecutionFailure.ADAPTER_ERROR
        ),
    )
    session.commit()
    if not succeeded:
        raise ApprovalOutcomeError(
            APPROVAL_EXECUTION_FAILED, status_code=502, approval_id=approval.id
        )


def cancel_approval(
    session: Session,
    *,
    workspace_id: UUID,
    approval_id: UUID,
    user_id: UUID,
) -> None:
    def operation() -> None:
        precheck = _fresh_caller(session, workspace_id, user_id)
        _require_canceller(
            _read_approval(session, workspace_id, approval_id), user_id, precheck.role
        )

        approval = _lock_approval(session, workspace_id, approval_id)
        caller = _lock_caller_authority(session, workspace_id, user_id)
        _require_canceller(approval, user_id, caller.role)
        if approval.decision_status is not ApprovalDecisionStatus.PENDING:
            if approval.decision_status is ApprovalDecisionStatus.CANCELLED:
                session.commit()
                return
            raise ConflictError(APPROVAL_NOT_PENDING)
        decided_at = _decision_time(session, approval)
        _transition(
            session,
            approval,
            decision_status=ApprovalDecisionStatus.CANCELLED,
            decided_by=user_id,
            decided_at=decided_at,
        )
        session.commit()

    _run_locked(session, operation)


# --- Reads ------------------------------------------------------------------


def _response_statement() -> Select[Any]:
    requester = aliased(User)
    decider = aliased(User)
    return (
        select(
            Approval,
            Agent.name.label("agent_name"),
            Tool.name.label("tool_name"),
            requester.name.label("requester_name"),
            decider.name.label("decider_name"),
            MockITAccessRequest.reference.label("mock_reference"),
            MockITAccessRequest.system.label("mock_system"),
            MockITAccessRequest.access_level.label("mock_access_level"),
            MockITAccessRequest.duration_days.label("mock_duration_days"),
            MockITAccessRequest.status.label("mock_status"),
        )
        .join(
            Agent,
            and_(Agent.id == Approval.agent_id, Agent.workspace_id == Approval.workspace_id),
        )
        .join(
            Tool,
            and_(Tool.id == Approval.tool_id, Tool.workspace_id == Approval.workspace_id),
        )
        .join(requester, requester.id == Approval.requester_id)
        .outerjoin(decider, decider.id == Approval.decided_by)
        .outerjoin(
            MockITAccessRequest,
            and_(
                MockITAccessRequest.approval_id == Approval.id,
                MockITAccessRequest.workspace_id == Approval.workspace_id,
            ),
        )
        .execution_options(populate_existing=True)
    )


def _to_response(row: Any, now: datetime) -> ApprovalResponse:
    approval: Approval = row.Approval
    decision_status = approval.decision_status
    decided_at = approval.decided_at
    if decision_status is ApprovalDecisionStatus.PENDING and now >= approval.expires_at:
        decision_status = ApprovalDecisionStatus.EXPIRED
        decided_at = approval.expires_at

    decision = None
    if decision_status is not ApprovalDecisionStatus.PENDING:
        assert decided_at is not None
        decision = ApprovalDecisionDetail(
            decided_by=(
                None
                if approval.decided_by is None
                else ApprovalPartyReference(id=approval.decided_by, name=row.decider_name)
            ),
            decided_at=decided_at,
            note=approval.decision_note,
            invalidation_reason=approval.invalidation_reason,
        )

    execution = None
    if approval.execution_status is not ApprovalExecutionStatus.NOT_STARTED:
        assert approval.executed_at is not None
        execution = {
            "executed_at": approval.executed_at,
            "failure_category": approval.execution_failure_category,
            "result": (
                {
                    "reference": row.mock_reference,
                    "system": row.mock_system,
                    "access_level": row.mock_access_level,
                    "duration_days": row.mock_duration_days,
                    "status": row.mock_status,
                }
                if approval.execution_status is ApprovalExecutionStatus.SUCCEEDED
                else None
            ),
        }

    snapshot = approval.capability_snapshot
    try:
        return ApprovalResponse(
            id=approval.id,
            workspace_id=approval.workspace_id,
            decision_status=decision_status,
            execution_status=approval.execution_status,
            action_type=approval.action_type,
            tool={"tool_key": snapshot.get("tool_key"), "name": row.tool_name},
            agent=ApprovalPartyReference(id=approval.agent_id, name=row.agent_name),
            requester=ApprovalPartyReference(
                id=approval.requester_id, name=row.requester_name
            ),
            arguments=approval.canonical_arguments,
            created_at=approval.created_at,
            expires_at=approval.expires_at,
            decision=decision,
            execution=execution,
        )
    except (ValidationError, AttributeError, KeyError, TypeError) as exc:
        raise ApprovalConfigurationError(APPROVAL_CONFIGURATION_UNAVAILABLE) from exc


def get_approval_response(
    session: Session, workspace_id: UUID, approval_id: UUID
) -> ApprovalResponse:
    """Build the representation after an authorized decision or cancel."""

    row = session.execute(
        _response_statement().where(
            Approval.id == approval_id, Approval.workspace_id == workspace_id
        )
    ).one_or_none()
    if row is None:
        raise NotFoundError(APPROVAL_NOT_FOUND)
    return _to_response(row, _db_now(session))


def read_approval(
    session: Session,
    *,
    workspace_id: UUID,
    approval_id: UUID,
    user_id: UUID,
    role: MembershipRole,
) -> ApprovalResponse:
    row = session.execute(
        _response_statement().where(
            Approval.id == approval_id, Approval.workspace_id == workspace_id
        )
    ).one_or_none()
    if row is None or not _is_visible(row.Approval, user_id, role):
        raise NotFoundError(APPROVAL_NOT_FOUND)
    return _to_response(row, _db_now(session))


def _effective_status_filter(status: ApprovalDecisionStatus) -> ColumnElement[bool]:
    pending = Approval.decision_status == ApprovalDecisionStatus.PENDING
    if status is ApprovalDecisionStatus.PENDING:
        return and_(pending, Approval.expires_at > func.clock_timestamp())
    if status is ApprovalDecisionStatus.EXPIRED:
        return or_(
            Approval.decision_status == ApprovalDecisionStatus.EXPIRED,
            and_(pending, Approval.expires_at <= func.clock_timestamp()),
        )
    return Approval.decision_status == status


def list_approvals(
    session: Session,
    *,
    workspace_id: UUID,
    user_id: UUID,
    role: MembershipRole,
    scope: Literal["mine", "review"],
    decision_status: ApprovalDecisionStatus | None,
    execution_status: ApprovalExecutionStatus | None,
    limit: int,
    offset: int,
) -> list[ApprovalResponse]:
    statement = _response_statement().where(Approval.workspace_id == workspace_id)
    if scope == "review":
        if role not in REVIEWER_ROLES:
            raise ForbiddenError(APPROVAL_REVIEW_NOT_PERMITTED)
    else:
        statement = statement.where(Approval.requester_id == user_id)
    if decision_status is not None:
        statement = statement.where(_effective_status_filter(decision_status))
    if execution_status is not None:
        statement = statement.where(Approval.execution_status == execution_status)
    rows = session.execute(
        statement.order_by(Approval.created_at.desc(), Approval.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    now = _db_now(session)
    return [_to_response(row, now) for row in rows]
