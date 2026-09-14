import secrets

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import User
from app.models.enums import UserStatus
from app.schemas.auth import LoginRequest
from app.security.passwords import hash_password, verify_password
from app.services.exceptions import AuthenticationError, ForbiddenError

DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(32))


def authenticate_user(session: Session, payload: LoginRequest) -> User:
    user = session.scalar(select(User).where(func.lower(User.email) == payload.email))
    password_hash = user.password_hash if user is not None else None
    password_is_valid = verify_password(
        payload.password.get_secret_value(),
        password_hash or DUMMY_PASSWORD_HASH,
    )

    if user is None or password_hash is None or not password_is_valid:
        raise AuthenticationError("Incorrect email or password")
    if user.status is UserStatus.DISABLED:
        raise ForbiddenError("User account is disabled")
    return user
