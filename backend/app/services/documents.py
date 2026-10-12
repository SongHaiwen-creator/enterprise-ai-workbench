"""Concrete immutable versions, with short serialized publication transactions."""

import hashlib
from contextlib import contextmanager
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.models import Document, DocumentFamily, KnowledgeBase, Membership, User, Workspace
from app.models.enums import DocumentStatus, KnowledgeBaseStatus
from app.schemas.document import DocumentActivation, DocumentResponse, DocumentStatusUpdate
from app.services.document_extraction import (
    DocumentExtractionError,
    PreparedDocumentUpload,
    extract_text,
)
from app.services.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.services.knowledge_bases import get_knowledge_base


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


@contextmanager
def write_boundary(session):
    try:
        session.execute(select(func.set_config("lock_timeout", "5000", True)))
        yield
    except DBAPIError as error:
        session.rollback()
        if getattr(error.orig, "sqlstate", None) in {"55P03", "40P01", "57014", "23505"}:
            raise ConflictError("Document version operation conflict") from None
        raise
    except Exception:
        session.rollback()
        raise


def current_authority(session, workspace_id, actor_id):
    # Column query bypasses cached ORM identities after parser/provider phases.
    row = session.execute(
        select(User.status, Workspace.status, Membership.status, Membership.role)
        .select_from(User)
        .join(Membership, Membership.user_id == User.id)
        .join(Workspace, Workspace.id == Membership.workspace_id)
        .where(
            User.id == actor_id,
            Workspace.id == workspace_id,
            Membership.workspace_id == workspace_id,
        )
    ).one_or_none()
    if row is None or row[:3] != ("active", "active", "active"):
        raise ForbiddenError("Not authorized for this workspace")
    if row[3] not in {"knowledge_admin", "system_admin"}:
        raise ForbiddenError("Knowledge administrator role required")


def locked_base(
    session,
    workspace_id,
    knowledge_base_id,
    actor_id,
    *,
    active=True,
    disabled_detail="Cannot manage versions in a disabled knowledge base",
):
    base = session.scalar(
        select(KnowledgeBase)
        .where(KnowledgeBase.id == knowledge_base_id, KnowledgeBase.workspace_id == workspace_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if base is None:
        raise NotFoundError("Knowledge base not found")
    current_authority(session, workspace_id, actor_id)
    if active and base.status is not KnowledgeBaseStatus.ACTIVE:
        raise ConflictError(disabled_detail)
    return base


def get_family(session, workspace_id, knowledge_base_id, family_id, *, lock=False):
    get_knowledge_base(session, workspace_id, knowledge_base_id)
    query = select(DocumentFamily).where(
        DocumentFamily.id == family_id,
        DocumentFamily.workspace_id == workspace_id,
        DocumentFamily.knowledge_base_id == knowledge_base_id,
    )
    if lock:
        query = query.with_for_update()
    family = session.scalar(query.execution_options(populate_existing=True))
    if family is None:
        raise NotFoundError("Document family not found")
    return family


def list_families(session, workspace_id, knowledge_base_id):
    get_knowledge_base(session, workspace_id, knowledge_base_id)
    return session.scalars(
        select(DocumentFamily)
        .where(
            DocumentFamily.workspace_id == workspace_id,
            DocumentFamily.knowledge_base_id == knowledge_base_id,
        )
        .order_by(DocumentFamily.display_name, DocumentFamily.id)
    ).all()


def get_document(
    session: Session,
    workspace_id: UUID,
    knowledge_base_id: UUID,
    document_id: UUID,
    *,
    lock=False,
    family_id=None,
) -> Document:
    get_knowledge_base(session, workspace_id, knowledge_base_id)
    query = select(Document).where(
        Document.id == document_id,
        Document.workspace_id == workspace_id,
        Document.knowledge_base_id == knowledge_base_id,
    )
    if family_id is not None:
        query = query.where(Document.family_id == family_id)
    if lock:
        query = query.with_for_update()
    document = session.scalar(query.execution_options(populate_existing=True))
    if document is None:
        raise NotFoundError("Document not found")
    return document


def list_documents(session, workspace_id, knowledge_base_id, *, family_id=None):
    get_knowledge_base(session, workspace_id, knowledge_base_id)
    query = select(Document).where(
        Document.workspace_id == workspace_id, Document.knowledge_base_id == knowledge_base_id
    )
    if family_id is not None:
        get_family(session, workspace_id, knowledge_base_id, family_id)
        query = query.where(Document.family_id == family_id).order_by(
            Document.version.desc(), Document.id
        )
    else:
        query = query.order_by(Document.file_name, Document.version, Document.id)
    return session.scalars(query.execution_options(populate_existing=True)).all()


def document_response(session, document):
    current = session.scalar(
        select(DocumentFamily.current_document_id).where(
            DocumentFamily.id == document.family_id,
            DocumentFamily.workspace_id == document.workspace_id,
            DocumentFamily.knowledge_base_id == document.knowledge_base_id,
        )
    )
    values = {
        name: getattr(document, name)
        for name in DocumentResponse.model_fields
        if name not in {"is_current", "indexing"}
    }
    values["is_current"] = current == document.id
    values["indexing"] = (
        None
        if document.indexed_at is None
        else {
            "chunk_count": document.indexed_chunk_count,
            "embedding_model": document.indexed_model,
            "embedding_dimensions": document.indexed_dimensions,
            "indexed_at": document.indexed_at,
        }
    )
    return DocumentResponse.model_validate(values)


def changed(family):
    if family.revision >= 2147483647:
        raise ConflictError("Document version operation conflict")
    family.revision += 1
    family.updated_at = func.clock_timestamp()


def upload_document(
    session,
    workspace_id,
    knowledge_base_id,
    creator_id,
    upload: PreparedDocumentUpload,
    *,
    family_id=None,
):
    initial = family_id is None
    with write_boundary(session):
        locked_base(
            session,
            workspace_id,
            knowledge_base_id,
            creator_id,
            disabled_detail="Cannot upload to a disabled knowledge base",
        )
        if initial:
            family = DocumentFamily(
                workspace_id=workspace_id,
                knowledge_base_id=knowledge_base_id,
                display_name=upload.file_name,
                created_by=creator_id,
            )
            session.add(family)
            session.flush()
            version = 1
        else:
            family = get_family(session, workspace_id, knowledge_base_id, family_id, lock=True)
            if family.next_version >= 2147483647:
                raise ConflictError("Document version operation conflict")
            version = family.next_version
            family.next_version += 1
            changed(family)
        document = Document(
            workspace_id=workspace_id,
            knowledge_base_id=knowledge_base_id,
            family_id=family.id,
            version=version,
            file_name=upload.file_name,
            file_type=upload.file_type,
            created_by=creator_id,
        )
        session.add(document)
        session.flush()
        document_id, family_id = document.id, family.id
        session.commit()
    with write_boundary(session):
        locked_base(
            session,
            workspace_id,
            knowledge_base_id,
            creator_id,
            disabled_detail="Cannot upload to a disabled knowledge base",
        )
        family = get_family(session, workspace_id, knowledge_base_id, family_id, lock=True)
        document = get_document(session, workspace_id, knowledge_base_id, document_id, lock=True)
        document.status = DocumentStatus.PROCESSING
        changed(family)
        session.commit()
    try:
        content = extract_text(upload.file_type, upload.content)
        error = None
    except DocumentExtractionError as exc:
        content, error = None, str(exc)[:500]
    with write_boundary(session):
        locked_base(
            session,
            workspace_id,
            knowledge_base_id,
            creator_id,
            disabled_detail="Cannot upload to a disabled knowledge base",
        )
        family = get_family(session, workspace_id, knowledge_base_id, family_id, lock=True)
        document = get_document(session, workspace_id, knowledge_base_id, document_id, lock=True)
        if document.status is not DocumentStatus.PROCESSING:
            raise ConflictError("Document version operation conflict")
        document.extracted_text = content
        document.content_sha256 = content_hash(content) if content is not None else None
        document.processing_error = error
        document.status = DocumentStatus.FAILED if error is not None else DocumentStatus.READY
        if initial and content is not None and family.current_document_id is None:
            family.current_document_id = document.id
        changed(family)
        session.commit()
        session.refresh(document)
    return document


def update_document_status(
    session,
    workspace_id,
    knowledge_base_id,
    document_id,
    payload: DocumentStatusUpdate,
    *,
    actor_id,
):
    family_id = get_document(session, workspace_id, knowledge_base_id, document_id).family_id
    with write_boundary(session):
        locked_base(session, workspace_id, knowledge_base_id, actor_id, active=False)
        family = get_family(session, workspace_id, knowledge_base_id, family_id, lock=True)
        document = get_document(session, workspace_id, knowledge_base_id, document_id, lock=True)
        pair = (document.status, payload.status)
        if pair not in {
            (DocumentStatus.READY, DocumentStatus.DISABLED),
            (DocumentStatus.DISABLED, DocumentStatus.READY),
        }:
            raise ConflictError("Invalid document status transition")
        document.status = payload.status
        changed(family)
        session.commit()
        session.refresh(document)
    return document


def activate_document(
    session,
    workspace_id,
    knowledge_base_id,
    family_id,
    payload: DocumentActivation,
    actor_id,
    model,
    dimensions,
):
    with write_boundary(session):
        locked_base(session, workspace_id, knowledge_base_id, actor_id)
        family = get_family(session, workspace_id, knowledge_base_id, family_id, lock=True)
        if family.revision != payload.expected_revision:
            raise ConflictError("Document family revision conflict")
        document = get_document(
            session,
            workspace_id,
            knowledge_base_id,
            payload.document_id,
            family_id=family_id,
            lock=True,
        )
        if (
            document.status is not DocumentStatus.READY
            or document.indexed_at is None
            or document.indexed_model != model
            or document.indexed_dimensions != dimensions
        ):
            raise ConflictError("Document version is not eligible for activation")
        if family.current_document_id != document.id:
            family.current_document_id = document.id
            changed(family)
        session.commit()
        session.refresh(family)
    return family
