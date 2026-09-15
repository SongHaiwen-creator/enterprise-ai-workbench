from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import KnowledgeBase
from app.schemas.knowledge_base import KnowledgeBaseCreate, KnowledgeBaseUpdate
from app.services.exceptions import NotFoundError


def get_knowledge_base(
    session: Session,
    workspace_id: UUID,
    knowledge_base_id: UUID,
) -> KnowledgeBase:
    knowledge_base = session.scalar(
        select(KnowledgeBase).where(
            KnowledgeBase.id == knowledge_base_id,
            KnowledgeBase.workspace_id == workspace_id,
        )
    )
    if knowledge_base is None:
        raise NotFoundError("Knowledge base not found")
    return knowledge_base


def list_knowledge_bases(
    session: Session,
    workspace_id: UUID,
) -> list[KnowledgeBase]:
    statement = (
        select(KnowledgeBase)
        .where(KnowledgeBase.workspace_id == workspace_id)
        .order_by(KnowledgeBase.name, KnowledgeBase.id)
    )
    return list(session.scalars(statement).all())


def create_knowledge_base(
    session: Session,
    workspace_id: UUID,
    creator_id: UUID,
    payload: KnowledgeBaseCreate,
) -> KnowledgeBase:
    knowledge_base = KnowledgeBase(
        workspace_id=workspace_id,
        name=payload.name,
        description=payload.description,
        created_by=creator_id,
    )
    session.add(knowledge_base)
    session.commit()
    session.refresh(knowledge_base)
    return knowledge_base


def update_knowledge_base(
    session: Session,
    workspace_id: UUID,
    knowledge_base_id: UUID,
    payload: KnowledgeBaseUpdate,
) -> KnowledgeBase:
    knowledge_base = get_knowledge_base(session, workspace_id, knowledge_base_id)
    for field_name, value in payload.model_dump(exclude_unset=True).items():
        setattr(knowledge_base, field_name, value)
    session.commit()
    session.refresh(knowledge_base)
    return knowledge_base
