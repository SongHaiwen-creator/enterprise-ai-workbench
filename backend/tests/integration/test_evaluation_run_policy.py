from itertools import product
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.api.dependencies.embeddings import get_embedding_provider
from app.api.dependencies.routing import get_routing_provider
from app.main import app
from app.models import Agent, KnowledgeBase, Tool
from app.models.enums import (
    AgentStatus,
    KnowledgeBaseStatus,
    MembershipRole,
    MembershipStatus,
    ToolRisk,
)
from app.schemas.agent_routing import RoutingIntent
from app.schemas.evaluation import DatasetCreate
from app.services import evaluation
from app.services.authorization_policy import permission_observation
from tests.integration.test_knowledge_base_api import (
    add_membership,
    bearer,
    create_user,
    create_workspace,
)

pytest_plugins = ["tests.integration.test_evaluation_run_api"]
pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "role,status,context,operation",
    list(
        product(
            list(MembershipRole),
            ["active", "invited", "disabled", "absent"],
            ["same_workspace", "other_workspace", "nonexistent"],
            [
                "agent_route",
                "knowledge_answer",
                "agent_configuration_read",
                "tool_configuration_read",
                "evaluation_dataset_read",
            ],
        )
    ),
)
def test_policy_has_real_endpoint_parity(
    client, scenario, db_session, role, status, context, operation
):
    s = scenario
    actor = create_user(db_session, email=f"policy-{uuid4()}@example.test")
    if status != "absent":
        membership = add_membership(db_session, actor, s.workspace, role=role)
        membership.status = MembershipStatus(status)
        db_session.commit()
    target_workspace = s.workspace
    if context == "other_workspace":
        target_workspace = create_workspace(db_session, slug=f"policy-foreign-{uuid4()}")
        add_membership(db_session, s.user, target_workspace, role=MembershipRole.SYSTEM_ADMIN)
    agent = Agent(
        workspace_id=target_workspace.id,
        created_by=s.user.id,
        name="Policy target",
        system_prompt="Synthetic",
        status=AgentStatus.ACTIVE,
    )
    kb = KnowledgeBase(workspace_id=target_workspace.id, created_by=s.user.id, name="Policy target")
    tool = Tool(
        workspace_id=target_workspace.id,
        created_by=s.user.id,
        name="Policy target",
        description="Synthetic",
        tool_key="get_employee_information",
        risk_level=ToolRisk.LOW,
    )
    db_session.add_all([agent, kb, tool])
    db_session.commit()
    dataset = evaluation.create_dataset(
        db_session, target_workspace.id, s.user.id, DatasetCreate(name="Policy target")
    )
    identifiers = {
        "agent_route": agent.id,
        "agent_configuration_read": agent.id,
        "knowledge_answer": kb.id,
        "tool_configuration_read": tool.id,
        "evaluation_dataset_read": dataset.id,
    }
    target_id = uuid4() if context == "nonexistent" else identifiers[operation]
    path = {
        "agent_route": f"agents/{target_id}/route",
        "knowledge_answer": f"knowledge-bases/{target_id}/answer",
        "agent_configuration_read": f"agents/{target_id}",
        "tool_configuration_read": f"tools/{target_id}",
        "evaluation_dataset_read": f"evaluation-datasets/{target_id}",
    }[operation]
    app.dependency_overrides[get_routing_provider] = lambda: SimpleNamespace(
        route=lambda *_: RoutingIntent.UNSUPPORTED
    )
    app.dependency_overrides[get_embedding_provider] = lambda: SimpleNamespace(
        model=s.settings.embedding_model,
        dimensions=1536,
        embed_texts=lambda texts: [[1.0] + [0.0] * 1535 for _ in texts],
    )
    url = f"/api/workspaces/{s.workspace.id}/{path}"
    if operation in {"agent_route", "knowledge_answer"}:
        body = {"request": "Synthetic"} if operation == "agent_route" else {"question": "Synthetic"}
        response = client.post(url, json=body, headers=bearer(actor, s.settings))
    else:
        response = client.get(url, headers=bearer(actor, s.settings))
    observed = permission_observation(
        role=role.value,
        membership_status=status,
        operation=operation,
        present=context == "same_workspace",
        active=True,
    )
    assert response.status_code == observed["http_status"], response.text


@pytest.mark.parametrize("operation", ["agent_route", "knowledge_answer"])
def test_inactive_target_lifecycle_parity(client, scenario, db_session, operation):
    s = scenario
    if operation == "agent_route":
        s.agent.status = AgentStatus.DISABLED
        url = f"/api/workspaces/{s.workspace.id}/agents/{s.agent.id}/route"
        body = {"request": "Synthetic"}
    else:
        s.kb.status = KnowledgeBaseStatus.DISABLED
        url = f"/api/workspaces/{s.workspace.id}/knowledge-bases/{s.kb.id}/answer"
        body = {"question": "Synthetic"}
    db_session.commit()
    app.dependency_overrides[get_embedding_provider] = lambda: SimpleNamespace(
        model=s.settings.embedding_model,
        dimensions=1536,
        embed_texts=lambda texts: [[1.0] + [0.0] * 1535 for _ in texts],
    )
    app.dependency_overrides[get_routing_provider] = lambda: SimpleNamespace(
        route=lambda *_: RoutingIntent.UNSUPPORTED
    )
    response = client.post(url, json=body, headers=s.headers)
    observed = permission_observation(
        role="agent_admin",
        membership_status="active",
        operation=operation,
        present=True,
        active=False,
    )
    assert response.status_code == observed["http_status"] == 409
