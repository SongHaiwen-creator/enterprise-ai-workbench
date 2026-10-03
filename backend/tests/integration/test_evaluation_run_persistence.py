import hashlib
import subprocess
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, update
from sqlalchemy.exc import IntegrityError

from alembic import command
from app.db.base import Base
from app.models import EvaluationRun, EvaluationRunCase
from app.schemas.evaluation_run import RunCreate
from app.services import evaluation_runs
from app.services.exceptions import ConflictError
from tests.integration.test_evaluation_run_api import add_case

pytest_plugins = ["tests.integration.test_evaluation_run_api"]
pytestmark = pytest.mark.integration
BACKEND = Path(__file__).resolve().parents[2]


def test_0012_roundtrip_existing_tables_unchanged(postgres_engine, database_urls):
    assert database_urls[1].database == "enterprise_ai_workbench_test"
    config = Config(str(BACKEND / "alembic.ini"))
    script = ScriptDirectory.from_config(config)
    assert script.get_heads() == ["0012"]
    assert script.get_revision("0012").down_revision == "0011"
    with postgres_engine.connect() as connection:
        config.attributes["connection"] = connection
        try:
            command.downgrade(config, "0011")
            before = {
                name: inspect(connection).get_columns(name)
                for name in inspect(connection).get_table_names()
            }
            command.upgrade(config, "0012")
            inspector = inspect(connection)
            assert set(inspector.get_table_names()) - set(before) == {
                "evaluation_runs",
                "evaluation_run_cases",
            }
            for name, columns in before.items():
                assert repr(inspector.get_columns(name)) == repr(columns)
            assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
            for name in ("evaluation_runs", "evaluation_run_cases"):
                assert all(
                    fk["options"]["ondelete"] == "RESTRICT"
                    for fk in inspector.get_foreign_keys(name)
                )
            command.downgrade(config, "0011")
            assert set(inspect(connection).get_table_names()) == set(before)
            command.upgrade(config, "0012")
            assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
        finally:
            connection.rollback()
            command.upgrade(config, "head")


def test_migrations_0001_through_0011_unchanged():
    for path in (BACKEND / "alembic" / "versions").glob("*.py"):
        if path.name[:4] > "0011":
            continue
        original = subprocess.check_output(
            ["git", "show", f"5c829ab:{path.relative_to(BACKEND.parent).as_posix()}"],
            cwd=BACKEND.parent,
        )
        assert (
            hashlib.sha256(original).digest()
            == hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).digest()
        )


@pytest.mark.parametrize(
    "model,values",
    [
        (EvaluationRun, {"status": "unknown"}),
        (EvaluationRun, {"total_cases": 6}),
        (EvaluationRun, {"passed_cases": 2}),
        (EvaluationRun, {"status": "completed"}),
        (EvaluationRun, {"status": "failed", "failure_category": "secret"}),
        (EvaluationRun, {"configuration_sha256": "bad"}),
        (EvaluationRun, {"config_snapshot": []}),
        (EvaluationRunCase, {"result": "error"}),
        (EvaluationRunCase, {"error_category": "internal_error"}),
        (EvaluationRunCase, {"result": "passed"}),
        (EvaluationRunCase, {"ordinal": 6}),
        (EvaluationRunCase, {"test_input_snapshot": " "}),
        (EvaluationRunCase, {"expected_behavior_snapshot": {}}),
        (EvaluationRunCase, {"case_type": "unknown"}),
        (EvaluationRunCase, {"latency_ms": -1}),
    ],
)
def test_run_constraints_reject_illegal_state(db_session, scenario, model, values):
    s = scenario
    add_case(db_session, s, "permission_boundary")
    run_id = evaluation_runs.capture(
        db_session,
        s.workspace.id,
        s.dataset.id,
        s.user.id,
        RunCreate(agent_id=s.agent.id, provider_egress_acknowledged=False),
        s.settings,
    )
    query = update(model)
    query = (
        query.where(model.id == run_id)
        if model is EvaluationRun
        else query.where(model.run_id == run_id)
    )
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.execute(query.values(**values))
        db_session.flush()


def test_running_concurrency_blocks_second_capture(db_session, scenario):
    s = scenario
    add_case(db_session, s, "permission_boundary")
    payload = RunCreate(agent_id=s.agent.id, provider_egress_acknowledged=False)
    evaluation_runs.capture(
        db_session, s.workspace.id, s.dataset.id, s.user.id, payload, s.settings
    )
    with pytest.raises(ConflictError, match="busy"):
        evaluation_runs.capture(
            db_session, s.workspace.id, s.dataset.id, s.user.id, payload, s.settings
        )
