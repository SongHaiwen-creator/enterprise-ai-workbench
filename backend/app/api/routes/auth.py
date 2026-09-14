from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies.auth import CurrentUser
from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.schemas.auth import CurrentUserResponse, LoginRequest, LoginResponse
from app.schemas.common import ErrorResponse
from app.security.tokens import create_access_token
from app.services.auth import authenticate_user

router = APIRouter(prefix="/auth", tags=["authentication"])
DatabaseSession = Annotated[Session, Depends(get_db_session)]
ApplicationSettings = Annotated[Settings, Depends(get_settings)]


@router.post(
    "/login",
    response_model=LoginResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
    },
)
def login(
    payload: LoginRequest,
    session: DatabaseSession,
    settings: ApplicationSettings,
) -> LoginResponse:
    user = authenticate_user(session, payload)
    return LoginResponse(access_token=create_access_token(user.id, settings))


@router.get(
    "/me",
    response_model=CurrentUserResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
    },
)
def get_me(current_user: CurrentUser) -> CurrentUserResponse:
    return CurrentUserResponse.model_validate(current_user)
