from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.main import app
from app.models import User
from app.models.enums import UserStatus
from app.security.passwords import hash_password
from app.security.tokens import create_access_token

pytestmark = pytest.mark.integration

JWT_SECRET = "integration-test-secret-that-is-longer-than-thirty-two-bytes"
PASSWORD = "correct horse battery staple"


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
    db_session: Session,
    *,
    email: str = "alice@company.com",
    password: str | None = PASSWORD,
    status: UserStatus = UserStatus.ACTIVE,
) -> User:
    user = User(
        email=email,
        name="Alice",
        password_hash=hash_password(password) if password is not None else None,
        status=status,
    )
    db_session.add(user)
    db_session.commit()
    return user


def login(client: TestClient, *, email: str = "alice@company.com", password: str = PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_login_accepts_case_insensitive_email_and_returns_access_token(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
) -> None:
    user = create_user(db_session)

    response = login(client, email=" Alice@Company.com ")

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    assert response.json()["expires_in"] == 1800
    me_response = client.get(
        "/api/auth/me",
        headers=bearer(response.json()["access_token"]),
    )
    assert me_response.status_code == 200
    assert me_response.json() == {
        "id": str(user.id),
        "email": "alice@company.com",
        "name": "Alice",
        "status": "active",
    }
    assert "password" not in me_response.text
    assert "password_hash" not in me_response.text
    assert auth_settings.jwt_secret_key.get_secret_value() not in response.text


def test_wrong_password_and_unknown_email_are_indistinguishable(
    client: TestClient,
    db_session: Session,
) -> None:
    create_user(db_session)

    wrong_password = login(client, password="wrong password")
    unknown_email = login(client, email="unknown@company.com")

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json() == {
        "detail": "Incorrect email or password"
    }
    assert wrong_password.headers["www-authenticate"] == "Bearer"
    assert unknown_email.headers["www-authenticate"] == "Bearer"


def test_user_without_password_hash_cannot_authenticate(
    client: TestClient,
    db_session: Session,
) -> None:
    create_user(db_session, password=None)

    response = login(client)

    assert response.status_code == 401
    assert response.json() == {"detail": "Incorrect email or password"}


def test_disabled_user_cannot_login(client: TestClient, db_session: Session) -> None:
    create_user(db_session, status=UserStatus.DISABLED)

    response = login(client)

    assert response.status_code == 403
    assert response.json() == {"detail": "User account is disabled"}
    assert "access_token" not in response.text


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"email": "alice@company.com", "password": ""},
        {"email": "alice@company.com", "password": PASSWORD, "role": "admin"},
    ],
)
def test_login_rejects_invalid_request_body(
    client: TestClient,
    payload: dict[str, object],
) -> None:
    response = client.post("/api/auth/login", json=payload)

    assert response.status_code == 422
    assert PASSWORD not in response.text


def test_me_requires_a_bearer_token(client: TestClient) -> None:
    response = client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}
    assert response.headers["www-authenticate"] == "Bearer"


def test_me_rejects_malformed_invalid_signature_and_expired_tokens(
    client: TestClient,
    auth_settings: Settings,
) -> None:
    tokens = [
        "not-a-jwt",
        create_access_token(
            uuid4(),
            Settings(
                database_url="postgresql+psycopg://unused/unused",
                jwt_secret_key="different-test-secret-that-is-at-least-thirty-two-bytes",
                _env_file=None,
            ),
        ),
        create_access_token(
            uuid4(),
            auth_settings,
            issued_at=datetime.now(UTC) - timedelta(minutes=31),
        ),
    ]

    for token in tokens:
        response = client.get("/api/auth/me", headers=bearer(token))
        assert response.status_code == 401
        assert response.json() == {"detail": "Could not validate credentials"}


def test_me_rejects_deleted_user(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
) -> None:
    user = create_user(db_session)
    token = create_access_token(user.id, auth_settings)
    db_session.delete(user)
    db_session.commit()

    response = client.get("/api/auth/me", headers=bearer(token))

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}


def test_me_rejects_user_disabled_after_token_issuance(
    client: TestClient,
    db_session: Session,
    auth_settings: Settings,
) -> None:
    user = create_user(db_session)
    token = create_access_token(user.id, auth_settings)
    user.status = UserStatus.DISABLED
    db_session.commit()

    response = client.get("/api/auth/me", headers=bearer(token))

    assert response.status_code == 403
    assert response.json() == {"detail": "User account is disabled"}
