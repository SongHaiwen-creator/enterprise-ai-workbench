from uuid import UUID

from sqlalchemy import ForeignKey, ForeignKeyConstraint, Index
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AgentTool(Base):
    __tablename__ = "agent_tools"
    __table_args__ = (
        ForeignKeyConstraint(
            ["agent_id", "workspace_id"],
            ["agents.id", "agents.workspace_id"], ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tool_id", "workspace_id"],
            ["tools.id", "tools.workspace_id"], ondelete="RESTRICT",
        ),
        Index("ix_agent_tools_workspace_id", "workspace_id"),
        Index("ix_agent_tools_tool_id", "tool_id"),
    )

    workspace_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False,
    )
    agent_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True,
    )
    tool_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True,
    )
