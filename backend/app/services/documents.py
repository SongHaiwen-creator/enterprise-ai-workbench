from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Document
from app.models.enums import DocumentStatus, KnowledgeBaseStatus
from app.schemas.document import DocumentStatusUpdate
from app.services.document_extraction import (
    DocumentExtractionError,
    PreparedDocumentUpload,
    extract_text,
)
from app.services.exceptions import ConflictError, NotFoundError
from app.services.knowledge_bases import get_knowledge_base


def get_document(
    session: Session,
    workspace_id: UUID,
    knowledge_base_id: UUID,
    document_id: UUID,
) -> Document:
    get_knowledge_base(session, workspace_id, knowledge_base_id)
    document = session.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.workspace_id == workspace_id,
            Document.knowledge_base_id == knowledge_base_id,
        )
    )
    if document is None:
        raise NotFoundError("Document not found")
    return document


def list_documents(
    session: Session,
    workspace_id: UUID,
    knowledge_base_id: UUID,
) -> list[Document]:
    get_knowledge_base(session, workspace_id, knowledge_base_id)
    statement = (
        select(Document)
        .where(
            Document.workspace_id == workspace_id,
            Document.knowledge_base_id == knowledge_base_id,
        )
        .order_by(Document.file_name, Document.version, Document.id)
    )
    return list(session.scalars(statement).all())


def upload_document(
    session: Session,
    workspace_id: UUID,
    knowledge_base_id: UUID,
    creator_id: UUID,
    upload: PreparedDocumentUpload,
) -> Document:
    knowledge_base = get_knowledge_base(session, workspace_id, knowledge_base_id)
    if knowledge_base.status is KnowledgeBaseStatus.DISABLED:
        raise ConflictError("Cannot upload to a disabled knowledge base")

    document = Document(
        workspace_id=workspace_id,
        knowledge_base_id=knowledge_base_id,
        file_name=upload.file_name,
        file_type=upload.file_type,
        created_by=creator_id,
    )
    session.add(document)
    session.commit()
    session.refresh(document)

    document.status = DocumentStatus.PROCESSING
    session.commit()

    try:
        document.extracted_text = extract_text(upload.file_type, upload.content)
    except DocumentExtractionError as exc:
        document.status = DocumentStatus.FAILED
        document.processing_error = str(exc)[:500]
    else:
        document.status = DocumentStatus.READY
        document.processing_error = None

    session.commit()
    session.refresh(document)
    return document


def update_document_status(
    session: Session,
    workspace_id: UUID,
    knowledge_base_id: UUID,
    document_id: UUID,
    payload: DocumentStatusUpdate,
) -> Document:
    document = get_document(
        session,
        workspace_id,
        knowledge_base_id,
        document_id,
    )
    allowed_transition = (
        document.status is DocumentStatus.READY and payload.status is DocumentStatus.DISABLED
    ) or (document.status is DocumentStatus.DISABLED and payload.status is DocumentStatus.READY)
    if not allowed_transition:
        raise ConflictError("Invalid document status transition")

    document.status = payload.status
    session.commit()
    session.refresh(document)
    return document
