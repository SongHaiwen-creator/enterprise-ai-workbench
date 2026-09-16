from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.api.dependencies.auth import CurrentUser, DatabaseSession
from app.api.dependencies.authorization import (
    ActiveWorkspaceMembership,
    KnowledgeAdministratorMembership,
)
from app.schemas.common import ErrorResponse
from app.schemas.document import DocumentResponse, DocumentStatusUpdate
from app.services import documents as document_service
from app.services.document_extraction import (
    UnsupportedDocumentTypeError,
    UploadTooLargeError,
    UploadValidationError,
    prepare_upload,
)

router = APIRouter(
    prefix=("/workspaces/{workspace_id}/knowledge-bases/{knowledge_base_id}/documents"),
    tags=["documents"],
)

DOCUMENT_RESPONSES = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    413: {"model": ErrorResponse},
    415: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}


@router.post(
    "",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    responses=DOCUMENT_RESPONSES,
)
async def upload_document(
    workspace_id: UUID,
    knowledge_base_id: UUID,
    file: Annotated[UploadFile, File()],
    session: DatabaseSession,
    current_user: CurrentUser,
    _administrator: KnowledgeAdministratorMembership,
) -> DocumentResponse:
    try:
        upload = await prepare_upload(file)
    except UploadTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except UnsupportedDocumentTypeError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except UploadValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    document = document_service.upload_document(
        session,
        workspace_id,
        knowledge_base_id,
        current_user.id,
        upload,
    )
    return DocumentResponse.model_validate(document)


@router.get(
    "",
    response_model=list[DocumentResponse],
    responses=DOCUMENT_RESPONSES,
)
def list_documents(
    workspace_id: UUID,
    knowledge_base_id: UUID,
    session: DatabaseSession,
    _membership: ActiveWorkspaceMembership,
) -> list[DocumentResponse]:
    documents = document_service.list_documents(
        session,
        workspace_id,
        knowledge_base_id,
    )
    return [DocumentResponse.model_validate(item) for item in documents]


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    responses=DOCUMENT_RESPONSES,
)
def get_document(
    workspace_id: UUID,
    knowledge_base_id: UUID,
    document_id: UUID,
    session: DatabaseSession,
    _membership: ActiveWorkspaceMembership,
) -> DocumentResponse:
    document = document_service.get_document(
        session,
        workspace_id,
        knowledge_base_id,
        document_id,
    )
    return DocumentResponse.model_validate(document)


@router.patch(
    "/{document_id}",
    response_model=DocumentResponse,
    responses=DOCUMENT_RESPONSES,
)
def update_document_status(
    workspace_id: UUID,
    knowledge_base_id: UUID,
    document_id: UUID,
    payload: DocumentStatusUpdate,
    session: DatabaseSession,
    _administrator: KnowledgeAdministratorMembership,
) -> DocumentResponse:
    document = document_service.update_document_status(
        session,
        workspace_id,
        knowledge_base_id,
        document_id,
        payload,
    )
    return DocumentResponse.model_validate(document)
