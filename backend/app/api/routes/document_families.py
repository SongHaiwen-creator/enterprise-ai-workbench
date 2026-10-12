from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, UploadFile

from app.api.dependencies.auth import ApplicationSettings, DatabaseSession
from app.api.dependencies.authorization import (
    ActiveWorkspaceMembership,
    KnowledgeAdministratorMembership,
)
from app.api.document_route import DocumentRoute
from app.api.routes.documents import prepared_upload
from app.schemas.document import DocumentActivation, DocumentFamilyResponse, DocumentResponse
from app.services import documents as service

router = APIRouter(
    prefix="/workspaces/{workspace_id}/knowledge-bases/{knowledge_base_id}/document-families",
    tags=["document-versions"],
    route_class=DocumentRoute,
)


@router.get("", response_model=list[DocumentFamilyResponse])
def list_families(
    workspace_id: UUID,
    knowledge_base_id: UUID,
    session: DatabaseSession,
    _member: ActiveWorkspaceMembership,
):
    return service.list_families(session, workspace_id, knowledge_base_id)


@router.get("/{family_id}", response_model=DocumentFamilyResponse)
def get_family(
    workspace_id: UUID,
    knowledge_base_id: UUID,
    family_id: UUID,
    session: DatabaseSession,
    _member: ActiveWorkspaceMembership,
):
    return service.get_family(session, workspace_id, knowledge_base_id, family_id)


@router.get("/{family_id}/versions", response_model=list[DocumentResponse])
def list_versions(
    workspace_id: UUID,
    knowledge_base_id: UUID,
    family_id: UUID,
    session: DatabaseSession,
    _member: ActiveWorkspaceMembership,
):
    return [
        service.document_response(session, document)
        for document in service.list_documents(
            session, workspace_id, knowledge_base_id, family_id=family_id
        )
    ]


@router.post("/{family_id}/versions", response_model=DocumentResponse, status_code=201)
async def upload_version(
    workspace_id: UUID,
    knowledge_base_id: UUID,
    family_id: UUID,
    file: Annotated[UploadFile, File()],
    session: DatabaseSession,
    admin: KnowledgeAdministratorMembership,
):
    upload = await prepared_upload(file)
    document = service.upload_document(
        session, workspace_id, knowledge_base_id, admin.user_id, upload, family_id=family_id
    )
    return service.document_response(session, document)


@router.post("/{family_id}/activate", response_model=DocumentFamilyResponse)
def activate(
    workspace_id: UUID,
    knowledge_base_id: UUID,
    family_id: UUID,
    payload: DocumentActivation,
    session: DatabaseSession,
    admin: KnowledgeAdministratorMembership,
    settings: ApplicationSettings,
):
    return service.activate_document(
        session,
        workspace_id,
        knowledge_base_id,
        family_id,
        payload,
        admin.user_id,
        settings.embedding_model,
        settings.embedding_dimensions,
    )
