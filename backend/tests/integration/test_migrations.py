import pytest
from alembic.migration import MigrationContext
from sqlalchemy import Engine, inspect

pytestmark = pytest.mark.integration


def test_initial_migration_creates_expected_schema(postgres_engine: Engine) -> None:
    inspector = inspect(postgres_engine)

    assert {"alembic_version", "memberships", "users", "workspaces"} <= set(
        inspector.get_table_names()
    )
    assert {index["name"] for index in inspector.get_indexes("users")} >= {
        "ix_users_email_lower"
    }
    assert {index["name"] for index in inspector.get_indexes("memberships")} >= {
        "ix_memberships_workspace_id",
    }
    assert {
        constraint["name"] for constraint in inspector.get_unique_constraints("memberships")
    } >= {"uq_memberships_user_workspace"}
    assert {
        tuple(foreign_key["constrained_columns"])
        for foreign_key in inspector.get_foreign_keys("memberships")
    } == {("user_id",), ("workspace_id",)}

    with postgres_engine.connect() as connection:
        migration_context = MigrationContext.configure(connection)
        assert migration_context.get_current_revision() == "0001"
