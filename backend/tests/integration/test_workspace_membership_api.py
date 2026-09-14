from collections.abc import Generator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.main import app
from app.models import User
from app.security.tokens import create_access_token

pytestmark = pytest.mark.integration
JWT_SECRET = "workspace-api-test-secret-that-is-longer-than-thirty-two-bytes"


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

    caller = User(email="api-caller@company.com", name="API Caller")
    db_session.add(caller)
    db_session.commit()

    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[get_settings] = lambda: auth_settings
    try:
        with TestClient(app) as test_client:
            test_client.headers["Authorization"] = (
                f"Bearer {create_access_token(caller.id, auth_settings)}"
            )
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        app.dependency_overrides.pop(get_settings, None)


def create_user(db_session: Session, *, email: str, name: str) -> User:
    user = User(email=email, name=name)
    db_session.add(user)
    db_session.flush()
    return user


def create_workspace(client: TestClient, *, slug: str = "example-company") -> dict[str, str]:
    response = client.post(
        "/api/workspaces",
        json={"name": "Example Company", "slug": slug},
    )
    assert response.status_code == 201
    return response.json()


def test_create_and_get_workspace_normalizes_slug(client: TestClient) -> None:
    created = create_workspace(client, slug=" Example-Company ")

    assert created["name"] == "Example Company"
    assert created["slug"] == "example-company"
    assert created["status"] == "active"
    assert created["created_at"] is not None

    response = client.get(f"/api/workspaces/{created['id']}")

    assert response.status_code == 200
    assert response.json() == created


def test_duplicate_normalized_workspace_slug_returns_conflict(client: TestClient) -> None:
    create_workspace(client)

    response = client.post(
        "/api/workspaces",
        json={"name": "Duplicate", "slug": "EXAMPLE-COMPANY"},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Workspace slug already exists"}


def test_get_unknown_workspace_returns_not_found(client: TestClient) -> None:
    response = client.get(f"/api/workspaces/{uuid4()}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Workspace not found"}


def test_list_members_joins_useful_user_information(
    client: TestClient,
    db_session: Session,
) -> None:
    workspace = create_workspace(client)
    alice = create_user(db_session, email="Alice@Company.com", name="Alice")
    bob = create_user(db_session, email="bob@company.com", name="Bob")

    first = client.post(
        f"/api/workspaces/{workspace['id']}/members",
        json={"user_id": str(bob.id)},
    )
    second = client.post(
        f"/api/workspaces/{workspace['id']}/members",
        json={"user_id": str(alice.id), "role": "knowledge_admin"},
    )
    assert first.status_code == 201
    assert second.status_code == 201

    response = client.get(f"/api/workspaces/{workspace['id']}/members")

    assert response.status_code == 200
    members = response.json()
    caller = db_session.scalar(select(User).where(User.email == "api-caller@company.com"))
    assert caller is not None
    assert len(members) == 3
    assert members == [
        {
            "id": members[0]["id"],
            "user_id": str(caller.id),
            "email": "api-caller@company.com",
            "name": "API Caller",
            "role": "system_admin",
            "status": "active",
            "joined_at": members[0]["joined_at"],
        },
        {
            "id": second.json()["id"],
            "user_id": str(alice.id),
            "email": "alice@company.com",
            "name": "Alice",
            "role": "knowledge_admin",
            "status": "invited",
            "joined_at": None,
        },
        {
            "id": first.json()["id"],
            "user_id": str(bob.id),
            "email": "bob@company.com",
            "name": "Bob",
            "role": "employee",
            "status": "invited",
            "joined_at": None,
        },
    ]
    assert members[0]["joined_at"] is not None


def test_list_members_includes_creator_and_checks_workspace(client: TestClient) -> None:
    workspace = create_workspace(client)

    members = client.get(f"/api/workspaces/{workspace['id']}/members").json()
    assert len(members) == 1
    assert members[0]["email"] == "api-caller@company.com"
    assert members[0]["role"] == "system_admin"
    assert members[0]["status"] == "active"
    assert members[0]["joined_at"] is not None

    response = client.get(f"/api/workspaces/{uuid4()}/members")
    assert response.status_code == 404
    assert response.json() == {"detail": "Workspace not found"}


def test_create_membership_uses_defaults(client: TestClient, db_session: Session) -> None:
    workspace = create_workspace(client)
    user = create_user(db_session, email="member@company.com", name="Member")

    response = client.post(
        f"/api/workspaces/{workspace['id']}/members",
        json={"user_id": str(user.id)},
    )

    assert response.status_code == 201
    assert response.json() == {
        "id": response.json()["id"],
        "user_id": str(user.id),
        "workspace_id": workspace["id"],
        "role": "employee",
        "status": "invited",
        "joined_at": None,
    }


def test_create_membership_rejects_unknown_resources(
    client: TestClient,
    db_session: Session,
) -> None:
    workspace = create_workspace(client)
    user = create_user(db_session, email="member@company.com", name="Member")

    unknown_user = client.post(
        f"/api/workspaces/{workspace['id']}/members",
        json={"user_id": str(uuid4())},
    )
    unknown_workspace = client.post(
        f"/api/workspaces/{uuid4()}/members",
        json={"user_id": str(user.id)},
    )

    assert unknown_user.status_code == 404
    assert unknown_user.json() == {"detail": "User not found"}
    assert unknown_workspace.status_code == 404
    assert unknown_workspace.json() == {"detail": "Workspace not found"}


def test_duplicate_membership_returns_conflict(client: TestClient, db_session: Session) -> None:
    workspace = create_workspace(client)
    user = create_user(db_session, email="member@company.com", name="Member")
    endpoint = f"/api/workspaces/{workspace['id']}/members"

    assert client.post(endpoint, json={"user_id": str(user.id)}).status_code == 201
    response = client.post(endpoint, json={"user_id": str(user.id)})

    assert response.status_code == 409
    assert response.json() == {"detail": "User is already a member of this workspace"}


def test_invalid_membership_role_is_rejected(client: TestClient, db_session: Session) -> None:
    workspace = create_workspace(client)
    user = create_user(db_session, email="member@company.com", name="Member")

    response = client.post(
        f"/api/workspaces/{workspace['id']}/members",
        json={"user_id": str(user.id), "role": "owner"},
    )

    assert response.status_code == 422


def test_update_membership_role_and_activation(
    client: TestClient,
    db_session: Session,
) -> None:
    workspace = create_workspace(client)
    user = create_user(db_session, email="member@company.com", name="Member")
    created = client.post(
        f"/api/workspaces/{workspace['id']}/members",
        json={"user_id": str(user.id)},
    ).json()
    endpoint = f"/api/workspaces/{workspace['id']}/members/{created['id']}"

    response = client.patch(
        endpoint,
        json={"role": "system_admin", "status": "active"},
    )

    assert response.status_code == 200
    assert response.json()["role"] == "system_admin"
    assert response.json()["status"] == "active"
    assert response.json()["joined_at"] is not None


@pytest.mark.parametrize("payload", [{}, {"status": "unknown"}, {"role": None}])
def test_invalid_membership_update_is_rejected(
    client: TestClient,
    db_session: Session,
    payload: dict[str, object],
) -> None:
    workspace = create_workspace(client)
    user = create_user(db_session, email="member@company.com", name="Member")
    membership = client.post(
        f"/api/workspaces/{workspace['id']}/members",
        json={"user_id": str(user.id)},
    ).json()

    response = client.patch(
        f"/api/workspaces/{workspace['id']}/members/{membership['id']}",
        json=payload,
    )

    assert response.status_code == 422


def test_update_membership_is_scoped_to_workspace(
    client: TestClient,
    db_session: Session,
) -> None:
    first_workspace = create_workspace(client, slug="first-workspace")
    second_workspace = create_workspace(client, slug="second-workspace")
    user = create_user(db_session, email="member@company.com", name="Member")
    membership = client.post(
        f"/api/workspaces/{first_workspace['id']}/members",
        json={"user_id": str(user.id)},
    ).json()

    response = client.patch(
        f"/api/workspaces/{second_workspace['id']}/members/{membership['id']}",
        json={"role": "agent_admin"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Membership not found"}


def test_update_unknown_membership_returns_not_found(client: TestClient) -> None:
    workspace = create_workspace(client)

    response = client.patch(
        f"/api/workspaces/{workspace['id']}/members/{uuid4()}",
        json={"status": "disabled"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Membership not found"}
