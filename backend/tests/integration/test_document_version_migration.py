import hashlib
import subprocess
from uuid import uuid4

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text

from alembic import command
from app.db.base import Base
from tests.integration.test_migrations import BACKEND_ROOT

pytestmark = pytest.mark.integration


def test_revisions_0001_through_0013_remain_unchanged():
    for migration in (BACKEND_ROOT / "alembic/versions").glob("*.py"):
        if migration.name[:4] > "0013":
            continue
        original = subprocess.check_output(
            ["git", "show", f"1c43530:{migration.relative_to(BACKEND_ROOT.parent).as_posix()}"],
            cwd=BACKEND_ROOT.parent,
        )
        assert migration.read_bytes().replace(b"\r\n", b"\n") == original


def seed(connection, *, invalid=False):
    user, workspace, base = uuid4(), uuid4(), uuid4()
    values = {"user": user, "workspace": workspace, "base": base}
    connection.execute(
        text(
            "INSERT INTO users(id,email,name) VALUES "
            "(:user,:email,'Synthetic migration administrator')"
        ),
        {**values, "email": f"backfill-{user}@example.com"},
    )
    connection.execute(
        text("INSERT INTO workspaces(id,name,slug) VALUES (:workspace,'Backfill',:slug)"),
        {**values, "slug": f"backfill-{workspace}"},
    )
    connection.execute(
        text(
            "INSERT INTO knowledge_bases(id,workspace_id,name,created_by) "
            "VALUES(:base,:workspace,'Backfill',:user)"
        ),
        values,
    )
    ids = []
    for status in ("ready", "disabled", "failed", "uploaded", "processing"):
        document = uuid4()
        content = "Legacy policy text" if status in {"ready", "disabled"} else None
        if invalid and status == "ready":
            content = None
        connection.execute(
            text(
                "INSERT INTO documents(id,workspace_id,knowledge_base_id,"
                "file_name,file_type,status,version,extracted_text,created_by) VALUES"
                "(:id,:workspace,:base,'same.txt','txt',:status,7,:content,:user)"
            ),
            {**values, "id": document, "status": status, "content": content},
        )
        if content:
            vector = "[1," + ",".join(["0"] * 1535) + "]"
            connection.execute(
                text(
                    "INSERT INTO chunks(workspace_id,document_id,content,chunk_index,"
                    "embedding_model,embedding) VALUES(:workspace,:id,'Legacy policy text',0,"
                    "'text-embedding-3-small',CAST(:vector AS vector))"
                ),
                {**values, "id": document, "vector": vector},
            )
        ids.append(document)
    connection.commit()
    return values, ids


def cleanup(connection, values):
    connection.rollback()
    if "document_families" in inspect(connection).get_table_names():
        connection.execute(
            text(
                "UPDATE document_families SET current_document_id=NULL "
                "WHERE workspace_id=:workspace"
            ),
            values,
        )
    connection.execute(text("DELETE FROM chunks WHERE workspace_id=:workspace"), values)
    connection.execute(text("DELETE FROM documents WHERE workspace_id=:workspace"), values)
    if "document_families" in inspect(connection).get_table_names():
        connection.execute(
            text("DELETE FROM document_families WHERE workspace_id=:workspace"), values
        )
    connection.execute(text("DELETE FROM knowledge_bases WHERE workspace_id=:workspace"), values)
    connection.execute(text("DELETE FROM workspaces WHERE id=:workspace"), values)
    connection.execute(text("DELETE FROM users WHERE id=:user"), values)
    connection.commit()


@pytest.mark.parametrize("guard", ["changed_revision", "new_family"])
def test_singleton_backfill_preserves_content_chunks_and_guarded_downgrade(postgres_engine, guard):
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    with postgres_engine.connect() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0013")
        values, ids = seed(connection)
        try:
            old = connection.execute(
                text(
                    "SELECT id,version,status,extracted_text,created_at,"
                    "updated_at FROM documents WHERE workspace_id=:workspace ORDER BY id"
                ),
                values,
            ).all()
            chunks = connection.execute(
                text(
                    "SELECT id,document_id,content,embedding,created_at "
                    "FROM chunks WHERE workspace_id=:workspace ORDER BY id"
                ),
                values,
            ).all()
            connection.commit()
            command.upgrade(config, "0014")
            assert (
                connection.execute(
                    text(
                        "SELECT id,version,status,extracted_text,created_at,"
                        "updated_at FROM documents WHERE workspace_id=:workspace ORDER BY id"
                    ),
                    values,
                ).all()
                == old
            )
            assert (
                connection.execute(
                    text(
                        "SELECT id,document_id,content,embedding,created_at "
                        "FROM chunks WHERE workspace_id=:workspace ORDER BY id"
                    ),
                    values,
                ).all()
                == chunks
            )
            families = connection.execute(
                text(
                    "SELECT id,current_document_id,next_version,revision,"
                    "legacy_backfill FROM document_families WHERE workspace_id=:workspace"
                ),
                values,
            ).all()
            assert len(families) == 5 and {r.id for r in families} == set(ids)
            assert all(
                r.next_version == 8 and r.revision == 1 and r.legacy_backfill for r in families
            )
            assert sum(r.current_document_id is not None for r in families) == 2
            assert (
                connection.scalar(
                    text("SELECT content_sha256 FROM documents WHERE id=:id"), {"id": ids[0]}
                )
                == hashlib.sha256(b"Legacy policy text").hexdigest()
            )
            context = MigrationContext.configure(connection)
            assert compare_metadata(context, Base.metadata) == []
            connection.commit()
            command.downgrade(config, "0013")
            assert (
                connection.execute(
                    text(
                        "SELECT id,version,status,extracted_text,created_at,"
                        "updated_at FROM documents WHERE workspace_id=:workspace ORDER BY id"
                    ),
                    values,
                ).all()
                == old
            )
            connection.commit()
            command.upgrade(config, "0014")
            guard_sql = "revision=2" if guard == "changed_revision" else "legacy_backfill=false"
            connection.execute(
                text(f"UPDATE document_families SET {guard_sql} WHERE id=:id"), {"id": ids[0]}
            )
            connection.commit()
            with pytest.raises(RuntimeError, match="prevent safe downgrade"):
                command.downgrade(config, "0013")
            connection.rollback()
            assert MigrationContext.configure(connection).get_current_revision() == "0014"
        finally:
            cleanup(connection, values)
            command.upgrade(config, "head")


def test_invalid_legacy_content_refuses_upgrade_atomically(postgres_engine):
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    with postgres_engine.connect() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0013")
        values, _ = seed(connection, invalid=True)
        try:
            with pytest.raises(RuntimeError, match="preflight failed"):
                command.upgrade(config, "0014")
            connection.rollback()
            assert MigrationContext.configure(connection).get_current_revision() == "0013"
            assert "document_families" not in inspect(connection).get_table_names()
            assert (
                connection.scalar(
                    text("SELECT count(*) FROM documents WHERE workspace_id=:workspace"), values
                )
                == 5
            )
        finally:
            cleanup(connection, values)
            command.upgrade(config, "head")
