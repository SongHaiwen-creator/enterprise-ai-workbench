from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException

from app.api.dependencies.auth import CurrentUser, DatabaseSession
from app.api.dependencies.authorization import AgentAdministratorMembership
from app.api.routes.evaluation import Limit, Offset
from app.schemas.bad_case import (
    BadCaseCreate,
    BadCaseDetail,
    BadCaseList,
    BadCaseUpdate,
    Category,
    HistoryList,
    Origin,
    Status,
)
from app.services import bad_cases as service


class BadCaseRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def safe_handler(request: Request):
            try:
                return await original(request)
            except (RequestValidationError, service.BadCaseValidationError):
                return JSONResponse(status_code=422, content={"detail": "Invalid bad case request"})
            except HTTPException as error:
                if (
                    error.status_code == 400
                    and error.detail == "There was an error parsing the body"
                ):
                    return JSONResponse(
                        status_code=422, content={"detail": "Invalid bad case request"}
                    )
                raise
            except (
                ResponseValidationError,
                ValidationError,
                SQLAlchemyError,
                service.BadCasePersistenceError,
            ):
                return JSONResponse(
                    status_code=500, content={"detail": "Bad case persistence unavailable"}
                )

        return safe_handler


router = APIRouter(
    prefix="/workspaces/{workspace_id}", tags=["bad-cases"], route_class=BadCaseRoute
)


@router.post(
    "/evaluation-runs/{run_id}/cases/{run_case_id}/bad-case",
    response_model=BadCaseDetail,
    status_code=201,
)
def create(
    workspace_id: UUID,
    run_id: UUID,
    run_case_id: UUID,
    payload: BadCaseCreate,
    session: DatabaseSession,
    user: CurrentUser,
    _admin: AgentAdministratorMembership,
):
    return service.create(session, workspace_id, run_id, run_case_id, user.id, payload)


@router.get("/bad-cases", response_model=BadCaseList)
def list_cases(
    workspace_id: UUID,
    session: DatabaseSession,
    user: CurrentUser,
    _admin: AgentAdministratorMembership,
    status: Status | None = None,
    category: Category | None = None,
    origin_kind: Origin | None = None,
    source_run_id: UUID | None = None,
    source_run_case_id: UUID | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
):
    return BadCaseList(
        items=service.list_cases(
            session,
            workspace_id,
            user.id,
            status,
            category,
            origin_kind,
            source_run_id,
            source_run_case_id,
            limit,
            offset,
        ),
        limit=limit,
        offset=offset,
    )


@router.get("/bad-cases/{bad_case_id}", response_model=BadCaseDetail)
def read(
    workspace_id: UUID,
    bad_case_id: UUID,
    session: DatabaseSession,
    user: CurrentUser,
    _admin: AgentAdministratorMembership,
):
    return service.read(session, workspace_id, bad_case_id, user.id)


@router.patch("/bad-cases/{bad_case_id}", response_model=BadCaseDetail)
def update(
    workspace_id: UUID,
    bad_case_id: UUID,
    payload: BadCaseUpdate,
    session: DatabaseSession,
    user: CurrentUser,
    _admin: AgentAdministratorMembership,
):
    return service.update(session, workspace_id, bad_case_id, user.id, payload)


@router.get("/bad-cases/{bad_case_id}/history", response_model=HistoryList)
def history(
    workspace_id: UUID,
    bad_case_id: UUID,
    session: DatabaseSession,
    user: CurrentUser,
    _admin: AgentAdministratorMembership,
    limit: Limit = 50,
    offset: Offset = 0,
):
    return HistoryList(
        items=service.history(session, workspace_id, bad_case_id, user.id, limit, offset),
        limit=limit,
        offset=offset,
    )
