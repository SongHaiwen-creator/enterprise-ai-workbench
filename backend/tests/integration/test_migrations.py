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

    assert {
        "alembic_version",
        "chunks",
        "documents",
        "knowledge_bases",
        "memberships",
        "users",
        "workspaces",
    } <= set(inspector.get_table_names())
    assert {index["name"] for index in inspector.get_indexes("users")} >= {"ix_users_email_lower"}
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
        assert migration_context.get_current_revision() == "0005"


def test_knowledge_base_migration_upgrades_and_downgrades(
    postgres_engine: Engine,
) -> None:
    alembic_config = Config(str(BACKEND_ROOT / "alembic.ini"))

    with postgres_engine.connect() as connection:
        alembic_config.attributes["connection"] = connection
        try:
            command.downgrade(alembic_config, "0002")
            inspector = inspect(connection)
            assert "knowledge_bases" not in inspector.get_table_names()
            assert {"memberships", "users", "workspaces"} <= set(inspector.get_table_names())

            command.upgrade(alembic_config, "0003")
            inspector = inspect(connection)
            assert "knowledge_bases" in inspector.get_table_names()
            assert {column["name"] for column in inspector.get_columns("knowledge_bases")} == {
                "id",
                "workspace_id",
                "name",
                "description",
                "status",
                "created_by",
                "created_at",
                "updated_at",
            }
            assert {index["name"] for index in inspector.get_indexes("knowledge_bases")} >= {
                "ix_knowledge_bases_created_by",
                "ix_knowledge_bases_workspace_id",
            }
            foreign_keys = {
                tuple(foreign_key["constrained_columns"]): (
                    foreign_key["referred_table"],
                    foreign_key["options"].get("ondelete"),
                )
                for foreign_key in inspector.get_foreign_keys("knowledge_bases")
            }
            assert foreign_keys == {
                ("created_by",): ("users", "RESTRICT"),
                ("workspace_id",): ("workspaces", "RESTRICT"),
            }
            assert {
                constraint["name"]
                for constraint in inspector.get_check_constraints("knowledge_bases")
            } >= {"ck_knowledge_bases_status_values"}

            command.downgrade(alembic_config, "0002")
            inspector = inspect(connection)
            assert "knowledge_bases" not in inspector.get_table_names()
            assert {"memberships", "users", "workspaces"} <= set(inspector.get_table_names())
        finally:
            connection.rollback()
            command.upgrade(alembic_config, "head")


def test_document_migration_upgrades_and_downgrades(
    postgres_engine: Engine,
) -> None:
    alembic_config = Config(str(BACKEND_ROOT / "alembic.ini"))

    with postgres_engine.connect() as connection:
        alembic_config.attributes["connection"] = connection
        try:
            command.downgrade(alembic_config, "0003")
            inspector = inspect(connection)
            assert "documents" not in inspector.get_table_names()
            assert "knowledge_bases" in inspector.get_table_names()

            command.upgrade(alembic_config, "0004")
            inspector = inspect(connection)
            assert "documents" in inspector.get_table_names()
            assert {column["name"] for column in inspector.get_columns("documents")} == {
                "id",
                "workspace_id",
                "knowledge_base_id",
                "file_name",
                "file_type",
                "status",
                "version",
                "extracted_text",
                "processing_error",
                "created_by",
                "created_at",
                "updated_at",
            }
            assert {index["name"] for index in inspector.get_indexes("documents")} >= {
                "ix_documents_created_by",
                "ix_documents_knowledge_base_id",
                "ix_documents_knowledge_base_status",
                "ix_documents_workspace_id",
            }
            foreign_keys = {
                tuple(foreign_key["constrained_columns"]): (
                    foreign_key["referred_table"],
                    foreign_key["options"].get("ondelete"),
                )
                for foreign_key in inspector.get_foreign_keys("documents")
            }
            assert foreign_keys == {
                ("created_by",): ("users", "RESTRICT"),
                ("knowledge_base_id",): ("knowledge_bases", "RESTRICT"),
                ("workspace_id",): ("workspaces", "RESTRICT"),
            }
            assert {
                constraint["name"] for constraint in inspector.get_check_constraints("documents")
            } >= {
                "ck_documents_file_type_values",
                "ck_documents_status_values",
                "ck_documents_version_positive",
            }

            command.downgrade(alembic_config, "0003")
            inspector = inspect(connection)
            assert "documents" not in inspector.get_table_names()
            assert "knowledge_bases" in inspector.get_table_names()
        finally:
            connection.rollback()
            command.upgrade(alembic_config, "head")


def test_chunk_migration_upgrades_and_downgrades(
    postgres_engine: Engine,
) -> None:
    alembic_config = Config(str(BACKEND_ROOT / "alembic.ini"))

    with postgres_engine.connect() as connection:
        alembic_config.attributes["connection"] = connection
        try:
            command.downgrade(alembic_config, "0004")
            inspector = inspect(connection)
            assert "chunks" not in inspector.get_table_names()
            assert "documents" in inspector.get_table_names()
            assert connection.scalar(text("SELECT to_regtype('vector')")) is None

            command.upgrade(alembic_config, "0005")
            inspector = inspect(connection)
            assert "chunks" in inspector.get_table_names()
            assert {column["name"] for column in inspector.get_columns("chunks")} == {
                "id",
                "workspace_id",
                "document_id",
                "content",
                "chunk_index",
                "embedding_model",
                "embedding",
                "created_at",
            }
            assert {index["name"] for index in inspector.get_indexes("chunks")} >= {
                "ix_chunks_document_id",
                "ix_chunks_workspace_id",
            }
            assert {
                constraint["name"] for constraint in inspector.get_unique_constraints("chunks")
            } >= {"uq_chunks_document_index"}
            assert {
                constraint["name"]
                for constraint in inspector.get_unique_constraints("documents")
            } >= {"uq_documents_id_workspace_id"}
            assert {
                constraint["name"] for constraint in inspector.get_check_constraints("chunks")
            } >= {
                "ck_chunks_chunk_index_non_negative",
                "ck_chunks_content_not_empty",
            }
            foreign_keys = {
                tuple(foreign_key["constrained_columns"]): (
                    foreign_key["referred_table"],
                    foreign_key["options"].get("ondelete"),
                )
                for foreign_key in inspector.get_foreign_keys("chunks")
            }
            assert foreign_keys == {
                ("document_id", "workspace_id"): ("documents", "RESTRICT"),
                ("workspace_id",): ("workspaces", "RESTRICT"),
            }
            vector_type = connection.scalar(
                text(
                    "SELECT format_type(attribute.atttypid, attribute.atttypmod) "
                    "FROM pg_attribute AS attribute "
                    "JOIN pg_class AS relation ON relation.oid = attribute.attrelid "
                    "WHERE relation.relname = 'chunks' "
                    "AND attribute.attname = 'embedding'"
                )
            )
            assert vector_type == "vector(1536)"

            command.downgrade(alembic_config, "0004")
            inspector = inspect(connection)
            assert "chunks" not in inspector.get_table_names()
            assert "documents" in inspector.get_table_names()
            assert "uq_documents_id_workspace_id" not in {
                constraint["name"]
                for constraint in inspector.get_unique_constraints("documents")
            }
            assert connection.scalar(text("SELECT to_regtype('vector')")) is None
        finally:
            connection.rollback()
            command.upgrade(alembic_config, "head")
