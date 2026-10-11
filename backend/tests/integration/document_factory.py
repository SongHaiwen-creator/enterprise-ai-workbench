"""Prepare concrete version fixtures explicitly under the Feature 021 schema."""

from datetime import UTC, datetime
from uuid import uuid4

from app.models import Document, DocumentFamily
from app.services.documents import content_hash


def make_document(session, *, indexed=False, **values):
    content = values.get("extracted_text")
    if values.get("status") == "failed":
        values["extracted_text"] = content = None
    family = DocumentFamily(
        workspace_id=values["workspace_id"],
        knowledge_base_id=values["knowledge_base_id"],
        display_name=values["file_name"],
        created_by=values["created_by"],
        next_version=values.get("version", 1) + 1,
    )
    session.add(family)
    session.flush()
    document = Document(
        id=uuid4(),
        family_id=family.id,
        content_sha256=content_hash(content) if content else None,
        **values,
    )
    if indexed:
        document.indexed_at = datetime.now(UTC)
        document.indexed_model = "text-embedding-3-small"
        document.indexed_dimensions = 1536
        document.indexed_chunk_count = 1
    session.add(document)
    session.flush()
    if document.status in {"ready", "disabled"}:
        family.current_document_id = document.id
        session.flush()
    return document


def mark_indexed(session, document):
    from sqlalchemy import func, select

    from app.models import Chunk

    count, indexed_at = session.execute(
        select(func.count(), func.max(Chunk.created_at)).where(
            Chunk.document_id == document.id,
            Chunk.workspace_id == document.workspace_id,
        )
    ).one()
    document.indexed_at = indexed_at
    document.indexed_model = "text-embedding-3-small"
    document.indexed_dimensions = 1536
    document.indexed_chunk_count = count
    session.flush()


def legacy_metadata(connection, excluded=()):
    """Compare historical revisions with their old Document schema, not 0014's.

    Current parity remains covered independently against the full Base metadata.
    All other in-scope tables still use the application's declared contracts.
    """
    from sqlalchemy import MetaData, Table

    from app.db.base import Base

    legacy = MetaData(naming_convention=Base.metadata.naming_convention)
    document = Table("documents", legacy, autoload_with=connection)
    assert "family_id" not in document.c
    for table in Base.metadata.sorted_tables:
        if table.name not in {*excluded, "document_families"} and table.name not in legacy.tables:
            table.to_metadata(legacy)
    return legacy
