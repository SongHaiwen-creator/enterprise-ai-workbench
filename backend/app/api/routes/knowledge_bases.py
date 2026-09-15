from uuid import UUID

from fastapi import APIRouter, status

from app.api.dependencies.auth import CurrentUser, DatabaseSession
from app.api.dependencies.authorization import (
    ActiveWorkspaceMembership,
    KnowledgeAdministratorMembership,
)
from app.schemas.common import ErrorResponse
from app.schemas.knowledge_base import (
    KnowledgeBaseCreate,
    KnowledgeBaseResponse,
    KnowledgeBaseUpdate,
)
from app.services import knowledge_bases as knowledge_base_service

router = APIRouter(
    prefix="/workspaces/{workspace_id}/knowledge-bases",
    tags=["knowledge-bases"],
)

WORKSPACE_ACCESS_RESPONSES = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
}


@router.post(
    "",
    response_model=KnowledgeBaseResponse,
    status_code=status.HTTP_201_CREATED,
    responses=WORKSPACE_ACCESS_RESPONSES,
)
def create_knowledge_base(
    workspace_id: UUID,
    payload: KnowledgeBaseCreate,
    session: DatabaseSession,
    current_user: CurrentUser,
    _administrator: KnowledgeAdministratorMembership,
) -> KnowledgeBaseResponse:
    knowledge_base = knowledge_base_service.create_knowledge_base(
        session,
        workspace_id,
        current_user.id,
        payload,
    )
    return KnowledgeBaseResponse.model_validate(knowledge_base)


@router.get(
    "",
    response_model=list[KnowledgeBaseResponse],
    responses=WORKSPACE_ACCESS_RESPONSES,
)
def list_knowledge_bases(
    workspace_id: UUID,
    session: DatabaseSession,
    _membership: ActiveWorkspaceMembership,
) -> list[KnowledgeBaseResponse]:
    knowledge_bases = knowledge_base_service.list_knowledge_bases(session, workspace_id)
    return [KnowledgeBaseResponse.model_validate(item) for item in knowledge_bases]


@router.get(
    "/{knowledge_base_id}",
    response_model=KnowledgeBaseResponse,
    responses=WORKSPACE_ACCESS_RESPONSES,
)
def get_knowledge_base(
    workspace_id: UUID,
    knowledge_base_id: UUID,
    session: DatabaseSession,
    _membership: ActiveWorkspaceMembership,
) -> KnowledgeBaseResponse:
    knowledge_base = knowledge_base_service.get_knowledge_base(
        session,
        workspace_id,
        knowledge_base_id,
    )
    return KnowledgeBaseResponse.model_validate(knowledge_base)


@router.patch(
    "/{knowledge_base_id}",
    response_model=KnowledgeBaseResponse,
    responses=WORKSPACE_ACCESS_RESPONSES,
)
def update_knowledge_base(
    workspace_id: UUID,
    knowledge_base_id: UUID,
    payload: KnowledgeBaseUpdate,
    session: DatabaseSession,
    _administrator: KnowledgeAdministratorMembership,
) -> KnowledgeBaseResponse:
    knowledge_base = knowledge_base_service.update_knowledge_base(
        session,
        workspace_id,
        knowledge_base_id,
        payload,
    )
    return KnowledgeBaseResponse.model_validate(knowledge_base)
