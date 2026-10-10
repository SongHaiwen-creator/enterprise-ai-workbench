import { type AgentSummary, type PublicToolReference, requestJson } from "./api";
import registeredToolHelp from "./registered-tool-help.json";

export type ToolKey = PublicToolReference["tool_key"];
export type AgentConfiguration = AgentSummary & { system_prompt: string };
export type AgentCreate = { name: string; description?: string | null; system_prompt: string };
export type AgentUpdate = Partial<AgentCreate> & { status?: AgentSummary["status"] };
export type ToolConfiguration = {
  id: string; workspace_id: string; tool_key: string; name: string; description: string;
  operation_type: "read_only" | "write_sensitive"; risk_level: "low" | "medium" | "high";
  status: "active" | "disabled"; created_by: string; created_at: string; updated_at: string;
};
export type ToolCreate = { tool_key: ToolKey; name: string; description: string };
export type ToolUpdate = Partial<Pick<ToolCreate, "name" | "description">> & { status?: ToolConfiguration["status"] };

// Help text only. Runtime validation and authorization remain backend-owned.
export const TOOL_HELP = registeredToolHelp;
export function toolHelp(key: string) { return TOOL_HELP.find(item => item.tool_key === key); }
export function isToolKey(key: string): key is ToolKey { return !!toolHelp(key); }
export function usableConfiguration(tool: ToolConfiguration) {
  const help = toolHelp(tool.tool_key);
  return !!help && help.operation_type === tool.operation_type && help.risk_level === tool.risk_level;
}
const root = (workspace: string) => `/api/workspaces/${workspace}`;
export function listManagedAgents(workspace: string, token: string) {
  return requestJson<AgentSummary[]>(`${root(workspace)}/agents?include_inactive=true`, {}, token);
}
export function getAgent(workspace: string, agent: string, token: string) {
  return requestJson<AgentConfiguration>(`${root(workspace)}/agents/${agent}`, {}, token);
}
export function createAgent(workspace: string, payload: AgentCreate, token: string) {
  return requestJson<AgentConfiguration>(`${root(workspace)}/agents`, { method: "POST", body: JSON.stringify(payload) }, token);
}
export function updateAgent(workspace: string, agent: string, payload: AgentUpdate, token: string) {
  return requestJson<AgentConfiguration>(`${root(workspace)}/agents/${agent}`, { method: "PATCH", body: JSON.stringify(payload) }, token);
}
export function listTools(workspace: string, token: string) {
  return requestJson<ToolConfiguration[]>(`${root(workspace)}/tools`, {}, token);
}
export function getTool(workspace: string, tool: string, token: string) {
  return requestJson<ToolConfiguration>(`${root(workspace)}/tools/${tool}`, {}, token);
}
export function createTool(workspace: string, payload: ToolCreate, token: string) {
  return requestJson<ToolConfiguration>(`${root(workspace)}/tools`, { method: "POST", body: JSON.stringify(payload) }, token);
}
export function updateTool(workspace: string, tool: string, payload: ToolUpdate, token: string) {
  return requestJson<ToolConfiguration>(`${root(workspace)}/tools/${tool}`, { method: "PATCH", body: JSON.stringify(payload) }, token);
}
export function listAgentTools(workspace: string, agent: string, token: string) {
  return requestJson<ToolConfiguration[]>(`${root(workspace)}/agents/${agent}/tools`, {}, token);
}
export function assignTool(workspace: string, agent: string, tool: string, token: string) {
  return requestJson<ToolConfiguration>(`${root(workspace)}/agents/${agent}/tools/${tool}`, { method: "PUT" }, token);
}
export function unassignTool(workspace: string, agent: string, tool: string, token: string) {
  return requestJson<void>(`${root(workspace)}/agents/${agent}/tools/${tool}`, { method: "DELETE" }, token);
}
