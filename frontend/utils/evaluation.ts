import { AgentSummary, KnowledgeBase, MembershipRole, PublicToolReference, requestJson } from "./api";

export type EvaluationStatus = "active" | "disabled";
export type EvaluationCaseType = "knowledge_qa" | "tool_calling" | "permission_boundary" | "refusal_behavior";
export type KnowledgeExpectation = {
  routing_intent: "knowledge_qa"; answer_status: "answered" | "unsupported";
  citation_requirement: "present" | "none";
};
export type ToolExpectation = {
  routing_intent: "tool_request"; outcome: "executed" | "approval_required" | "not_executed";
  tool_key: PublicToolReference["tool_key"] | null; approval_required: boolean;
  non_execution_reason: "no_available_tool" | "no_matching_tool" | "missing_required_arguments" | null;
};
export type PermissionExpectation = {
  actor_role: MembershipRole; actor_membership_status: "active" | "invited" | "disabled" | "absent";
  target_context: "same_workspace" | "other_workspace" | "nonexistent";
  operation: "agent_route" | "knowledge_answer" | "agent_configuration_read" | "tool_configuration_read" | "evaluation_dataset_read";
  expected_http_status: 403 | 404; result_category: "forbidden" | "not_found"; access_denied: true;
};
export type RefusalExpectation = {
  routing_intent: "unsupported" | "knowledge_qa";
  response_category: "unsupported_request" | "knowledge_unsupported"; safe_response_required: true;
};
export type EvaluationExpectation = KnowledgeExpectation | ToolExpectation | PermissionExpectation | RefusalExpectation;
export interface EvaluationDataset {
  id: string; workspace_id: string; name: string; description: string | null;
  status: EvaluationStatus; created_by: string; created_at: string; updated_at: string;
}
export interface EvaluationCaseSummary extends EvaluationDataset {
  dataset_id: string; case_type: EvaluationCaseType; schema_version: 1;
  agent_id: string | null; knowledge_base_id: string | null; tool_id: string | null;
}
export interface EvaluationCase extends EvaluationCaseSummary {
  test_input: string; expected_behavior: EvaluationExpectation;
}
export type DatasetCreate = { name: string; description?: string | null };
export type DatasetUpdate = Partial<DatasetCreate & { status: EvaluationStatus }>;
export type CaseCreate = DatasetCreate & {
  case_type: EvaluationCaseType; test_input: string; expected_behavior: EvaluationExpectation;
  agent_id?: string | null; knowledge_base_id?: string | null; tool_id?: string | null;
};
export type CaseUpdate = Partial<Omit<CaseCreate, "case_type"> & { status: EvaluationStatus }>;
export type Page<T> = { items: T[]; limit: number; offset: number };
export interface EvaluationTool extends PublicToolReference { id: string; status: EvaluationStatus }

const root = (workspace: string) => `/api/workspaces/${workspace}/evaluation-datasets`;
const pageQuery = (offset: number) => `?limit=50&offset=${offset}`;
export function listEvaluationDatasets(workspace: string, offset: number, token: string) {
  return requestJson<Page<EvaluationDataset>>(root(workspace) + pageQuery(offset), {}, token);
}
export function getEvaluationDataset(workspace: string, dataset: string, token: string) {
  return requestJson<EvaluationDataset>(`${root(workspace)}/${dataset}`, {}, token);
}
export function createEvaluationDataset(workspace: string, payload: DatasetCreate, token: string) {
  return requestJson<EvaluationDataset>(root(workspace), { method: "POST", body: JSON.stringify(payload) }, token);
}
export function updateEvaluationDataset(workspace: string, dataset: string, payload: DatasetUpdate, token: string) {
  return requestJson<EvaluationDataset>(`${root(workspace)}/${dataset}`, { method: "PATCH", body: JSON.stringify(payload) }, token);
}
export function listEvaluationCases(workspace: string, dataset: string, offset: number, token: string) {
  return requestJson<Page<EvaluationCaseSummary>>(`${root(workspace)}/${dataset}/cases${pageQuery(offset)}`, {}, token);
}
export function getEvaluationCase(workspace: string, dataset: string, id: string, token: string) {
  return requestJson<EvaluationCase>(`${root(workspace)}/${dataset}/cases/${id}`, {}, token);
}
export function createEvaluationCase(workspace: string, dataset: string, payload: CaseCreate, token: string) {
  return requestJson<EvaluationCase>(`${root(workspace)}/${dataset}/cases`, { method: "POST", body: JSON.stringify(payload) }, token);
}
export function updateEvaluationCase(workspace: string, dataset: string, id: string, payload: CaseUpdate, token: string) {
  return requestJson<EvaluationCase>(`${root(workspace)}/${dataset}/cases/${id}`, { method: "PATCH", body: JSON.stringify(payload) }, token);
}
export async function evaluationResources(workspace: string, token: string) {
  const [agents, knowledgeBases, tools] = await Promise.all([
    requestJson<AgentSummary[]>(`/api/workspaces/${workspace}/agents?include_inactive=true`, {}, token),
    requestJson<KnowledgeBase[]>(`/api/workspaces/${workspace}/knowledge-bases`, {}, token),
    requestJson<EvaluationTool[]>(`/api/workspaces/${workspace}/tools`, {}, token),
  ]);
  return { agents, knowledgeBases, tools };
}
