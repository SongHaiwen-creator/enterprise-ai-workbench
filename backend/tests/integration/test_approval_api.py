import dataclasses
import json
from collections.abc import Generator
from datetime import timedelta
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import (
    AgentTool,
    Approval,
    MockITAccessRequest,
    Tool,
)
from app.models.enums import (
    AgentStatus,
    ApprovalDecisionStatus,
    ApprovalExecutionStatus,
    MembershipRole,
    MembershipStatus,
    ToolRisk,
    ToolStatus,
    UserStatus,
    WorkspaceStatus,
)
from app.schemas.agent_routing import RoutingIntent
from app.services import tool_registry
from app.services.approval_execution import (
    WRITE_EXECUTORS,
    execute_mock_it_access_request,
    mock_it_access_reference,
)
from app.services.tool_selection import ToolSelectionProposal
from tests.integration.approval_support import (
    ARGUMENTS,
    INVALIDATED,
    REQUEST_TEXT,
    FakeRoutingProvider,
    FakeToolSelector,
    Scenario,
    bearer,
    decide,
    install_overrides,
    make_membership,
    make_scenario,
    make_settings,
    make_user,
    request_approval,
    set_status,
)

pytestmark = pytest.mark.integration
RESPONSE_KEYS = {
    "id", "workspace_id", "decision_status", "execution_status", "action_type", "tool",
    "agent", "requester", "arguments", "created_at", "expires_at", "decision", "execution",
}


@pytest.fixture
def settings(database_urls: tuple[object, object]) -> Settings:
    return make_settings(database_urls)


@pytest.fixture
def router_provider() -> FakeRoutingProvider:
    return FakeRoutingProvider()


@pytest.fixture
def selector() -> FakeToolSelector:
    return FakeToolSelector()


@pytest.fixture
def client(
    db_session: Session,
    settings: Settings,
    router_provider: FakeRoutingProvider,
    selector: FakeToolSelector,
) -> Generator[TestClient, None, None]:
    def override_db_session() -> Generator[Session, None, None]:
        db_session.commit()
        yield db_session

    yield from install_overrides(override_db_session, settings, router_provider, selector)


@pytest.fixture
def scenario(db_session: Session) -> Scenario:
    return make_scenario(db_session)


def load(session: Session, approval_id: str) -> Approval:
    approval = session.scalar(
        select(Approval)
        .where(Approval.id == approval_id)
        .execution_options(populate_existing=True)
    )
    assert approval is not None
    return approval


def mock_rows(session: Session, approval_id: str) -> list[MockITAccessRequest]:
    return list(
        session.scalars(
            select(MockITAccessRequest).where(MockITAccessRequest.approval_id == approval_id)
        ).all()
    )


def force_expired(session: Session, approval_id: str) -> None:
    session.execute(
        text(
            "UPDATE approvals SET created_at = now() - interval '80 hours', "
            "expires_at = now() - interval '8 hours' WHERE id = :id"
        ),
        {"id": approval_id},
    )
    session.flush()


# --- Creation ---------------------------------------------------------------


def test_creation_persists_complete_pending_snapshot_without_executing(
    client: TestClient,
    db_session: Session,
    scenario: Scenario,
    selector: FakeToolSelector,
    settings: Settings,
) -> None:
    approval_id = request_approval(client, scenario, selector, settings)
    approval = load(db_session, approval_id)

    assert approval.decision_status is ApprovalDecisionStatus.PENDING
    assert approval.execution_status is ApprovalExecutionStatus.NOT_STARTED
    assert approval.requester_id == scenario.requester.id
    assert approval.agent_id == scenario.agent.id
    assert approval.tool_id == scenario.tool.id
    assert approval.action_type == "it_access_request.create"
    assert approval.canonical_arguments == ARGUMENTS
    assert approval.expires_at - approval.created_at == timedelta(hours=72)
    capability = approval.capability_snapshot
    assert capability["requester_membership_id"] == str(scenario.requester_membership.id)
    assert capability["assignment"] == {
        "agent_id": str(scenario.agent.id), "tool_id": str(scenario.tool.id)
    }
    assert capability["tool_risk_level"] == "high"
    assert capability["canonical_arguments_sha256"] == approval.canonical_arguments_sha256
    assert approval.policy_snapshot["required_reviewer_roles"] == ["system_admin"]
    stored = json.dumps(
        [approval.canonical_arguments, approval.capability_snapshot, approval.policy_snapshot]
    )
    assert REQUEST_TEXT not in stored
    assert "system_prompt" not in stored
    assert mock_rows(db_session, approval_id) == []


def test_identical_pending_request_is_deduplicated(
    client: TestClient,
    db_session: Session,
    scenario: Scenario,
    selector: FakeToolSelector,
    settings: Settings,
) -> None:
    first = request_approval(client, scenario, selector, settings)
    second = request_approval(client, scenario, selector, settings)
    different = request_approval(
        client, scenario, selector, settings, {**ARGUMENTS, "duration_days": 15}
    )

    assert first == second
    assert different != first
    other_requester = make_user(db_session, "Employee Two")
    make_membership(db_session, other_requester, scenario.workspace)
    other = request_approval(
        client, scenario, selector, settings, requester=other_requester
    )
    assert other not in {first, different}


def drive_to_terminal(
    client: TestClient,
    session: Session,
    scenario: Scenario,
    settings: Settings,
    approval_id: str,
    terminal: str,
) -> None:
    if terminal == "approved":
        assert decide(client, scenario, approval_id, settings).status_code == 200
    elif terminal == "rejected":
        assert decide(client, scenario, approval_id, settings, "reject").status_code == 200
    elif terminal == "cancelled":
        response = client.post(
            f"{scenario.approval_url(approval_id)}/cancel",
            headers=bearer(scenario.requester, settings),
        )
        assert response.status_code == 200
    elif terminal == "invalidated":
        set_status(session, scenario.requester_membership, MembershipStatus.DISABLED)
        assert decide(client, scenario, approval_id, settings).status_code == 409
        set_status(session, scenario.requester_membership, MembershipStatus.ACTIVE)
    else:
        force_expired(session, approval_id)
        assert decide(client, scenario, approval_id, settings).status_code == 409
    assert load(session, approval_id).decision_status.value == terminal


@pytest.mark.parametrize(
    "terminal", ["approved", "rejected", "cancelled", "invalidated", "expired"]
)
def test_terminal_approval_never_blocks_resubmission(
    client: TestClient,
    db_session: Session,
    scenario: Scenario,
    selector: FakeToolSelector,
    settings: Settings,
    terminal: str,
) -> None:
    first = request_approval(client, scenario, selector, settings)
    drive_to_terminal(client, db_session, scenario, settings, first, terminal)

    second = request_approval(client, scenario, selector, settings)

    assert second != first
    assert load(db_session, second).decision_status is ApprovalDecisionStatus.PENDING


def test_past_expiry_pending_row_is_expired_then_replaced(
    client: TestClient,
    db_session: Session,
    scenario: Scenario,
    selector: FakeToolSelector,
    settings: Settings,
) -> None:
    first = request_approval(client, scenario, selector, settings)
    force_expired(db_session, first)

    second = request_approval(client, scenario, selector, settings)

    expired = load(db_session, first)
    assert second != first
    assert expired.decision_status is ApprovalDecisionStatus.EXPIRED
    assert expired.decided_at == expired.expires_at
    assert expired.decided_by is None


def test_capability_or_caller_loss_during_selection_creates_nothing(
    client: TestClient,
    db_session: Session,
    scenario: Scenario,
    selector: FakeToolSelector,
    settings: Settings,
) -> None:
    def disable_tool(*args: object) -> ToolSelectionProposal:
        del args
        set_status(db_session, scenario.tool, ToolStatus.DISABLED)
        return ToolSelectionProposal("create_it_access_request", dict(ARGUMENTS))

    selector.select = disable_tool  # type: ignore[method-assign]
    response = client.post(
        scenario.route_url, headers=bearer(scenario.requester, settings),
        json={"request": REQUEST_TEXT},
    )
    assert response.status_code == 409
    set_status(db_session, scenario.tool, ToolStatus.ACTIVE)

    def revoke_caller(*args: object) -> ToolSelectionProposal:
        del args
        set_status(db_session, scenario.requester_membership, MembershipStatus.DISABLED)
        return ToolSelectionProposal("create_it_access_request", dict(ARGUMENTS))

    selector.select = revoke_caller  # type: ignore[method-assign]
    response = client.post(
        scenario.route_url, headers=bearer(scenario.requester, settings),
        json={"request": REQUEST_TEXT},
    )
    assert response.status_code == 403
    assert "validated_arguments" not in response.text
    assert db_session.scalar(
        select(func.count()).select_from(Approval).where(
            Approval.workspace_id == scenario.workspace.id
        )
    ) == 0


def test_missing_approval_policy_fails_closed_without_row(
    client: TestClient,
    db_session: Session,
    scenario: Scenario,
    selector: FakeToolSelector,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = tool_registry.get_tool_definition

    def without_policy(tool_key: str) -> tool_registry.ToolDefinition | None:
        definition = original(tool_key)
        if definition is None or definition.approval is None:
            return definition
        return dataclasses.replace(definition, approval=None)

    monkeypatch.setattr("app.services.tools.get_tool_definition", without_policy)
    selector.selection = ToolSelectionProposal("create_it_access_request", dict(ARGUMENTS))
    response = client.post(
        scenario.route_url, headers=bearer(scenario.requester, settings),
        json={"request": REQUEST_TEXT},
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "Tool configuration is unavailable"}
    assert db_session.scalar(
        select(func.count()).select_from(Approval).where(
            Approval.workspace_id == scenario.workspace.id
        )
    ) == 0


def test_read_only_knowledge_and_unsupported_routes_create_no_approval(
    client: TestClient,
    db_session: Session,
    scenario: Scenario,
    selector: FakeToolSelector,
    router_provider: FakeRoutingProvider,
    settings: Settings,
) -> None:
    read_tool = Tool(
        workspace_id=scenario.workspace.id,
        created_by=scenario.reviewer.id,
        tool_key="get_reimbursement_status",
        name="Reimbursement status",
        description="Read own reimbursement status.",
        risk_level=ToolRisk.LOW,
        status=ToolStatus.ACTIVE,
    )
    db_session.add(read_tool)
    db_session.flush()
    db_session.add(
        AgentTool(
            workspace_id=scenario.workspace.id, agent_id=scenario.agent.id,
            tool_id=read_tool.id,
        )
    )
    db_session.flush()
    headers = bearer(scenario.requester, settings)
    selector.selection = ToolSelectionProposal("get_reimbursement_status", {})
    executed = client.post(scenario.route_url, headers=headers, json={"request": "Status?"})
    assert executed.json()["outcome"]["status"] == "executed"

    router_provider.intent = RoutingIntent.UNSUPPORTED
    assert client.post(
        scenario.route_url, headers=headers, json={"request": "Weather?"}
    ).json()["outcome"]["status"] == "unsupported"
    router_provider.intent = RoutingIntent.KNOWLEDGE_QA
    assert client.post(
        scenario.route_url, headers=headers, json={"request": "Policy?"}
    ).status_code == 422

    assert db_session.scalar(
        select(func.count()).select_from(Approval).where(
            Approval.workspace_id == scenario.workspace.id
        )
    ) == 0


def test_misconfigured_low_risk_write_tool_never_reaches_write_adapter(
    client: TestClient,
    db_session: Session,
    scenario: Scenario,
    selector: FakeToolSelector,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []
    monkeypatch.setattr(
        "app.services.approvals.WRITE_EXECUTORS",
        {"mock_it_access_request.v1": lambda *args: calls.append(args)},
    )
    scenario.tool.risk_level = ToolRisk.LOW
    db_session.flush()
    selector.selection = ToolSelectionProposal("create_it_access_request", dict(ARGUMENTS))

    response = client.post(
        scenario.route_url, headers=bearer(scenario.requester, settings),
        json={"request": REQUEST_TEXT},
    )

    assert response.status_code == 503
    assert calls == []
    assert selector.calls == []


# --- Decision authorization --------------------------------------------------


@pytest.mark.parametrize(
    "role",
    [MembershipRole.EMPLOYEE, MembershipRole.KNOWLEDGE_ADMIN, MembershipRole.AGENT_ADMIN],
)
def test_only_system_admin_can_decide(
    client: TestClient,
    db_session: Session,
    scenario: Scenario,
    selector: FakeToolSelector,
    settings: Settings,
    role: MembershipRole,
) -> None:
    approval_id = request_approval(client, scenario, selector, settings)
    member = make_user(db_session, "Other Member")
    make_membership(db_session, member, scenario.workspace, role)

    for decision in ("approve", "reject"):
        response = decide(client, scenario, approval_id, settings, decision, user=member)
        assert response.status_code == 404
        assert response.json() == {"detail": "Approval not found"}
    listed = client.get(
        f"{scenario.approvals_url}?scope=review", headers=bearer(member, settings)
    )
    assert listed.status_code == 403
    assert listed.json() == {"detail": "Approval review not permitted"}
    assert load(db_session, approval_id).decision_status is ApprovalDecisionStatus.PENDING


def test_requester_cannot_decide_own_approval_even_as_system_admin(
    client: TestClient,
    db_session: Session,
    selector: FakeToolSelector,
    settings: Settings,
) -> None:
    scenario = make_scenario(db_session, requester_role=MembershipRole.SYSTEM_ADMIN)
    approval_id = request_approval(client, scenario, selector, settings)

    for decision in ("approve", "reject"):
        response = decide(
            client, scenario, approval_id, settings, decision, user=scenario.requester
        )
        assert response.status_code == 403
        assert response.json() == {"detail": "Approval action not permitted"}
    assert load(db_session, approval_id).decision_status is ApprovalDecisionStatus.PENDING
    assert mock_rows(db_session, approval_id) == []


def test_employee_requester_cannot_decide_own_approval(
    client: TestClient,
    db_session: Session,
    scenario: Scenario,
    selector: FakeToolSelector,
    settings: Settings,
) -> None:
    approval_id = request_approval(client, scenario, selector, settings)
    response = decide(client, scenario, approval_id, settings, user=scenario.requester)
    assert response.status_code == 403
    assert response.json() == {"detail": "Approval action not permitted"}


@pytest.mark.parametrize("revocation", ["user", "membership", "demoted", "workspace"])
def test_reviewer_side_loss_denies_and_leaves_pending(
    client: TestClient,
    db_session: Session,
    scenario: Scenario,
    selector: FakeToolSelector,
    settings: Settings,
    revocation: str,
) -> None:
    approval_id = request_approval(client, scenario, selector, settings)
    if revocation == "user":
        set_status(db_session, scenario.reviewer, UserStatus.DISABLED)
    elif revocation == "membership":
        set_status(db_session, scenario.reviewer_membership, MembershipStatus.DISABLED)
    elif revocation == "demoted":
        scenario.reviewer_membership.role = MembershipRole.AGENT_ADMIN
        db_session.flush()
    else:
        set_status(db_session, scenario.workspace, WorkspaceStatus.DISABLED)

    response = decide(client, scenario, approval_id, settings)

    assert response.status_code in {403, 404}
    approval = load(db_session, approval_id)
    assert approval.decision_status is ApprovalDecisionStatus.PENDING
    assert approval.invalidation_reason is None
    assert mock_rows(db_session, approval_id) == []


def test_reviewer_authority_is_resolved_per_workspace(
    client: TestClient,
    db_session: Session,
    selector: FakeToolSelector,
    settings: Settings,
) -> None:
    first = make_scenario(db_session)
    second = make_scenario(db_session)
    dual = make_user(db_session, "Dual Role")
    make_membership(db_session, dual, first.workspace, MembershipRole.SYSTEM_ADMIN)
    make_membership(db_session, dual, second.workspace, MembershipRole.EMPLOYEE)
    first_id = request_approval(client, first, selector, settings)
    second_id = request_approval(client, second, selector, settings)

    assert decide(client, second, second_id, settings, user=dual).status_code == 404
    assert decide(client, first, first_id, settings, user=dual).status_code == 200
    cross = client.get(first.approval_url(second_id), headers=bearer(dual, settings))
    assert cross.status_code == 404


def test_replay_table(
    client: TestClient,
    db_session: Session,
    scenario: Scenario,
    selector: FakeToolSelector,
    settings: Settings,
) -> None:
    other_reviewer = make_user(db_session, "Admin Two")
    make_membership(
        db_session, other_reviewer, scenario.workspace, MembershipRole.SYSTEM_ADMIN
    )
    approved_id = request_approval(client, scenario, selector, settings)
    first = decide(client, scenario, approved_id, settings)
    replay = decide(client, scenario, approved_id, settings)
    assert first.status_code == replay.status_code == 200
    assert first.json() == replay.json()
    assert len(mock_rows(db_session, approved_id)) == 1
    assert decide(client, scenario, approved_id, settings, "reject").status_code == 409
    other = decide(client, scenario, approved_id, settings, user=other_reviewer)
    assert other.status_code == 409
    assert other.json() == {"detail": "Approval is no longer pending"}

    rejected_id = request_approval(
        client, scenario, selector, settings, {**ARGUMENTS, "duration_days": 3}
    )
    assert decide(client, scenario, rejected_id, settings, "reject").status_code == 200
    assert decide(client, scenario, rejected_id, settings, "reject").status_code == 200
    assert decide(client, scenario, rejected_id, settings).status_code == 409

    cancelled_id = request_approval(
        client, scenario, selector, settings, {**ARGUMENTS, "duration_days": 4}
    )
    cancel_url = f"{scenario.approval_url(cancelled_id)}/cancel"
    headers = bearer(scenario.requester, settings)
    assert client.post(cancel_url, headers=headers).status_code == 200
    assert client.post(cancel_url, headers=headers, json={}).status_code == 200
    assert decide(client, scenario, cancelled_id, settings).status_code == 409

    # A replay is never served to a caller who has since lost authority.
    scenario.reviewer_membership.role = MembershipRole.EMPLOYEE
    db_session.flush()
    assert decide(client, scenario, approved_id, settings).status_code == 404


def test_cancel_rules(
    client: TestClient,
    db_session: Session,
    scenario: Scenario,
    selector: FakeToolSelector,
    settings: Settings,
) -> None:
    approval_id = request_approval(client, scenario, selector, settings)
    cancel_url = f"{scenario.approval_url(approval_id)}/cancel"

    reviewer_cancel = client.post(cancel_url, headers=bearer(scenario.reviewer, settings))
    assert reviewer_cancel.status_code == 403
    assert reviewer_cancel.json() == {"detail": "Approval action not permitted"}
    extra = client.post(
        cancel_url, headers=bearer(scenario.requester, settings), json={"note": "x"}
    )
    assert extra.status_code == 422

    response = client.post(cancel_url, headers=bearer(scenario.requester, settings))
    assert response.status_code == 200
    body = response.json()
    assert body["decision_status"] == "cancelled"
    assert body["execution_status"] == "not_started"
    assert body["decision"]["decided_by"]["id"] == str(scenario.requester.id)
    assert body["decision"]["note"] is None


@pytest.mark.parametrize(
    "field",
    [
        {"validated_arguments": ARGUMENTS},
        {"tool_id": "00000000-0000-0000-0000-000000000001"},
        {"agent_id": "00000000-0000-0000-0000-000000000001"},
        {"risk_level": "low"},
        {"policy": {"required_reviewer_roles": ["employee"]}},
    ],
)
def test_replayed_execution_fields_are_rejected(
    client: TestClient,
    db_session: Session,
    scenario: Scenario,
    selector: FakeToolSelector,
    settings: Settings,
    field: dict[str, Any],
) -> None:
    approval_id = request_approval(client, scenario, selector, settings)
    response = client.post(
        f"{scenario.approval_url(approval_id)}/decision",
        headers=bearer(scenario.reviewer, settings),
        json={"decision": "approve", **field},
    )

    assert response.status_code == 422
    assert load(db_session, approval_id).decision_status is ApprovalDecisionStatus.PENDING
    assert mock_rows(db_session, approval_id) == []


def test_expired_approval_cannot_be_approved(
    client: TestClient,
    db_session: Session,
    scenario: Scenario,
    selector: FakeToolSelector,
    settings: Settings,
) -> None:
    approval_id = request_approval(client, scenario, selector, settings)
    force_expired(db_session, approval_id)
    before = client.get(
        scenario.approval_url(approval_id), headers=bearer(scenario.requester, settings)
    ).json()
    assert before["decision_status"] == "expired"
    assert load(db_session, approval_id).decision_status is ApprovalDecisionStatus.PENDING

    response = decide(client, scenario, approval_id, settings)

    assert response.status_code == 409
    assert response.json() == {"detail": "Approval has expired"}
    approval = load(db_session, approval_id)
    assert approval.decision_status is ApprovalDecisionStatus.EXPIRED
    assert approval.decided_at == approval.expires_at
    after = client.get(
        scenario.approval_url(approval_id), headers=bearer(scenario.requester, settings)
    ).json()
    assert after == before
    assert mock_rows(db_session, approval_id) == []


# --- Execution authorization and drift (H3) ---------------------------------


def _registry_with(monkeypatch: pytest.MonkeyPatch, **changes: str) -> None:
    original = tool_registry.get_tool_definition
    policy_version = changes.pop("policy_version", None)

    def changed(tool_key: str) -> tool_registry.ToolDefinition | None:
        definition = original(tool_key)
        if definition is None or definition.approval is None:
            return definition
        approval = definition.approval
        if policy_version is not None:
            approval = dataclasses.replace(
                approval,
                policy=dataclasses.replace(approval.policy, policy_version=policy_version),
            )
        return dataclasses.replace(
            definition, approval=dataclasses.replace(approval, **changes)
        )

    monkeypatch.setattr("app.services.approvals.get_tool_definition", changed)


DRIFT_CASES = {
    "requester_disabled": "requester_ineligible",
    "requester_membership_disabled": "requester_ineligible",
    "agent_disabled": "capability_unavailable",
    "tool_disabled": "capability_unavailable",
    "assignment_removed": "capability_unavailable",
    "tool_risk_changed": "configuration_drift",
    "tool_definition_version": "configuration_drift",
    "executor_key": "configuration_drift",
    "policy_version": "configuration_drift",
    "arguments_tampered": "configuration_drift",
    "digest_tampered": "configuration_drift",
}


def apply_drift(
    session: Session,
    scenario: Scenario,
    approval_id: str,
    case: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if case == "requester_disabled":
        set_status(session, scenario.requester, UserStatus.DISABLED)
    elif case == "requester_membership_disabled":
        set_status(session, scenario.requester_membership, MembershipStatus.DISABLED)
    elif case == "agent_disabled":
        set_status(session, scenario.agent, AgentStatus.DISABLED)
    elif case == "tool_disabled":
        set_status(session, scenario.tool, ToolStatus.DISABLED)
    elif case == "assignment_removed":
        edge = session.get(AgentTool, (scenario.agent.id, scenario.tool.id))
        session.delete(edge)
        session.flush()
    elif case == "tool_risk_changed":
        scenario.tool.risk_level = ToolRisk.MEDIUM
        session.flush()
    elif case == "tool_definition_version":
        _registry_with(monkeypatch, tool_definition_version="create_it_access_request.v2")
    elif case == "executor_key":
        _registry_with(monkeypatch, executor_key="mock_it_access_request.v2")
    elif case == "policy_version":
        _registry_with(monkeypatch, policy_version="it-access-approval-v2")
    elif case == "arguments_tampered":
        session.execute(
            text(
                "UPDATE approvals SET canonical_arguments = jsonb_set("
                "canonical_arguments, '{duration_days}', '90') WHERE id = :id"
            ),
            {"id": approval_id},
        )
    else:
        session.execute(
            text("UPDATE approvals SET snapshot_sha256 = repeat('0', 64) WHERE id = :id"),
            {"id": approval_id},
        )
    session.flush()


@pytest.mark.parametrize(("case", "reason"), sorted(DRIFT_CASES.items()))
def test_drift_or_lost_authority_invalidates_without_approving(
    client: TestClient,
    db_session: Session,
    scenario: Scenario,
    selector: FakeToolSelector,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    reason: str,
) -> None:
    approval_id = request_approval(client, scenario, selector, settings)
    executor_calls: list[object] = []
    monkeypatch.setattr(
        "app.services.approvals.WRITE_EXECUTORS",
        {
            "mock_it_access_request.v1": lambda *args: executor_calls.append(args),
        },
    )
    apply_drift(db_session, scenario, approval_id, case, monkeypatch)
    before = load(db_session, approval_id)
    snapshot_before = (
        before.canonical_arguments, before.capability_snapshot,
        before.policy_snapshot, before.snapshot_sha256,
    )

    response = decide(client, scenario, approval_id, settings, note="Looks fine")

    assert response.status_code == 409
    assert response.json() == {"detail": INVALIDATED, "approval_id": approval_id}
    assert executor_calls == []
    approval = load(db_session, approval_id)
    assert approval.decision_status is ApprovalDecisionStatus.INVALIDATED
    assert approval.execution_status is ApprovalExecutionStatus.NOT_STARTED
    assert approval.invalidation_reason is not None
    assert approval.invalidation_reason.value == reason
    assert approval.invalidation_triggered_by == scenario.reviewer.id
    assert approval.decided_by is None
    assert approval.decided_at is not None
    assert approval.decision_note is None
    assert approval.executed_at is None
    assert (
        approval.canonical_arguments, approval.capability_snapshot,
        approval.policy_snapshot, approval.snapshot_sha256,
    ) == snapshot_before
    assert mock_rows(db_session, approval_id) == []


def test_invalidated_approval_stays_dead_after_configuration_is_restored(
    client: TestClient,
    db_session: Session,
    scenario: Scenario,
    selector: FakeToolSelector,
    settings: Settings,
) -> None:
    approval_id = request_approval(client, scenario, selector, settings)
    set_status(db_session, scenario.tool, ToolStatus.DISABLED)
    assert decide(client, scenario, approval_id, settings).status_code == 409
    set_status(db_session, scenario.tool, ToolStatus.ACTIVE)

    retry = decide(client, scenario, approval_id, settings)

    assert retry.status_code == 409
    assert retry.json() == {"detail": "Approval is no longer pending"}
    assert load(db_session, approval_id).decision_status is ApprovalDecisionStatus.INVALIDATED
    assert mock_rows(db_session, approval_id) == []
    replacement = request_approval(client, scenario, selector, settings)
    assert replacement != approval_id


def test_assignment_remove_and_readd_is_undetected_known_limitation_h2(
    client: TestClient,
    db_session: Session,
    scenario: Scenario,
    selector: FakeToolSelector,
    settings: Settings,
) -> None:
    """Pins the documented Section 16.3 limitation (H2), not desired behavior."""

    approval_id = request_approval(client, scenario, selector, settings)
    edge = db_session.get(AgentTool, (scenario.agent.id, scenario.tool.id))
    db_session.delete(edge)
    db_session.flush()
    db_session.add(
        AgentTool(
            workspace_id=scenario.workspace.id, agent_id=scenario.agent.id,
            tool_id=scenario.tool.id,
        )
    )
    db_session.flush()

    response = decide(client, scenario, approval_id, settings)

    assert response.status_code == 200
    assert response.json()["execution_status"] == "succeeded"


# --- Execution ---------------------------------------------------------------


def test_successful_approval_executes_exactly_one_mock_write(
    client: TestClient,
    db_session: Session,
    scenario: Scenario,
    selector: FakeToolSelector,
    settings: Settings,
    router_provider: FakeRoutingProvider,
) -> None:
    approval_id = request_approval(client, scenario, selector, settings)
    tables = ("users", "memberships", "workspaces", "agents", "tools", "agent_tools")
    counts = {
        table: db_session.scalar(text(f"SELECT count(*) FROM {table}")) for table in tables
    }
    model_calls = (len(router_provider.calls), len(selector.calls))

    response = decide(
        client, scenario, approval_id, settings, note="Approved for incident INC-1042."
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body) == RESPONSE_KEYS
    assert body["decision_status"] == "approved"
    assert body["execution_status"] == "succeeded"
    assert body["decision"] == {
        "decided_by": {"id": str(scenario.reviewer.id), "name": "Admin One"},
        "decided_at": body["decision"]["decided_at"],
        "note": "Approved for incident INC-1042.",
        "invalidation_reason": None,
    }
    reference = mock_it_access_reference(load(db_session, approval_id).id)
    assert body["execution"]["failure_category"] is None
    assert body["execution"]["result"] == {
        "type": "it_access_request",
        "reference": reference,
        "system": "production_database",
        "access_level": "read_only",
        "duration_days": 14,
        "status": "recorded",
    }
    rows = mock_rows(db_session, approval_id)
    assert len(rows) == 1
    assert rows[0].reference == reference
    assert rows[0].workspace_id == scenario.workspace.id
    assert rows[0].requester_id == scenario.requester.id
    assert {
        table: db_session.scalar(text(f"SELECT count(*) FROM {table}")) for table in tables
    } == counts
    assert (len(router_provider.calls), len(selector.calls)) == model_calls


@pytest.mark.parametrize("failure", ["raises", "invalid_result"])
def test_adapter_failure_records_approved_failed_without_mock_row(
    client: TestClient,
    db_session: Session,
    scenario: Scenario,
    selector: FakeToolSelector,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    approval_id = request_approval(client, scenario, selector, settings)

    def failing_executor(session: Session, context: Any, arguments: Any) -> Any:
        if failure == "raises":
            raise RuntimeError("internal adapter detail db-password")
        execute_mock_it_access_request(session, context, arguments)
        return {"type": "it_access_request", "reference": "not-a-reference"}

    monkeypatch.setattr(
        "app.services.approvals.WRITE_EXECUTORS",
        {"mock_it_access_request.v1": failing_executor},
    )

    response = decide(client, scenario, approval_id, settings, note="Approved")

    assert response.status_code == 502
    assert response.json() == {
        "detail": "Enterprise Tool request failed", "approval_id": approval_id
    }
    assert "db-password" not in response.text
    approval = load(db_session, approval_id)
    assert approval.decision_status is ApprovalDecisionStatus.APPROVED
    assert approval.execution_status is ApprovalExecutionStatus.FAILED
    assert approval.execution_failure_category is not None
    assert approval.execution_failure_category.value == "adapter_error"
    assert approval.decided_by == scenario.reviewer.id
    assert mock_rows(db_session, approval_id) == []
    read = client.get(
        scenario.approval_url(approval_id), headers=bearer(scenario.requester, settings)
    ).json()
    assert read["execution"] == {
        "executed_at": read["execution"]["executed_at"],
        "failure_category": "adapter_error",
        "result": None,
    }
    assert decide(client, scenario, approval_id, settings).status_code == 200
    assert mock_rows(db_session, approval_id) == []


def test_write_executor_registry_is_only_the_local_mock() -> None:
    assert dict(WRITE_EXECUTORS) == {
        "mock_it_access_request.v1": execute_mock_it_access_request
    }


# --- Reads and disclosure ----------------------------------------------------


def test_list_and_read_visibility(
    client: TestClient,
    db_session: Session,
    scenario: Scenario,
    selector: FakeToolSelector,
    settings: Settings,
) -> None:
    mine = request_approval(client, scenario, selector, settings)
    colleague = make_user(db_session, "Colleague")
    make_membership(db_session, colleague, scenario.workspace)
    theirs = request_approval(client, scenario, selector, settings, requester=colleague)
    foreign = make_scenario(db_session)
    foreign_id = request_approval(client, foreign, selector, settings)
    assert decide(client, scenario, theirs, settings, "reject").status_code == 200
    # One test transaction shares now(); spread creation times to pin ordering.
    db_session.execute(
        text(
            "UPDATE approvals SET created_at = created_at + interval '1 second', "
            "expires_at = expires_at + interval '1 second' WHERE id = :id"
        ),
        {"id": theirs},
    )
    db_session.flush()

    requester_headers = bearer(scenario.requester, settings)
    listed = client.get(scenario.approvals_url, headers=requester_headers).json()
    assert [item["id"] for item in listed["items"]] == [mine]
    assert (listed["limit"], listed["offset"]) == (50, 0)
    review = client.get(
        f"{scenario.approvals_url}?scope=review", headers=bearer(scenario.reviewer, settings)
    ).json()
    assert [item["id"] for item in review["items"]] == [theirs, mine]
    rejected_only = client.get(
        f"{scenario.approvals_url}?scope=review&decision_status=rejected",
        headers=bearer(scenario.reviewer, settings),
    ).json()
    assert [item["id"] for item in rejected_only["items"]] == [theirs]
    paged = client.get(
        f"{scenario.approvals_url}?scope=review&limit=1&offset=1",
        headers=bearer(scenario.reviewer, settings),
    ).json()
    assert [item["id"] for item in paged["items"]] == [mine]

    not_found = {"detail": "Approval not found"}
    for approval_id in (theirs, foreign_id, str(uuid4())):
        response = client.get(scenario.approval_url(approval_id), headers=requester_headers)
        assert response.status_code == 404
        assert response.json() == not_found
    for query in ("limit=0", "limit=101", "offset=-1", "scope=all", "decision_status=done"):
        response = client.get(f"{scenario.approvals_url}?{query}", headers=requester_headers)
        assert response.status_code == 422


def test_responses_never_disclose_internal_or_sensitive_fields(
    client: TestClient,
    db_session: Session,
    scenario: Scenario,
    selector: FakeToolSelector,
    settings: Settings,
) -> None:
    approval_id = request_approval(client, scenario, selector, settings)
    approval = load(db_session, approval_id)
    decided = decide(client, scenario, approval_id, settings)
    read = client.get(
        scenario.approval_url(approval_id), headers=bearer(scenario.requester, settings)
    )

    for response in (decided, read):
        assert set(response.json()) == RESPONSE_KEYS
        for secret in (
            str(scenario.tool.id), approval.snapshot_sha256,
            approval.canonical_arguments_sha256, scenario.requester.email,
            scenario.reviewer.email, REQUEST_TEXT, scenario.agent.system_prompt,
            "capability_snapshot", "policy_snapshot", "executor_key",
        ):
            assert secret not in response.text


@pytest.mark.parametrize("character", ["\x85", "\u202e", "\u200b"])
def test_decision_note_with_unicode_control_or_format_character_is_422(
    client: TestClient,
    db_session: Session,
    scenario: Scenario,
    selector: FakeToolSelector,
    settings: Settings,
    character: str,
) -> None:
    approval_id = request_approval(client, scenario, selector, settings)

    response = decide(client, scenario, approval_id, settings, note=f"ok{character}ok")

    assert response.status_code == 422
    assert load(db_session, approval_id).decision_status is ApprovalDecisionStatus.PENDING
    assert mock_rows(db_session, approval_id) == []
