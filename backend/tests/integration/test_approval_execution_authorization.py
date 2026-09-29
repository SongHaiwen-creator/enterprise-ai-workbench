"""The execution boundary tested independently of the decision path."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import Approval, Membership
from app.models.enums import (
    ApprovalDecisionStatus,
    ApprovalInvalidationReason,
    MembershipStatus,
    WorkspaceStatus,
)
from app.schemas.tool_calling import CreateITAccessRequestArguments
from app.services.approval_snapshot import snapshot_sha256
from app.services.approvals import authorize_execution, create_pending_approval
from app.services.exceptions import ConflictError, ForbiddenError
from app.services.tool_registry import get_tool_definition
from tests.integration.approval_support import ARGUMENTS, Scenario, make_scenario, set_status

pytestmark = pytest.mark.integration


@pytest.fixture
def scenario(db_session: Session) -> Scenario:
    return make_scenario(db_session)


def pending(session: Session, scenario: Scenario) -> Approval:
    definition = get_tool_definition("create_it_access_request")
    assert definition is not None
    created = create_pending_approval(
        session,
        workspace_id=scenario.workspace.id,
        requester_id=scenario.requester.id,
        agent_id=scenario.agent.id,
        tool_id=scenario.tool.id,
        definition=definition,
        arguments=CreateITAccessRequestArguments.model_validate(ARGUMENTS),
    )
    return reload(session, created.id)


def reload(session: Session, approval_id: UUID) -> Approval:
    approval = session.scalar(
        select(Approval)
        .where(Approval.id == approval_id)
        .execution_options(populate_existing=True)
    )
    assert approval is not None
    return approval


def test_valid_snapshot_is_authorized_with_revalidated_arguments(
    db_session: Session, scenario: Scenario
) -> None:
    approval = pending(db_session, scenario)

    result = authorize_execution(db_session, approval, workspace_id=scenario.workspace.id)

    assert result.authorized
    assert result.arguments == CreateITAccessRequestArguments.model_validate(ARGUMENTS)
    assert result.requirement is not None
    assert result.requirement.executor_key == "mock_it_access_request.v1"
    assert reload(db_session, approval.id).decision_status is ApprovalDecisionStatus.PENDING


def test_replaced_requester_membership_is_requester_ineligible(
    db_session: Session, scenario: Scenario
) -> None:
    """A consistent snapshot naming an older Membership row is not the requester's."""

    approval = pending(db_session, scenario)
    capability = {**approval.capability_snapshot, "requester_membership_id": str(uuid4())}
    digest = snapshot_sha256(
        canonical_arguments_sha256=approval.canonical_arguments_sha256,
        capability=capability,
        policy=approval.policy_snapshot,
    )
    approval.capability_snapshot = capability
    approval.snapshot_sha256 = digest
    db_session.flush()

    result = authorize_execution(
        db_session, reload(db_session, approval.id), workspace_id=scenario.workspace.id
    )

    assert result.reason is ApprovalInvalidationReason.REQUESTER_INELIGIBLE


def test_invited_requester_membership_is_requester_ineligible(
    db_session: Session, scenario: Scenario
) -> None:
    approval = pending(db_session, scenario)
    set_status(db_session, scenario.requester_membership, MembershipStatus.INVITED)

    result = authorize_execution(db_session, approval, workspace_id=scenario.workspace.id)

    assert result.reason is ApprovalInvalidationReason.REQUESTER_INELIGIBLE
    assert db_session.get(Membership, scenario.requester_membership.id) is not None


def test_snapshot_workspace_mismatch_is_configuration_drift(
    db_session: Session, scenario: Scenario
) -> None:
    approval = pending(db_session, scenario)
    db_session.execute(
        text(
            "UPDATE approvals SET capability_snapshot = jsonb_set(capability_snapshot, "
            "'{workspace_id}', to_jsonb(CAST(:other AS text))) WHERE id = :id"
        ),
        {"other": str(uuid4()), "id": approval.id},
    )

    result = authorize_execution(
        db_session, reload(db_session, approval.id), workspace_id=scenario.workspace.id
    )

    assert result.reason is ApprovalInvalidationReason.CONFIGURATION_DRIFT


def test_inactive_route_workspace_is_the_callers_access_loss(
    db_session: Session, scenario: Scenario
) -> None:
    approval = pending(db_session, scenario)
    set_status(db_session, scenario.workspace, WorkspaceStatus.DISABLED)

    with pytest.raises(ForbiddenError):
        authorize_execution(db_session, approval, workspace_id=scenario.workspace.id)


def test_only_pending_unstarted_approvals_can_be_authorized(
    db_session: Session, scenario: Scenario
) -> None:
    approval = pending(db_session, scenario)
    db_session.execute(
        text(
            "UPDATE approvals SET decision_status = 'cancelled', decided_by = requester_id, "
            "decided_at = now() WHERE id = :id"
        ),
        {"id": approval.id},
    )

    with pytest.raises(ConflictError):
        authorize_execution(
            db_session, reload(db_session, approval.id), workspace_id=scenario.workspace.id
        )
