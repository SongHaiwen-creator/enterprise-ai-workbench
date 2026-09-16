from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.enums import (
    DocumentFileType,
    DocumentStatus,
    KnowledgeBaseStatus,
    MembershipRole,
    MembershipStatus,
    WorkspaceStatus,
)
from app.schemas.document import DocumentResponse, DocumentStatusUpdate
from app.schemas.knowledge_base import (
    KnowledgeBaseCreate,
    KnowledgeBaseResponse,
    KnowledgeBaseUpdate,
)
from app.schemas.membership import MembershipResponse, MembershipUpdate
from app.schemas.workspace import WorkspaceCreate, WorkspaceResponse


def test_workspace_create_normalizes_input() -> None:
    payload = WorkspaceCreate(name=" Example Company ", slug=" Example-Company ")

    assert payload.name == "Example Company"
    assert payload.slug == "example-company"


@pytest.mark.parametrize("slug", ["has spaces", "has_underscore", "-leading", "trailing-"])
def test_workspace_create_rejects_invalid_slug(slug: str) -> None:
    with pytest.raises(ValidationError):
        WorkspaceCreate(name="Example Company", slug=slug)


@pytest.mark.parametrize("payload", [{}, {"role": None}, {"status": None}])
def test_membership_update_requires_a_non_null_field(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        MembershipUpdate.model_validate(payload)


def test_knowledge_base_create_normalizes_text() -> None:
    payload = KnowledgeBaseCreate(
        name=" Employee Policies ",
        description=" Approved policies ",
    )

    assert payload.name == "Employee Policies"
    assert payload.description == "Approved policies"


@pytest.mark.parametrize("payload", [{}, {"name": None}, {"status": None}])
def test_knowledge_base_update_requires_a_valid_field(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        KnowledgeBaseUpdate.model_validate(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"status": "uploaded"},
        {"status": "processing"},
        {"status": "failed"},
        {"status": None},
        {"status": "ready", "unknown": "value"},
    ],
)
def test_document_status_update_only_accepts_manageable_statuses(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        DocumentStatusUpdate.model_validate(payload)


def test_orm_response_models_read_attributes() -> None:
    now = datetime.now(UTC)
    workspace_id = uuid4()
    user_id = uuid4()
    workspace = SimpleNamespace(
        id=workspace_id,
        name="Example Company",
        slug="example-company",
        status=WorkspaceStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )
    membership = SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        workspace_id=workspace_id,
        role=MembershipRole.EMPLOYEE,
        status=MembershipStatus.INVITED,
        joined_at=None,
    )
    knowledge_base = SimpleNamespace(
        id=uuid4(),
        workspace_id=workspace_id,
        name="Employee Policies",
        description=None,
        status=KnowledgeBaseStatus.ACTIVE,
        created_by=user_id,
        created_at=now,
        updated_at=now,
    )
    document = SimpleNamespace(
        id=uuid4(),
        workspace_id=workspace_id,
        knowledge_base_id=knowledge_base.id,
        file_name="employee-handbook.pdf",
        file_type=DocumentFileType.PDF,
        status=DocumentStatus.READY,
        version=1,
        processing_error=None,
        created_by=user_id,
        created_at=now,
        updated_at=now,
    )

    assert WorkspaceResponse.model_validate(workspace).id == workspace_id
    assert MembershipResponse.model_validate(membership).user_id == user_id
    assert KnowledgeBaseResponse.model_validate(knowledge_base).created_by == user_id
    response = DocumentResponse.model_validate(document)
    assert response.knowledge_base_id == knowledge_base.id
    assert "extracted_text" not in response.model_dump()
