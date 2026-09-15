from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import KnowledgeBase, Membership, User, Workspace
from app.models.enums import (
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
