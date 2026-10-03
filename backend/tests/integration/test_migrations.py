import hashlib
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError

import app.models  # noqa: F401
from alembic import command
from app.db.base import Base

pytestmark = pytest.mark.integration
BACKEND_ROOT = Path(__file__).resolve().parents[2]


def insert_document_ownership_rows(
    connection: Connection,
    *,
    mismatched: bool,
) -> tuple[UUID, UUID, UUID]:
    user_id = uuid4()
    workspace_id = uuid4()
    other_workspace_id = uuid4()
    knowledge_base_id = uuid4()
    document_id = uuid4()
    connection.execute(
        text("INSERT INTO users (id, email, name) VALUES (:id, :email, :name)"),
        {"id": user_id, "email": f"migration-{user_id}@company.com", "name": "Migration"},
    )
    connection.execute(
        text(
            "INSERT INTO workspaces (id, name, slug) VALUES "
            "(:workspace_id, :workspace_name, :workspace_slug), "
            "(:other_workspace_id, :other_workspace_name, :other_workspace_slug)"
        ),
        {
            "workspace_id": workspace_id,
            "workspace_name": "Migration Workspace",
            "workspace_slug": f"migration-{workspace_id}",
            "other_workspace_id": other_workspace_id,
            "other_workspace_name": "Other Migration Workspace",
            "other_workspace_slug": f"migration-{other_workspace_id}",
        },
    )
    connection.execute(
        text(
            "INSERT INTO knowledge_bases (id, workspace_id, name, created_by) "
            "VALUES (:id, :workspace_id, :name, :created_by)"
        ),
        {
            "id": knowledge_base_id,
            "workspace_id": workspace_id,
            "name": "Migration Policies",
            "created_by": user_id,
        },
    )
    connection.execute(
        text(
            "INSERT INTO documents "
            "(id, workspace_id, knowledge_base_id, file_name, file_type, status, created_by) "
            "VALUES (:id, :workspace_id, :knowledge_base_id, :file_name, 'txt', "
            "'ready', :created_by)"
        ),
        {
            "id": document_id,
            "workspace_id": other_workspace_id if mismatched else workspace_id,
            "knowledge_base_id": knowledge_base_id,
            "file_name": f"migration-{document_id}.txt",
            "created_by": user_id,
        },
    )
    return document_id, workspace_id, other_workspace_id


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
        assert migration_context.get_current_revision() == "0012"


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
            connection.execute(text("DROP EXTENSION IF EXISTS vector"))
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
            assert connection.scalar(text("SELECT to_regtype('vector')")) is not None
        finally:
            connection.rollback()
            command.upgrade(alembic_config, "head")


def test_chunk_migration_preserves_preexisting_vector_extension(
    postgres_engine: Engine,
) -> None:
    alembic_config = Config(str(BACKEND_ROOT / "alembic.ini"))

    with postgres_engine.connect() as connection:
        alembic_config.attributes["connection"] = connection
        try:
            command.downgrade(alembic_config, "0004")
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            connection.commit()

            command.upgrade(alembic_config, "0005")
            command.downgrade(alembic_config, "0004")

            assert "chunks" not in inspect(connection).get_table_names()
            assert connection.scalar(text("SELECT to_regtype('vector')")) is not None
        finally:
            connection.rollback()
            command.upgrade(alembic_config, "head")


def test_chunk_downgrade_preserves_other_vector_dependent_objects(
    postgres_engine: Engine,
) -> None:
    alembic_config = Config(str(BACKEND_ROOT / "alembic.ini"))

    with postgres_engine.connect() as connection:
        alembic_config.attributes["connection"] = connection
        try:
            command.downgrade(alembic_config, "0004")
            command.upgrade(alembic_config, "0005")
            connection.execute(
                text("CREATE TABLE external_vector_dependency (embedding vector(3) NOT NULL)")
            )
            connection.commit()

            command.downgrade(alembic_config, "0004")

            assert "chunks" not in inspect(connection).get_table_names()
            assert "external_vector_dependency" in inspect(connection).get_table_names()
            assert connection.scalar(text("SELECT to_regtype('vector')")) is not None
        finally:
            connection.rollback()
            connection.execute(text("DROP TABLE IF EXISTS external_vector_dependency"))
            connection.commit()
            command.upgrade(alembic_config, "head")


def test_document_workspace_ownership_migration_upgrades_and_downgrades(
    postgres_engine: Engine,
) -> None:
    alembic_config = Config(str(BACKEND_ROOT / "alembic.ini"))

    with postgres_engine.connect() as connection:
        alembic_config.attributes["connection"] = connection
        try:
            command.downgrade(alembic_config, "0005")
            command.upgrade(alembic_config, "0006")
            inspector = inspect(connection)
            assert {
                constraint["name"]
                for constraint in inspector.get_unique_constraints("knowledge_bases")
            } >= {"uq_knowledge_bases_id_workspace_id"}
            document_foreign_keys = {
                tuple(foreign_key["constrained_columns"]): (
                    foreign_key["referred_table"],
                    foreign_key["options"].get("ondelete"),
                )
                for foreign_key in inspector.get_foreign_keys("documents")
            }
            assert document_foreign_keys[("knowledge_base_id", "workspace_id")] == (
                "knowledge_bases",
                "RESTRICT",
            )

            insert_document_ownership_rows(connection, mismatched=False)
            connection.commit()
            with pytest.raises(IntegrityError):
                insert_document_ownership_rows(connection, mismatched=True)
            connection.rollback()

            command.downgrade(alembic_config, "0005")
            inspector = inspect(connection)
            assert "uq_knowledge_bases_id_workspace_id" not in {
                constraint["name"]
                for constraint in inspector.get_unique_constraints("knowledge_bases")
            }
            assert ("knowledge_base_id", "workspace_id") not in {
                tuple(foreign_key["constrained_columns"])
                for foreign_key in inspector.get_foreign_keys("documents")
            }
        finally:
            connection.rollback()
            command.upgrade(alembic_config, "head")


def test_document_workspace_ownership_migration_rejects_legacy_inconsistency_atomically(
    postgres_engine: Engine,
) -> None:
    alembic_config = Config(str(BACKEND_ROOT / "alembic.ini"))

    with postgres_engine.connect() as connection:
        alembic_config.attributes["connection"] = connection
        try:
            command.downgrade(alembic_config, "0005")
            document_id, _, _ = insert_document_ownership_rows(connection, mismatched=True)
            connection.commit()

            with pytest.raises(IntegrityError):
                command.upgrade(alembic_config, "0006")
            connection.rollback()

            migration_context = MigrationContext.configure(connection)
            assert migration_context.get_current_revision() == "0005"
            assert "uq_knowledge_bases_id_workspace_id" not in {
                constraint["name"]
                for constraint in inspect(connection).get_unique_constraints("knowledge_bases")
            }

            connection.execute(
                text("DELETE FROM documents WHERE id = :document_id"),
                {"document_id": document_id},
            )
            connection.commit()
            command.upgrade(alembic_config, "0006")
        finally:
            connection.rollback()
            command.upgrade(alembic_config, "head")


def test_agent_migration_upgrades_and_downgrades(postgres_engine: Engine) -> None:
    alembic_config = Config(str(BACKEND_ROOT / "alembic.ini"))

    with postgres_engine.connect() as connection:
        alembic_config.attributes["connection"] = connection
        try:
            command.downgrade(alembic_config, "0006")
            assert "agents" not in inspect(connection).get_table_names()

            command.upgrade(alembic_config, "0007")
            inspector = inspect(connection)
            assert {column["name"] for column in inspector.get_columns("agents")} == {
                "id",
                "workspace_id",
                "name",
                "description",
                "system_prompt",
                "status",
                "created_by",
                "created_at",
                "updated_at",
            }
            assert {index["name"] for index in inspector.get_indexes("agents")} == {
                "ix_agents_created_by",
                "ix_agents_workspace_id",
            }
            check_names = {
                constraint["name"] for constraint in inspector.get_check_constraints("agents")
            }
            assert check_names == {
                "ck_agents_status_values",
                "ck_agents_name_not_empty",
                "ck_agents_system_prompt_not_empty",
            }
            foreign_keys = {
                tuple(foreign_key["constrained_columns"]): (
                    foreign_key["referred_table"],
                    foreign_key["options"].get("ondelete"),
                )
                for foreign_key in inspector.get_foreign_keys("agents")
            }
            assert foreign_keys == {
                ("created_by",): ("users", "RESTRICT"),
                ("workspace_id",): ("workspaces", "RESTRICT"),
            }
            columns = {column["name"]: column for column in inspector.get_columns("agents")}
            assert "draft" in columns["status"]["default"]
            assert columns["created_at"]["default"] == "CURRENT_TIMESTAMP"
            assert columns["updated_at"]["default"] == "CURRENT_TIMESTAMP"
            assert str(columns["name"]["type"]) == "VARCHAR(255)"
            assert str(columns["status"]["type"]) == "VARCHAR(32)"
            assert columns["description"]["nullable"] is True
            assert columns["system_prompt"]["nullable"] is False
            assert columns["created_at"]["type"].timezone is True
            assert columns["updated_at"]["type"].timezone is True

            command.downgrade(alembic_config, "0006")
            assert "agents" not in inspect(connection).get_table_names()
            assert {"chunks", "documents", "knowledge_bases"} <= set(
                inspect(connection).get_table_names()
            )
        finally:
            connection.rollback()
            command.upgrade(alembic_config, "head")
            command.upgrade(alembic_config, "head")


def test_tool_migration_upgrades_downgrades_and_reupgrades(
    postgres_engine: Engine,
) -> None:
    alembic_config = Config(str(BACKEND_ROOT / "alembic.ini"))

    with postgres_engine.connect() as connection:
        alembic_config.attributes["connection"] = connection
        try:
            command.downgrade(alembic_config, "0007")
            inspector = inspect(connection)
            assert "tools" not in inspector.get_table_names()
            assert "agent_tools" not in inspector.get_table_names()
            assert "uq_agents_id_workspace_id" not in {
                item["name"] for item in inspector.get_unique_constraints("agents")
            }

            command.upgrade(alembic_config, "0008")
            inspector = inspect(connection)
            assert {column["name"] for column in inspector.get_columns("tools")} == {
                "id", "workspace_id", "tool_key", "name", "description",
                "risk_level", "status", "created_by", "created_at", "updated_at",
            }
            assert {
                item["name"] for item in inspector.get_unique_constraints("tools")
            } >= {"uq_tools_workspace_tool_key", "uq_tools_id_workspace_id"}
            assert {
                item["name"] for item in inspector.get_unique_constraints("agents")
            } >= {"uq_agents_id_workspace_id"}
            assert {index["name"] for index in inspector.get_indexes("tools")} >= {
                "ix_tools_workspace_id", "ix_tools_created_by",
            }
            assert {
                item["name"] for item in inspector.get_check_constraints("tools")
            } >= {
                "ck_tools_tool_key_format", "ck_tools_name_not_empty",
                "ck_tools_description_not_empty", "ck_tools_risk_level_values",
                "ck_tools_status_values",
            }
            tool_foreign_keys = {
                tuple(item["constrained_columns"]): (
                    item["referred_table"], item["options"].get("ondelete")
                )
                for item in inspector.get_foreign_keys("tools")
            }
            assert tool_foreign_keys == {
                ("workspace_id",): ("workspaces", "RESTRICT"),
                ("created_by",): ("users", "RESTRICT"),
            }
            assert {column["name"] for column in inspector.get_columns("agent_tools")} == {
                "workspace_id", "agent_id", "tool_id",
            }
            assignment_foreign_keys = {
                tuple(item["constrained_columns"]): (
                    item["referred_table"], item["options"].get("ondelete")
                )
                for item in inspector.get_foreign_keys("agent_tools")
            }
            assert assignment_foreign_keys == {
                ("workspace_id",): ("workspaces", "RESTRICT"),
                ("agent_id", "workspace_id"): ("agents", "RESTRICT"),
                ("tool_id", "workspace_id"): ("tools", "RESTRICT"),
            }

            command.downgrade(alembic_config, "0007")
            inspector = inspect(connection)
            assert "tools" not in inspector.get_table_names()
            assert "agent_tools" not in inspector.get_table_names()
            command.upgrade(alembic_config, "0008")
            assert {"tools", "agent_tools"} <= set(inspect(connection).get_table_names())
        finally:
            connection.rollback()
            command.upgrade(alembic_config, "head")


APPLIED_MIGRATION_SHA256 = {
    "0001_create_users_workspaces_memberships.py": (
        "fd5755ad005a2960264c3a8682b47f82a3d448e4bf074028b7967c81de6fe99b"
    ),
    "0002_add_password_hash_to_users.py": (
        "5fa9e1f26f27b43908785e7694f778a637ff0fc82486f2984322b60aa1db4c9a"
    ),
    "0003_create_knowledge_bases.py": (
        "9c029bac0f9f209402e8fd6cdc3c3fe29280052953d88f3b70989978c0fb8512"
    ),
    "0004_create_documents.py": (
        "eccee423e3922bf979b543496802bab693e18f5cf41e95b12bfed785d90ab296"
    ),
    "0005_create_chunks.py": (
        "86cc33b63649f9f078d957c2711fdb1af7893826f4da83a63159b213a102b9e2"
    ),
    "0006_enforce_document_workspace_ownership.py": (
        "869406fdfb066c4416140fb91aa9617588638f19d8df0d415ac5960be87b8116"
    ),
    "0007_create_agents.py": (
        "bf72b01d6bfd2757120506b277928b6496884d90c382f89416fef1a6632df5ae"
    ),
    "0008_create_tools_and_agent_tools.py": (
        "66f75aa0fda1ccaf63f19197ffafad3e4fbb383823ab29d564135a92b4e83cba"
    ),
    "0009_create_approvals_and_mock_it_access_requests.py": (
        "3506c2c397b9137c63b015c33e37f314d20cda599f2887462e3210b318bc1ad2"
    ),
}


def test_applied_migrations_are_unchanged_and_head_is_single() -> None:
    versions = BACKEND_ROOT / "alembic" / "versions"
    for name, expected in APPLIED_MIGRATION_SHA256.items():
        content = (versions / name).read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(content).hexdigest() == expected, name
    script = ScriptDirectory.from_config(Config(str(BACKEND_ROOT / "alembic.ini")))
    assert script.get_heads() == ["0012"]
    assert script.get_revision("0010").down_revision == "0009"


def test_models_match_migrated_schema_without_drift(postgres_engine: Engine) -> None:
    with postgres_engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        assert compare_metadata(context, Base.metadata) == []


def test_approval_migration_upgrades_downgrades_and_reupgrades(
    postgres_engine: Engine,
) -> None:
    alembic_config = Config(str(BACKEND_ROOT / "alembic.ini"))

    with postgres_engine.connect() as connection:
        alembic_config.attributes["connection"] = connection
        try:
            command.downgrade(alembic_config, "0008")
            inspector = inspect(connection)
            assert "approvals" not in inspector.get_table_names()
            assert "mock_it_access_requests" not in inspector.get_table_names()
            assert {"tools", "agent_tools", "memberships"} <= set(inspector.get_table_names())

            command.upgrade(alembic_config, "0009")
            inspector = inspect(connection)
            columns = {column["name"]: column for column in inspector.get_columns("approvals")}
            assert set(columns) == {
                "id", "workspace_id", "requester_id", "agent_id", "tool_id", "action_type",
                "canonical_arguments", "canonical_arguments_sha256", "capability_snapshot",
                "policy_snapshot", "snapshot_sha256", "decision_status", "decided_by",
                "decided_at", "decision_note", "invalidation_reason",
                "invalidation_triggered_by", "execution_status", "executed_at",
                "execution_failure_category", "expires_at", "created_at", "updated_at",
            }
            nullable = {name for name, column in columns.items() if column["nullable"]}
            assert nullable == {
                "decided_by", "decided_at", "decision_note", "invalidation_reason",
                "invalidation_triggered_by", "executed_at", "execution_failure_category",
            }
            assert "pending" in columns["decision_status"]["default"]
            assert "not_started" in columns["execution_status"]["default"]
            assert columns["created_at"]["default"] == "CURRENT_TIMESTAMP"
            assert str(columns["canonical_arguments_sha256"]["type"]) == "CHAR(64)"
            assert str(columns["canonical_arguments"]["type"]) == "JSONB"
            assert columns["expires_at"]["type"].timezone is True

            foreign_keys = {
                tuple(item["constrained_columns"]): (
                    item["referred_table"],
                    tuple(item["referred_columns"]),
                    item["options"].get("ondelete"),
                )
                for item in inspector.get_foreign_keys("approvals")
            }
            assert foreign_keys == {
                ("workspace_id",): ("workspaces", ("id",), "RESTRICT"),
                ("requester_id", "workspace_id"): (
                    "memberships", ("user_id", "workspace_id"), "RESTRICT"
                ),
                ("decided_by", "workspace_id"): (
                    "memberships", ("user_id", "workspace_id"), "RESTRICT"
                ),
                ("invalidation_triggered_by", "workspace_id"): (
                    "memberships", ("user_id", "workspace_id"), "RESTRICT"
                ),
                ("agent_id", "workspace_id"): ("agents", ("id", "workspace_id"), "RESTRICT"),
                ("tool_id", "workspace_id"): ("tools", ("id", "workspace_id"), "RESTRICT"),
            }
            indexes = {index["name"]: index for index in inspector.get_indexes("approvals")}
            assert set(indexes) >= {
                "uq_approvals_pending_dedupe", "ix_approvals_ws_decision_created",
                "ix_approvals_ws_requester_created", "ix_approvals_agent_id",
                "ix_approvals_tool_id", "ix_approvals_decided_by",
            }
            dedupe = indexes["uq_approvals_pending_dedupe"]
            assert dedupe["unique"] is True
            assert dedupe["column_names"] == ["workspace_id", "requester_id", "snapshot_sha256"]
            assert "pending" in dedupe["dialect_options"]["postgresql_where"]
            assert {
                item["name"] for item in inspector.get_unique_constraints("approvals")
            } == {"uq_approvals_id_workspace_id"}
            checks = {item["name"] for item in inspector.get_check_constraints("approvals")}
            assert {
                "ck_approvals_status_pair_legal", "ck_approvals_no_self_decision",
                "ck_approvals_cancel_by_requester", "ck_approvals_decision_note_decided_only",
                "ck_approvals_expired_decided_at", "ck_approvals_invalidation_not_requester",
            } <= checks
            assert len(checks) == 24

            mock_foreign_keys = {
                tuple(item["constrained_columns"]): item["referred_table"]
                for item in inspector.get_foreign_keys("mock_it_access_requests")
            }
            assert mock_foreign_keys == {
                ("workspace_id",): "workspaces",
                ("approval_id", "workspace_id"): "approvals",
                ("requester_id", "workspace_id"): "memberships",
            }
            assert {
                item["name"]
                for item in inspector.get_unique_constraints("mock_it_access_requests")
            } == {
                "uq_mock_it_access_requests_approval_id",
                "uq_mock_it_access_requests_reference",
            }

            command.downgrade(alembic_config, "0008")
            inspector = inspect(connection)
            assert "approvals" not in inspector.get_table_names()
            assert "mock_it_access_requests" not in inspector.get_table_names()
            command.upgrade(alembic_config, "0009")
            assert {"approvals", "mock_it_access_requests"} <= set(
                inspect(connection).get_table_names()
            )
        finally:
            connection.rollback()
            command.upgrade(alembic_config, "head")


def test_execution_log_migration_upgrades_downgrades_and_reupgrades(
    postgres_engine: Engine,
) -> None:
    alembic_config = Config(str(BACKEND_ROOT / "alembic.ini"))

    with postgres_engine.connect() as connection:
        alembic_config.attributes["connection"] = connection
        try:
            command.downgrade(alembic_config, "0009")
            inspector = inspect(connection)
            assert "execution_logs" not in inspector.get_table_names()
            assert {"approvals", "agents", "tools", "knowledge_bases"} <= set(
                inspector.get_table_names()
            )

            command.upgrade(alembic_config, "0010")
            inspector = inspect(connection)
            columns = {
                column["name"]: column for column in inspector.get_columns("execution_logs")
            }
            assert set(columns) == {
                "id", "workspace_id", "user_id", "operation", "routing_intent", "status",
                "outcome", "error_category", "http_status", "latency_ms", "agent_id",
                "tool_id", "tool_key", "approval_id", "knowledge_base_id", "details",
                "created_at",
            }
            nullable = {name for name, column in columns.items() if column["nullable"]}
            assert nullable == {
                "routing_intent", "outcome", "error_category", "agent_id", "tool_id",
                "tool_key", "approval_id", "knowledge_base_id",
            }
            assert str(columns["details"]["type"]) == "JSONB"
            assert "'{}'::jsonb" in columns["details"]["default"]
            assert str(columns["http_status"]["type"]) == "SMALLINT"
            assert columns["created_at"]["type"].timezone is True
            assert columns["created_at"]["default"] == "CURRENT_TIMESTAMP"

            foreign_keys = {
                tuple(item["constrained_columns"]): (
                    item["referred_table"],
                    tuple(item["referred_columns"]),
                    item["options"].get("ondelete"),
                )
                for item in inspector.get_foreign_keys("execution_logs")
            }
            assert foreign_keys == {
                ("workspace_id",): ("workspaces", ("id",), "RESTRICT"),
                ("user_id", "workspace_id"): (
                    "memberships", ("user_id", "workspace_id"), "RESTRICT"
                ),
                ("agent_id", "workspace_id"): ("agents", ("id", "workspace_id"), "RESTRICT"),
                ("tool_id", "workspace_id"): ("tools", ("id", "workspace_id"), "RESTRICT"),
                ("approval_id", "workspace_id"): (
                    "approvals", ("id", "workspace_id"), "RESTRICT"
                ),
                ("knowledge_base_id", "workspace_id"): (
                    "knowledge_bases", ("id", "workspace_id"), "RESTRICT"
                ),
            }
            indexes = {
                index["name"]: index["column_names"]
                for index in inspector.get_indexes("execution_logs")
            }
            assert indexes == {
                "ix_execution_logs_workspace_created": ["workspace_id", "created_at", "id"],
                "ix_execution_logs_workspace_agent_created": [
                    "workspace_id", "agent_id", "created_at",
                ],
            }
            checks = {
                item["name"] for item in inspector.get_check_constraints("execution_logs")
            }
            assert checks == {
                f"ck_execution_logs_{name}"
                for name in (
                    "operation_values", "routing_intent_values", "status_values",
                    "outcome_values", "error_category_values", "http_status_range",
                    "latency_non_negative", "status_error_consistency",
                    "status_http_consistency", "routing_intent_agent_route_only",
                    "tool_reference_pair", "details_object",
                )
            }
            # Feature 014 does not change any existing table.
            assert len(inspector.get_check_constraints("approvals")) == 24

            command.downgrade(alembic_config, "0009")
            inspector = inspect(connection)
            assert "execution_logs" not in inspector.get_table_names()
            assert "approvals" in inspector.get_table_names()
            command.upgrade(alembic_config, "0010")
            assert "execution_logs" in inspect(connection).get_table_names()
        finally:
            connection.rollback()
            command.upgrade(alembic_config, "head")
