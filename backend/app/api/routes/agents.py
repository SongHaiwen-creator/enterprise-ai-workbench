from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.api.dependencies.auth import ApplicationSettings, CurrentUser, DatabaseSession
from app.api.dependencies.authorization import (
    AGENT_ADMIN_REQUIRED,
    ActiveWorkspaceMembership,
    AgentAdministratorMembership,
)
from app.api.dependencies.generation import ConfiguredGenerationProvider
from app.api.dependencies.routing import ConfiguredRoutingProvider
from app.models.enums import AgentStatus, KnowledgeBaseStatus, MembershipRole
from app.schemas.agent import (
    AgentConfigurationResponse,
    AgentCreate,
    AgentSummaryResponse,
    AgentUpdate,
)
from app.schemas.agent_routing import (
    AgentRouteRequest,
    AgentRouteResponse,
    KnowledgeRouteResponse,
    RoutingIntent,
    ToolNotExecutedOutcome,
    ToolRouteResponse,
    UnsupportedOutcome,
    UnsupportedRouteResponse,
)
from app.schemas.answer import GenerationMetadata, GroundedAnswerResponse, GroundedCitation
from app.schemas.common import ErrorResponse
from app.services import agents as agent_service
from app.services import answers as answer_service
from app.services import knowledge_bases as knowledge_base_service
from app.services.embeddings import (
    EmbeddingConfigurationError,
    EmbeddingProviderError,
    create_openai_embedding_provider,
)
from app.services.exceptions import ConflictError, ForbiddenError
from app.services.generation import (
    GenerationConfigurationError,
    GenerationInputTooLargeError,
    GenerationProviderError,
)
from app.services.routing import (
    ROUTING_PROVIDER_FAILURE,
    RoutingConfigurationError,
    RoutingInputTooLargeError,
    RoutingProviderError,
)

router = APIRouter(prefix="/workspaces/{workspace_id}/agents", tags=["agents"])

AGENT_RESPONSES = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
    502: {"model": ErrorResponse},
    503: {"model": ErrorResponse},
}
KNOWLEDGE_CONTEXT_REQUIRED = "Knowledge base context is required for knowledge questions."
TOOL_NOT_EXECUTED_MESSAGE = (
    "This request requires an enterprise tool. No action was executed."
)
UNSUPPORTED_MESSAGE = "This request is outside the configured Agent capabilities."


@router.post(
    "",
    response_model=AgentConfigurationResponse,
    status_code=status.HTTP_201_CREATED,
    responses=AGENT_RESPONSES,
)
def create_agent(
    workspace_id: UUID,
    payload: AgentCreate,
    session: DatabaseSession,
    current_user: CurrentUser,
    _administrator: AgentAdministratorMembership,
) -> AgentConfigurationResponse:
    agent = agent_service.create_agent(session, workspace_id, current_user.id, payload)
    return AgentConfigurationResponse.model_validate(agent)


@router.get("", response_model=list[AgentSummaryResponse], responses=AGENT_RESPONSES)
def list_agents(
    workspace_id: UUID,
    session: DatabaseSession,
    membership: ActiveWorkspaceMembership,
    include_inactive: bool = False,
) -> list[AgentSummaryResponse]:
    if include_inactive and membership.role not in {
        MembershipRole.AGENT_ADMIN,
        MembershipRole.SYSTEM_ADMIN,
    }:
        raise ForbiddenError(AGENT_ADMIN_REQUIRED)
    agents = agent_service.list_agents(session, workspace_id, include_inactive)
    return [AgentSummaryResponse.model_validate(agent) for agent in agents]


@router.get(
    "/{agent_id}",
    response_model=AgentConfigurationResponse,
    responses=AGENT_RESPONSES,
)
def get_agent(
    workspace_id: UUID,
    agent_id: UUID,
    session: DatabaseSession,
    _administrator: AgentAdministratorMembership,
) -> AgentConfigurationResponse:
    agent = agent_service.get_agent(session, workspace_id, agent_id)
    return AgentConfigurationResponse.model_validate(agent)


@router.patch(
    "/{agent_id}",
    response_model=AgentConfigurationResponse,
    responses=AGENT_RESPONSES,
)
def update_agent(
    workspace_id: UUID,
    agent_id: UUID,
    payload: AgentUpdate,
    session: DatabaseSession,
    _administrator: AgentAdministratorMembership,
) -> AgentConfigurationResponse:
    agent = agent_service.update_agent(session, workspace_id, agent_id, payload)
    return AgentConfigurationResponse.model_validate(agent)


@router.post(
    "/{agent_id}/route",
    response_model=AgentRouteResponse,
    responses=AGENT_RESPONSES,
)
def route_agent_request(
    workspace_id: UUID,
    agent_id: UUID,
    payload: AgentRouteRequest,
    session: DatabaseSession,
    _membership: ActiveWorkspaceMembership,
    routing_provider: ConfiguredRoutingProvider,
    settings: ApplicationSettings,
    generation_provider: ConfiguredGenerationProvider,
) -> AgentRouteResponse:
    agent = agent_service.get_agent(session, workspace_id, agent_id)
    if agent.status is not AgentStatus.ACTIVE:
        raise ConflictError("Agent is not active")

    try:
        intent = routing_provider.route(payload.request, agent.system_prompt)
    except RoutingInputTooLargeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RoutingConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RoutingProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if type(intent) is not RoutingIntent:
        raise HTTPException(status_code=502, detail=ROUTING_PROVIDER_FAILURE)

    if intent is RoutingIntent.TOOL_REQUEST:
        return ToolRouteResponse(
            request=payload.request,
            intent=RoutingIntent.TOOL_REQUEST,
            outcome=ToolNotExecutedOutcome(
                status="not_executed",
                required_capability="enterprise_tool",
                message=TOOL_NOT_EXECUTED_MESSAGE,
            ),
        )
    if intent is RoutingIntent.UNSUPPORTED:
        return UnsupportedRouteResponse(
            request=payload.request,
            intent=RoutingIntent.UNSUPPORTED,
            outcome=UnsupportedOutcome(
                status="unsupported",
                message=UNSUPPORTED_MESSAGE,
            ),
        )

    if payload.knowledge_base_id is None:
        raise HTTPException(status_code=422, detail=KNOWLEDGE_CONTEXT_REQUIRED)
    knowledge_base = knowledge_base_service.get_knowledge_base(
        session, workspace_id, payload.knowledge_base_id
    )
    if knowledge_base.status is not KnowledgeBaseStatus.ACTIVE:
        raise ConflictError("Knowledge base is not active")

    try:
        embedding_provider = create_openai_embedding_provider(settings)
        result = answer_service.answer_question(
            session,
            workspace_id,
            knowledge_base.id,
            payload.request,
            embedding_provider,
            generation_provider,
        )
    except GenerationInputTooLargeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (EmbeddingConfigurationError, GenerationConfigurationError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (EmbeddingProviderError, GenerationProviderError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    usage = result.usage
    answer = GroundedAnswerResponse(
        question=result.question,
        status=result.status,
        answer=result.answer,
        message=result.message,
        citations=[
            GroundedCitation.model_validate(citation, from_attributes=True)
            for citation in result.citations
        ],
        generation=GenerationMetadata(
            model=generation_provider.model,
            reasoning_effort=generation_provider.reasoning_effort,
            retrieval_limit=generation_provider.retrieval_limit,
            prompt_version=generation_provider.prompt_version,
            max_input_tokens=generation_provider.max_input_tokens,
            max_output_tokens=generation_provider.max_output_tokens,
            input_tokens=usage.input_tokens if usage is not None else None,
            output_tokens=usage.output_tokens if usage is not None else None,
            total_tokens=usage.total_tokens if usage is not None else None,
        ),
    )
    return KnowledgeRouteResponse(
        request=payload.request,
        intent=RoutingIntent.KNOWLEDGE_QA,
        outcome=answer,
    )
