import hashlib
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import MetaData, inspect
from sqlalchemy.exc import IntegrityError

from alembic import command
from app.db.base import Base
from app.models import Agent, EvaluationCase, EvaluationDataset, KnowledgeBase, Tool
from app.models.enums import MembershipRole
from app.schemas.evaluation import DatasetCreate
from app.services import evaluation
from tests.integration.test_knowledge_base_api import add_membership, create_user, create_workspace

pytestmark = pytest.mark.integration
BACKEND = Path(__file__).resolve().parents[2]


def test_migration_roundtrip_and_drift(postgres_engine, database_urls):
    assert database_urls[1].database == "enterprise_ai_workbench_test"
    config = Config(str(BACKEND / "alembic.ini"))
    script = ScriptDirectory.from_config(config)
    assert script.get_heads() == ["0013"]
    assert script.get_revision("0011").down_revision == "0010"
    legacy = MetaData(naming_convention=Base.metadata.naming_convention)
    for table in Base.metadata.sorted_tables:
        if table.name not in {
            "evaluation_runs",
            "evaluation_run_cases",
            "bad_cases",
            "bad_case_history",
        }:
            table.to_metadata(legacy)
    with postgres_engine.connect() as connection:
        config.attributes["connection"] = connection
        try:
            command.downgrade(config, "0010")
            before = set(inspect(connection).get_table_names())
            assert not {"evaluation_datasets", "evaluation_cases"} & before
            command.upgrade(config, "0011")
            assert set(inspect(connection).get_table_names()) - before == {
                "evaluation_datasets",
                "evaluation_cases",
            }
            assert compare_metadata(MigrationContext.configure(connection), legacy) == []
            for table in ("evaluation_datasets", "evaluation_cases"):
                for fk in inspect(connection).get_foreign_keys(table):
                    assert fk["options"]["ondelete"] == "RESTRICT"
                assert ["id", "workspace_id"] in [
                    c["column_names"] for c in inspect(connection).get_unique_constraints(table)
                ]
            command.downgrade(config, "0010")
            assert set(inspect(connection).get_table_names()) == before
            command.upgrade(config, "0011")
            assert MigrationContext.configure(connection).get_current_revision() == "0011"
            assert compare_metadata(MigrationContext.configure(connection), legacy) == []
        finally:
            connection.rollback()
            command.upgrade(config, "head")


def test_previous_migrations_byte_for_byte():
    repo = BACKEND.parent
    for path in (BACKEND / "alembic" / "versions").glob("*.py"):
        if path.name[:4] >= "0011":
            continue
        baseline = subprocess.check_output(
            ["git", "show", f"760d7fb:{path.relative_to(repo).as_posix()}"], cwd=repo
        )
        # Compare Git-normalized bytes; working copies may use CRLF on Windows.
        actual = subprocess.check_output(["git", "hash-object", str(path)], cwd=repo).strip()
        expected = subprocess.check_output(
            ["git", "hash-object", "--stdin"], input=baseline, cwd=repo
        ).strip()
        assert actual == expected
        assert (
            hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).digest()
            == hashlib.sha256(baseline).digest()
        )


@pytest.fixture
def owned(db_session):
    user = create_user(db_session, email=f"fk-{uuid4()}@example.test")
    other_user = create_user(db_session, email=f"fk-other-{uuid4()}@example.test")
    workspace = create_workspace(db_session, slug=f"fk-{uuid4()}")
    other_workspace = create_workspace(db_session, slug=f"fk-other-{uuid4()}")
    add_membership(db_session, user, workspace, role=MembershipRole.SYSTEM_ADMIN)
    add_membership(db_session, other_user, other_workspace, role=MembershipRole.SYSTEM_ADMIN)
    parent = evaluation.create_dataset(
        db_session, workspace.id, user.id, DatasetCreate(name="Parent")
    )
    foreign_parent = evaluation.create_dataset(
        db_session, other_workspace.id, other_user.id, DatasetCreate(name="Foreign")
    )
    agent = Agent(
        workspace_id=other_workspace.id,
        created_by=other_user.id,
        name="Agent",
        system_prompt="Synthetic",
    )
    kb = KnowledgeBase(workspace_id=other_workspace.id, created_by=other_user.id, name="KB")
    tool = Tool(
        workspace_id=other_workspace.id,
        created_by=other_user.id,
        name="Tool",
        description="Synthetic",
        tool_key="get_reimbursement_status",
        risk_level="low",
    )
    db_session.add_all([agent, kb, tool])
    db_session.commit()
    return user, other_user, workspace, parent, foreign_parent, agent, kb, tool


@pytest.mark.parametrize(
    "column,index",
    [
        ("created_by", 1),
        ("dataset_id", 4),
        ("agent_id", 5),
        ("knowledge_base_id", 6),
        ("tool_id", 7),
    ],
)
@pytest.mark.parametrize("operation", ["insert", "update"])
def test_composite_fk_rejects_foreign_reference(db_session, owned, column, index, operation):
    user, _, workspace, parent, *_ = owned
    values = dict(
        workspace_id=workspace.id,
        dataset_id=parent.id,
        created_by=user.id,
        name="Case",
        case_type="refusal_behavior",
        test_input="Synthetic",
        expected_behavior={"test": True},
    )
    if operation == "update":
        existing = EvaluationCase(**values)
        db_session.add(existing)
        db_session.flush()
    with pytest.raises(IntegrityError), db_session.begin_nested():
        if operation == "insert":
            values[column] = owned[index].id
            db_session.add(EvaluationCase(**values))
        else:
            setattr(existing, column, owned[index].id)
        db_session.flush()


def test_dataset_creator_fk_rejects_foreign_membership(db_session, owned):
    _, other, workspace, *_ = owned
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(
            EvaluationDataset(workspace_id=workspace.id, created_by=other.id, name="Dataset")
        )
        db_session.flush()


@pytest.mark.parametrize(
    "column,value",
    [
        ("status", "draft"),
        ("case_type", "future"),
        ("schema_version", 2),
        ("test_input", ""),
        ("test_input", "x" * 2001),
        ("expected_behavior", []),
        ("expected_behavior", {}),
        ("name", " "),
        ("description", "x" * 5001),
    ],
)
def test_database_check_constraints(db_session, owned, column, value):
    user, _, workspace, parent, *_ = owned
    values = dict(
        workspace_id=workspace.id,
        dataset_id=parent.id,
        created_by=user.id,
        name="Case",
        case_type="refusal_behavior",
        test_input="Synthetic",
        expected_behavior={"test": True},
    )
    values[column] = value
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(EvaluationCase(**values))
        db_session.flush()
