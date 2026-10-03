"""Explicit, secret-free configuration capture. Never serialize Settings wholesale."""

import hashlib
import json
from uuid import UUID

from sqlalchemy import select

from app.models import Agent, AgentTool, Chunk, Document, KnowledgeBase, Tool
from app.models.enums import DocumentStatus
from app.schemas.agent_routing import ModelRoutingOutput
from app.schemas.answer import ModelGenerationOutput
from app.services.authorization_policy import POLICY_VERSION
from app.services.exceptions import NotFoundError
from app.services.generation import GROUNDING_INSTRUCTIONS
from app.services.routing import ROUTING_INSTRUCTIONS
from app.services.tool_registry import TOOL_REGISTRY
from app.services.tool_selection import TOOL_SELECTOR_INSTRUCTIONS


class SnapshotTooLarge(Exception):
    pass


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def fields(row, names) -> dict:
    result = {}
    for name in names:
        value = getattr(row, name)
        if isinstance(value, UUID):
            value = str(value)
        elif hasattr(value, "isoformat"):
            value = value.isoformat()
        result[name] = value
    return result


def scoped(session, model, workspace_id, object_id):
    row = session.scalar(
        select(model)
        .where(model.workspace_id == workspace_id, model.id == object_id)
        .execution_options(populate_existing=True)
    )
    if row is None:
        raise NotFoundError("Evaluation reference not found")
    return row


def agent_snapshot(session, workspace_id, agent_id):
    return fields(
        scoped(session, Agent, workspace_id, agent_id),
        ("id", "name", "status", "system_prompt", "updated_at"),
    )


def configuration(session, workspace_id, agent_id, settings):
    settings_fields = (
        "routing_model",
        "routing_reasoning_effort",
        "routing_prompt_version",
        "routing_max_input_tokens",
        "routing_max_output_tokens",
        "tool_selector_model",
        "tool_selector_reasoning_effort",
        "tool_selector_prompt_version",
        "tool_selector_max_input_tokens",
        "tool_selector_max_output_tokens",
        "generation_model",
        "generation_reasoning_effort",
        "generation_prompt_version",
        "generation_retrieval_limit",
        "generation_max_input_tokens",
        "generation_max_output_tokens",
        "embedding_model",
        "embedding_dimensions",
        "openai_timeout_seconds",
    )
    tools = session.scalars(
        select(Tool)
        .join(
            AgentTool,
            (Tool.id == AgentTool.tool_id) & (Tool.workspace_id == AgentTool.workspace_id),
        )
        .where(
            AgentTool.workspace_id == workspace_id,
            AgentTool.agent_id == agent_id,
            Tool.workspace_id == workspace_id,
        )
        .order_by(Tool.id)
        .execution_options(populate_existing=True)
    ).all()
    registry = {}
    for key, definition in TOOL_REGISTRY.items():
        approval = definition.approval
        registry[key] = {
            "argument_schema_sha256": digest(definition.argument_model.model_json_schema()),
            "selector_name": definition.selector_name,
            "selector_description": definition.selector_description,
            "risk": definition.risk.value,
            "operation_type": definition.operation_type.value,
            "immediate_execution": definition.immediate_execution,
            "approval": None
            if approval is None
            else {
                "definition_version": approval.tool_definition_version,
                "policy_version": approval.policy.policy_version,
                "required_roles": [r.value for r in approval.policy.required_reviewer_roles],
                "self_approval": approval.policy.self_approval_allowed,
                "ttl_hours": approval.policy.ttl_hours,
                "executor_key": approval.executor_key,
            },
        }
    return {
        "providers": {name: getattr(settings, name) for name in settings_fields},
        "tools": [
            fields(t, ("id", "tool_key", "status", "risk_level", "updated_at")) for t in tools
        ],
        "registry": registry,
        "policy_version": POLICY_VERSION,
        "evaluator_version": "evaluation-run-v1",
        "scorer_version": "evaluation-scorer-v1",
        "build_identifier": None,
        "instruction_hashes": {
            "routing": digest(ROUTING_INSTRUCTIONS),
            "generation": digest(GROUNDING_INSTRUCTIONS),
            "selector": digest(TOOL_SELECTOR_INSTRUCTIONS),
        },
        "schema_hashes": {
            "routing": digest(ModelRoutingOutput.model_json_schema()),
            "generation": digest(ModelGenerationOutput.model_json_schema()),
        },
        "limits": {"cases": 5, "case_seconds": 60, "run_seconds": 120, "call_seconds": 30},
    }


def knowledge_context(session, workspace_id, kb_id, settings):
    kb = scoped(session, KnowledgeBase, workspace_id, kb_id)
    documents = session.execute(
        select(Document.id, Document.version)
        .where(
            Document.workspace_id == workspace_id,
            Document.knowledge_base_id == kb_id,
            Document.status == DocumentStatus.READY,
        )
        .order_by(Document.id)
    ).all()
    manifest = {"documents": [], "chunks": []}
    size = 0
    for document in documents:
        entry = {"id": str(document.id), "version": document.version}
        size += len(canonical(entry).encode("utf-8"))
        if size > 1024 * 1024:
            raise SnapshotTooLarge()
        manifest["documents"].append(entry)
    chunks = session.execute(
        select(Chunk.id, Chunk.document_id, Chunk.content)
        .join(
            Document,
            (Chunk.document_id == Document.id) & (Chunk.workspace_id == Document.workspace_id),
        )
        .where(
            Chunk.workspace_id == workspace_id,
            Document.workspace_id == workspace_id,
            Document.knowledge_base_id == kb_id,
            Document.status == DocumentStatus.READY,
            Chunk.embedding_model == settings.embedding_model,
        )
        .order_by(Chunk.id)
        .execution_options(yield_per=100)
    )
    for chunk in chunks:
        entry = {
            "id": str(chunk.id),
            "document_id": str(chunk.document_id),
            "content_sha256": digest(chunk.content),
        }
        size += len(canonical(entry).encode("utf-8"))
        if size > 1024 * 1024:
            raise SnapshotTooLarge()
        manifest["chunks"].append(entry)
    return {
        "knowledge_base": fields(kb, ("id", "name", "status", "updated_at")),
        "corpus": manifest,
    }


def permission_context(session, workspace_id, case):
    expected = case.expected_behavior
    same = expected["target_context"] == "same_workspace"
    present, active, source = same, True, "code_fixture"
    target = None
    mapping = {
        "agent_route": (Agent, case.agent_id),
        "agent_configuration_read": (Agent, case.agent_id),
        "knowledge_answer": (KnowledgeBase, case.knowledge_base_id),
        "tool_configuration_read": (Tool, case.tool_id),
    }
    if same and expected["operation"] == "evaluation_dataset_read":
        source = "run_dataset"
    elif same and expected["operation"] in mapping:
        model, reference = mapping[expected["operation"]]
        if reference:
            target = scoped(session, model, workspace_id, reference)
            active, source = target.status == "active", "scoped_reference"
    return {
        "fixture_source": source,
        "resource_present_in_scope": present,
        "target_active": active,
        "target": None if target is None else fields(target, ("id", "status", "updated_at")),
        "policy_version": POLICY_VERSION,
        "actor_role": expected["actor_role"],
        "actor_membership_status": expected["actor_membership_status"],
        "target_context": expected["target_context"],
        "operation": expected["operation"],
    }
