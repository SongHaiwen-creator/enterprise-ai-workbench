from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.models.enums import (
    ApprovalDecisionStatus,
    ApprovalExecutionStatus,
    ExecutionLogErrorCategory,
    ExecutionLogOperation,
    ExecutionLogOutcome,
)
from app.services import approvals as approval_service
from app.services import execution_logs
from app.services.agents import (
    AGENT_NOT_ACTIVE,
    AGENT_NOT_FOUND,
    KNOWLEDGE_BASE_NOT_ACTIVE,
    KNOWLEDGE_CONTEXT_REQUIRED,
)
from app.services.embeddings import EmbeddingConfigurationError, EmbeddingProviderError
from app.services.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.services.execution_logs import (
    DisallowedDetailError,
    approval_outcome,
    classify_exception,
    validate_details,
)
from app.services.generation import (
    GenerationConfigurationError,
    GenerationInputTooLargeError,
    GenerationProviderError,
)
from app.services.knowledge_bases import KNOWLEDGE_BASE_NOT_FOUND
from app.services.retrieval import KNOWLEDGE_BASE_SEARCH_DISABLED
from app.services.routing import (
    ROUTING_PROVIDER_FAILURE,
    RoutingConfigurationError,
    RoutingInputTooLargeError,
    RoutingProviderError,
)
from app.services.tool_selection import (
    ToolSelectionConfigurationError,
    ToolSelectionInputTooLargeError,
    ToolSelectionProviderError,
)
from app.services.tools import (
    TOOL_ADAPTER_FAILURE,
    TOOL_PROVIDER_FAILURE,
    ToolAdapterError,
    ToolRegistryConfigurationError,
)

Category = ExecutionLogErrorCategory
Operation = ExecutionLogOperation
SECRET = "sensitive-request-text-that-must-not-leak"


def wrapped(status: int, cause: Exception) -> HTTPException:
    try:
        raise HTTPException(status_code=status, detail=str(cause)) from cause
    except HTTPException as exc:
        return exc


CLASSIFICATION_CASES = [
    (NotFoundError(AGENT_NOT_FOUND), 404, Category.AGENT_NOT_FOUND),
    (ConflictError(AGENT_NOT_ACTIVE), 409, Category.AGENT_INACTIVE),
    (
        HTTPException(status_code=422, detail=KNOWLEDGE_CONTEXT_REQUIRED),
        422,
        Category.KNOWLEDGE_BASE_REQUIRED,
    ),
    (NotFoundError(KNOWLEDGE_BASE_NOT_FOUND), 404, Category.KNOWLEDGE_BASE_NOT_FOUND),
    (ConflictError(KNOWLEDGE_BASE_NOT_ACTIVE), 409, Category.KNOWLEDGE_BASE_INACTIVE),
    (ConflictError(KNOWLEDGE_BASE_SEARCH_DISABLED), 409, Category.KNOWLEDGE_BASE_INACTIVE),
    (wrapped(422, RoutingInputTooLargeError(SECRET)), 422, Category.INPUT_TOO_LARGE),
    (wrapped(422, ToolSelectionInputTooLargeError(SECRET)), 422, Category.INPUT_TOO_LARGE),
    (wrapped(422, GenerationInputTooLargeError(SECRET)), 422, Category.INPUT_TOO_LARGE),
    (wrapped(503, RoutingConfigurationError(SECRET)), 503, Category.PROVIDER_UNAVAILABLE),
    (
        wrapped(503, ToolSelectionConfigurationError(SECRET)),
        503,
        Category.PROVIDER_UNAVAILABLE,
    ),
    (wrapped(503, EmbeddingConfigurationError(SECRET)), 503, Category.PROVIDER_UNAVAILABLE),
    (wrapped(503, GenerationConfigurationError(SECRET)), 503, Category.PROVIDER_UNAVAILABLE),
    (wrapped(502, RoutingProviderError(SECRET)), 502, Category.PROVIDER_ERROR),
    (wrapped(502, ToolSelectionProviderError(SECRET)), 502, Category.PROVIDER_ERROR),
    (wrapped(502, EmbeddingProviderError(SECRET)), 502, Category.PROVIDER_ERROR),
    (wrapped(502, GenerationProviderError(SECRET)), 502, Category.PROVIDER_ERROR),
    (
        HTTPException(status_code=502, detail=ROUTING_PROVIDER_FAILURE),
        502,
        Category.PROVIDER_ERROR,
    ),
    (wrapped(502, ToolAdapterError(TOOL_PROVIDER_FAILURE)), 502, Category.PROVIDER_ERROR),
    (
        wrapped(502, ToolAdapterError(TOOL_ADAPTER_FAILURE)),
        502,
        Category.TOOL_EXECUTION_FAILED,
    ),
    (
        wrapped(503, ToolRegistryConfigurationError(SECRET)),
        503,
        Category.TOOL_CONFIGURATION_ERROR,
    ),
    (
        wrapped(503, approval_service.ApprovalConfigurationError(SECRET)),
        503,
        Category.TOOL_CONFIGURATION_ERROR,
    ),
    (
        ConflictError(approval_service.CAPABILITY_UNAVAILABLE),
        409,
        Category.TOOL_UNAVAILABLE,
    ),
    (ForbiddenError("Not authorized for this workspace"), 403, Category.ACCESS_DENIED),
    (
        ForbiddenError(approval_service.APPROVAL_ACTION_NOT_PERMITTED),
        403,
        Category.ACCESS_DENIED,
    ),
    (
        NotFoundError(approval_service.APPROVAL_NOT_FOUND),
        404,
        Category.APPROVAL_NOT_FOUND,
    ),
    (
        ConflictError(approval_service.APPROVAL_NOT_PENDING),
        409,
        Category.APPROVAL_NOT_PENDING,
    ),
    (ConflictError(approval_service.APPROVAL_EXPIRED), 409, Category.APPROVAL_EXPIRED),
    (ConflictError(approval_service.APPROVAL_BUSY), 409, Category.APPROVAL_BUSY),
    (
        approval_service.ApprovalOutcomeError(
            approval_service.APPROVAL_INVALIDATED, status_code=409, approval_id=uuid4()
        ),
        409,
        Category.APPROVAL_INVALIDATED,
    ),
    (
        approval_service.ApprovalOutcomeError(
            approval_service.APPROVAL_EXECUTION_FAILED, status_code=502, approval_id=uuid4()
        ),
        502,
        Category.APPROVAL_EXECUTION_FAILED,
    ),
    (RuntimeError(SECRET), 500, Category.INTERNAL_ERROR),
    (NotFoundError(SECRET), 404, Category.INTERNAL_ERROR),
    (ConflictError(SECRET), 409, Category.INTERNAL_ERROR),
    (HTTPException(status_code=418, detail=SECRET), 418, Category.INTERNAL_ERROR),
    (wrapped(502, ToolAdapterError(SECRET)), 502, Category.INTERNAL_ERROR),
]


@pytest.mark.parametrize(("exc", "status", "category"), CLASSIFICATION_CASES)
def test_classification_uses_types_and_constants(
    exc: Exception, status: int, category: ExecutionLogErrorCategory
) -> None:
    assert classify_exception(exc) == (status, category)


def test_every_error_category_is_reachable_by_classification() -> None:
    reachable = {category for _, _, category in CLASSIFICATION_CASES}
    assert reachable == set(ExecutionLogErrorCategory)


def test_approval_outcome_follows_committed_state() -> None:
    decision = ApprovalDecisionStatus
    execution = ApprovalExecutionStatus
    assert approval_outcome(decision.PENDING, execution.NOT_STARTED) is None
    assert (
        approval_outcome(decision.APPROVED, execution.SUCCEEDED)
        is ExecutionLogOutcome.APPROVED_EXECUTION_SUCCEEDED
    )
    assert (
        approval_outcome(decision.APPROVED, execution.FAILED)
        is ExecutionLogOutcome.APPROVED_EXECUTION_FAILED
    )
    for status in ("rejected", "cancelled", "expired", "invalidated"):
        assert approval_outcome(decision(status), execution.NOT_STARTED) is ExecutionLogOutcome(
            status
        )


def test_details_allow_only_permitted_keys_per_operation() -> None:
    generation = {
        "citation_count": 2,
        "generation_model": "gpt-5.6-terra",
        "prompt_version": "grounded-answer-v1",
        "input_tokens": 10,
        "output_tokens": None,
        "total_tokens": 10,
    }
    assert validate_details(Operation.KNOWLEDGE_ANSWER, generation) == generation
    assert validate_details(
        Operation.AGENT_ROUTE, {"tool_not_executed_reason": "no_matching_tool"}
    ) == {"tool_not_executed_reason": "no_matching_tool"}
    assert validate_details(Operation.APPROVAL_DECISION, {"decision": "reject"}) == {
        "decision": "reject"
    }
    assert validate_details(Operation.APPROVAL_CANCEL, {}) == {}

    for operation, details in (
        (Operation.APPROVAL_CANCEL, {"decision": "approve"}),
        (Operation.KNOWLEDGE_ANSWER, {"tool_not_executed_reason": "no_matching_tool"}),
        (Operation.APPROVAL_DECISION, {"citation_count": 1}),
        (Operation.AGENT_ROUTE, {"request": SECRET}),
        (Operation.AGENT_ROUTE, {"note": SECRET}),
    ):
        with pytest.raises(DisallowedDetailError):
            validate_details(operation, details)


@pytest.mark.parametrize(
    "details",
    [
        {"citation_count": -1},
        {"citation_count": 101},
        {"citation_count": "2"},
        {"input_tokens": -5},
        {"total_tokens": 1.5},
        {"generation_model": SECRET + " with spaces"},
        {"prompt_version": "x" * 65},
        {"tool_not_executed_reason": "because"},
    ],
)
def test_details_reject_invalid_values(details: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        validate_details(Operation.AGENT_ROUTE, details)


def test_latency_is_floored_non_negative_milliseconds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(execution_logs.time, "perf_counter", lambda: 10.0)
    assert execution_logs._elapsed_ms(8.7654) == 1234
    assert execution_logs._elapsed_ms(10.5) == 0
