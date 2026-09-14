from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt

from app.core.config import Settings

ALLOWED_JWT_ALGORITHM = "HS256"
REQUIRED_JWT_CLAIMS = ["sub", "iat", "exp"]


class InvalidAccessTokenError(Exception):
    """An access token failed validation."""


def create_access_token(
    user_id: UUID,
    settings: Settings,
    *,
    issued_at: datetime | None = None,
) -> str:
    token_issued_at = issued_at or datetime.now(UTC)
    expires_at = token_issued_at + timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode(
        {
            "sub": str(user_id),
            "iat": token_issued_at,
            "exp": expires_at,
        },
        settings.jwt_secret_key.get_secret_value(),
        algorithm=ALLOWED_JWT_ALGORITHM,
    )


def decode_access_token(token: str, settings: Settings) -> UUID:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key.get_secret_value(),
            algorithms=[ALLOWED_JWT_ALGORITHM],
            options={
                "require": REQUIRED_JWT_CLAIMS,
                "verify_signature": True,
                "verify_exp": True,
                "verify_iat": True,
            },
        )
        subject = payload["sub"]
        if not isinstance(subject, str):
            raise InvalidAccessTokenError
        return UUID(subject)
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError) as error:
        raise InvalidAccessTokenError from error
