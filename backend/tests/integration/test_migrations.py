from pathlib import Path

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import Engine, inspect, text

from alembic import command

pytestmark = pytest.mark.integration
BACKEND_ROOT = Path(__file__).resolve().parents[2]


def test_password_hash_migration_preserves_existing_users(postgres_engine: Engine) -> None:
    alembic_config = Config(str(BACKEND_ROOT / "alembic.ini"))

    with postgres_engine.connect() as connection:
        alembic_config.attributes["connection"] = connection
        try:
            command.downgrade(alembic_config, "base")
            command.upgrade(alembic_config, "0001")
            assert "password_hash" not in {
                column["name"] for column in inspect(connection).get_columns("users")
            }
            connection.execute(
                text("INSERT INTO users (email, name) VALUES (:email, :name)"),
                {"email": "legacy@company.com", "name": "Legacy User"},
            )
            connection.commit()

            command.upgrade(alembic_config, "0002")
            assert "password_hash" in {
                column["name"] for column in inspect(connection).get_columns("users")
            }
            password_hash = connection.scalar(
                text("SELECT password_hash FROM users WHERE email = :email"),
                {"email": "legacy@company.com"},
            )
            assert password_hash is None

            command.downgrade(alembic_config, "0001")
            assert "password_hash" not in {
                column["name"] for column in inspect(connection).get_columns("users")
            }
        finally:
            connection.rollback()
            command.upgrade(alembic_config, "head")


def test_initial_migration_creates_expected_schema(postgres_engine: Engine) -> None:
    inspector = inspect(postgres_engine)

    assert {"alembic_version", "memberships", "users", "workspaces"} <= set(
        inspector.get_table_names()
    )
    assert {index["name"] for index in inspector.get_indexes("users")} >= {
        "ix_users_email_lower"
    }
    assert "password_hash" in {column["name"] for column in inspector.get_columns("users")}
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
        assert migration_context.get_current_revision() == "0002"
