from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest

from app.core.config import Settings
from app.security.tokens import (
    ALLOWED_JWT_ALGORITHM,
    InvalidAccessTokenError,
    create_access_token,
    decode_access_token,
)

JWT_SECRET = "test-only-secret-that-is-longer-than-thirty-two-bytes"


def make_settings(*, secret: str = JWT_SECRET) -> Settings:
    return Settings(
        database_url="postgresql+psycopg://unused/unused",
        jwt_secret_key=secret,
        _env_file=None,
    )


def test_access_token_contains_required_minimal_claims() -> None:
    settings = make_settings()
    user_id = uuid4()
    issued_at = datetime.now(UTC).replace(microsecond=0)

    token = create_access_token(user_id, settings, issued_at=issued_at)
    payload = jwt.decode(
        token,
        JWT_SECRET,
        algorithms=[ALLOWED_JWT_ALGORITHM],
    )

    assert set(payload) == {"sub", "iat", "exp"}
    assert payload["sub"] == str(user_id)
    assert payload["iat"] == int(issued_at.timestamp())
    assert payload["exp"] - payload["iat"] == 1800
    assert decode_access_token(token, settings) == user_id


@pytest.mark.parametrize(
    "token_factory",
    [
        lambda settings: "not-a-jwt",
        lambda settings: create_access_token(uuid4(), make_settings(secret="x" * 32)),
        lambda settings: create_access_token(
            uuid4(),
            settings,
            issued_at=datetime.now(UTC) - timedelta(minutes=31),
        ),
        lambda settings: jwt.encode(
            {"sub": str(uuid4()), "iat": datetime.now(UTC)},
            JWT_SECRET,
            algorithm=ALLOWED_JWT_ALGORITHM,
        ),
        lambda settings: jwt.encode(
            {
                "sub": "not-a-uuid",
                "iat": datetime.now(UTC),
                "exp": datetime.now(UTC) + timedelta(minutes=30),
            },
            JWT_SECRET,
            algorithm=ALLOWED_JWT_ALGORITHM,
        ),
        lambda settings: jwt.encode(
            {
                "sub": str(uuid4()),
                "iat": datetime.now(UTC),
                "exp": datetime.now(UTC) + timedelta(minutes=30),
            },
            JWT_SECRET,
            algorithm="HS384",
        ),
    ],
    ids=[
        "malformed",
        "invalid-signature",
        "expired",
        "missing-required-claim",
        "invalid-subject",
        "disallowed-algorithm",
    ],
)
def test_invalid_access_tokens_are_rejected(token_factory: object) -> None:
    settings = make_settings()
    token = token_factory(settings)  # type: ignore[operator]

    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(token, settings)
