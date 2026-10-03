"""Category execution without the production dispatcher or HTTP route handlers."""

import time

from openai import APIError, APITimeoutError
from pydantic import ValidationError

from app.schemas.agent_routing import RoutingIntent
from app.schemas.evaluation_run import ACTUAL_MODELS
from app.schemas.tool_calling import ToolNotExecutedOutcome
from app.services import answers, embeddings, generation, routing, tool_selection, tools
from app.services.agent_responses import unsupported_outcome
from app.services.authorization_policy import permission_observation
from app.services.evaluation_snapshot import digest


class EvaluationFailure(Exception):
    def __init__(self, category: str):
        self.category = category
        super().__init__(category)


def error_category(error: Exception) -> str:
    if isinstance(error, EvaluationFailure):
        return error.category
    if isinstance(
        error,
        (
            routing.RoutingConfigurationError,
            generation.GenerationConfigurationError,
            embeddings.EmbeddingConfigurationError,
            tool_selection.ToolSelectionConfigurationError,
            tools.ToolRegistryConfigurationError,
        ),
    ):
        return "provider_configuration"
    if isinstance(
        error,
        (
            routing.RoutingInputTooLargeError,
            generation.GenerationInputTooLargeError,
            tool_selection.ToolSelectionInputTooLargeError,
        ),
    ):
        return "input_budget"
    if isinstance(
        error,
        (
            routing.RoutingProviderError,
            generation.GenerationProviderError,
            embeddings.EmbeddingProviderError,
            tool_selection.ToolSelectionProviderError,
            tools.ToolAdapterError,
        ),
    ):
        cause = error.__cause__
        if isinstance(cause, APITimeoutError):
            return "case_timeout"
        return "provider_failure" if isinstance(cause, APIError) else "provider_contract"
    if isinstance(error, ValidationError):
        return "provider_contract"
    return "internal_error"


class Providers:
    """Factories are lazy: consent/preflight always precedes client construction."""

    def routing(self, settings):
        return routing.create_openai_routing_provider(settings)

    def selector(self, settings):
        return tool_selection.create_openai_tool_selector(settings)

    def embedding(self, settings):
        return embeddings.create_openai_embedding_provider(settings)

    def generation(self, settings):
        return generation.create_openai_generation_provider(settings)


class CaseBudget:
    def __init__(self, run_end: float):
        self.run_end = run_end
        self.case_end = time.monotonic() + 60

    def remaining(self):
        now = time.monotonic()
        if now >= self.run_end:
            raise EvaluationFailure("run_timeout")
        if now >= self.case_end:
            raise EvaluationFailure("case_timeout")
        return min(self.run_end, self.case_end) - now


class PhaseProviders:
    def __init__(self, settings, providers, budget, before, release):
        self.settings, self.providers, self.budget = settings, providers, budget
        self.before, self.release = before, release
        # Answer service needs embedding metadata before its first call.
        self.model = settings.embedding_model
        self.dimensions = settings.embedding_dimensions

    def call(self, kind, method, *arguments):
        self.before()
        remaining = self.budget.remaining()
        settings = self.settings.model_copy(
            update={
                "openai_timeout_seconds": min(self.settings.openai_timeout_seconds, 30, remaining)
            }
        )
        self.release()  # No database transaction/connection across external IO.
        provider = getattr(self.providers, kind)(settings)
        result = getattr(provider, method)(*arguments)
        self.budget.remaining()
        self.before()
        return result

    def select(self, request, scope, candidates):
        return self.call("selector", "select", request, scope, candidates)

    def embed_texts(self, texts):
        return self.call("embedding", "embed_texts", texts)

    def generate(self, question, evidence):
        return self.call("generation", "generate", question, evidence)


def execute_case(session, workspace_id, user_id, agent_id, scope, case, phases):
    category, context = case["case_type"], case["context"]
    if category == "permission_boundary":
        result = permission_observation(
            role=context["actor_role"],
            membership_status=context["actor_membership_status"],
            operation=context["operation"],
            present=context["resource_present_in_scope"],
            active=context["target_active"],
        )
        return ACTUAL_MODELS[category].model_validate(result).model_dump(mode="json")

    intent = phases.call("routing", "route", case["input"], scope)
    if type(intent) is not RoutingIntent:
        raise EvaluationFailure("provider_contract")
    result = {"routing_intent": intent.value}
    if category == "tool_calling" and intent is RoutingIntent.TOOL_REQUEST:
        plan = tools.plan_tool_request(
            session,
            workspace_id=workspace_id,
            agent_id=agent_id,
            request=case["input"],
            agent_scope=scope,
            user_id=user_id,
            selector=phases,
        )
        if isinstance(plan, ToolNotExecutedOutcome):
            result.update(
                would_outcome="not_executed",
                approval_required=False,
                non_execution_reason=plan.reason,
            )
        else:
            approval = not plan.definition.immediate_execution
            result.update(
                tool_id=str(plan.tool.id),
                tool_key=plan.tool.tool_key,
                would_outcome="approval_required" if approval else "executed",
                approval_required=approval,
            )
    elif category == "refusal_behavior" and intent is RoutingIntent.UNSUPPORTED:
        outcome = unsupported_outcome()
        result.update(
            response_category="unsupported_request", safe_response=outcome.status == "unsupported"
        )
    elif category in {"knowledge_qa", "refusal_behavior"} and (
        intent is RoutingIntent.KNOWLEDGE_QA and case["snapshot"]["knowledge_base_id"] is not None
    ):
        if context["knowledge_base"]["status"] != "active":
            raise EvaluationFailure("resource_configuration")
        evidence = []

        def observed(items):
            evidence.extend(
                {
                    "document_id": str(r.document_id),
                    "document_version": r.document_version,
                    "chunk_id": str(r.chunk_id),
                    "content_sha256": digest(r.content),
                }
                for r in items
            )

        answer = answers.answer_question(
            session,
            workspace_id,
            case["kb_id"],
            case["input"],
            phases,
            phases,
            observe_retrieval=observed,
        )
        cited = {str(c.chunk_id) for c in answer.citations}
        for item in evidence:
            item["cited"] = int(item["chunk_id"] in cited)
        result["evidence"] = evidence
        if category == "knowledge_qa":
            result.update(
                answer_status=answer.status.value,
                citation_count=len(answer.citations),
                knowledge_base_id=case["snapshot"]["knowledge_base_id"],
            )
        else:
            refused = answer.status.value == "unsupported"
            result.update(
                response_category="knowledge_unsupported" if refused else "knowledge_answered",
                safe_response=refused and answer.answer is None and not answer.citations,
            )
    return ACTUAL_MODELS[category].model_validate(result).model_dump(mode="json")
