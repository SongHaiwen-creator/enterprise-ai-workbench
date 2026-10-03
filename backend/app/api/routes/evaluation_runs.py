from collections.abc import Generator
from functools import lru_cache
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.dependencies.auth import ApplicationSettings, CurrentUser
from app.api.dependencies.authorization import AgentAdministratorMembership
from app.api.routes.evaluation import EvaluationRoute, Limit, Offset
from app.core.config import get_settings
from app.schemas.evaluation import CaseType
from app.schemas.evaluation_run import (
    CaseResult,
    RunCaseDetail,
    RunCaseList,
    RunCreate,
    RunDetail,
    RunList,
    RunStatus,
    RunSummary,
)
from app.services import evaluation_runs as service
from app.services.evaluation_execution import Providers


@lru_cache
def evaluation_engine():
    # Separate bounded pool; no changes to ordinary request Session semantics.
    return create_engine(
        get_settings().database_url,
        pool_timeout=5,
        connect_args={"connect_timeout": 5},
        hide_parameters=True,
    )


def evaluation_session() -> Generator[Session, None, None]:
    with Session(evaluation_engine(), autoflush=False, expire_on_commit=False) as session:
        try:
            yield session
        finally:
            session.rollback()


def evaluation_providers() -> Providers:
    return Providers()


EvaluationSession = Annotated[Session, Depends(evaluation_session)]
EvaluationProviders = Annotated[Providers, Depends(evaluation_providers)]
router = APIRouter(
    prefix="/workspaces/{workspace_id}", tags=["evaluation-runs"], route_class=EvaluationRoute
)


@router.post("/evaluation-datasets/{dataset_id}/runs", response_model=RunSummary, status_code=201)
def create_run(
    workspace_id: UUID,
    dataset_id: UUID,
    payload: RunCreate,
    session: EvaluationSession,
    user: CurrentUser,
    _admin: AgentAdministratorMembership,
    settings: ApplicationSettings,
    providers: EvaluationProviders,
):
    return service.create_run(
        session, workspace_id, dataset_id, user.id, payload, settings, providers
    )


@router.get("/evaluation-runs", response_model=RunList)
def list_runs(
    workspace_id: UUID,
    session: EvaluationSession,
    user: CurrentUser,
    _admin: AgentAdministratorMembership,
    dataset_id: UUID | None = None,
    agent_id: UUID | None = None,
    status: RunStatus | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
):
    return RunList(
        items=service.list_runs(
            session, workspace_id, user.id, dataset_id, agent_id, status, limit, offset
        ),
        limit=limit,
        offset=offset,
    )


@router.get("/evaluation-runs/{run_id}", response_model=RunDetail)
def read_run(
    workspace_id: UUID,
    run_id: UUID,
    session: EvaluationSession,
    user: CurrentUser,
    _admin: AgentAdministratorMembership,
):
    return service.read_run(session, workspace_id, run_id, user.id)


@router.get("/evaluation-runs/{run_id}/cases", response_model=RunCaseList)
def list_cases(
    workspace_id: UUID,
    run_id: UUID,
    session: EvaluationSession,
    user: CurrentUser,
    _admin: AgentAdministratorMembership,
    case_type: CaseType | None = None,
    result: CaseResult | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
):
    return RunCaseList(
        items=service.list_run_cases(
            session, workspace_id, run_id, user.id, case_type, result, limit, offset
        ),
        limit=limit,
        offset=offset,
    )


@router.get("/evaluation-runs/{run_id}/cases/{run_case_id}", response_model=RunCaseDetail)
def read_case(
    workspace_id: UUID,
    run_id: UUID,
    run_case_id: UUID,
    session: EvaluationSession,
    user: CurrentUser,
    _admin: AgentAdministratorMembership,
):
    return service.read_run_case(session, workspace_id, run_id, run_case_id, user.id)
