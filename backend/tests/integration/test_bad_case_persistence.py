import hashlib
import subprocess
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, update
from sqlalchemy.exc import DataError, IntegrityError

from alembic import command
from app.db.base import Base
from app.models import BadCase, BadCaseHistory
from tests.integration.test_bad_case_api import register, seed

pytest_plugins = ["tests.integration.test_evaluation_run_api"]
pytestmark = pytest.mark.integration
BACKEND = Path(__file__).resolve().parents[2]


def test_0013_roundtrip_and_prior_schema(postgres_engine, database_urls):
    assert database_urls[1].database == "enterprise_ai_workbench_test"
    config = Config(str(BACKEND / "alembic.ini"))
    script = ScriptDirectory.from_config(config)
    assert script.get_heads() == ["0013"]
    assert script.get_revision("0013").down_revision == "0012"
    with postgres_engine.connect() as connection:
        config.attributes["connection"] = connection
        try:
            command.downgrade(config, "0012")
            prior = {
                name: repr(inspect(connection).get_columns(name))
                for name in inspect(connection).get_table_names()
            }
            command.upgrade(config, "0013")
            inspector = inspect(connection)
            assert set(inspector.get_table_names()) - set(prior) == {
                "bad_cases",
                "bad_case_history",
            }
            for name, columns in prior.items():
                assert repr(inspector.get_columns(name)) == columns
            assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
            for name in ("bad_cases", "bad_case_history"):
                assert all(
                    fk["options"]["ondelete"] == "RESTRICT"
                    for fk in inspector.get_foreign_keys(name)
                )
            command.downgrade(config, "0012")
            assert set(inspect(connection).get_table_names()) == set(prior)
            command.upgrade(config, "0013")
            assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
        finally:
            connection.rollback()
            command.upgrade(config, "head")


def test_0001_through_0012_byte_unchanged():
    for path in (BACKEND / "alembic" / "versions").glob("*.py"):
        if path.name[:4] > "0012":
            continue
        original = subprocess.check_output(
            ["git", "show", f"78ec013:{path.relative_to(BACKEND.parent).as_posix()}"],
            cwd=BACKEND.parent,
        )
        assert (
            hashlib.sha256(original).digest()
            == hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).digest()
        )


@pytest.mark.parametrize(
    "values",
    [
        {"title": " "},
        {"description": ""},
        {"category": "invalid"},
        {"origin_kind": "invalid"},
        {"status": "invalid"},
        {"revision": 0},
        {"resolution_note": "Only on terminal"},
        {"status": "resolved"},
        {"possible_cause": " "},
        {"handling_note": "x" * 5001},
        {"source_run_case_id": uuid4()},
        {"created_by": uuid4()},
        {"updated_by": uuid4()},
    ],
)
def test_bad_case_constraints(client, scenario, db_session, values):
    _, _, path = seed(client, scenario, db_session)
    item, _ = register(client, scenario, path)
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.execute(update(BadCase).where(BadCase.id == UUID(item["id"])).values(**values))


@pytest.mark.parametrize(
    "values",
    [
        {"event": "invalid"},
        {"revision": 0},
        {"revision": 2},
        {"event": "updated", "revision": 2, "before_values": None},
        {"event": "updated", "revision": 2, "before_values": {}},
        {"after_values": {}},
        {"after_values": []},
        {"actor_id": uuid4()},
        {"change_reason": " "},
        {"change_reason": "x" * 1001},
    ],
)
def test_history_constraints(client, scenario, db_session, values):
    _, _, path = seed(client, scenario, db_session)
    item, _ = register(client, scenario, path)
    with pytest.raises((IntegrityError, DataError)), db_session.begin_nested():
        db_session.execute(
            update(BadCaseHistory)
            .where(BadCaseHistory.bad_case_id == UUID(item["id"]))
            .values(**values)
        )
