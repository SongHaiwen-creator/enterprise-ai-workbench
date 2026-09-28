"""Feature 013 guarantees that need real commits and separate connections.

These tests commit to the dedicated ``_test`` database (reset for every test
session) and use unique Workspaces, so they never affect other tests.
"""

import threading
from collections.abc import Callable, Generator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.models import Approval, MockITAccessRequest
from app.models.enums import (
    ApprovalDecisionStatus,
    ApprovalExecutionStatus,
    MembershipRole,
)
from app.schemas.tool_calling import CreateITAccessRequestArguments
from app.services import approvals
from app.services.approval_execution import execute_mock_it_access_request
from app.services.exceptions import ConflictError
from app.services.tool_registry import get_tool_definition
from tests.integration.approval_support import (
    ARGUMENTS,
    INVALIDATED,
    FakeRoutingProvider,
    FakeToolSelector,
    Scenario,
    decide,
    install_overrides,
    make_membership,
    make_scenario,
    make_settings,
    make_user,
    request_approval,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def factory(postgres_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=postgres_engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def scenario(factory: sessionmaker[Session]) -> Scenario:
    with factory() as session:
        result = make_scenario(session)
        session.commit()
    return result


@pytest.fixture
def settings(database_urls: tuple[object, object]) -> Settings:
    return make_settings(database_urls)


@pytest.fixture
def selector() -> FakeToolSelector:
    return FakeToolSelector()


@pytest.fixture
def client(
    factory: sessionmaker[Session],
    settings: Settings,
    selector: FakeToolSelector,
) -> Generator[TestClient, None, None]:
    def production_like_session() -> Generator[Session, None, None]:
        session = factory()
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    yield from install_overrides(
        production_like_session, settings, FakeRoutingProvider(), selector
    )


def create(factory: sessionmaker[Session], scenario: Scenario) -> Any:
    definition = get_tool_definition("create_it_access_request")
    assert definition is not None
    with factory() as session:
        approval = approvals.create_pending_approval(
            session,
            workspace_id=scenario.workspace.id,
            requester_id=scenario.requester.id,
            agent_id=scenario.agent.id,
            tool_id=scenario.tool.id,
            definition=definition,
            arguments=CreateITAccessRequestArguments.model_validate(ARGUMENTS),
        )
    return approval.id


def state(factory: sessionmaker[Session], approval_id: Any) -> tuple[Approval, int]:
    with factory() as session:
        approval = session.get(Approval, approval_id)
        assert approval is not None
        mock_count = len(
            session.scalars(
                select(MockITAccessRequest).where(MockITAccessRequest.approval_id == approval_id)
            ).all()
        )
    return approval, mock_count


def run_parallel(*operations: Callable[[], None]) -> list[BaseException | None]:
    barrier = threading.Barrier(len(operations))
    outcomes: list[BaseException | None] = [None] * len(operations)

    def runner(index: int, operation: Callable[[], None]) -> None:
        barrier.wait()
        try:
            operation()
        except BaseException as exc:  # noqa: BLE001 - recorded for assertions
            outcomes[index] = exc

    threads = [
        threading.Thread(target=runner, args=(index, operation))
        for index, operation in enumerate(operations)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    return outcomes


def decision(
    factory: sessionmaker[Session],
    scenario: Scenario,
    approval_id: Any,
    user_id: Any,
    choice: str = "approve",
) -> Callable[[], None]:
    def operation() -> None:
        with factory() as session:
            if choice == "cancel":
                approvals.cancel_approval(
                    session, workspace_id=scenario.workspace.id,
                    approval_id=approval_id, user_id=user_id,
                )
            else:
                approvals.decide_approval(
                    session, workspace_id=scenario.workspace.id, approval_id=approval_id,
                    user_id=user_id, decision=choice,  # type: ignore[arg-type]
                    note=None,
                )

    return operation


@pytest.mark.parametrize("competitor", ["approve", "reject", "cancel"])
def test_competing_decisions_serialize_with_at_most_one_write(
    factory: sessionmaker[Session],
    scenario: Scenario,
    competitor: str,
) -> None:
    with factory() as session:
        second_reviewer = make_user(session, "Admin Two")
        make_membership(session, second_reviewer, scenario.workspace, MembershipRole.SYSTEM_ADMIN)
        session.commit()
    approval_id = create(factory, scenario)
    competitor_user = (
        scenario.requester.id if competitor == "cancel" else second_reviewer.id
    )

    outcomes = run_parallel(
        decision(factory, scenario, approval_id, scenario.reviewer.id),
        decision(factory, scenario, approval_id, competitor_user, competitor),
    )

    assert sorted(outcome is None for outcome in outcomes) == [False, True]
    loser = next(outcome for outcome in outcomes if outcome is not None)
    assert isinstance(loser, ConflictError)
    assert loser.detail == "Approval is no longer pending"
    approval, mock_count = state(factory, approval_id)
    if approval.decision_status is ApprovalDecisionStatus.APPROVED:
        assert approval.execution_status is ApprovalExecutionStatus.SUCCEEDED
        assert mock_count == 1
    else:
        assert approval.execution_status is ApprovalExecutionStatus.NOT_STARTED
        assert mock_count == 0


def test_parallel_identical_requests_create_one_pending_approval(
    factory: sessionmaker[Session],
    scenario: Scenario,
) -> None:
    created: list[Any] = []

    outcomes = run_parallel(
        lambda: created.append(create(factory, scenario)),
        lambda: created.append(create(factory, scenario)),
    )

    assert outcomes == [None, None]
    assert len(set(created)) == 1
    with factory() as session:
        rows = session.scalars(
            select(Approval).where(Approval.workspace_id == scenario.workspace.id)
        ).all()
    assert [row.id for row in rows] == [created[0]]


def test_lock_timeout_returns_conflict_without_change(
    factory: sessionmaker[Session],
    scenario: Scenario,
) -> None:
    approval_id = create(factory, scenario)
    with factory() as holder:
        holder.execute(
            text("SELECT id FROM approvals WHERE id = :id FOR UPDATE"), {"id": approval_id}
        )
        with pytest.raises(ConflictError) as raised:
            decision(factory, scenario, approval_id, scenario.reviewer.id)()
        holder.rollback()

    assert raised.value.detail == "Approval is being processed; retry"
    approval, mock_count = state(factory, approval_id)
    assert approval.decision_status is ApprovalDecisionStatus.PENDING
    assert mock_count == 0


def test_concurrent_tool_disable_waits_for_the_approve_transaction(
    factory: sessionmaker[Session],
    scenario: Scenario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    approval_id = create(factory, scenario)
    inside = threading.Event()
    release = threading.Event()

    def pausing_executor(session: Session, context: Any, arguments: Any) -> Any:
        inside.set()
        assert release.wait(timeout=20)
        return execute_mock_it_access_request(session, context, arguments)

    monkeypatch.setattr(
        "app.services.approvals.WRITE_EXECUTORS",
        {"mock_it_access_request.v1": pausing_executor},
    )
    approver = threading.Thread(
        target=decision(factory, scenario, approval_id, scenario.reviewer.id)
    )
    approver.start()
    assert inside.wait(timeout=20)

    disable = text("UPDATE tools SET status = 'disabled' WHERE id = :id")
    with factory() as admin:
        admin.execute(text("SET LOCAL lock_timeout = '300ms'"))
        with pytest.raises(OperationalError):
            admin.execute(disable, {"id": scenario.tool.id})
        admin.rollback()
    release.set()
    approver.join(timeout=30)
    with factory() as admin:
        admin.execute(disable, {"id": scenario.tool.id})
        admin.commit()

    approval, mock_count = state(factory, approval_id)
    assert approval.decision_status is ApprovalDecisionStatus.APPROVED
    assert approval.execution_status is ApprovalExecutionStatus.SUCCEEDED
    assert mock_count == 1


def test_failure_before_commit_leaves_pending_without_mock_row(
    factory: sessionmaker[Session],
    scenario: Scenario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    approval_id = create(factory, scenario)
    original = approvals._transition

    def crash_on_approval(session: Session, approval: Approval, **values: object) -> None:
        if values.get("decision_status") is ApprovalDecisionStatus.APPROVED:
            raise RuntimeError("simulated crash before commit")
        original(session, approval, **values)

    monkeypatch.setattr("app.services.approvals._transition", crash_on_approval)
    with factory() as session:
        with pytest.raises(RuntimeError):
            approvals.decide_approval(
                session, workspace_id=scenario.workspace.id, approval_id=approval_id,
                user_id=scenario.reviewer.id, decision="approve", note=None,
            )
        session.rollback()

    approval, mock_count = state(factory, approval_id)
    assert approval.decision_status is ApprovalDecisionStatus.PENDING
    assert approval.execution_status is ApprovalExecutionStatus.NOT_STARTED
    assert mock_count == 0


def test_invalidated_state_is_committed_before_the_409(
    client: TestClient,
    factory: sessionmaker[Session],
    scenario: Scenario,
    selector: FakeToolSelector,
    settings: Settings,
) -> None:
    approval_id = request_approval(client, scenario, selector, settings)
    with factory() as admin:
        admin.execute(
            text("UPDATE tools SET status = 'disabled' WHERE id = :id"),
            {"id": scenario.tool.id},
        )
        admin.commit()

    response = decide(client, scenario, approval_id, settings, note="Approved")

    assert response.status_code == 409
    assert response.json() == {"detail": INVALIDATED, "approval_id": approval_id}
    approval, mock_count = state(factory, approval_id)
    assert approval.decision_status is ApprovalDecisionStatus.INVALIDATED
    assert approval.invalidation_reason is not None
    assert approval.invalidation_reason.value == "capability_unavailable"
    assert approval.decision_note is None
    assert mock_count == 0


def test_adapter_failure_is_committed_before_the_502(
    client: TestClient,
    factory: sessionmaker[Session],
    scenario: Scenario,
    selector: FakeToolSelector,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    approval_id = request_approval(client, scenario, selector, settings)

    def failing_executor(*args: object) -> None:
        raise RuntimeError("adapter down")

    monkeypatch.setattr(
        "app.services.approvals.WRITE_EXECUTORS",
        {"mock_it_access_request.v1": failing_executor},
    )

    assert decide(client, scenario, approval_id, settings).status_code == 502
    approval, mock_count = state(factory, approval_id)
    assert approval.decision_status is ApprovalDecisionStatus.APPROVED
    assert approval.execution_status is ApprovalExecutionStatus.FAILED
    assert mock_count == 0


def test_fresh_checks_see_changes_committed_after_the_request_dependency(
    client: TestClient,
    factory: sessionmaker[Session],
    scenario: Scenario,
    selector: FakeToolSelector,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    demoted_id = request_approval(client, scenario, selector, settings)
    original_caller = approvals._fresh_caller
    demote_once = [True]

    def demote_then_check(session: Session, workspace_id: Any, user_id: Any) -> Any:
        # The dependency already loaded this reviewer's Membership entity.
        if demote_once and user_id == scenario.reviewer.id:
            demote_once.clear()
            with factory() as admin:
                admin.execute(
                    text("UPDATE memberships SET role = 'employee' WHERE id = :id"),
                    {"id": scenario.reviewer_membership.id},
                )
                admin.commit()
        return original_caller(session, workspace_id, user_id)

    monkeypatch.setattr("app.services.approvals._fresh_caller", demote_then_check)
    response = decide(client, scenario, demoted_id, settings)

    assert response.status_code == 404
    approval, mock_count = state(factory, demoted_id)
    assert approval.decision_status is ApprovalDecisionStatus.PENDING
    assert mock_count == 0

    with factory() as admin:
        admin.execute(
            text("UPDATE memberships SET role = 'system_admin' WHERE id = :id"),
            {"id": scenario.reviewer_membership.id},
        )
        admin.commit()
    original_authorize = approvals.authorize_execution

    def disable_requester_then_authorize(session: Session, approval: Any, **kwargs: Any) -> Any:
        with factory() as admin:
            admin.execute(
                text("UPDATE memberships SET status = 'disabled' WHERE id = :id"),
                {"id": scenario.requester_membership.id},
            )
            admin.commit()
        return original_authorize(session, approval, **kwargs)

    monkeypatch.setattr(
        "app.services.approvals.authorize_execution", disable_requester_then_authorize
    )
    response = decide(client, scenario, demoted_id, settings)

    assert response.status_code == 409
    approval, _ = state(factory, demoted_id)
    assert approval.invalidation_reason is not None
    assert approval.invalidation_reason.value == "requester_ineligible"
