import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.models import (
    Agent,
    EvaluationCase,
    EvaluationDataset,
    EvaluationRun,
    EvaluationRunCase,
    Membership,
    User,
    Workspace,
)
from app.models.enums import AgentStatus, MembershipRole
from app.schemas.evaluation import CaseCreate, DatasetCreate
from app.schemas.evaluation_run import RunCreate
from app.services import evaluation, evaluation_runs
from app.services.exceptions import ConflictError
from tests.evaluation_support import case_body
from tests.integration.test_knowledge_base_api import add_membership, create_user, create_workspace

pytestmark = pytest.mark.integration


@pytest.fixture
def committed(postgres_engine, database_urls):
    runtime, test = database_urls
    assert test.database == "enterprise_ai_workbench_test"
    factory = sessionmaker(postgres_engine, expire_on_commit=False, autoflush=False)
    settings = Settings(
        database_url=str(runtime),
        test_database_url=str(test),
        jwt_secret_key="evaluation-concurrent-secret-longer-than-32",
        _env_file=None,
    )
    with factory() as session:
        user = create_user(session, email=f"concurrent-run-{uuid4()}@example.test")
        workspace = create_workspace(session, slug=f"concurrent-run-{uuid4()}")
        add_membership(session, user, workspace, role=MembershipRole.AGENT_ADMIN)
        agent = Agent(
            workspace_id=workspace.id,
            created_by=user.id,
            name="Synthetic",
            system_prompt="Synthetic",
            status=AgentStatus.ACTIVE,
        )
        session.add(agent)
        session.commit()
        dataset = evaluation.create_dataset(
            session, workspace.id, user.id, DatasetCreate(name="Synthetic")
        )
        case = evaluation.create_case(
            session,
            workspace.id,
            dataset.id,
            user.id,
            CaseCreate.model_validate(case_body("permission_boundary")),
        )
    s = SimpleNamespace(
        user=user.id,
        workspace=workspace.id,
        agent=agent.id,
        dataset=dataset.id,
        case=case.id,
        settings=settings,
    )
    try:
        yield factory, s
    finally:
        with factory() as session:
            for model in (
                EvaluationRunCase,
                EvaluationRun,
                EvaluationCase,
                EvaluationDataset,
                Agent,
                Membership,
            ):
                session.query(model).filter_by(workspace_id=s.workspace).delete()
            session.query(Workspace).filter_by(id=s.workspace).delete()
            session.query(User).filter_by(id=s.user).delete()
            session.commit()


def capture(factory, s):
    with factory() as session:
        try:
            return evaluation_runs.capture(
                session,
                s.workspace,
                s.dataset,
                s.user,
                RunCreate(agent_id=s.agent, provider_egress_acknowledged=False),
                s.settings,
            )
        except ConflictError:
            return "busy"


def test_competing_sessions_allow_exactly_one_running_run(committed):
    factory, s = committed
    barrier = threading.Barrier(2)

    def concurrent():
        barrier.wait(timeout=5)
        return capture(factory, s)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(concurrent) for _ in range(2)]
        results = [future.result(timeout=15) for future in futures]
    assert results.count("busy") == 1
    with factory() as session:
        assert (
            len(
                session.scalars(
                    select(EvaluationRun).where(EvaluationRun.workspace_id == s.workspace)
                ).all()
            )
            == 1
        )


def test_source_edit_while_capture_waits_uses_latest_locked_definition(committed, postgres_engine):
    factory, s = committed
    reached_lock = threading.Event()

    def before_cursor(conn, cursor, statement, parameters, context, executemany):
        if "evaluation_datasets" in statement and "FOR UPDATE" in statement:
            reached_lock.set()

    with factory() as editor, ThreadPoolExecutor(max_workers=1) as executor:
        evaluation.get_dataset(editor, s.workspace, s.dataset, lock=True)
        event.listen(postgres_engine, "before_cursor_execute", before_cursor)
        try:
            future = executor.submit(capture, factory, s)
            assert reached_lock.wait(5)
            case = editor.get(EvaluationCase, s.case)
            case.test_input = "Latest synthetic definition"
            editor.commit()
            run_id = future.result(timeout=15)
        finally:
            event.remove(postgres_engine, "before_cursor_execute", before_cursor)
    with factory() as session:
        row = evaluation_runs.case_rows(session, s.workspace, run_id)[0]
        assert row.test_input_snapshot == "Latest synthetic definition"
