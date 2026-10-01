"""Production-session transaction boundaries for Feature 014."""

import threading
import time
from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, select, text, update
from sqlalchemy.orm import Session, sessionmaker

from app.models import Agent, ExecutionLog, Workspace
from app.models.enums import ExecutionLogErrorCategory, ExecutionLogOperation
from app.services.execution_logs import execution_log
from tests.integration.approval_support import Scenario, make_scenario

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


def run(
    session: Session, scenario: Scenario, body: Callable[[Session], None]
) -> BaseException | None:
    try:
        with execution_log(
            session,
            workspace_id=scenario.workspace.id,
            user_id=scenario.requester.id,
            operation=ExecutionLogOperation.AGENT_ROUTE,
        ):
            body(session)
    except BaseException as exc:
        return exc
    return None


def agent_name(factory: sessionmaker[Session], agent_id: UUID) -> str:
    with factory() as session:
        return session.scalar(select(Agent.name).where(Agent.id == agent_id))


def logs(factory: sessionmaker[Session], scenario: Scenario) -> list[ExecutionLog]:
    with factory() as session:
        return list(session.scalars(select(ExecutionLog).where(
            ExecutionLog.workspace_id == scenario.workspace.id
        )))


@pytest.mark.parametrize("flush", [False, True])
def test_pending_and_flushed_pre_entry_orm_state_is_never_committed(
    factory: sessionmaker[Session], scenario: Scenario, flush: bool
) -> None:
    slug = f"pre-entry-orm-{uuid4().hex}"
    with factory() as session:
        session.add(Workspace(name="Pre-entry state", slug=slug))
        if flush:
            session.flush()
        assert run(session, scenario, lambda _: None) is None
    with factory() as session:
        assert session.scalar(select(Workspace.id).where(Workspace.slug == slug)) is None
    assert len(logs(factory, scenario)) == 1


@pytest.mark.parametrize("kind", ["core", "text", "connection"])
def test_pre_entry_dml_is_never_committed(
    factory: sessionmaker[Session], scenario: Scenario, kind: str
) -> None:
    marker = f"pre-entry-{kind}"
    statement = update(Agent).where(Agent.id == scenario.agent.id).values(name=marker)
    with factory() as session:
        if kind == "core":
            session.execute(statement)
        elif kind == "text":
            session.execute(text("UPDATE agents SET name=:name WHERE id=:id"), {
                "name": marker, "id": scenario.agent.id,
            })
        else:
            session.connection().execute(statement)
        assert run(session, scenario, lambda _: None) is None
    assert agent_name(factory, scenario.agent.id) != marker
    assert len(logs(factory, scenario)) == 1


@pytest.mark.parametrize("kind", ["core", "text", "connection"])
def test_handler_dml_without_commit_is_never_committed(
    factory: sessionmaker[Session], scenario: Scenario, kind: str
) -> None:
    marker = f"handler-{kind}"

    def body(session: Session) -> None:
        statement = update(Agent).where(Agent.id == scenario.agent.id).values(name=marker)
        if kind == "core":
            session.execute(statement)
        elif kind == "text":
            session.execute(text("UPDATE agents SET name=:name WHERE id=:id"), {
                "name": marker, "id": scenario.agent.id,
            })
        else:
            session.connection().execute(statement)

    with factory() as session:
        assert run(session, scenario, body) is None
    assert agent_name(factory, scenario.agent.id) != marker
    assert len(logs(factory, scenario)) == 1


@pytest.mark.parametrize("kind", ["core", "text", "connection", "nested_rollback"])
def test_post_commit_dml_is_never_committed(
    factory: sessionmaker[Session], scenario: Scenario, kind: str
) -> None:
    marker = f"post-commit-{kind}"

    def body(session: Session) -> None:
        session.commit()
        statement = update(Agent).where(Agent.id == scenario.agent.id).values(name=marker)
        if kind == "core":
            session.execute(statement)
        elif kind == "text":
            session.execute(text("UPDATE agents SET name=:name WHERE id=:id"), {
                "name": marker, "id": scenario.agent.id,
            })
        elif kind == "connection":
            session.connection().execute(statement)
        else:
            session.execute(statement)
            with pytest.raises(ValueError):
                with session.begin_nested():
                    raise ValueError("handled nested rollback")

    with factory() as session:
        assert run(session, scenario, body) is None
    assert agent_name(factory, scenario.agent.id) != marker
    assert len(logs(factory, scenario)) == 1


def test_post_commit_database_error_records_internal_error(
    factory: sessionmaker[Session], scenario: Scenario
) -> None:
    def body(session: Session) -> None:
        session.commit()
        session.execute(text("SELECT 1/0"))

    with factory() as session:
        assert run(session, scenario, body) is not None
    rows = logs(factory, scenario)
    assert len(rows) == 1
    assert rows[0].error_category is ExecutionLogErrorCategory.INTERNAL_ERROR
    assert rows[0].http_status == 500


def test_log_lock_timeout_preserves_committed_business_state(
    factory: sessionmaker[Session], postgres_engine: Engine, scenario: Scenario
) -> None:
    locked = threading.Event()
    marker = f"committed-before-log-timeout-{uuid4().hex}"

    def hold_tool_lock() -> None:
        with postgres_engine.connect() as connection:
            connection.execute(
                text("SELECT id FROM tools WHERE id=:id FOR UPDATE"),
                {"id": scenario.tool.id},
            )
            locked.set()
            time.sleep(1)
            connection.rollback()

    holder = threading.Thread(target=hold_tool_lock)
    holder.start()
    assert locked.wait(timeout=1)
    with factory() as session:
        with execution_log(
            session,
            workspace_id=scenario.workspace.id,
            user_id=scenario.requester.id,
            operation=ExecutionLogOperation.AGENT_ROUTE,
        ) as trace:
            trace.tool_id = scenario.tool.id
            session.execute(
                update(Agent).where(Agent.id == scenario.agent.id).values(name=marker)
            )
            session.commit()
    holder.join(timeout=2)

    assert agent_name(factory, scenario.agent.id) == marker
    assert logs(factory, scenario) == []
