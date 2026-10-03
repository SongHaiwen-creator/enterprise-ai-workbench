from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import Agent, EvaluationCase, EvaluationDataset, KnowledgeBase, Tool
from app.schemas.evaluation import (
    CaseCreate,
    CaseUpdate,
    DatasetCreate,
    DatasetUpdate,
    ToolExpectation,
)
from app.services.authorization_policy import require_scoped_resource
from app.services.exceptions import ConflictError, NotFoundError, ServiceError
from app.services.tool_registry import TOOL_REGISTRY


class EvaluationValidationError(ServiceError):
    """Content-free validation error for merged PATCH or reference mismatch."""


class EvaluationPersistenceError(ServiceError):
    """Content-free persistence failure."""


def _locked(session: Session, statement):
    session.execute(text("SET LOCAL lock_timeout = '5s'"))
    return session.scalar(statement.with_for_update().execution_options(populate_existing=True))


def get_dataset(session: Session, workspace_id: UUID, dataset_id: UUID, *, lock: bool = False):
    query = select(EvaluationDataset).where(
        EvaluationDataset.workspace_id == workspace_id,
        EvaluationDataset.id == dataset_id,
    )
    row = _locked(session, query) if lock else session.scalar(query)
    require_scoped_resource(row is not None, "Evaluation dataset not found")
    return row


def get_case(
    session: Session, workspace_id: UUID, dataset_id: UUID, case_id: UUID, *, lock: bool = False
):
    get_dataset(session, workspace_id, dataset_id)
    query = select(EvaluationCase).where(
        EvaluationCase.workspace_id == workspace_id,
        EvaluationCase.dataset_id == dataset_id,
        EvaluationCase.id == case_id,
    )
    row = _locked(session, query) if lock else session.scalar(query)
    if row is None:
        raise NotFoundError("Evaluation case not found")
    return row


def list_datasets(
    session: Session, workspace_id: UUID, status: str | None, limit: int, offset: int
):
    query = select(EvaluationDataset).where(EvaluationDataset.workspace_id == workspace_id)
    if status is not None:
        query = query.where(EvaluationDataset.status == status)
    return session.scalars(
        query.order_by(EvaluationDataset.created_at.desc(), EvaluationDataset.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()


def list_cases(
    session: Session,
    workspace_id: UUID,
    dataset_id: UUID,
    status: str | None,
    case_type: str | None,
    limit: int,
    offset: int,
):
    get_dataset(session, workspace_id, dataset_id)
    query = select(EvaluationCase).where(
        EvaluationCase.workspace_id == workspace_id,
        EvaluationCase.dataset_id == dataset_id,
    )
    if status is not None:
        query = query.where(EvaluationCase.status == status)
    if case_type is not None:
        query = query.where(EvaluationCase.case_type == case_type)
    return session.scalars(
        query.order_by(EvaluationCase.created_at.desc(), EvaluationCase.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()


def _references(session: Session, workspace_id: UUID, payload: CaseCreate) -> None:
    for column, model in (
        ("agent_id", Agent),
        ("knowledge_base_id", KnowledgeBase),
        ("tool_id", Tool),
    ):
        reference = getattr(payload, column)
        if reference is None:
            continue
        row = session.scalar(
            select(model).where(model.id == reference, model.workspace_id == workspace_id)
        )
        if row is None:
            raise NotFoundError("Evaluation reference not found")
        if column == "tool_id" and isinstance(payload.expected_behavior, ToolExpectation):
            key = payload.expected_behavior.tool_key
            if row.tool_key != key or key not in TOOL_REGISTRY:
                raise EvaluationValidationError("Invalid evaluation request")


def _save(session: Session, row):
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def _write_error(session: Session, error: SQLAlchemyError) -> None:
    session.rollback()
    if isinstance(error, DBAPIError) and getattr(error.orig, "sqlstate", None) == "55P03":
        raise ConflictError("Evaluation resource is busy") from None
    # Never expose SQL, bound input or the original driver exception.
    raise EvaluationPersistenceError("Evaluation persistence unavailable") from None


def create_dataset(session: Session, workspace_id: UUID, creator: UUID, payload: DatasetCreate):
    try:
        return _save(
            session,
            EvaluationDataset(
                workspace_id=workspace_id, created_by=creator, **payload.model_dump()
            ),
        )
    except SQLAlchemyError as error:
        _write_error(session, error)


def update_dataset(session: Session, workspace_id: UUID, dataset_id: UUID, payload: DatasetUpdate):
    try:
        row = get_dataset(session, workspace_id, dataset_id, lock=True)
        for name, value in payload.model_dump(exclude_unset=True).items():
            setattr(row, name, value)
        # Even a repeated status PATCH records its successful update time.
        row.updated_at = session.scalar(select(text("clock_timestamp()")))
        return _save(session, row)
    except SQLAlchemyError as error:
        _write_error(session, error)


def create_case(
    session: Session, workspace_id: UUID, dataset_id: UUID, creator: UUID, payload: CaseCreate
):
    try:
        parent = get_dataset(session, workspace_id, dataset_id, lock=True)
        if parent.status != "active":
            raise ConflictError("Evaluation dataset is disabled")
        _references(session, workspace_id, payload)
        return _save(
            session,
            EvaluationCase(
                workspace_id=workspace_id,
                dataset_id=dataset_id,
                created_by=creator,
                **payload.model_dump(mode="python"),
            ),
        )
    except SQLAlchemyError as error:
        _write_error(session, error)


def update_case(
    session: Session, workspace_id: UUID, dataset_id: UUID, case_id: UUID, payload: CaseUpdate
):
    try:
        row = get_case(session, workspace_id, dataset_id, case_id, lock=True)
        data = {name: getattr(row, name) for name in CaseCreate.model_fields}
        changes = payload.model_dump(exclude_unset=True)
        data.update({key: value for key, value in changes.items() if key != "status"})
        try:
            merged = CaseCreate.model_validate(data)
        except ValidationError:
            raise EvaluationValidationError("Invalid evaluation request") from None
        _references(session, workspace_id, merged)
        for name, value in merged.model_dump().items():
            setattr(row, name, value)
        if "status" in changes:
            row.status = changes["status"]
        row.updated_at = session.scalar(select(text("clock_timestamp()")))
        return _save(session, row)
    except SQLAlchemyError as error:
        _write_error(session, error)
