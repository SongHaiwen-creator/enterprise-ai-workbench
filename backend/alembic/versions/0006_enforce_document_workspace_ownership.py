"""Enforce Document and Knowledge Base workspace ownership.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-17
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_knowledge_bases_id_workspace_id",
        "knowledge_bases",
        ["id", "workspace_id"],
    )
    op.create_foreign_key(
        "fk_documents_knowledge_base_workspace_knowledge_bases",
        "documents",
        "knowledge_bases",
        ["knowledge_base_id", "workspace_id"],
        ["id", "workspace_id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_documents_knowledge_base_workspace_knowledge_bases",
        "documents",
        type_="foreignkey",
    )
    op.drop_constraint(
        "uq_knowledge_bases_id_workspace_id",
        "knowledge_bases",
        type_="unique",
    )
