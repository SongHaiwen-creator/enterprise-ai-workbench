"""Create chunks with pgvector embeddings.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import VECTOR

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_unique_constraint(
        "uq_documents_id_workspace_id",
        "documents",
        ["id", "workspace_id"],
    )
    op.create_table(
        "chunks",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("embedding_model", sa.String(length=100), nullable=False),
        sa.Column("embedding", VECTOR(dim=1536), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "chunk_index >= 0",
            name=op.f("ck_chunks_chunk_index_non_negative"),
        ),
        sa.CheckConstraint(
            "btrim(content) <> ''",
            name=op.f("ck_chunks_content_not_empty"),
        ),
        sa.ForeignKeyConstraint(
            ["document_id", "workspace_id"],
            ["documents.id", "documents.workspace_id"],
            name="fk_chunks_document_workspace_documents",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_chunks_workspace_id_workspaces"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chunks")),
        sa.UniqueConstraint(
            "document_id",
            "chunk_index",
            name="uq_chunks_document_index",
        ),
    )
    op.create_index("ix_chunks_document_id", "chunks", ["document_id"], unique=False)
    op.create_index("ix_chunks_workspace_id", "chunks", ["workspace_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_chunks_workspace_id", table_name="chunks")
    op.drop_index("ix_chunks_document_id", table_name="chunks")
    op.drop_table("chunks")
    op.drop_constraint(
        "uq_documents_id_workspace_id",
        "documents",
        type_="unique",
    )
    op.execute("DROP EXTENSION IF EXISTS vector")
