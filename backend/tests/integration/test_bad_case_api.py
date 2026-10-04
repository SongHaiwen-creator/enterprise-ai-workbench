from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import StatementError

from app.models import BadCase, BadCaseHistory, EvaluationRun, EvaluationRunCase
from app.models.enums import MembershipRole, MembershipStatus, UserStatus, WorkspaceStatus
from app.schemas.evaluation_run import RunCreate
from app.services import bad_cases, evaluation_runs
from tests.integration.test_evaluation_run_api import (
    add_case,
    forbid_side_effects,
    post,
    root,
)
from tests.integration.test_knowledge_base_api import add_membership, create_workspace

pytest_plugins = ["tests.integration.test_evaluation_run_api"]
pytestmark = pytest.mark.integration
BODY = {"title": "Synthetic issue", "description": "Redacted concern"}


def seed(client, s, db_session, result="passed"):
    if result == "failed":
        add_case(db_session, s, "knowledge_qa")
    else:
        add_case(db_session, s)
    if result == "error":
        from app.services.routing import RoutingProviderError

        s.providers.error = RoutingProviderError("SECRET-SENTINEL")
    response = post(client, s)
    assert response.status_code == 201, response.text
    run = response.json()
    rows = client.get(f"{root(s)}/evaluation-runs/{run['id']}/cases", headers=s.headers).json()
    case = rows["items"][0]
    assert case["result"] == result
    path = f"{root(s)}/evaluation-runs/{run['id']}/cases/{case['id']}/bad-case"
    return run, case, path


def register(client, s, path):
    response = client.post(path, headers=s.headers, json=BODY)
    assert response.status_code == 201, response.text
    return response.json(), f"{root(s)}/bad-cases/{response.json()['id']}"


@pytest.mark.parametrize(
    "result,kind",
    [
        ("passed", "manual_review"),
        ("failed", "behavior_failure"),
        ("error", "execution_error"),
    ],
)
def test_register_source_history_and_no_execution(
    client, scenario, db_session, monkeypatch, result, kind
):
    s = scenario
    run, case, path = seed(client, s, db_session, result)
    before = client.get(f"{root(s)}/evaluation-runs/{run['id']}", headers=s.headers).json()
    calls = list(s.providers.calls)
    forbid_side_effects(monkeypatch)
    monkeypatch.setattr(evaluation_runs, "reconcile", lambda *_: pytest.fail("018 reconciled Run"))
    item, detail = register(client, s, path)
    assert item["origin_kind"] == kind and item["source_result"] == result
    assert item["source_evidence"]["case_id"] == case["case_id"]
    assert item["revision"] == 1
    assert client.post(path, headers=s.headers, json=BODY).json() == {
        "detail": "Bad case already exists"
    }
    listing = client.get(f"{root(s)}/bad-cases", headers=s.headers).json()["items"]
    assert (
        len(listing) == 1
        and "description" not in listing[0]
        and "source_evidence" not in listing[0]
    )
    history = client.get(f"{detail}/history", headers=s.headers).json()["items"]
    assert history[0]["before_values"] is None
    assert set(history[0]["after_values"]) == set(bad_cases.HUMAN_FIELDS)
    assert s.providers.calls == calls
    # Compare captured history without invoking legacy reconciliation.
    persisted = db_session.get(EvaluationRun, UUID(run["id"]))
    assert (
        evaluation_runs.summary(db_session, persisted, detail=True).model_dump(mode="json")
        == before
    )


def test_status_revision_noop_and_history_atomicity(client, scenario, db_session, monkeypatch):
    s = scenario
    _, _, path = seed(client, s, db_session)
    item, detail = register(client, s, path)

    def patch(**values):
        return client.patch(
            detail, headers=s.headers, json={"expected_revision": item["revision"], **values}
        )

    assert patch(title=BODY["title"]).json()["revision"] == 1
    for state in ("investigating", "resolved", "dismissed"):
        assert patch(status=state).status_code == 422
    item = patch(
        status="resolved", resolution_note="Manually addressed", change_reason="Human review"
    ).json()
    assert item["revision"] == 2
    assert (
        client.patch(
            detail, headers=s.headers, json={"expected_revision": 1, "title": "Stale"}
        ).status_code
        == 409
    )
    assert patch(status="dismissed", change_reason="Direct terminal change").status_code == 422
    item = patch(status="open", change_reason="Reopen").json()
    assert item["revision"] == 3 and item["resolution_note"] is None
    entries = client.get(f"{detail}/history", headers=s.headers).json()["items"]
    assert [h["revision"] for h in entries] == [1, 2, 3]
    assert entries[-1]["before_values"]["resolution_note"] == "Manually addressed"
    original = bad_cases.write_history

    def fail(*args):
        original(*args)
        raise StatementError("SECRET-SENTINEL", "secret sql", {"content": "secret"}, None)

    monkeypatch.setattr(bad_cases, "write_history", fail)
    error = patch(title="Not committed")
    assert error.status_code == 500 and "secret" not in error.text.lower()
    assert client.get(detail, headers=s.headers).json()["title"] == BODY["title"]
    assert len(client.get(f"{detail}/history", headers=s.headers).json()["items"]) == 3


@pytest.mark.parametrize("mode", ["running_terminal", "pending"])
def test_reject_nonterminal_source(client, scenario, db_session, mode):
    s = scenario
    add_case(db_session, s)
    run_id = evaluation_runs.capture(
        db_session,
        s.workspace.id,
        s.dataset.id,
        s.user.id,
        RunCreate(agent_id=s.agent.id, provider_egress_acknowledged=True),
        s.settings,
    )
    row = db_session.scalar(select(EvaluationRunCase).where(EvaluationRunCase.run_id == run_id))
    if mode == "running_terminal":
        # Atomic measured terminal case within a still-running Run.
        evaluation_runs._store(
            db_session,
            s.workspace.id,
            run_id,
            row.id,
            {
                "routing_intent": "unsupported",
                "response_category": "unsupported_request",
                "safe_response": True,
                "evidence": [],
            },
            {"routing_intent": True},
            1,
            None,
            evaluation_runs.db_now(db_session),
        )
    response = client.post(
        f"{root(s)}/evaluation-runs/{run_id}/cases/{row.id}/bad-case", headers=s.headers, json=BODY
    )
    assert response.status_code == 409
    assert not db_session.scalar(select(BadCase.id).where(BadCase.workspace_id == s.workspace.id))


@pytest.mark.parametrize(
    "restriction",
    [
        "employee",
        "knowledge_admin",
        "invited",
        "membership_disabled",
        "user_disabled",
        "workspace_disabled",
    ],
)
def test_every_route_denies_current_authority(client, scenario, db_session, restriction):
    s = scenario
    _, _, path = seed(client, s, db_session)
    _, detail = register(client, s, path)
    if restriction in {"employee", "knowledge_admin"}:
        s.member.role = MembershipRole(restriction)
    elif restriction in {"invited", "membership_disabled"}:
        s.member.status = (
            MembershipStatus.INVITED if restriction == "invited" else MembershipStatus.DISABLED
        )
    elif restriction == "user_disabled":
        s.user.status = UserStatus.DISABLED
    else:
        s.workspace.status = WorkspaceStatus.DISABLED
    db_session.commit()
    for method, url, body in [
        ("post", path, BODY),
        ("get", detail, None),
        ("get", detail + "/history", None),
        ("get", root(s) + "/bad-cases", None),
        ("patch", detail, {"expected_revision": 1, "title": "No"}),
    ]:
        response = client.request(
            method, url, headers=s.headers, **({"json": body} if body else {})
        )
        assert response.status_code in {401, 403}


def test_missing_foreign_filters_and_parent_mismatch(client, scenario, db_session):
    s = scenario
    run, case, path = seed(client, s, db_session)
    _, detail = register(client, s, path)
    foreign = create_workspace(db_session, slug=f"foreign-{uuid4()}")
    for suffix in (detail.split(root(s))[1], detail.split(root(s))[1] + "/history"):
        assert (
            client.get(f"/api/workspaces/{foreign.id}{suffix}", headers=s.headers).status_code
            == 403
        )
    for suffix in (
        f"/bad-cases/{uuid4()}",
        f"/bad-cases/{uuid4()}/history",
        f"/bad-cases?source_run_id={uuid4()}",
        f"/bad-cases?source_run_case_id={uuid4()}",
    ):
        response = client.get(root(s) + suffix, headers=s.headers)
        assert response.status_code == 404 and response.json() == {
            "detail": "Bad case resource not found"
        }
    response = client.post(path.replace(run["id"], str(uuid4())), headers=s.headers, json=BODY)
    assert response.status_code == 404
    filtered = client.get(
        f"{root(s)}/bad-cases?source_run_case_id={case['id']}&origin_kind=manual_review&limit=1&offset=0",
        headers=s.headers,
    )
    assert len(filtered.json()["items"]) == 1
    assert (
        client.get(f"{root(s)}/bad-cases?status=resolved", headers=s.headers).json()["items"] == []
    )
    assert client.get(f"{root(s)}/bad-cases?offset=1", headers=s.headers).json()["items"] == []


@pytest.mark.parametrize(
    "body",
    [
        {**BODY, "description": "SECRET-SENTINEL\0"},
        {**BODY, "source_result": "passed"},
        {**BODY, "title": None},
    ],
)
def test_sanitized_validation(client, scenario, db_session, body):
    _, _, path = seed(client, scenario, db_session)
    response = client.post(path, headers=scenario.headers, json=body)
    assert response.status_code == 422 and response.json() == {"detail": "Invalid bad case request"}
    for url in (
        root(scenario) + "/bad-cases?limit=0",
        root(scenario) + "/bad-cases?origin_kind=SECRET-SENTINEL",
        root(scenario) + "/bad-cases/invalid",
    ):
        assert client.get(url, headers=scenario.headers).json() == {
            "detail": "Invalid bad case request"
        }
    assert client.post(
        path, headers={**scenario.headers, "Content-Type": "application/json"}, content=b"\xff"
    ).json() == {"detail": "Invalid bad case request"}


def test_terminal_history_survives_disabled_sources(client, scenario, db_session):
    _, _, path = seed(client, scenario, db_session)
    item, detail = register(client, scenario, path)
    from app.models.enums import AgentStatus

    scenario.dataset.status = "disabled"
    scenario.agent.status = AgentStatus.DISABLED
    db_session.commit()
    assert (
        client.get(detail, headers=scenario.headers).json()["source_evidence"]
        == item["source_evidence"]
    )
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(BadCaseHistory)
            .where(BadCaseHistory.bad_case_id == UUID(item["id"]))
        )
        == 1
    )


def test_cross_workspace_ids_are_indistinguishable_from_missing(client, scenario, db_session):
    s = scenario
    run, case, path = seed(client, s, db_session)
    item, _ = register(client, s, path)
    other = create_workspace(db_session, slug=f"foreign-active-{uuid4()}")
    add_membership(db_session, s.user, other, role=MembershipRole.AGENT_ADMIN)
    db_session.commit()
    foreign_root = f"/api/workspaces/{other.id}"
    for supplied_id in (item["id"], str(uuid4())):
        for suffix in (f"/bad-cases/{supplied_id}", f"/bad-cases/{supplied_id}/history"):
            response = client.get(foreign_root + suffix, headers=s.headers)
            assert response.status_code == 404
            assert response.json() == {"detail": "Bad case resource not found"}
        response = client.patch(
            f"{foreign_root}/bad-cases/{supplied_id}",
            headers=s.headers,
            json={"expected_revision": 1, "title": "Foreign"},
        )
        assert response.status_code == 404
    for suffix in (
        f"/bad-cases?source_run_id={run['id']}",
        f"/bad-cases?source_run_case_id={case['id']}",
    ):
        assert client.get(foreign_root + suffix, headers=s.headers).status_code == 404
    assert (
        client.post(path.replace(root(s), foreign_root), headers=s.headers, json=BODY).status_code
        == 404
    )
    assert client.get(foreign_root + "/bad-cases", headers=s.headers).json()["items"] == []


def test_same_case_new_run_new_issue_and_system_admin_access(client, scenario, db_session):
    s = scenario
    first, first_case, path = seed(client, s, db_session)
    register(client, s, path)
    second = post(client, s).json()
    case = client.get(f"{root(s)}/evaluation-runs/{second['id']}/cases", headers=s.headers).json()[
        "items"
    ][0]
    assert case["case_id"] == first_case["case_id"] and second["id"] != first["id"]
    s.member.role = MembershipRole.SYSTEM_ADMIN
    db_session.commit()
    register(client, s, f"{root(s)}/evaluation-runs/{second['id']}/cases/{case['id']}/bad-case")
    assert len(client.get(root(s) + "/bad-cases", headers=s.headers).json()["items"]) == 2
