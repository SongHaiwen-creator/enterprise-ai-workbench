from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.models import User
from app.models.enums import UserStatus
from app.security.tokens import InvalidAccessTokenError, decode_access_token
from app.services.exceptions import AuthenticationError, ForbiddenError

bearer_scheme = HTTPBearer(auto_error=False)

DatabaseSession = Annotated[Session, Depends(get_db_session)]
ApplicationSettings = Annotated[Settings, Depends(get_settings)]
BearerCredentials = Annotated[
    HTTPAuthorizationCredentials | None,
    Depends(bearer_scheme),
]


def get_current_user(
    credentials: BearerCredentials,
    session: DatabaseSession,
    settings: ApplicationSettings,
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationError("Could not validate credentials")

    try:
        user_id = decode_access_token(credentials.credentials, settings)
    except InvalidAccessTokenError as error:
        raise AuthenticationError("Could not validate credentials") from error

    user = session.get(User, user_id)
    if user is None:
        raise AuthenticationError("Could not validate credentials")
    if user.status is UserStatus.DISABLED:
        raise ForbiddenError("User account is disabled")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
