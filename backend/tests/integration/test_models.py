from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Chunk, Document, KnowledgeBase, Membership, User, Workspace
from app.models.enums import (
    DocumentFileType,
    DocumentStatus,
    KnowledgeBaseStatus,
    MembershipRole,
    MembershipStatus,
    UserStatus,
    WorkspaceStatus,
)

pytestmark = pytest.mark.integration


def test_successful_user_workspace_and_membership_insert(db_session: Session) -> None:
    user = User(email="Alice@Company.com", name="Alice")
    workspace = Workspace(name="Example Company", slug="example-company")
    db_session.add_all([user, workspace])
    db_session.flush()

    membership = Membership(user_id=user.id, workspace_id=workspace.id)
    db_session.add(membership)
    db_session.commit()

    assert user.email == "alice@company.com"
    assert user.password_hash is None
    assert user.status is UserStatus.ACTIVE
    assert workspace.status is WorkspaceStatus.ACTIVE
    assert membership.role is MembershipRole.EMPLOYEE
    assert membership.status is MembershipStatus.INVITED
    assert user.id is not None
    assert workspace.id is not None
    assert membership.id is not None
    assert user.created_at is not None
    assert workspace.created_at is not None


def test_email_is_case_insensitively_unique(db_session: Session) -> None:
    db_session.execute(
        text("INSERT INTO users (email, name) VALUES (:email, :name)"),
        {"email": "Alice@Company.com", "name": "Alice"},
    )

    with pytest.raises(IntegrityError):
        db_session.execute(
            text("INSERT INTO users (email, name) VALUES (:email, :name)"),
            {"email": "alice@company.com", "name": "Another Alice"},
        )


def test_workspace_slug_is_unique(db_session: Session) -> None:
    db_session.add_all(
        [
            Workspace(name="First Workspace", slug="duplicate"),
            Workspace(name="Second Workspace", slug="duplicate"),
        ]
    )

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_duplicate_membership_is_rejected(db_session: Session) -> None:
    user = User(email="member@company.com", name="Member")
    workspace = Workspace(name="Membership Workspace", slug="membership-workspace")
    db_session.add_all([user, workspace])
    db_session.flush()
    db_session.add_all(
        [
            Membership(user_id=user.id, workspace_id=workspace.id),
            Membership(user_id=user.id, workspace_id=workspace.id),
        ]
    )

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_membership_foreign_keys_are_enforced(db_session: Session) -> None:
    db_session.add(Membership(user_id=uuid4(), workspace_id=uuid4()))

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_status_check_constraint_is_enforced(db_session: Session) -> None:
    with pytest.raises(IntegrityError):
        db_session.execute(
            text("INSERT INTO users (email, name, status) VALUES (:email, :name, :status)"),
            {"email": "invalid@company.com", "name": "Invalid", "status": "unknown"},
        )


def test_successful_knowledge_base_insert(db_session: Session) -> None:
    creator = User(email="creator@company.com", name="Creator")
    workspace = Workspace(name="Knowledge Workspace", slug="knowledge-workspace")
    db_session.add_all([creator, workspace])
    db_session.flush()
    knowledge_base = KnowledgeBase(
        workspace_id=workspace.id,
        name="Employee Policies",
        description="Approved policies",
        created_by=creator.id,
    )
    db_session.add(knowledge_base)
    db_session.commit()

    assert knowledge_base.id is not None
    assert knowledge_base.status is KnowledgeBaseStatus.ACTIVE
    assert knowledge_base.created_at is not None
    assert knowledge_base.updated_at is not None


def test_knowledge_base_foreign_keys_are_enforced(db_session: Session) -> None:
    db_session.add(
        KnowledgeBase(
            workspace_id=uuid4(),
            name="Orphaned Knowledge",
            created_by=uuid4(),
        )
    )

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_knowledge_base_status_check_constraint_is_enforced(
    db_session: Session,
) -> None:
    creator = User(email="status-creator@company.com", name="Creator")
    workspace = Workspace(name="Status Workspace", slug="status-workspace")
    db_session.add_all([creator, workspace])
    db_session.flush()

    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                "INSERT INTO knowledge_bases "
                "(workspace_id, name, status, created_by) "
                "VALUES (:workspace_id, :name, :status, :created_by)"
            ),
            {
                "workspace_id": workspace.id,
                "name": "Invalid Status",
                "status": "unknown",
                "created_by": creator.id,
            },
        )


def test_successful_document_insert(db_session: Session) -> None:
    creator = User(email="document-creator@company.com", name="Creator")
    workspace = Workspace(name="Document Workspace", slug="document-workspace")
    db_session.add_all([creator, workspace])
    db_session.flush()
    knowledge_base = KnowledgeBase(
        workspace_id=workspace.id,
        name="Employee Policies",
        created_by=creator.id,
    )
    db_session.add(knowledge_base)
    db_session.flush()
    document = Document(
        workspace_id=workspace.id,
        knowledge_base_id=knowledge_base.id,
        file_name="handbook.md",
        file_type=DocumentFileType.MARKDOWN,
        created_by=creator.id,
    )
    db_session.add(document)
    db_session.commit()

    assert document.id is not None
    assert document.status is DocumentStatus.UPLOADED
    assert document.version == 1
    assert document.extracted_text is None
    assert document.processing_error is None
    assert document.created_at is not None
    assert document.updated_at is not None


def test_document_foreign_keys_are_enforced(db_session: Session) -> None:
    db_session.add(
        Document(
            workspace_id=uuid4(),
            knowledge_base_id=uuid4(),
            file_name="orphan.txt",
            file_type=DocumentFileType.TXT,
            created_by=uuid4(),
        )
    )

    with pytest.raises(IntegrityError):
        db_session.flush()


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("file_type", "docx"),
        ("status", "unknown"),
        ("version", 0),
    ],
)
def test_document_check_constraints_are_enforced(
    db_session: Session,
    column: str,
    value: str | int,
) -> None:
    creator = User(email=f"constraint-{column}@company.com", name="Creator")
    workspace = Workspace(name=f"{column} Workspace", slug=f"constraint-{column}")
    db_session.add_all([creator, workspace])
    db_session.flush()
    knowledge_base = KnowledgeBase(
        workspace_id=workspace.id,
        name="Policies",
        created_by=creator.id,
    )
    db_session.add(knowledge_base)
    db_session.flush()

    values: dict[str, object] = {
        "workspace_id": workspace.id,
        "knowledge_base_id": knowledge_base.id,
        "file_name": "policy.txt",
        "file_type": "txt",
        "status": "uploaded",
        "version": 1,
        "created_by": creator.id,
    }
    values[column] = value
    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                "INSERT INTO documents "
                "(workspace_id, knowledge_base_id, file_name, file_type, status, "
                "version, created_by) VALUES (:workspace_id, :knowledge_base_id, "
                ":file_name, :file_type, :status, :version, :created_by)"
            ),
            values,
        )


def test_successful_chunk_insert(db_session: Session) -> None:
    creator = User(email="chunk-creator@company.com", name="Creator")
    workspace = Workspace(name="Chunk Workspace", slug="chunk-workspace")
    db_session.add_all([creator, workspace])
    db_session.flush()
    knowledge_base = KnowledgeBase(
        workspace_id=workspace.id,
        name="Policies",
        created_by=creator.id,
    )
    db_session.add(knowledge_base)
    db_session.flush()
    document = Document(
        workspace_id=workspace.id,
        knowledge_base_id=knowledge_base.id,
        file_name="policy.txt",
        file_type=DocumentFileType.TXT,
        status=DocumentStatus.READY,
        extracted_text="Policy text",
        created_by=creator.id,
    )
    db_session.add(document)
    db_session.flush()
    chunk = Chunk(
        workspace_id=workspace.id,
        document_id=document.id,
        content="Policy text",
        chunk_index=0,
        embedding_model="text-embedding-3-small",
        embedding=[0.0] * 1536,
    )
    db_session.add(chunk)
    db_session.commit()

    assert chunk.id is not None
    assert chunk.created_at is not None
    assert len(chunk.embedding) == 1536


@pytest.mark.parametrize(
    ("content", "chunk_index"),
    [("", 0), ("   ", 0), ("valid", -1)],
)
def test_chunk_check_constraints_are_enforced(
    db_session: Session,
    content: str,
    chunk_index: int,
) -> None:
    creator = User(email=f"chunk-{chunk_index}-{len(content)}@company.com", name="Creator")
    workspace = Workspace(
        name=f"Chunk Constraint {chunk_index} {len(content)}",
        slug=f"chunk-constraint-{chunk_index + 1}-{len(content)}",
    )
    db_session.add_all([creator, workspace])
    db_session.flush()
    knowledge_base = KnowledgeBase(
        workspace_id=workspace.id,
        name="Policies",
        created_by=creator.id,
    )
    db_session.add(knowledge_base)
    db_session.flush()
    document = Document(
        workspace_id=workspace.id,
        knowledge_base_id=knowledge_base.id,
        file_name="policy.txt",
        file_type=DocumentFileType.TXT,
        status=DocumentStatus.READY,
        extracted_text="Policy text",
        created_by=creator.id,
    )
    db_session.add(document)
    db_session.flush()
    db_session.add(
        Chunk(
            workspace_id=workspace.id,
            document_id=document.id,
            content=content,
            chunk_index=chunk_index,
            embedding_model="text-embedding-3-small",
            embedding=[0.0] * 1536,
        )
    )

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_chunk_foreign_keys_are_enforced(db_session: Session) -> None:
    db_session.add(
        Chunk(
            workspace_id=uuid4(),
            document_id=uuid4(),
            content="Orphan chunk",
            chunk_index=0,
            embedding_model="text-embedding-3-small",
            embedding=[0.0] * 1536,
        )
    )

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_chunk_workspace_must_match_parent_document(db_session: Session) -> None:
    creator = User(email="chunk-workspace-owner@company.com", name="Creator")
    workspace = Workspace(name="Chunk Owner", slug="chunk-owner")
    other_workspace = Workspace(name="Other Owner", slug="other-owner")
    db_session.add_all([creator, workspace, other_workspace])
    db_session.flush()
    knowledge_base = KnowledgeBase(
        workspace_id=workspace.id,
        name="Policies",
        created_by=creator.id,
    )
    db_session.add(knowledge_base)
    db_session.flush()
    document = Document(
        workspace_id=workspace.id,
        knowledge_base_id=knowledge_base.id,
        file_name="policy.txt",
        file_type=DocumentFileType.TXT,
        status=DocumentStatus.READY,
        extracted_text="Policy text",
        created_by=creator.id,
    )
    db_session.add(document)
    db_session.flush()
    db_session.add(
        Chunk(
            workspace_id=other_workspace.id,
            document_id=document.id,
            content="Cross-workspace chunk",
            chunk_index=0,
            embedding_model="text-embedding-3-small",
            embedding=[0.0] * 1536,
        )
    )

    with pytest.raises(IntegrityError):
        db_session.flush()
