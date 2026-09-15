from collections.abc import Generator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.main import app
from app.models import KnowledgeBase, Membership, User, Workspace
from app.models.enums import (
    KnowledgeBaseStatus,
    MembershipRole,
    MembershipStatus,
    WorkspaceStatus,
)
from app.security.tokens import create_access_token

pytestmark = pytest.mark.integration
JWT_SECRET = "knowledge-base-api-secret-longer-than-thirty-two-bytes"


@pytest.fixture
def auth_settings(database_urls: tuple[object, object]) -> Settings:
    database_url, test_database_url = database_urls
    return Settings(
        database_url=str(database_url),
        test_database_url=str(test_database_url),
        jwt_secret_key=JWT_SECRET,
        _env_file=None,
    )


@pytest.fixture
def client(
    db_session: Session,
    auth_settings: Settings,
) -> Generator[TestClient, None, None]:
    def override_db_session() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[get_settings] = lambda: auth_settings
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_settings, None)


def create_user(session: Session, *, email: str) -> User:
    user = User(email=email, name=email.split("@", maxsplit=1)[0].title())
    session.add(user)
    session.flush()
    return user


def create_workspace(
    session: Session,
    *,
    slug: str,
    status: WorkspaceStatus = WorkspaceStatus.ACTIVE,
) -> Workspace:
    workspace = Workspace(name=slug.replace("-", " ").title(), slug=slug, status=status)
    session.add(workspace)
    session.flush()
    return workspace


def add_membership(
    session: Session,
    user: User,
    workspace: Workspace,
    *,
    role: MembershipRole = MembershipRole.EMPLOYEE,
    status: MembershipStatus = MembershipStatus.ACTIVE,
) -> Membership:
    membership = Membership(
        user_id=user.id,
        workspace_id=workspace.id,
        role=role,
        status=status,
        joined_at=datetime.now(UTC) if status is MembershipStatus.ACTIVE else None,
    )
    session.add(membership)
    session.flush()
    return membership


def create_knowledge_base(
    session: Session,
    workspace: Workspace,
    creator: User,
    *,
    name: str = "Employee Policies",
    status: KnowledgeBaseStatus = KnowledgeBaseStatus.ACTIVE,
) -> KnowledgeBase:
    knowledge_base = KnowledgeBase(
        workspace_id=workspace.id,
        name=name,
        description=f"Description for {name}",
        status=status,
        created_by=creator.id,
    )
    session.add(knowledge_base)
    session.flush()
    return knowledge_base


def bearer(user: User, settings: Settings) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, settings)}"}


def knowledge_base_collection(workspace: Workspace) -> str:
    return f"/api/workspaces/{workspace.id}/knowledge-bases"


@pytest.mark.parametrize(
    ("method", "suffix", "body"),
    [
        ("get", "", None),
        ("post", "", {"name": "Employee Policies"}),
        ("get", f"/{uuid4()}", None),
        ("patch", f"/{uuid4()}", {"name": "Updated"}),
    ],
)
def test_knowledge_base_routes_require_authentication(
    client: TestClient,
    method: str,
    suffix: str,
    body: dict[str, str] | None,
) -> None:
    response = client.request(
        method,
        f"/api/workspaces/{uuid4()}/knowledge-bases{suffix}",
        json=body,
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "role",
    [MembershipRole.KNOWLEDGE_ADMIN, MembershipRole.SYSTEM_ADMIN],
)
def test_authorized_administrator_can_create_knowledge_base(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    role: MembershipRole,
) -> None:
    caller = create_user(db_session, email=f"{role.value}@company.com")
    workspace = create_workspace(db_session, slug=f"{role.value}-workspace")
    add_membership(db_session, caller, workspace, role=role)

    response = client.post(
        knowledge_base_collection(workspace),
        headers=bearer(caller, auth_settings),
        json={
            "name": " Employee Policies ",
            "description": " Approved policies ",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["workspace_id"] == str(workspace.id)
    assert payload["created_by"] == str(caller.id)
    assert payload["name"] == "Employee Policies"
    assert payload["description"] == "Approved policies"
    assert payload["status"] == "active"
    assert payload["created_at"] is not None
    assert payload["updated_at"] is not None
    persisted = db_session.get(KnowledgeBase, UUID(payload["id"]))
    assert persisted is not None
    assert persisted.workspace_id == workspace.id
    assert persisted.created_by == caller.id


@pytest.mark.parametrize(
    "role",
    [MembershipRole.EMPLOYEE, MembershipRole.AGENT_ADMIN],
)
@pytest.mark.parametrize("method", ["post", "patch"])
def test_knowledge_base_mutation_requires_knowledge_administrator(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    role: MembershipRole,
    method: str,
) -> None:
    caller = create_user(db_session, email=f"{role.value}-{method}@company.com")
    creator = create_user(db_session, email=f"creator-{role.value}-{method}@company.com")
    workspace = create_workspace(db_session, slug=f"{role.value}-{method}")
    add_membership(db_session, caller, workspace, role=role)
    knowledge_base = create_knowledge_base(db_session, workspace, creator)
    path = knowledge_base_collection(workspace)
    if method == "patch":
        path = f"{path}/{knowledge_base.id}"

    response = client.request(
        method,
        path,
        headers=bearer(caller, auth_settings),
        json={"name": "Updated Policies"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Knowledge administrator role required"}


@pytest.mark.parametrize("role", list(MembershipRole))
def test_active_workspace_member_can_read_knowledge_bases(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    role: MembershipRole,
) -> None:
    caller = create_user(db_session, email=f"reader-{role.value}@company.com")
    workspace = create_workspace(db_session, slug=f"reader-{role.value}")
    add_membership(db_session, caller, workspace, role=role)
    knowledge_base = create_knowledge_base(db_session, workspace, caller)

    list_response = client.get(
        knowledge_base_collection(workspace),
        headers=bearer(caller, auth_settings),
    )
    item_response = client.get(
        f"{knowledge_base_collection(workspace)}/{knowledge_base.id}",
        headers=bearer(caller, auth_settings),
    )

    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [str(knowledge_base.id)]
    assert item_response.status_code == 200
    assert item_response.json()["id"] == str(knowledge_base.id)


def test_knowledge_base_list_is_ordered_and_includes_disabled_records(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
) -> None:
    caller = create_user(db_session, email="ordered-reader@company.com")
    workspace = create_workspace(db_session, slug="ordered-list")
    add_membership(db_session, caller, workspace)
    create_knowledge_base(db_session, workspace, caller, name="Zulu")
    create_knowledge_base(
        db_session,
        workspace,
        caller,
        name="Alpha",
        status=KnowledgeBaseStatus.DISABLED,
    )

    response = client.get(
        knowledge_base_collection(workspace),
        headers=bearer(caller, auth_settings),
    )

    assert response.status_code == 200
    assert [(item["name"], item["status"]) for item in response.json()] == [
        ("Alpha", "disabled"),
        ("Zulu", "active"),
    ]


def test_knowledge_base_list_is_empty_for_workspace_without_records(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
) -> None:
    caller = create_user(db_session, email="empty-reader@company.com")
    workspace = create_workspace(db_session, slug="empty-list")
    add_membership(db_session, caller, workspace)

    response = client.get(
        knowledge_base_collection(workspace),
        headers=bearer(caller, auth_settings),
    )

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize(
    "role",
    [MembershipRole.KNOWLEDGE_ADMIN, MembershipRole.SYSTEM_ADMIN],
)
def test_authorized_administrator_can_update_disable_and_reenable_knowledge_base(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    role: MembershipRole,
) -> None:
    caller = create_user(db_session, email=f"updater-{role.value}@company.com")
    workspace = create_workspace(db_session, slug=f"managed-{role.value}")
    add_membership(db_session, caller, workspace, role=role)
    knowledge_base = create_knowledge_base(db_session, workspace, caller)
    endpoint = f"{knowledge_base_collection(workspace)}/{knowledge_base.id}"

    disabled = client.patch(
        endpoint,
        headers=bearer(caller, auth_settings),
        json={
            "name": " Global Policies ",
            "description": None,
            "status": "disabled",
        },
    )
    reenabled = client.patch(
        endpoint,
        headers=bearer(caller, auth_settings),
        json={"status": "active"},
    )

    assert disabled.status_code == 200
    assert disabled.json()["name"] == "Global Policies"
    assert disabled.json()["description"] is None
    assert disabled.json()["status"] == "disabled"
    assert reenabled.status_code == 200
    assert reenabled.json()["status"] == "active"


def test_active_member_can_read_disabled_knowledge_base(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
) -> None:
    caller = create_user(db_session, email="disabled-reader@company.com")
    workspace = create_workspace(db_session, slug="disabled-record-reader")
    add_membership(db_session, caller, workspace)
    knowledge_base = create_knowledge_base(
        db_session,
        workspace,
        caller,
        status=KnowledgeBaseStatus.DISABLED,
    )

    response = client.get(
        f"{knowledge_base_collection(workspace)}/{knowledge_base.id}",
        headers=bearer(caller, auth_settings),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "disabled"


@pytest.mark.parametrize("membership_status", [None, *list(MembershipStatus)[1:]])
@pytest.mark.parametrize("method", ["get", "post"])
def test_knowledge_base_access_requires_active_membership(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    membership_status: MembershipStatus | None,
    method: str,
) -> None:
    caller = create_user(
        db_session,
        email=f"{membership_status or 'missing'}-{method}@company.com",
    )
    workspace = create_workspace(
        db_session,
        slug=f"{membership_status or 'missing'}-{method}",
    )
    if membership_status is not None:
        add_membership(
            db_session,
            caller,
            workspace,
            role=MembershipRole.KNOWLEDGE_ADMIN,
            status=membership_status,
        )

    response = client.request(
        method,
        knowledge_base_collection(workspace),
        headers=bearer(caller, auth_settings),
        json={"name": "Employee Policies"} if method == "post" else None,
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Not authorized for this workspace"}


def test_disabled_workspace_denies_knowledge_base_access(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
) -> None:
    caller = create_user(db_session, email="disabled-workspace@company.com")
    workspace = create_workspace(
        db_session,
        slug="disabled-knowledge-workspace",
        status=WorkspaceStatus.DISABLED,
    )
    add_membership(
        db_session,
        caller,
        workspace,
        role=MembershipRole.KNOWLEDGE_ADMIN,
    )

    response = client.get(
        knowledge_base_collection(workspace),
        headers=bearer(caller, auth_settings),
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Not authorized for this workspace"}


@pytest.mark.parametrize("method", ["get", "patch"])
def test_cross_workspace_knowledge_base_id_does_not_leak_existence(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    method: str,
) -> None:
    caller = create_user(db_session, email=f"cross-workspace-{method}@company.com")
    allowed_workspace = create_workspace(db_session, slug=f"allowed-{method}")
    foreign_workspace = create_workspace(db_session, slug=f"foreign-{method}")
    add_membership(
        db_session,
        caller,
        allowed_workspace,
        role=MembershipRole.KNOWLEDGE_ADMIN,
    )
    foreign_knowledge_base = create_knowledge_base(
        db_session,
        foreign_workspace,
        caller,
    )

    response = client.request(
        method,
        f"{knowledge_base_collection(allowed_workspace)}/{foreign_knowledge_base.id}",
        headers=bearer(caller, auth_settings),
        json={"name": "Guessed"} if method == "patch" else None,
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Knowledge base not found"}


def test_missing_workspace_and_knowledge_base_return_not_found(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
) -> None:
    caller = create_user(db_session, email="not-found@company.com")
    workspace = create_workspace(db_session, slug="not-found-workspace")
    add_membership(db_session, caller, workspace)

    missing_workspace = client.get(
        f"/api/workspaces/{uuid4()}/knowledge-bases",
        headers=bearer(caller, auth_settings),
    )
    missing_knowledge_base = client.get(
        f"{knowledge_base_collection(workspace)}/{uuid4()}",
        headers=bearer(caller, auth_settings),
    )

    assert missing_workspace.status_code == 404
    assert missing_workspace.json() == {"detail": "Workspace not found"}
    assert missing_knowledge_base.status_code == 404
    assert missing_knowledge_base.json() == {"detail": "Knowledge base not found"}


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"name": ""},
        {"name": None},
        {"status": None},
        {"status": "unknown"},
        {"description": "x" * 5001},
        {"unknown": "value"},
    ],
)
def test_invalid_knowledge_base_update_is_rejected(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    payload: dict[str, object],
) -> None:
    caller = create_user(db_session, email=f"invalid-update-{uuid4()}@company.com")
    workspace = create_workspace(db_session, slug=f"invalid-update-{uuid4()}")
    add_membership(
        db_session,
        caller,
        workspace,
        role=MembershipRole.KNOWLEDGE_ADMIN,
    )
    knowledge_base = create_knowledge_base(db_session, workspace, caller)

    response = client.patch(
        f"{knowledge_base_collection(workspace)}/{knowledge_base.id}",
        headers=bearer(caller, auth_settings),
        json=payload,
    )

    assert response.status_code == 422
    persisted_name = db_session.scalar(
        select(KnowledgeBase.name).where(KnowledgeBase.id == knowledge_base.id)
    )
    assert persisted_name == "Employee Policies"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"name": ""},
        {"name": None},
        {"name": "x" * 256},
        {"name": "Valid", "description": "x" * 5001},
        {"name": "Valid", "status": "active"},
        {"name": "Valid", "unknown": "value"},
    ],
)
def test_invalid_knowledge_base_create_is_rejected(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    payload: dict[str, object],
) -> None:
    caller = create_user(db_session, email=f"invalid-create-{uuid4()}@company.com")
    workspace = create_workspace(db_session, slug=f"invalid-create-{uuid4()}")
    add_membership(
        db_session,
        caller,
        workspace,
        role=MembershipRole.KNOWLEDGE_ADMIN,
    )

    response = client.post(
        knowledge_base_collection(workspace),
        headers=bearer(caller, auth_settings),
        json=payload,
    )

    assert response.status_code == 422
    assert db_session.scalars(
        select(KnowledgeBase).where(KnowledgeBase.workspace_id == workspace.id)
    ).all() == []
