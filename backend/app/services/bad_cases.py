"""Manual issue records; never run or reconcile evaluation or dispatch providers."""

from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError, SQLAlchemyError

from app.models import BadCase, BadCaseHistory, EvaluationRun, EvaluationRunCase
from app.schemas.bad_case import (
    HUMAN_FIELDS,
    BadCaseDetail,
    BadCaseSummary,
    HistoryItem,
    HumanValues,
)
from app.services.evaluation_runs import case_summary, current_authority
from app.services.exceptions import ConflictError, NotFoundError, ServiceError

ORIGINS = {"passed": "manual_review", "failed": "behavior_failure", "error": "execution_error"}
TRANSITIONS = {
    "open": {"investigating", "resolved", "dismissed"},
    "investigating": {"open", "resolved", "dismissed"},
    "resolved": {"open"},
    "dismissed": {"open"},
}


class BadCaseValidationError(ServiceError):
    pass


class BadCasePersistenceError(ServiceError):
    pass


def scoped(session, model, workspace_id, object_id):
    row = session.scalar(
        select(model)
        .where(model.workspace_id == workspace_id, model.id == object_id)
        .execution_options(populate_existing=True)
    )
    if row is None:
        raise NotFoundError("Bad case resource not found")
    return row


def source(session, workspace_id, run_id, run_case_id):
    run = scoped(session, EvaluationRun, workspace_id, run_id)
    case = scoped(session, EvaluationRunCase, workspace_id, run_case_id)
    if case.run_id != run.id:
        raise NotFoundError("Bad case resource not found")
    return run, case


def query(workspace_id):
    return (
        select(BadCase, EvaluationRunCase, EvaluationRun)
        .join(
            EvaluationRunCase,
            (BadCase.source_run_case_id == EvaluationRunCase.id)
            & (BadCase.workspace_id == EvaluationRunCase.workspace_id),
        )
        .join(
            EvaluationRun,
            (EvaluationRunCase.run_id == EvaluationRun.id)
            & (EvaluationRunCase.workspace_id == EvaluationRun.workspace_id),
        )
        .where(
            BadCase.workspace_id == workspace_id,
            EvaluationRunCase.workspace_id == workspace_id,
            EvaluationRun.workspace_id == workspace_id,
        )
        .execution_options(populate_existing=True)
    )


def serialize(row, case, run, detail=False):
    derived = {
        "source_run_id": run.id,
        "source_case_id": case.case_id,
        "dataset_id": run.dataset_id,
        "agent_id": run.agent_id,
        "source_result": case.result,
        "source_case_type": case.case_type,
    }
    values = {key: getattr(row, key) for key in BadCaseSummary.model_fields if key not in derived}
    values.update(derived)
    if detail:
        values.update({key: getattr(row, key) for key in HUMAN_FIELDS if key not in values})
        values["source_evidence"] = case_summary(case, detail=True)
    return (BadCaseDetail if detail else BadCaseSummary).model_validate(values)


def read(session, workspace_id, bad_case_id, user_id):
    current_authority(session, workspace_id, user_id)
    rows = session.execute(query(workspace_id).where(BadCase.id == bad_case_id)).one_or_none()
    if rows is None:
        raise NotFoundError("Bad case resource not found")
    response = serialize(*rows, detail=True)
    current_authority(session, workspace_id, user_id)
    return response


def list_cases(
    session,
    workspace_id,
    user_id,
    status,
    category,
    origin_kind,
    source_run_id,
    source_run_case_id,
    limit,
    offset,
):
    current_authority(session, workspace_id, user_id)
    statement = query(workspace_id)
    if source_run_id:
        scoped(session, EvaluationRun, workspace_id, source_run_id)
        statement = statement.where(EvaluationRun.id == source_run_id)
    if source_run_case_id:
        scoped(session, EvaluationRunCase, workspace_id, source_run_case_id)
        statement = statement.where(EvaluationRunCase.id == source_run_case_id)
    for field, value in (("status", status), ("category", category), ("origin_kind", origin_kind)):
        if value is not None:
            statement = statement.where(getattr(BadCase, field) == value)
    rows = session.execute(
        statement.order_by(BadCase.created_at.desc(), BadCase.id.desc()).limit(limit).offset(offset)
    ).all()
    response = [serialize(*row) for row in rows]
    current_authority(session, workspace_id, user_id)
    return response


def history(session, workspace_id, bad_case_id, user_id, limit, offset):
    current_authority(session, workspace_id, user_id)
    scoped(session, BadCase, workspace_id, bad_case_id)
    rows = session.scalars(
        select(BadCaseHistory)
        .where(
            BadCaseHistory.workspace_id == workspace_id, BadCaseHistory.bad_case_id == bad_case_id
        )
        .order_by(BadCaseHistory.revision)
        .limit(limit)
        .offset(offset)
    ).all()
    response = [HistoryItem.model_validate(row) for row in rows]
    current_authority(session, workspace_id, user_id)
    return response


def write_history(session, row, actor, before, after, reason=None):
    entry = BadCaseHistory(
        workspace_id=row.workspace_id,
        bad_case_id=row.id,
        actor_id=actor,
        revision=row.revision,
        event="created" if before is None else "updated",
        change_reason=reason,
        before_values=before,
        after_values=after,
    )
    session.add(entry)
    session.flush()
    HistoryItem.model_validate(entry)


def write_error(error):
    if isinstance(error, DBAPIError):
        code = getattr(error.orig, "sqlstate", None)
        if code == "55P03":
            raise ConflictError("Bad case resource is busy") from None
        if (
            isinstance(error, IntegrityError)
            and code == "23505"
            and (
                getattr(getattr(error.orig, "diag", None), "constraint_name", None)
                == "uq_bad_cases_source"
            )
        ):
            raise ConflictError("Bad case already exists") from None
    raise BadCasePersistenceError("Bad case persistence unavailable") from None


def create(session, workspace_id, run_id, case_id, actor, payload):
    try:
        current_authority(session, workspace_id, actor)
        session.execute(text("SET LOCAL lock_timeout = '5s'"))
        run, case = source(session, workspace_id, run_id, case_id)
        if run.status not in {"completed", "failed"} or case.result not in ORIGINS:
            raise ConflictError("Bad case source is not terminal")
        if session.scalar(
            select(BadCase.id).where(
                BadCase.workspace_id == workspace_id,
                BadCase.source_run_case_id == case.id,
            )
        ):
            raise ConflictError("Bad case already exists")
        human = HumanValues.model_validate(payload.model_dump()).model_dump()
        row = BadCase(
            workspace_id=workspace_id,
            source_run_case_id=case.id,
            origin_kind=ORIGINS[case.result],
            created_by=actor,
            updated_by=actor,
            **human,
        )
        session.add(row)
        session.flush()
        write_history(session, row, actor, None, human)
        response = serialize(row, case, run, detail=True)
        current_authority(session, workspace_id, actor)
        session.commit()
        current_authority(session, workspace_id, actor)
        return response
    except SQLAlchemyError as error:
        session.rollback()
        write_error(error)
    except Exception:
        session.rollback()
        raise


def update(session, workspace_id: UUID, bad_case_id: UUID, actor: UUID, payload):
    try:
        current_authority(session, workspace_id, actor)
        session.execute(text("SET LOCAL lock_timeout = '5s'"))
        row = session.scalar(
            select(BadCase)
            .where(
                BadCase.workspace_id == workspace_id,
                BadCase.id == bad_case_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if row is None:
            raise NotFoundError("Bad case resource not found")
        if row.revision != payload.expected_revision:
            raise ConflictError("Bad case revision conflict")
        before = {key: getattr(row, key) for key in HUMAN_FIELDS}
        patch = payload.model_dump(
            exclude_unset=True, exclude={"expected_revision", "change_reason"}
        )
        merged = {**before, **patch}
        if merged["status"] != row.status:
            if merged["status"] not in TRANSITIONS[row.status] or not payload.change_reason:
                raise BadCaseValidationError("Invalid bad case request")
            if merged["status"] == "open":
                merged["resolution_note"] = None
        try:
            human = HumanValues.model_validate(merged).model_dump()
        except ValidationError:
            raise BadCaseValidationError("Invalid bad case request") from None
        changed = {key for key in HUMAN_FIELDS if before[key] != human[key]}
        if changed:
            for key in changed:
                setattr(row, key, human[key])
            row.revision += 1
            row.updated_by = actor
            row.updated_at = session.scalar(select(func.clock_timestamp()))
            write_history(
                session,
                row,
                actor,
                {key: before[key] for key in changed},
                {key: human[key] for key in changed},
                payload.change_reason,
            )
        run, case = source(
            session,
            workspace_id,
            scoped(session, EvaluationRunCase, workspace_id, row.source_run_case_id).run_id,
            row.source_run_case_id,
        )
        response = serialize(row, case, run, detail=True)
        current_authority(session, workspace_id, actor)
        session.commit()
        current_authority(session, workspace_id, actor)
        return response
    except SQLAlchemyError as error:
        session.rollback()
        write_error(error)
    except Exception:
        session.rollback()
        raise
