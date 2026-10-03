import { requestJson } from "./api";
import { EvaluationCaseSummary, EvaluationCaseType, EvaluationExpectation, Page } from "./evaluation";

export type Rate = { matched: number; eligible: number; value: number | null };
export type RunMetrics = {
  overall_pass_rate: Rate; category_pass_rate: Record<EvaluationCaseType, Rate>;
  routing_match_rate: Rate; tool_selection_match_rate: Rate; tool_outcome_match_rate: Rate;
  permission_boundary_pass_rate: Rate; refusal_behavior_pass_rate: Rate;
  citation_requirement_compliance: Rate; error_rate: Rate; evaluation_coverage: Rate;
  latency_ms: { count: number; error_count: number; min: number | null; max: number | null;
    mean: number | null; median: number | null };
};
export type EvaluationRun = {
  id: string; workspace_id: string; dataset_id: string; agent_id: string; created_by: string;
  dataset_name: string; agent_name: string; status: "running" | "completed" | "failed";
  created_at: string; started_at: string; deadline_at: string; completed_at: string | null;
  total_cases: number; passed_cases: number; failed_cases: number; error_cases: number;
  pending_cases: number; failure_category: string | null; metrics: RunMetrics;
};
export type RunCase = {
  id: string; workspace_id: string; run_id: string; case_id: string; ordinal: number;
  case_type: EvaluationCaseType; name: string; result: "passed" | "failed" | "error" | null;
  attempted: boolean; latency_ms: number | null; error_category: string | null;
  started_at: string | null; completed_at: string | null;
};
export type RunCaseDetail = RunCase & {
  case_snapshot: Record<string, unknown>; test_input_snapshot: string;
  expected_behavior_snapshot: EvaluationExpectation; context_snapshot: Record<string, unknown>;
  actual_behavior: Record<string, unknown> | null; comparison_checks: Record<string, boolean> | null;
};
export type RunDetail = EvaluationRun & {
  dataset_snapshot: Record<string, unknown>; agent_snapshot: Record<string, unknown>;
  config_snapshot: Record<string, unknown>; configuration_sha256: string;
  snapshot_version: 1; scorer_version: "evaluation-scorer-v1"; provider_egress_acknowledged: boolean;
};
const root = (workspace: string) => `/api/workspaces/${workspace}/evaluation-runs`;
export async function activeRunCases(workspace: string, dataset: string, token: string) {
  const items: EvaluationCaseSummary[] = [];
  for (let offset = 0; ; offset += 100) {
    const page = await requestJson<Page<EvaluationCaseSummary>>(
      `/api/workspaces/${workspace}/evaluation-datasets/${dataset}/cases?status=active&limit=100&offset=${offset}`, {}, token);
    items.push(...page.items);
    if (page.items.length < 100) return items;
  }
}
export function createEvaluationRun(workspace: string, dataset: string, agent: string, acknowledged: boolean, token: string) {
  return requestJson<EvaluationRun>(`/api/workspaces/${workspace}/evaluation-datasets/${dataset}/runs`, {
    method: "POST", body: JSON.stringify({ agent_id: agent, provider_egress_acknowledged: acknowledged }),
    signal: AbortSignal.timeout(150_000),
  }, token);
}
export function listEvaluationRuns(workspace: string, dataset: string, offset: number, token: string) {
  return requestJson<Page<EvaluationRun>>(`${root(workspace)}?dataset_id=${dataset}&limit=50&offset=${offset}`, {}, token);
}
export function getEvaluationRun(workspace: string, run: string, token: string) {
  return requestJson<RunDetail>(`${root(workspace)}/${run}`, {}, token);
}
export function listRunCases(workspace: string, run: string, token: string) {
  return requestJson<Page<RunCase>>(`${root(workspace)}/${run}/cases?limit=100&offset=0`, {}, token);
}
export function getRunCase(workspace: string, run: string, id: string, token: string) {
  return requestJson<RunCaseDetail>(`${root(workspace)}/${run}/cases/${id}`, {}, token);
}
