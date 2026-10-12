"""Stable document families and immutable successful indexes.

Revision ID: 0014
Revises: 0013
"""

import hashlib

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    # Validate before schema changes. Do not repair or discard source data.
    invalid = connection.scalar(
        sa.text("""
        SELECT EXISTS (
          SELECT 1 FROM documents d LEFT JOIN knowledge_bases k
            ON k.id=d.knowledge_base_id AND k.workspace_id=d.workspace_id
          WHERE k.id IS NULL OR d.version >= 2147483647
            OR (d.status IN ('ready','disabled') AND
                (d.extracted_text IS NULL OR length(btrim(d.extracted_text))=0))
            OR (d.status='failed' AND d.extracted_text IS NOT NULL)
        ) OR EXISTS (
          SELECT 1 FROM chunks c JOIN documents d ON d.id=c.document_id
          GROUP BY d.id, d.status HAVING d.status NOT IN ('ready','disabled')
            OR min(c.chunk_index) <> 0 OR max(c.chunk_index) <> count(*)-1
            OR count(DISTINCT c.chunk_index) <> count(*)
            OR bool_or(c.workspace_id<>d.workspace_id)
            OR bool_or(c.embedding_model<>'text-embedding-3-small')
            OR bool_or(vector_dims(c.embedding)<>1536)
        )
    """)
    )
    if invalid:
        raise RuntimeError("Document version backfill preflight failed")
    op.create_table(
        "document_families",
        sa.Column("id", pg.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "workspace_id",
            pg.UUID(),
            sa.ForeignKey("workspaces.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("knowledge_base_id", pg.UUID(), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("current_document_id", pg.UUID(), nullable=True),
        sa.Column("next_version", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("legacy_backfill", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_by", pg.UUID(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "length(btrim(display_name)) > 0",
            name=op.f("ck_document_families_display_name_nonblank"),
        ),
        sa.CheckConstraint(
            "next_version > 0 AND revision > 0", name=op.f("ck_document_families_counters_positive")
        ),
        sa.UniqueConstraint(
            "id", "workspace_id", "knowledge_base_id", name="uq_document_families_scope"
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_base_id", "workspace_id"],
            ["knowledge_bases.id", "knowledge_bases.workspace_id"],
            name="fk_document_families_knowledge_base_workspace",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_document_families_list",
        "document_families",
        ["workspace_id", "knowledge_base_id", "display_name", "id"],
    )
    op.create_index("ix_document_families_created_by", "document_families", ["created_by"])
    additions = [
        sa.Column("family_id", pg.UUID(), nullable=True),
        sa.Column("content_sha256", sa.CHAR(64), nullable=True),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("indexed_model", sa.String(100), nullable=True),
        sa.Column("indexed_dimensions", sa.Integer(), nullable=True),
        sa.Column("indexed_chunk_count", sa.Integer(), nullable=True),
    ]
    for column in additions:
        op.add_column("documents", column)
    connection.execute(
        sa.text("""
        INSERT INTO document_families
          (id,workspace_id,knowledge_base_id,display_name,next_version,revision,
           legacy_backfill,created_by,created_at,updated_at)
        SELECT id,workspace_id,knowledge_base_id,file_name,version+1,1,true,
               created_by,created_at,updated_at FROM documents;
    """)
    )
    connection.execute(sa.text("UPDATE documents SET family_id=id"))
    # Hash in Python to avoid installing another PostgreSQL extension.
    rows = connection.execute(
        sa.text("SELECT id, extracted_text FROM documents WHERE extracted_text IS NOT NULL")
    ).all()
    for document_id, content in rows:
        connection.execute(
            sa.text("UPDATE documents SET content_sha256=:hash WHERE id=:id"),
            {"id": document_id, "hash": hashlib.sha256(content.encode("utf-8")).hexdigest()},
        )
    connection.execute(
        sa.text("""
        UPDATE documents d SET indexed_at=x.indexed_at,indexed_model=x.model,
          indexed_dimensions=1536,indexed_chunk_count=x.count FROM
          (SELECT document_id,max(created_at) indexed_at,min(embedding_model) model,count(*) count
           FROM chunks GROUP BY document_id) x WHERE d.id=x.document_id
    """)
    )
    connection.execute(
        sa.text("""
        UPDATE document_families f SET current_document_id=d.id FROM documents d
        WHERE f.id=d.family_id AND d.status IN ('ready','disabled')
    """)
    )
    op.alter_column("documents", "family_id", nullable=False)
    op.create_unique_constraint(
        "uq_documents_family_version", "documents", ["family_id", "version"]
    )
    op.create_unique_constraint(
        "uq_documents_version_scope",
        "documents",
        ["id", "family_id", "workspace_id", "knowledge_base_id"],
    )
    op.create_foreign_key(
        "fk_documents_family_scope",
        "documents",
        "document_families",
        ["family_id", "workspace_id", "knowledge_base_id"],
        ["id", "workspace_id", "knowledge_base_id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_document_families_current_version",
        "document_families",
        "documents",
        ["current_document_id", "id", "workspace_id", "knowledge_base_id"],
        ["id", "family_id", "workspace_id", "knowledge_base_id"],
        ondelete="RESTRICT",
    )
    checks = {
        "content_hash_valid": "content_sha256 IS NULL OR content_sha256 ~ '^[0-9a-f]{64}$'",
        "index_complete": (
            "(indexed_at IS NULL AND indexed_model IS NULL AND indexed_dimensions IS NULL "
            "AND indexed_chunk_count IS NULL) OR (indexed_at IS NOT NULL AND indexed_model "
            "IS NOT NULL AND length(btrim(indexed_model)) > 0 AND indexed_dimensions IS NOT NULL "
            "AND indexed_dimensions = 1536 AND indexed_chunk_count IS NOT NULL "
            "AND indexed_chunk_count > 0 AND content_sha256 IS NOT NULL "
            "AND status IN ('ready', 'disabled'))"
        ),
        "ready_content_valid": (
            "status NOT IN ('ready', 'disabled') OR (extracted_text IS NOT NULL "
            "AND length(btrim(extracted_text)) > 0 AND content_sha256 IS NOT NULL)"
        ),
        "failed_content_empty": (
            "status <> 'failed' OR (extracted_text IS NULL AND content_sha256 IS NULL "
            "AND indexed_at IS NULL)"
        ),
    }
    for name, sql in checks.items():
        op.create_check_constraint(op.f(f"ck_documents_{name}"), "documents", sql)
    op.create_index(
        "ix_documents_family_versions",
        "documents",
        ["workspace_id", "knowledge_base_id", "family_id", "version", "id"],
    )


def downgrade():
    connection = op.get_bind()
    # The older retrieval cannot represent current pointers. Refuse unsafe rollback.
    if connection.scalar(
        sa.text("""
        SELECT EXISTS(SELECT 1 FROM document_families WHERE NOT legacy_backfill OR revision<>1)
    """)
    ):
        raise RuntimeError("Document version writes prevent safe downgrade")
    op.drop_constraint(
        "fk_document_families_current_version", "document_families", type_="foreignkey"
    )
    op.drop_constraint("fk_documents_family_scope", "documents", type_="foreignkey")
    op.drop_constraint("uq_documents_family_version", "documents", type_="unique")
    op.drop_constraint("uq_documents_version_scope", "documents", type_="unique")
    op.drop_index("ix_documents_family_versions", table_name="documents")
    for name in (
        "content_hash_valid",
        "index_complete",
        "ready_content_valid",
        "failed_content_empty",
    ):
        op.drop_constraint(op.f(f"ck_documents_{name}"), "documents", type_="check")
    for name in (
        "family_id",
        "content_sha256",
        "indexed_at",
        "indexed_model",
        "indexed_dimensions",
        "indexed_chunk_count",
    ):
        op.drop_column("documents", name)
    op.drop_index("ix_document_families_list", table_name="document_families")
    op.drop_index("ix_document_families_created_by", table_name="document_families")
    op.drop_table("document_families")
