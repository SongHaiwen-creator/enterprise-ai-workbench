from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, StrictBool, StrictInt

from app.schemas.evaluation import CaseType, StrictModel, ToolKey

RunStatus = Literal["running", "completed", "failed"]
CaseResult = Literal["passed", "failed", "error"]
ErrorCategory = Literal[
    "provider_configuration",
    "provider_failure",
    "provider_contract",
    "input_budget",
    "resource_configuration",
    "configuration_drift",
    "authorization_revoked",
    "case_timeout",
    "run_timeout",
    "persistence_failure",
    "interrupted",
    "internal_error",
]
Intent = Literal["knowledge_qa", "tool_request", "unsupported"]


class RunCreate(StrictModel):
    agent_id: UUID
    provider_egress_acknowledged: StrictBool


class KnowledgeActual(StrictModel):
    routing_intent: Intent
    answer_status: Literal["answered", "unsupported"] | None = None
    citation_count: StrictInt | None = Field(default=None, ge=0)
    knowledge_base_id: UUID | None = None
    evidence: list[dict[str, str | int]] = Field(default_factory=list)


class ToolActual(StrictModel):
    routing_intent: Intent
    tool_id: UUID | None = None
    tool_key: ToolKey | None = None
    would_outcome: Literal["executed", "approval_required", "not_executed"] | None = None
    approval_required: StrictBool | None = None
    non_execution_reason: (
        Literal["no_available_tool", "no_matching_tool", "missing_required_arguments"] | None
    ) = None
    execution_mode: Literal["dry_run"] = "dry_run"
    adapter_executed: Literal[False] = False


class PermissionActual(StrictModel):
    http_status: Literal[200, 403, 404, 409]
    result_category: Literal["allowed", "forbidden", "not_found", "conflict"]
    access_denied: StrictBool
    policy_version: Literal["workspace-policy-v1"] = "workspace-policy-v1"
    execution_mode: Literal["policy_simulation"] = "policy_simulation"


class RefusalActual(StrictModel):
    routing_intent: Intent
    response_category: (
        Literal["unsupported_request", "knowledge_unsupported", "knowledge_answered"] | None
    ) = None
    safe_response: StrictBool = False
    evidence: list[dict[str, str | int]] = Field(default_factory=list)


ACTUAL_MODELS = {
    "knowledge_qa": KnowledgeActual,
    "tool_calling": ToolActual,
    "permission_boundary": PermissionActual,
    "refusal_behavior": RefusalActual,
}


class Rate(StrictModel):
    matched: int
    eligible: int
    value: float | None


class LatencySummary(StrictModel):
    count: int
    error_count: int
    min: int | None
    max: int | None
    mean: float | None
    median: float | None


class Metrics(StrictModel):
    overall_pass_rate: Rate
    category_pass_rate: dict[CaseType, Rate]
    routing_match_rate: Rate
    tool_selection_match_rate: Rate
    tool_outcome_match_rate: Rate
    permission_boundary_pass_rate: Rate
    refusal_behavior_pass_rate: Rate
    citation_requirement_compliance: Rate
    error_rate: Rate
    evaluation_coverage: Rate
    latency_ms: LatencySummary


class RunSummary(StrictModel):
    id: UUID
    workspace_id: UUID
    dataset_id: UUID
    agent_id: UUID
    created_by: UUID
    dataset_name: str
    agent_name: str
    status: RunStatus
    created_at: datetime
    started_at: datetime
    deadline_at: datetime
    completed_at: datetime | None
    total_cases: int
    passed_cases: int
    failed_cases: int
    error_cases: int
    pending_cases: int
    failure_category: ErrorCategory | None
    metrics: Metrics


class RunDetail(RunSummary):
    dataset_snapshot: dict
    agent_snapshot: dict
    config_snapshot: dict
    snapshot_version: Literal[1]
    scorer_version: Literal["evaluation-scorer-v1"]
    configuration_sha256: str
    provider_egress_acknowledged: StrictBool


class RunCaseSummary(StrictModel):
    id: UUID
    workspace_id: UUID
    run_id: UUID
    case_id: UUID
    ordinal: int
    case_type: CaseType
    name: str
    result: CaseResult | None
    attempted: bool
    latency_ms: int | None
    error_category: ErrorCategory | None
    started_at: datetime | None
    completed_at: datetime | None


class RunCaseDetail(RunCaseSummary):
    case_snapshot: dict
    test_input_snapshot: str
    expected_behavior_snapshot: dict
    context_snapshot: dict
    actual_behavior: KnowledgeActual | ToolActual | PermissionActual | RefusalActual | None
    comparison_checks: dict[str, bool] | None


class RunList(StrictModel):
    items: list[RunSummary]
    limit: int
    offset: int


class RunCaseList(StrictModel):
    items: list[RunCaseSummary]
    limit: int
    offset: int
