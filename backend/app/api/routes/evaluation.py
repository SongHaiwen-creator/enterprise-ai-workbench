from collections.abc import Awaitable, Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy.exc import DBAPIError

from app.api.dependencies.auth import CurrentUser, DatabaseSession
from app.api.dependencies.authorization import AgentAdministratorMembership
from app.schemas.common import ErrorResponse
from app.schemas.evaluation import (
    CaseCreate,
    CaseListResponse,
    CaseResponse,
    CaseSummary,
    CaseType,
    CaseUpdate,
    DatasetCreate,
    DatasetListResponse,
    DatasetResponse,
    DatasetUpdate,
    Status,
)
from app.services import evaluation as service


class EvaluationRoute(APIRoute):
    """Sanitize at the FastAPI boundary, including pre-handler validation.

    Only this router uses the wrapper; existing validation contracts are untouched.
    Do not inspect, log or re-raise body-bearing validation/persistence exceptions.
    """

    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        original = super().get_route_handler()

        async def safe_handler(request: Request) -> Response:
            try:
                return await original(request)
            except (RequestValidationError, service.EvaluationValidationError):
                return JSONResponse(
                    status_code=422, content={"detail": "Invalid evaluation request"}
                )
            except (ResponseValidationError, DBAPIError, service.EvaluationPersistenceError):
                return JSONResponse(
                    status_code=500, content={"detail": "Evaluation persistence unavailable"}
                )

        return safe_handler


router = APIRouter(
    prefix="/workspaces/{workspace_id}/evaluation-datasets",
    tags=["evaluation-datasets"],
    route_class=EvaluationRoute,
    responses={code: {"model": ErrorResponse} for code in (401, 403, 404, 409, 422, 500)},
)
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


@router.post("", response_model=DatasetResponse, status_code=201)
def create_dataset(
    workspace_id: UUID,
    payload: DatasetCreate,
    session: DatabaseSession,
    current_user: CurrentUser,
    _admin: AgentAdministratorMembership,
):
    return service.create_dataset(session, workspace_id, current_user.id, payload)


@router.get("", response_model=DatasetListResponse)
def list_datasets(
    workspace_id: UUID,
    session: DatabaseSession,
    _admin: AgentAdministratorMembership,
    status: Status | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
):
    rows = service.list_datasets(session, workspace_id, status, limit, offset)
    return DatasetListResponse(
        items=[DatasetResponse.model_validate(row) for row in rows], limit=limit, offset=offset
    )


@router.get("/{dataset_id}", response_model=DatasetResponse)
def get_dataset(
    workspace_id: UUID,
    dataset_id: UUID,
    session: DatabaseSession,
    _admin: AgentAdministratorMembership,
):
    return service.get_dataset(session, workspace_id, dataset_id)


@router.patch("/{dataset_id}", response_model=DatasetResponse)
def update_dataset(
    workspace_id: UUID,
    dataset_id: UUID,
    payload: DatasetUpdate,
    session: DatabaseSession,
    _admin: AgentAdministratorMembership,
):
    return service.update_dataset(session, workspace_id, dataset_id, payload)


@router.post("/{dataset_id}/cases", response_model=CaseResponse, status_code=201)
def create_case(
    workspace_id: UUID,
    dataset_id: UUID,
    payload: CaseCreate,
    session: DatabaseSession,
    current_user: CurrentUser,
    _admin: AgentAdministratorMembership,
):
    return service.create_case(session, workspace_id, dataset_id, current_user.id, payload)


@router.get("/{dataset_id}/cases", response_model=CaseListResponse)
def list_cases(
    workspace_id: UUID,
    dataset_id: UUID,
    session: DatabaseSession,
    _admin: AgentAdministratorMembership,
    status: Status | None = None,
    case_type: CaseType | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
):
    rows = service.list_cases(session, workspace_id, dataset_id, status, case_type, limit, offset)
    return CaseListResponse(
        items=[CaseSummary.model_validate(row) for row in rows], limit=limit, offset=offset
    )


@router.get("/{dataset_id}/cases/{case_id}", response_model=CaseResponse)
def get_case(
    workspace_id: UUID,
    dataset_id: UUID,
    case_id: UUID,
    session: DatabaseSession,
    _admin: AgentAdministratorMembership,
):
    return service.get_case(session, workspace_id, dataset_id, case_id)


@router.patch("/{dataset_id}/cases/{case_id}", response_model=CaseResponse)
def update_case(
    workspace_id: UUID,
    dataset_id: UUID,
    case_id: UUID,
    payload: CaseUpdate,
    session: DatabaseSession,
    _admin: AgentAdministratorMembership,
):
    return service.update_case(session, workspace_id, dataset_id, case_id, payload)
