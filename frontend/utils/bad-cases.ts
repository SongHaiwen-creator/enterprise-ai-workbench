import { requestJson } from "./api";
import { Page } from "./evaluation";
import { RunCaseDetail } from "./evaluation-runs";

export const categories = {
  unclassified: "未分类", routing: "请求路由", knowledge: "知识", tool_planning: "工具规划",
  permission: "权限", refusal: "拒绝行为", runtime: "运行环境", other: "其他",
} as const;
export const statuses = { open: "待处理", investigating: "处理中", resolved: "已处理（人工）", dismissed: "不处理（人工）" } as const;
export const origins = { behavior_failure: "结构化行为未通过（FAIL）", execution_error: "运行错误（ERROR）", manual_review: "通过结果的人工复核（PASS）" } as const;
export type Category = keyof typeof categories;
export type Status = keyof typeof statuses;
export type Origin = keyof typeof origins;
export type HumanValues = {
  title: string; description: string; category: Category; possible_cause: string | null;
  handling_note: string | null; status: Status; resolution_note: string | null;
};
export type BadCaseSummary = {
  id: string; workspace_id: string; source_run_case_id: string; source_run_id: string;
  source_case_id: string; dataset_id: string; agent_id: string; source_result: "passed" | "failed" | "error";
  source_case_type: RunCaseDetail["case_type"]; origin_kind: Origin; title: string; category: Category;
  status: Status; created_by: string; updated_by: string; created_at: string; updated_at: string; revision: number;
};
export type BadCaseDetail = BadCaseSummary & HumanValues & { source_evidence: RunCaseDetail };
export type HistoryItem = {
  id: string; workspace_id: string; bad_case_id: string; actor_id: string; revision: number;
  event: "created" | "updated"; created_at: string; change_reason: string | null;
  before_values: Partial<HumanValues> | null; after_values: Partial<HumanValues>;
};
export type Filters = { status?: Status; category?: Category; origin_kind?: Origin; source_run_id?: string; source_run_case_id?: string };
const root = (workspace: string) => `/api/workspaces/${workspace}/bad-cases`;
export function listBadCases(workspace: string, filters: Filters, offset: number, token: string) {
  const query = new URLSearchParams({ limit: "50", offset: String(offset) });
  Object.entries(filters).forEach(([key, value]) => { if (value) query.set(key, value); });
  return requestJson<Page<BadCaseSummary>>(`${root(workspace)}?${query}`, {}, token);
}
export function getBadCase(workspace: string, id: string, token: string) {
  return requestJson<BadCaseDetail>(`${root(workspace)}/${id}`, {}, token);
}
export function getBadCaseHistory(workspace: string, id: string, offset: number, token: string) {
  return requestJson<Page<HistoryItem>>(`${root(workspace)}/${id}/history?limit=50&offset=${offset}`, {}, token);
}
export function createBadCase(workspace: string, source: RunCaseDetail, payload: Pick<HumanValues, "title" | "description" | "category" | "possible_cause">, token: string) {
  return requestJson<BadCaseDetail>(`/api/workspaces/${workspace}/evaluation-runs/${source.run_id}/cases/${source.id}/bad-case`, {
    method: "POST", body: JSON.stringify(payload), signal: AbortSignal.timeout(20_000),
  }, token);
}
export function updateBadCase(workspace: string, id: string, payload: Partial<HumanValues> & { expected_revision: number; change_reason?: string | null }, token: string) {
  return requestJson<BadCaseDetail>(`${root(workspace)}/${id}`, {
    method: "PATCH", body: JSON.stringify(payload), signal: AbortSignal.timeout(20_000),
  }, token);
}
