import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import select

from app.models import BadCase, BadCaseHistory, EvaluationRunCase, Membership
from app.models.enums import MembershipRole
from app.schemas.bad_case import BadCaseCreate, BadCaseUpdate
from app.schemas.evaluation_run import RunCreate
from app.services import bad_cases, evaluation_runs
from app.services.exceptions import ConflictError, ForbiddenError

pytest_plugins = ["tests.integration.test_evaluation_run_concurrency"]
pytestmark = pytest.mark.integration


@pytest.fixture
def issue_context(committed):
    factory, s = committed
    with factory() as session:
        run = evaluation_runs.create_run(
            session,
            s.workspace,
            s.dataset,
            s.user,
            RunCreate(agent_id=s.agent, provider_egress_acknowledged=False),
            s.settings,
        )
        case_id = session.scalar(
            select(EvaluationRunCase.id).where(EvaluationRunCase.run_id == run.id)
        )
    try:
        yield factory, s, run.id, case_id
    finally:
        with factory() as session:
            session.query(BadCaseHistory).filter_by(workspace_id=s.workspace).delete()
            session.query(BadCase).filter_by(workspace_id=s.workspace).delete()
            session.commit()


def create(factory, s, run_id, case_id):
    with factory() as session:
        return bad_cases.create(
            session,
            s.workspace,
            run_id,
            case_id,
            s.user,
            BadCaseCreate(title="Synthetic issue", description="Redacted"),
        )


def test_concurrent_register_and_revision_conflicts(issue_context):
    factory, s, run_id, case_id = issue_context
    barrier = threading.Barrier(2)

    def register():
        barrier.wait(timeout=10)
        try:
            return create(factory, s, run_id, case_id)
        except ConflictError as error:
            return str(error)

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = [f.result(timeout=20) for f in [executor.submit(register) for _ in range(2)]]
    assert sum(isinstance(r, str) for r in responses) == 1
    item = next(r for r in responses if not isinstance(r, str))
    barrier = threading.Barrier(2)

    def edit(title):
        with factory() as session:
            barrier.wait(timeout=10)
            try:
                return bad_cases.update(
                    session,
                    s.workspace,
                    item.id,
                    s.user,
                    BadCaseUpdate(expected_revision=1, title=title),
                )
            except ConflictError as error:
                return str(error)

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = [
            f.result(timeout=20)
            for f in [executor.submit(edit, title) for title in ("First", "Second")]
        ]
    assert sum(isinstance(r, str) for r in responses) == 1
    with factory() as session:
        entries = bad_cases.history(session, s.workspace, item.id, s.user, 50, 0)
        assert [r.revision for r in entries] == [1, 2]
        assert session.get(BadCase, item.id).revision == 2


def test_bounded_row_lock_timeout(issue_context):
    factory, s, run_id, case_id = issue_context
    item = create(factory, s, run_id, case_id)
    with factory() as holder, factory() as writer:
        holder.scalar(select(BadCase).where(BadCase.id == item.id).with_for_update())
        with pytest.raises(ConflictError, match="Bad case resource is busy"):
            bad_cases.update(
                writer,
                s.workspace,
                item.id,
                s.user,
                BadCaseUpdate(expected_revision=1, title="Locked"),
            )
        holder.rollback()
    with factory() as session:
        assert session.get(BadCase, item.id).revision == 1


@pytest.mark.parametrize("operation", ["create", "update", "read"])
def test_current_authority_revoked_before_commit_or_return(issue_context, monkeypatch, operation):
    factory, s, run_id, case_id = issue_context
    item = create(factory, s, run_id, case_id) if operation != "create" else None
    original = bad_cases.current_authority
    calls = 0

    def authority(session, workspace, actor):
        nonlocal calls
        calls += 1
        if calls == 2:
            with factory() as revoker:
                member = revoker.scalar(
                    select(Membership).where(
                        Membership.workspace_id == workspace, Membership.user_id == actor
                    )
                )
                member.role = MembershipRole.EMPLOYEE
                revoker.commit()
        return original(session, workspace, actor)

    monkeypatch.setattr(bad_cases, "current_authority", authority)
    with factory() as session, pytest.raises(ForbiddenError):
        if operation == "create":
            bad_cases.create(
                session,
                s.workspace,
                run_id,
                case_id,
                s.user,
                BadCaseCreate(title="Denied", description="Redacted"),
            )
        elif operation == "update":
            bad_cases.update(
                session,
                s.workspace,
                item.id,
                s.user,
                BadCaseUpdate(expected_revision=1, title="Denied"),
            )
        else:
            bad_cases.read(session, s.workspace, item.id, s.user)
    with factory() as session:
        rows = session.scalars(select(BadCase).where(BadCase.workspace_id == s.workspace)).all()
        assert len(rows) == (0 if item is None else 1)
        if item:
            assert rows[0].title == item.title and rows[0].revision == 1
