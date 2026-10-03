"""Workspace-owned synchronous runner with incremental durability and terminal fencing."""

import time
from datetime import timedelta
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.exc import DBAPIError, SQLAlchemyError

from app.models import (
    Agent,
    EvaluationCase,
    EvaluationDataset,
    EvaluationRun,
    EvaluationRunCase,
    Membership,
    User,
    Workspace,
)
from app.schemas.evaluation import CaseCreate
from app.schemas.evaluation_run import RunCaseDetail, RunCaseSummary, RunDetail, RunSummary
from app.services import evaluation_snapshot as snapshot
from app.services.authorization_policy import active_membership, agent_administrator
from app.services.evaluation import EvaluationPersistenceError, EvaluationValidationError
from app.services.evaluation_execution import (
    CaseBudget,
    EvaluationFailure,
    PhaseProviders,
    Providers,
    error_category,
    execute_case,
)
from app.services.evaluation_scoring import compare, metrics
from app.services.exceptions import ConflictError, ForbiddenError, NotFoundError


def db_now(session):
    return session.scalar(select(func.clock_timestamp()))


def database_budget(session, seconds=5):
    ms = max(1, int(min(5, seconds) * 1000))
    session.execute(select(func.set_config("statement_timeout", str(ms), True)))
    session.execute(select(func.set_config("lock_timeout", str(ms), True)))


def current_authority(session, workspace_id, user_id):
    row = session.execute(
        select(User.status, Workspace.status, Membership.status, Membership.role)
        .select_from(User)
        .join(Membership, User.id == Membership.user_id)
        .join(Workspace, Membership.workspace_id == Workspace.id)
        .where(
            User.id == user_id,
            Membership.workspace_id == workspace_id,
            Workspace.id == workspace_id,
        )
    ).one_or_none()
    if (
        row is None
        or row[0] != "active"
        or row[1] != "active"
        or (not active_membership(row[2]) or not agent_administrator(row[3]))
    ):
        raise ForbiddenError("Not authorized for this workspace")


def run_row(session, workspace_id, run_id, *, lock=False):
    query = select(EvaluationRun).where(
        EvaluationRun.workspace_id == workspace_id, EvaluationRun.id == run_id
    )
    if lock:
        query = query.with_for_update()
    row = session.scalar(query.execution_options(populate_existing=True))
    if row is None:
        raise NotFoundError("Evaluation run not found")
    return row


def case_rows(session, workspace_id, run_id):
    return session.scalars(
        select(EvaluationRunCase)
        .where(EvaluationRunCase.workspace_id == workspace_id, EvaluationRunCase.run_id == run_id)
        .order_by(EvaluationRunCase.ordinal)
        .execution_options(populate_existing=True)
    ).all()


def counts(run, rows):
    run.passed_cases = sum(r.result == "passed" for r in rows)
    run.failed_cases = sum(r.result == "failed" for r in rows)
    run.error_cases = sum(r.result == "error" for r in rows)


def finish(session, workspace_id, run_id, failure=None, measured=None):
    database_budget(session)
    run = run_row(session, workspace_id, run_id, lock=True)
    if run.status != "running":
        session.rollback()
        return
    now = db_now(session)
    rows = case_rows(session, workspace_id, run_id)
    if failure:
        for row in rows:
            if row.result is None:
                row.result, row.error_category, row.completed_at = "error", failure, now
                if measured and row.id == measured[0]:
                    row.attempted, row.started_at, row.latency_ms = True, measured[1], measured[2]
    if any(r.result is None for r in rows):
        raise EvaluationFailure("internal_error")
    counts(run, rows)
    run.status, run.failure_category = ("failed", failure) if failure else ("completed", None)
    run.completed_at = now
    session.commit()


def reconcile(session, workspace_id):
    database_budget(session)
    stale = session.scalars(
        select(EvaluationRun.id).where(
            EvaluationRun.workspace_id == workspace_id,
            EvaluationRun.status == "running",
            EvaluationRun.deadline_at + timedelta(seconds=15) < func.clock_timestamp(),
        )
    ).all()
    for run_id in stale:
        # finish re-locks and fences any competing executor; terminal rows untouched.
        finish(session, workspace_id, run_id, "interrupted")


def _context(session, workspace_id, case, settings):
    if case.case_type == "permission_boundary":
        return snapshot.permission_context(session, workspace_id, case)
    if case.knowledge_base_id:
        return snapshot.knowledge_context(session, workspace_id, case.knowledge_base_id, settings)
    return {"execution_mode": "dry_run" if case.case_type == "tool_calling" else "routing_only"}


def capture(session, workspace_id, dataset_id, user_id, payload, settings):
    database_budget(session)
    current_authority(session, workspace_id, user_id)
    # Scoped preflight before locks/reconciliation/provider initialization.
    dataset = snapshot.scoped(session, EvaluationDataset, workspace_id, dataset_id)
    agent = snapshot.scoped(session, Agent, workspace_id, payload.agent_id)
    if dataset.status != "active" or agent.status != "active":
        raise ConflictError("Evaluation dataset and Agent must be active")
    session.scalar(select(Workspace.id).where(Workspace.id == workspace_id).with_for_update())
    reconcile(session, workspace_id)
    # Reconciliation may commit: reacquire the concurrency lock afterwards.
    database_budget(session)
    session.scalar(select(Workspace.id).where(Workspace.id == workspace_id).with_for_update())
    current_authority(session, workspace_id, user_id)
    if session.scalar(
        select(EvaluationRun.id).where(
            EvaluationRun.workspace_id == workspace_id, EvaluationRun.status == "running"
        )
    ):
        raise ConflictError("Evaluation resource is busy")
    dataset = session.scalar(
        select(EvaluationDataset)
        .where(EvaluationDataset.id == dataset_id, EvaluationDataset.workspace_id == workspace_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    agent_config = snapshot.agent_snapshot(session, workspace_id, payload.agent_id)
    if dataset.status != "active" or agent_config["status"] != "active":
        raise ConflictError("Evaluation dataset and Agent must be active")
    cases = session.scalars(
        select(EvaluationCase)
        .where(
            EvaluationCase.workspace_id == workspace_id,
            EvaluationCase.dataset_id == dataset_id,
            EvaluationCase.status == "active",
        )
        .order_by(EvaluationCase.created_at, EvaluationCase.id)
        .limit(6)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).all()
    if not 1 <= len(cases) <= 5:
        raise ConflictError("Evaluation requires 1 to 5 active cases")
    if any(c.case_type != "permission_boundary" for c in cases) and (
        not payload.provider_egress_acknowledged
    ):
        raise EvaluationValidationError("Invalid evaluation request")
    contexts = []
    for case in cases:
        CaseCreate.model_validate(
            snapshot.fields(
                case,
                (
                    "name",
                    "description",
                    "case_type",
                    "test_input",
                    "expected_behavior",
                    "agent_id",
                    "knowledge_base_id",
                    "tool_id",
                ),
            )
        )
        if case.case_type != "permission_boundary" and case.agent_id not in (
            None,
            payload.agent_id,
        ):
            raise ConflictError("Evaluation Agent context does not match")
        for column, model in (
            ("agent_id", Agent),
            ("knowledge_base_id", snapshot.KnowledgeBase),
            ("tool_id", snapshot.Tool),
        ):
            if getattr(case, column):
                snapshot.scoped(session, model, workspace_id, getattr(case, column))
        contexts.append(_context(session, workspace_id, case, settings))
    config = snapshot.configuration(session, workspace_id, payload.agent_id, settings)
    now = db_now(session)
    run = EvaluationRun(
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        agent_id=payload.agent_id,
        created_by=user_id,
        started_at=now,
        deadline_at=now + timedelta(seconds=120),
        total_cases=len(cases),
        dataset_snapshot=snapshot.fields(dataset, ("id", "name", "description", "updated_at")),
        agent_snapshot=agent_config,
        config_snapshot=config,
        configuration_sha256=snapshot.digest(config),
        provider_egress_acknowledged=payload.provider_egress_acknowledged,
    )
    session.add(run)
    session.flush()
    for ordinal, (case, context) in enumerate(zip(cases, contexts, strict=True), 1):
        session.add(
            EvaluationRunCase(
                workspace_id=workspace_id,
                run_id=run.id,
                case_id=case.id,
                ordinal=ordinal,
                case_type=case.case_type,
                test_input_snapshot=case.test_input,
                expected_behavior_snapshot=case.expected_behavior,
                context_snapshot=context,
                case_snapshot=snapshot.fields(
                    case,
                    (
                        "id",
                        "name",
                        "description",
                        "case_type",
                        "schema_version",
                        "updated_at",
                        "agent_id",
                        "knowledge_base_id",
                        "tool_id",
                    ),
                ),
            )
        )
    session.commit()
    return run.id


def _check_environment(session, workspace_id, user_id, state, case, settings, budget):
    database_budget(session, budget.remaining())
    try:
        current_authority(session, workspace_id, user_id)
    except ForbiddenError:
        raise EvaluationFailure("authorization_revoked") from None
    run = run_row(session, workspace_id, state["id"])
    if run.status != "running":
        raise EvaluationFailure("interrupted")
    if db_now(session) >= run.deadline_at:
        raise EvaluationFailure("run_timeout")
    try:
        agent = snapshot.agent_snapshot(session, workspace_id, state["agent_id"])
        config = snapshot.configuration(session, workspace_id, state["agent_id"], settings)
        if agent != state["agent"] or snapshot.digest(config) != state["config_hash"]:
            raise EvaluationFailure("configuration_drift")
        if case["kb_id"] and case["case_type"] != "permission_boundary":
            context = snapshot.knowledge_context(session, workspace_id, case["kb_id"], settings)
            if context != case["context"]:
                raise EvaluationFailure("configuration_drift")
        if case["case_type"] == "permission_boundary" and case["context"]["target"]:
            # Only same-Workspace real targets are inspected; no synthetic foreign lookup.
            op = case["context"]["operation"]
            model = (
                Agent
                if op.startswith("agent_")
                else snapshot.KnowledgeBase
                if op == "knowledge_answer"
                else snapshot.Tool
            )
            target = snapshot.scoped(
                session, model, workspace_id, UUID(case["context"]["target"]["id"])
            )
            if snapshot.fields(target, ("id", "status", "updated_at")) != case["context"]["target"]:
                raise EvaluationFailure("configuration_drift")
    except (NotFoundError, snapshot.SnapshotTooLarge):
        raise EvaluationFailure("configuration_drift") from None
    budget.remaining()


def _attempt(session, workspace_id, run_id, case_id):
    database_budget(session)
    run = run_row(session, workspace_id, run_id, lock=True)
    if run.status != "running" or db_now(session) >= run.deadline_at:
        session.rollback()
        raise EvaluationFailure("run_timeout")
    # Attempt timing stays in process until a terminal observation is durable.
    # Crash recovery cannot reconstruct a monotonic duration and must not invent one.
    started_at = db_now(session)
    session.commit()
    return started_at


def _store(session, workspace_id, run_id, case_id, actual, checks, latency, error, started_at):
    database_budget(session)
    run = run_row(session, workspace_id, run_id, lock=True)
    if run.status != "running":
        session.rollback()
        raise EvaluationFailure("interrupted")
    if db_now(session) >= run.deadline_at:
        session.rollback()
        raise EvaluationFailure("run_timeout")
    result = "error" if error else "passed" if all(checks.values()) else "failed"
    saved = session.execute(
        update(EvaluationRunCase)
        .where(
            EvaluationRunCase.workspace_id == workspace_id,
            EvaluationRunCase.run_id == run_id,
            EvaluationRunCase.id == case_id,
            EvaluationRunCase.result.is_(None),
        )
        .values(
            result=result,
            attempted=True,
            started_at=started_at,
            actual_behavior=actual,
            comparison_checks=checks,
            latency_ms=latency,
            error_category=error,
            completed_at=db_now(session),
        )
    )
    if saved.rowcount != 1:
        session.rollback()
        raise EvaluationFailure("interrupted")
    session.flush()
    counts(run, case_rows(session, workspace_id, run_id))
    session.commit()


def execute_run(session, workspace_id, run_id, user_id, settings, providers):
    run = run_row(session, workspace_id, run_id)
    state = {
        "id": run.id,
        "agent_id": run.agent_id,
        "agent": run.agent_snapshot,
        "config_hash": run.configuration_sha256,
    }
    remaining = max(0, (run.deadline_at - db_now(session)).total_seconds())
    run_end = time.monotonic() + min(120, remaining)
    inputs = [
        {
            "id": row.id,
            "case_type": row.case_type,
            "input": row.test_input_snapshot,
            "expected": row.expected_behavior_snapshot,
            "snapshot": row.case_snapshot,
            "context": row.context_snapshot,
            "kb_id": UUID(row.case_snapshot["knowledge_base_id"])
            if row.case_snapshot["knowledge_base_id"]
            else None,
        }
        for row in case_rows(session, workspace_id, run_id)
    ]
    session.rollback()
    for case in inputs:
        started_at = start = latency = None
        actual = checks = error = None
        fatal = None
        try:
            started_at = _attempt(session, workspace_id, run_id, case["id"])
            budget = CaseBudget(run_end)
            start = time.monotonic()

            def guard(case=case, budget=budget):
                _check_environment(session, workspace_id, user_id, state, case, settings, budget)

            phases = PhaseProviders(settings, providers, budget, guard, session.rollback)
            guard()
            actual = execute_case(
                session,
                workspace_id,
                user_id,
                state["agent_id"],
                state["agent"]["system_prompt"],
                case,
                phases,
            )
            guard()
            checks = compare(case["case_type"], case["expected"], actual, case["snapshot"])
        except SQLAlchemyError:
            latency = max(0, int((time.monotonic() - start) * 1000)) if start is not None else None
            session.rollback()
            fatal = error = "persistence_failure"
        except Exception as exc:
            latency = max(0, int((time.monotonic() - start) * 1000)) if start is not None else None
            session.rollback()
            error = error_category(exc)
            if isinstance(exc, (ForbiddenError, ConflictError, NotFoundError)):
                error = (
                    "authorization_revoked"
                    if isinstance(exc, ForbiddenError)
                    else "configuration_drift"
                )
            if error in {
                "run_timeout",
                "authorization_revoked",
                "configuration_drift",
                "interrupted",
                "internal_error",
            }:
                fatal = error
        if latency is None and start is not None:
            latency = max(0, int((time.monotonic() - start) * 1000))
        measured = (case["id"], started_at, latency) if latency is not None else None
        if fatal:
            finish(session, workspace_id, run_id, fatal, measured)
            return
        try:
            _store(
                session,
                workspace_id,
                run_id,
                case["id"],
                actual,
                None if error else checks,
                latency,
                error,
                started_at,
            )
        except EvaluationFailure as failure:
            session.rollback()
            finish(session, workspace_id, run_id, failure.category, measured)
            return
        except SQLAlchemyError:
            session.rollback()
            finish(session, workspace_id, run_id, "persistence_failure", measured)
            return
    finish(session, workspace_id, run_id)


def create_run(session, workspace_id, dataset_id, user_id, payload, settings, providers=None):
    run_id = None
    try:
        run_id = capture(session, workspace_id, dataset_id, user_id, payload, settings)
        execute_run(session, workspace_id, run_id, user_id, settings, providers or Providers())
    except snapshot.SnapshotTooLarge:
        session.rollback()
        raise ConflictError("Evaluation configuration snapshot is too large") from None
    except EvaluationFailure as failure:
        session.rollback()
        if run_id:
            finish(session, workspace_id, run_id, failure.category)
        else:
            raise EvaluationPersistenceError("Evaluation persistence unavailable") from None
    except SQLAlchemyError as error:
        session.rollback()
        if isinstance(error, DBAPIError) and getattr(error.orig, "sqlstate", None) == "55P03":
            raise ConflictError("Evaluation resource is busy") from None
        raise EvaluationPersistenceError("Evaluation persistence unavailable") from None
    result = summary(session, run_row(session, workspace_id, run_id))
    current_authority(session, workspace_id, user_id)
    return result


def summary(session, run, *, detail=False):
    rows = case_rows(session, run.workspace_id, run.id)
    values = {
        name: getattr(run, name)
        for name in RunSummary.model_fields
        if name not in {"dataset_name", "agent_name", "pending_cases", "metrics"}
    }
    values.update(
        dataset_name=run.dataset_snapshot["name"],
        agent_name=run.agent_snapshot["name"],
        pending_cases=sum(r.result is None for r in rows),
        metrics=metrics(rows),
    )
    if detail:
        values.update(
            {
                name: getattr(run, name)
                for name in RunDetail.model_fields
                if name not in RunSummary.model_fields
            }
        )
    return (RunDetail if detail else RunSummary).model_validate(values)


def list_runs(session, workspace_id, user_id, dataset_id, agent_id, status, limit, offset):
    database_budget(session)
    current_authority(session, workspace_id, user_id)
    for model, object_id in ((EvaluationDataset, dataset_id), (Agent, agent_id)):
        if object_id:
            snapshot.scoped(session, model, workspace_id, object_id)
    reconcile(session, workspace_id)
    query = select(EvaluationRun).where(EvaluationRun.workspace_id == workspace_id)
    for field, value in (("dataset_id", dataset_id), ("agent_id", agent_id), ("status", status)):
        if value:
            query = query.where(getattr(EvaluationRun, field) == value)
    rows = session.scalars(
        query.order_by(EvaluationRun.created_at.desc(), EvaluationRun.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    results = [summary(session, r) for r in rows]
    current_authority(session, workspace_id, user_id)
    return results


def read_run(session, workspace_id, run_id, user_id):
    database_budget(session)
    current_authority(session, workspace_id, user_id)
    run_row(session, workspace_id, run_id)
    reconcile(session, workspace_id)
    result = summary(session, run_row(session, workspace_id, run_id), detail=True)
    current_authority(session, workspace_id, user_id)
    return result


def case_summary(row, *, detail=False):
    values = {name: getattr(row, name) for name in RunCaseSummary.model_fields if name != "name"}
    values["name"] = row.case_snapshot["name"]
    if detail:
        values.update(
            {
                name: getattr(row, name)
                for name in RunCaseDetail.model_fields
                if name not in RunCaseSummary.model_fields
            }
        )
    return (RunCaseDetail if detail else RunCaseSummary).model_validate(values)


def list_run_cases(session, workspace_id, run_id, user_id, category, result, limit, offset):
    read_run(session, workspace_id, run_id, user_id)
    rows = case_rows(session, workspace_id, run_id)
    rows = [
        r
        for r in rows
        if (not category or r.case_type == category) and (not result or r.result == result)
    ]
    results = [case_summary(row) for row in rows[offset : offset + limit]]
    current_authority(session, workspace_id, user_id)
    return results


def read_run_case(session, workspace_id, run_id, case_id, user_id):
    read_run(session, workspace_id, run_id, user_id)
    row = session.scalar(
        select(EvaluationRunCase).where(
            EvaluationRunCase.workspace_id == workspace_id,
            EvaluationRunCase.run_id == run_id,
            EvaluationRunCase.id == case_id,
        )
    )
    if row is None:
        raise NotFoundError("Evaluation run case not found")
    result = case_summary(row, detail=True)
    current_authority(session, workspace_id, user_id)
    return result
