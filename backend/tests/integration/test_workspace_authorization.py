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
from app.models import Membership, User, Workspace
from app.models.enums import (
    MembershipRole,
    MembershipStatus,
    UserStatus,
    WorkspaceStatus,
)
from app.security.tokens import create_access_token

pytestmark = pytest.mark.integration
JWT_SECRET = "workspace-authorization-secret-longer-than-thirty-two-bytes"


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


def create_user(
    session: Session,
    *,
    email: str,
    status: UserStatus = UserStatus.ACTIVE,
) -> User:
    user = User(email=email, name=email.split("@", maxsplit=1)[0].title(), status=status)
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


def bearer(user: User, settings: Settings) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, settings)}"}


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("post", "/api/workspaces", {"name": "Example", "slug": "example"}),
        ("get", "/api/workspaces", None),
        ("get", f"/api/workspaces/{uuid4()}", None),
        ("get", f"/api/workspaces/{uuid4()}/members", None),
        (
            "post",
            f"/api/workspaces/{uuid4()}/members",
            {"user_id": str(uuid4())},
        ),
        (
            "patch",
            f"/api/workspaces/{uuid4()}/members/{uuid4()}",
            {"role": "employee"},
        ),
    ],
)
def test_workspace_routes_require_authentication(
    client: TestClient,
    method: str,
    path: str,
    body: dict[str, str] | None,
) -> None:
    response = client.request(method, path, json=body)

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}
    assert response.headers["www-authenticate"] == "Bearer"


def test_workspace_list_rejects_invalid_token(client: TestClient) -> None:
    response = client.get(
        "/api/workspaces",
        headers={"Authorization": "Bearer not-a-jwt"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}


def test_workspace_creation_atomically_adds_creator_as_active_system_admin(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
) -> None:
    creator = create_user(db_session, email="creator@company.com")

    response = client.post(
        "/api/workspaces",
        headers=bearer(creator, auth_settings),
        json={"name": "Example Company", "slug": "example-company"},
    )

    assert response.status_code == 201
    workspace_id = UUID(response.json()["id"])
    membership = db_session.scalar(
        select(Membership).where(
            Membership.workspace_id == workspace_id,
            Membership.user_id == creator.id,
        )
    )
    assert membership is not None
    assert membership.role is MembershipRole.SYSTEM_ADMIN
    assert membership.status is MembershipStatus.ACTIVE
    assert membership.joined_at is not None


def test_duplicate_workspace_does_not_create_orphan_creator_membership(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
) -> None:
    first_creator = create_user(db_session, email="first@company.com")
    second_creator = create_user(db_session, email="second@company.com")
    payload = {"name": "Example Company", "slug": "example-company"}
    assert (
        client.post(
            "/api/workspaces",
            headers=bearer(first_creator, auth_settings),
            json=payload,
        ).status_code
        == 201
    )

    response = client.post(
        "/api/workspaces",
        headers=bearer(second_creator, auth_settings),
        json=payload,
    )

    assert response.status_code == 409
    second_memberships = db_session.scalars(
        select(Membership).where(Membership.user_id == second_creator.id)
    ).all()
    assert second_memberships == []


def test_workspace_list_returns_only_active_accessible_workspaces(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
) -> None:
    caller = create_user(db_session, email="caller@company.com")
    other_user = create_user(db_session, email="other@company.com")
    accessible = create_workspace(db_session, slug="accessible")
    invited = create_workspace(db_session, slug="invited")
    disabled_workspace = create_workspace(
        db_session,
        slug="disabled-workspace",
        status=WorkspaceStatus.DISABLED,
    )
    other_workspace = create_workspace(db_session, slug="other-workspace")
    active_membership = add_membership(
        db_session,
        caller,
        accessible,
        role=MembershipRole.KNOWLEDGE_ADMIN,
    )
    add_membership(db_session, caller, invited, status=MembershipStatus.INVITED)
    add_membership(db_session, caller, disabled_workspace)
    add_membership(db_session, other_user, other_workspace)

    response = client.get("/api/workspaces", headers=bearer(caller, auth_settings))

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": str(accessible.id),
            "name": accessible.name,
            "slug": accessible.slug,
            "status": "active",
            "role": "knowledge_admin",
            "joined_at": active_membership.joined_at.isoformat().replace("+00:00", "Z"),
        }
    ]


def test_workspace_list_is_empty_without_active_memberships(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
) -> None:
    caller = create_user(db_session, email="caller@company.com")

    response = client.get("/api/workspaces", headers=bearer(caller, auth_settings))

    assert response.status_code == 200
    assert response.json() == []


def test_active_member_can_get_workspace(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
) -> None:
    caller = create_user(db_session, email="caller@company.com")
    workspace = create_workspace(db_session, slug="example")
    add_membership(db_session, caller, workspace)

    response = client.get(
        f"/api/workspaces/{workspace.id}",
        headers=bearer(caller, auth_settings),
    )

    assert response.status_code == 200
    assert response.json()["id"] == str(workspace.id)


@pytest.mark.parametrize(
    "membership_status",
    [None, MembershipStatus.INVITED, MembershipStatus.DISABLED],
)
def test_workspace_access_requires_active_membership(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    membership_status: MembershipStatus | None,
) -> None:
    caller = create_user(db_session, email="caller@company.com")
    workspace = create_workspace(db_session, slug="example")
    if membership_status is not None:
        add_membership(db_session, caller, workspace, status=membership_status)

    response = client.get(
        f"/api/workspaces/{workspace.id}",
        headers=bearer(caller, auth_settings),
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Not authorized for this workspace"}


def test_disabled_workspace_is_forbidden_to_active_member(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
) -> None:
    caller = create_user(db_session, email="caller@company.com")
    workspace = create_workspace(
        db_session,
        slug="disabled-workspace",
        status=WorkspaceStatus.DISABLED,
    )
    add_membership(db_session, caller, workspace)

    response = client.get(
        f"/api/workspaces/{workspace.id}",
        headers=bearer(caller, auth_settings),
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Not authorized for this workspace"}


@pytest.mark.parametrize(
    "role",
    [
        MembershipRole.EMPLOYEE,
        MembershipRole.KNOWLEDGE_ADMIN,
        MembershipRole.AGENT_ADMIN,
    ],
)
@pytest.mark.parametrize(
    ("method", "suffix", "body"),
    [
        ("get", "/members", None),
        ("post", "/members", {"user_id": str(uuid4())}),
        ("patch", f"/members/{uuid4()}", {"role": "employee"}),
    ],
)
def test_member_management_requires_system_admin_role(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
    role: MembershipRole,
    method: str,
    suffix: str,
    body: dict[str, str] | None,
) -> None:
    caller = create_user(db_session, email="caller@company.com")
    workspace = create_workspace(db_session, slug="example")
    add_membership(db_session, caller, workspace, role=role)

    response = client.request(
        method,
        f"/api/workspaces/{workspace.id}{suffix}",
        headers=bearer(caller, auth_settings),
        json=body,
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "System administrator role required"}


def test_role_is_scoped_to_each_workspace(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
) -> None:
    caller = create_user(db_session, email="caller@company.com")
    administered = create_workspace(db_session, slug="administered")
    not_administered = create_workspace(db_session, slug="not-administered")
    add_membership(
        db_session,
        caller,
        administered,
        role=MembershipRole.SYSTEM_ADMIN,
    )
    add_membership(db_session, caller, not_administered, role=MembershipRole.EMPLOYEE)

    allowed = client.get(
        f"/api/workspaces/{administered.id}/members",
        headers=bearer(caller, auth_settings),
    )
    denied = client.get(
        f"/api/workspaces/{not_administered.id}/members",
        headers=bearer(caller, auth_settings),
    )

    assert allowed.status_code == 200
    assert denied.status_code == 403
    assert denied.json() == {"detail": "System administrator role required"}


def test_authenticated_unknown_workspace_returns_not_found(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
) -> None:
    caller = create_user(db_session, email="caller@company.com")

    response = client.get(
        f"/api/workspaces/{uuid4()}",
        headers=bearer(caller, auth_settings),
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Workspace not found"}


def test_self_demotion_takes_effect_on_next_request(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
) -> None:
    caller = create_user(db_session, email="caller@company.com")
    workspace = create_workspace(db_session, slug="example")
    membership = add_membership(
        db_session,
        caller,
        workspace,
        role=MembershipRole.SYSTEM_ADMIN,
    )
    endpoint = f"/api/workspaces/{workspace.id}/members/{membership.id}"

    demotion = client.patch(
        endpoint,
        headers=bearer(caller, auth_settings),
        json={"role": "employee"},
    )
    next_request = client.get(
        f"/api/workspaces/{workspace.id}/members",
        headers=bearer(caller, auth_settings),
    )

    assert demotion.status_code == 200
    assert demotion.json()["role"] == "employee"
    assert next_request.status_code == 403
    assert next_request.json() == {"detail": "System administrator role required"}
