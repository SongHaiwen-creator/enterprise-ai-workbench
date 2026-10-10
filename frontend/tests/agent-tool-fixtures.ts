import { type AgentConfiguration, type ToolConfiguration } from "@/utils/agent-tool-admin";
import type { AgentSummary } from "@/utils/api";
export const agentSummary = (agent: AgentConfiguration): AgentSummary => ({
  id: agent.id, workspace_id: agent.workspace_id, name: agent.name, description: agent.description,
  status: agent.status, created_by: agent.created_by, created_at: agent.created_at, updated_at: agent.updated_at,
});
export const agentFixture = (id = "a", status: AgentConfiguration["status"] = "draft"): AgentConfiguration => ({
  id, workspace_id: "w", name: `助手 ${id}`, description: "原描述", system_prompt: `Scope ${id}`, status,
  created_by: "u", created_at: "2026-10-10T00:00:00Z", updated_at: "2026-10-10T00:00:00Z",
});
export const toolFixture = (id = "t", status: ToolConfiguration["status"] = "disabled", tool_key = "get_reimbursement_status"): ToolConfiguration => ({
  id, workspace_id: "w", tool_key, name: `工具 ${id}`, description: "本人数据", status,
  operation_type: tool_key === "create_it_access_request" ? "write_sensitive" : "read_only",
  risk_level: tool_key === "create_it_access_request" ? "high" : "low", created_by: "u",
  created_at: "2026-10-10T00:00:00Z", updated_at: "2026-10-10T00:00:00Z",
});
export function deferred<T>() {
  let resolve!: (value: T) => void, reject!: (reason: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
