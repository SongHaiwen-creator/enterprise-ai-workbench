import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { AgentToolAdmin } from "@/app/components/agent-tool-admin";
import { ApiError, type AgentSummary, type MembershipRole, listAgents } from "@/utils/api";
import {
  type AgentConfiguration, type ToolConfiguration, assignTool, createAgent, createTool, getAgent,
  getTool, listAgentTools, listManagedAgents, listTools, unassignTool, updateAgent, updateTool,
} from "@/utils/agent-tool-admin";
import { agentFixture, agentSummary, deferred, toolFixture } from "./agent-tool-fixtures";

vi.mock("@/utils/api", async original => ({ ...await original<typeof import("@/utils/api")>(), listAgents: vi.fn() }));
vi.mock("@/utils/agent-tool-admin", async original => ({
  ...await original<typeof import("@/utils/agent-tool-admin")>(), assignTool: vi.fn(), createAgent: vi.fn(), createTool: vi.fn(),
  getAgent: vi.fn(), getTool: vi.fn(), listAgentTools: vi.fn(), listManagedAgents: vi.fn(), listTools: vi.fn(),
  unassignTool: vi.fn(), updateAgent: vi.fn(), updateTool: vi.fn(),
}));
let agents: AgentConfiguration[], tools: ToolConfiguration[], assignments: ToolConfiguration[];
const onUnauthorized = vi.fn(), onPendingChange = vi.fn(), onAgentsChange = vi.fn();
const props = { workspaceId: "w", accessToken: "token", role: "agent_admin" as MembershipRole, onUnauthorized, onPendingChange, onAgentsChange };
const originalShow = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, "showModal");
const originalClose = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, "close");
beforeAll(() => {
  Object.defineProperty(HTMLDialogElement.prototype, "showModal", { configurable: true, value: function (this: HTMLDialogElement) { this.setAttribute("open", ""); } });
  Object.defineProperty(HTMLDialogElement.prototype, "close", { configurable: true, value: function (this: HTMLDialogElement) { this.removeAttribute("open"); } });
});
afterAll(() => {
  if (originalShow) Object.defineProperty(HTMLDialogElement.prototype, "showModal", originalShow); else Reflect.deleteProperty(HTMLDialogElement.prototype, "showModal");
  if (originalClose) Object.defineProperty(HTMLDialogElement.prototype, "close", originalClose); else Reflect.deleteProperty(HTMLDialogElement.prototype, "close");
});
beforeEach(() => {
  vi.resetAllMocks(); agents = [agentFixture()]; tools = [toolFixture()]; assignments = [];
  vi.mocked(listManagedAgents).mockImplementation(async () => agents.map(agentSummary));
  vi.mocked(getAgent).mockImplementation(async (_w, id) => agents.find(item => item.id === id)!);
  vi.mocked(listTools).mockImplementation(async () => tools);
  vi.mocked(getTool).mockImplementation(async (_w, id) => tools.find(item => item.id === id)!);
  vi.mocked(listAgentTools).mockImplementation(async () => assignments);
  vi.mocked(listAgents).mockImplementation(async () => agents.filter(item => item.status === "active").map(agentSummary));
  vi.mocked(updateAgent).mockImplementation(async (_w, id, patch) => {
    agents = agents.map(item => item.id === id ? { ...item, ...patch } as AgentConfiguration : item);
    return agents.find(item => item.id === id)!;
  });
  vi.mocked(updateTool).mockImplementation(async (_w, id, patch) => {
    tools = tools.map(item => item.id === id ? { ...item, ...patch } as ToolConfiguration : item);
    return tools.find(item => item.id === id)!;
  });
  vi.mocked(assignTool).mockImplementation(async (_w, _a, id) => { assignments = [tools.find(item => item.id === id)!]; return assignments[0]; });
  vi.mocked(unassignTool).mockImplementation(async () => { assignments = []; });
  vi.mocked(createAgent).mockImplementation(async (_w, patch) => { const created = { ...agentFixture("new"), ...patch }; agents.push(created); return created; });
  vi.mocked(createTool).mockImplementation(async (_w, patch) => { const created = { ...toolFixture("new", "disabled", patch.tool_key), ...patch }; tools.push(created); return created; });
});
afterEach(cleanup);
async function mount() {
  const view = render(<AgentToolAdmin {...props} />);
  await waitFor(() => expect(screen.getByLabelText("Agent 名称")).toBeEnabled());
  return { ...view, user: userEvent.setup() };
}
async function toolTab(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: "工具配置" }));
  await waitFor(() => expect(screen.getByLabelText("工具名称")).toBeEnabled());
}
async function confirm(user: ReturnType<typeof userEvent.setup>) { await user.click(screen.getByRole("button", { name: "确认继续" })); }
describe("Agent and Tool administration", () => {
  it.each(["employee", "knowledge_admin"] as const)("does not fetch protected configuration for %s", role => {
    render(<AgentToolAdmin {...props} role={role} />);
    expect(screen.getByRole("alert")).toHaveTextContent("管理员");
    expect(listManagedAgents).not.toHaveBeenCalled(); expect(listTools).not.toHaveBeenCalled(); expect(getAgent).not.toHaveBeenCalled();
  });
  it.each(["agent_admin", "system_admin"] as const)("lets %s read full config without execution calls", async role => {
    render(<AgentToolAdmin {...props} role={role} />);
    await waitFor(() => expect(screen.getByLabelText("系统提示词")).toHaveValue("Scope a"));
    expect(listManagedAgents).toHaveBeenCalledWith("w", "token"); expect(listAgentTools).toHaveBeenCalledWith("w", "a", "token");
    expect(onAgentsChange).not.toHaveBeenCalled(); expect(assignTool).not.toHaveBeenCalled();
  });
  it("creates a draft in an empty workspace without assigning all tools", async () => {
    agents = []; tools = []; render(<AgentToolAdmin {...props} />); const user = userEvent.setup();
    await screen.findByText("暂无 Agent，可先创建草稿。");
    await user.click(screen.getByRole("button", { name: "新建 Agent" }));
    await user.type(screen.getByLabelText("Agent 名称"), "  重复名称  ");
    await user.type(screen.getByLabelText("系统提示词"), "  Approved scope  ");
    await user.click(screen.getByRole("button", { name: "创建 Agent" }));
    await screen.findByText("Agent 已创建为草稿，尚未开放使用。");
    expect(createAgent).toHaveBeenCalledWith("w", { name: "重复名称", description: null, system_prompt: "Approved scope" }, "token");
    expect(onAgentsChange).toHaveBeenLastCalledWith([]); expect(assignTool).not.toHaveBeenCalled();
  });
  it("saves only modified fields, clears description and avoids no-op PATCH", async () => {
    const { user } = await mount(); await user.click(screen.getByRole("button", { name: "保存 Agent" }));
    expect(updateAgent).not.toHaveBeenCalled();
    await user.clear(screen.getByLabelText("Agent 描述"));
    await user.click(screen.getByRole("button", { name: "保存 Agent" }));
    await screen.findByText("Agent 已保存。"); expect(updateAgent).toHaveBeenCalledWith("w", "a", { description: null }, "token");
  });
  it.each([["Agent 名称", " "], ["Agent 名称", "x".repeat(256)], ["系统提示词", " "], ["系统提示词", "x".repeat(8001)], ["Agent 描述", "x".repeat(5001)]])("validates %s before a write", async (label, value) => {
    await mount(); fireEvent.change(screen.getByLabelText(label), { target: { value } });
    fireEvent.submit(screen.getByRole("button", { name: "保存 Agent" }).closest("form")!);
    expect(screen.getByRole("alert")).toHaveTextContent("字符"); expect(updateAgent).not.toHaveBeenCalled();
  });
  it.each(["draft", "active", "disabled"] as const)("offers the other two states from %s and confirms transition", async status => {
    agents = [agentFixture("a", status)]; const { user } = await mount();
    const labels = { draft: "改为草稿", active: "启用 Agent", disabled: "禁用 Agent" };
    expect(screen.queryByRole("button", { name: labels[status] })).not.toBeInTheDocument();
    const next = status === "active" ? "draft" : "active";
    await user.click(screen.getByRole("button", { name: labels[next] }));
    expect(updateAgent).not.toHaveBeenCalled(); await user.click(screen.getByRole("button", { name: "取消", exact: true }));
    expect(updateAgent).not.toHaveBeenCalled(); await user.click(screen.getByRole("button", { name: labels[next] })); await confirm(user);
    await screen.findByText("Agent 状态已更新。"); expect(updateAgent).toHaveBeenCalledWith("w", "a", { status: next }, "token");
    await waitFor(() => expect(onAgentsChange).toHaveBeenLastCalledWith(next === "active" ? [expect.objectContaining({ status: "active" })] : []));
  });
  it("preserves the draft when abandoning a selection is cancelled", async () => {
    agents.push(agentFixture("b")); const { user } = await mount();
    await user.type(screen.getByLabelText("Agent 名称"), "修改");
    await user.click(screen.getByRole("button", { name: /助手 b/ }));
    expect(screen.getByRole("dialog")).toHaveTextContent("未保存");
    fireEvent(screen.getByRole("dialog"), new Event("cancel", { bubbles: true, cancelable: true })); expect(screen.getByLabelText("Agent 名称")).toHaveValue("助手 a修改");
    await user.click(screen.getByRole("button", { name: /助手 b/ })); await confirm(user);
    await waitFor(() => expect(screen.getByLabelText("Agent 名称")).toHaveValue("助手 b")); expect(updateAgent).not.toHaveBeenCalled();
  });
  it("discards unsaved input only after confirming a tab change", async () => {
    const { user } = await mount(); await user.type(screen.getByLabelText("系统提示词"), "Draft");
    await user.click(screen.getByRole("button", { name: "工具配置" })); await confirm(user);
    await screen.findByLabelText("工具名称"); expect(screen.queryByLabelText("系统提示词")).not.toBeInTheDocument();
  });
  it("creates only an unconfigured registered tool, disabled by default", async () => {
    const { user } = await mount(); await toolTab(user); await user.click(screen.getByRole("button", { name: "新建工具" }));
    expect(screen.queryByRole("option", { name: "查询本人报销状态" })).not.toBeInTheDocument();
    await user.type(screen.getByLabelText("工具名称"), "  本人资料  "); await user.type(screen.getByLabelText("工具说明"), "  仅查询本人  ");
    await user.click(screen.getByRole("button", { name: "创建工具" }));
    await screen.findByText("工具已创建为禁用状态，尚未开放使用。");
    expect(createTool).toHaveBeenCalledWith("w", { tool_key: "get_employee_information", name: "本人资料", description: "仅查询本人" }, "token");
    expect(updateTool).not.toHaveBeenCalled(); expect(assignTool).not.toHaveBeenCalled();
  });
  it("disables creation when all three registry capabilities are configured", async () => {
    tools.push(toolFixture("self", "disabled", "get_employee_information"), toolFixture("write", "disabled", "create_it_access_request"));
    const { user } = await mount(); await toolTab(user);
    expect(screen.getByRole("button", { name: "新建工具" })).toBeDisabled(); expect(screen.getByText("所有注册能力均已配置。")).toBeInTheDocument();
  });
  it.each(["工具名称", "工具说明"])("rejects a blank %s", async label => {
    const { user } = await mount(); await toolTab(user); fireEvent.change(screen.getByLabelText(label), { target: { value: " " } });
    fireEvent.submit(screen.getByRole("button", { name: "保存工具" }).closest("form")!);
    expect(screen.getByRole("alert")).toHaveTextContent("字符"); expect(updateTool).not.toHaveBeenCalled();
  });
  it("keeps write capability parameters and approval policies read-only", async () => {
    tools = [toolFixture("write", "disabled", "create_it_access_request")]; const { user } = await mount(); await toolTab(user);
    const help = screen.getByRole("region", { name: "能力限制" });
    expect(help).toHaveTextContent("72 小时"); expect(help).toHaveTextContent("1–90"); expect(help).toHaveTextContent("生产数据库仅允许 read_only");
    expect(screen.queryByLabelText("风险级别")).not.toBeInTheDocument(); expect(screen.queryByRole("button", { name: /执行|试运行/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "启用工具" })); await confirm(user);
    await screen.findByText("工具状态已更新。"); expect(updateTool).toHaveBeenCalledWith("w", "write", { status: "active" }, "token");
  });
  it("saves tool display metadata without status or immutable fields", async () => {
    const { user } = await mount(); await toolTab(user); await user.click(screen.getByRole("button", { name: "保存工具" })); expect(updateTool).not.toHaveBeenCalled();
    await user.clear(screen.getByLabelText("工具说明")); await user.type(screen.getByLabelText("工具说明"), "新的显示说明");
    await user.click(screen.getByRole("button", { name: "保存工具" })); await screen.findByText("工具已保存。");
    expect(updateTool).toHaveBeenCalledWith("w", "t", { description: "新的显示说明" }, "token");
  });
  it("shows staged assignment and removes only the association", async () => {
    const { user } = await mount(); await user.click(screen.getByRole("button", { name: "分配 工具 t" })); await confirm(user);
    await screen.findByText(/已分配，当前未生效/); expect(assignTool).toHaveBeenCalledWith("w", "a", "t", "token");
    await waitFor(() => expect(screen.getByRole("button", { name: "解除 工具 t" })).toBeEnabled());
    await user.click(screen.getByRole("button", { name: "解除 工具 t" })); expect(screen.getByRole("dialog")).toHaveTextContent("不删除工具"); await confirm(user);
    await screen.findByText("工具关联已解除。"); expect(unassignTool).toHaveBeenCalledWith("w", "a", "t", "token"); expect(updateTool).not.toHaveBeenCalled();
  });
  it("shows active assignment as a candidate condition, not execution authorization", async () => {
    agents = [agentFixture("a", "active")]; tools = [toolFixture("t", "active")]; assignments = tools;
    await mount(); expect(screen.getByText(/满足候选状态条件/)).toBeInTheDocument(); expect(screen.getByText(/后端仍检查当前权限/)).toBeInTheDocument();
  });
  it("does not render an assignment read failure as an empty allowlist", async () => {
    vi.mocked(listAgentTools).mockRejectedValue(new ApiError("Unavailable", 500)); render(<AgentToolAdmin {...props} />);
    await screen.findByRole("alert"); expect(screen.queryByRole("button", { name: "分配 工具 t" })).not.toBeInTheDocument();
  });
  it("blocks unknown registry configurations", async () => {
    tools = [toolFixture("unknown", "active", "unknown")]; await mount();
    expect(screen.getByRole("button", { name: "分配 工具 unknown" })).toBeDisabled();
    const user = userEvent.setup(); await user.click(screen.getByRole("button", { name: "工具配置" }));
    await screen.findByLabelText("工具名称"); expect(screen.getByRole("button", { name: "禁用工具" })).toBeDisabled();
  });
  it.each([401, 403])("clears protected configuration after %s", async status => {
    const { user } = await mount(); vi.mocked(updateAgent).mockRejectedValue(new ApiError("Denied", status));
    await user.type(screen.getByLabelText("系统提示词"), "private draft"); await user.click(screen.getByRole("button", { name: "保存 Agent" }));
    await waitFor(() => expect(screen.queryByLabelText("系统提示词")).not.toBeInTheDocument());
    expect(onAgentsChange).toHaveBeenLastCalledWith(null); expect(onUnauthorized).toHaveBeenCalledTimes(status === 401 ? 1 : 0);
  });
  it("preserves editable input for 422 without a write retry", async () => {
    const { user } = await mount(); vi.mocked(updateAgent).mockRejectedValue(new ApiError("Invalid", 422));
    await user.type(screen.getByLabelText("Agent 名称"), "修正"); await user.click(screen.getByRole("button", { name: "保存 Agent" }));
    await screen.findByRole("alert"); expect(screen.getByLabelText("Agent 名称")).toHaveValue("助手 a修正"); expect(updateAgent).toHaveBeenCalledTimes(1);
  });
  it.each([0, 500, 503])("requires verification after an ambiguous write %s", async status => {
    const { user } = await mount(); vi.mocked(updateAgent).mockRejectedValue(new ApiError("Private exception", status));
    await user.type(screen.getByLabelText("Agent 名称"), "修改"); await user.click(screen.getByRole("button", { name: "保存 Agent" }));
    await screen.findByRole("alert"); expect(screen.getByRole("button", { name: "保存 Agent" })).toBeDisabled();
    expect(screen.getByRole("alert")).not.toHaveTextContent("Private exception"); expect(updateAgent).toHaveBeenCalledTimes(1);
  });
  it("separates successful write from failed refresh, disabling another write", async () => {
    const { user } = await mount(); vi.mocked(listAgents).mockRejectedValue(new ApiError("Unavailable", 500));
    await user.type(screen.getByLabelText("Agent 名称"), "改名"); await user.click(screen.getByRole("button", { name: "保存 Agent" }));
    await screen.findByText(/操作已完成，列表刷新失败/); expect(updateAgent).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "保存 Agent" })).toBeDisabled(); expect(onAgentsChange).toHaveBeenLastCalledWith(null);
  });
  it("recovers a duplicate tool creation with GET, not another POST", async () => {
    const { user } = await mount(); await toolTab(user); await user.click(screen.getByRole("button", { name: "新建工具" }));
    await user.type(screen.getByLabelText("工具名称"), "Self"); await user.type(screen.getByLabelText("工具说明"), "Only self");
    vi.mocked(createTool).mockImplementation(async () => { tools.push(toolFixture("existing", "disabled", "get_employee_information")); throw new ApiError("Duplicate", 409); });
    await user.click(screen.getByRole("button", { name: "创建工具" })); await waitFor(() => expect(screen.getByLabelText("工具名称")).toHaveValue("工具 existing"));
    expect(createTool).toHaveBeenCalledTimes(1); expect(listTools).toHaveBeenCalledTimes(2);
  });
  it("clears a missing detail and lets the user refresh", async () => {
    vi.mocked(getAgent).mockRejectedValue(new ApiError("Missing", 404)); render(<AgentToolAdmin {...props} />);
    await screen.findByRole("alert"); expect(screen.queryByLabelText("系统提示词")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "刷新配置" })).toBeEnabled();
  });
  it("blocks synchronous double submission and releases pending after success", async () => {
    const request = deferred<AgentConfiguration>(); const { user } = await mount();
    vi.mocked(updateAgent).mockReturnValue(request.promise); await user.type(screen.getByLabelText("Agent 名称"), "双击");
    const form = screen.getByRole("button", { name: "保存 Agent" }).closest("form")!; fireEvent.submit(form); fireEvent.submit(form);
    expect(updateAgent).toHaveBeenCalledTimes(1); expect(onPendingChange).toHaveBeenLastCalledWith(true);
    expect(screen.getByRole("button", { name: "工具配置" })).toBeDisabled();
    await act(async () => request.resolve(agentFixture())); await waitFor(() => expect(onPendingChange).toHaveBeenLastCalledWith(false));
  });
  it("discards a mutation result and shared callback after unmount", async () => {
    const request = deferred<AgentConfiguration>(); const { user, unmount } = await mount();
    vi.mocked(updateAgent).mockReturnValue(request.promise); await user.type(screen.getByLabelText("Agent 名称"), "late");
    await user.click(screen.getByRole("button", { name: "保存 Agent" })); const count = onAgentsChange.mock.calls.length;
    unmount(); await act(async () => request.resolve(agentFixture())); expect(onAgentsChange).toHaveBeenCalledTimes(count); expect(listAgents).not.toHaveBeenCalled();
  });
  it("ignores an old shared-list refresh after a newer mutation", async () => {
    agents = [agentFixture("a", "active")]; const old = deferred<AgentSummary[]>();
    const { user } = await mount(); vi.mocked(listAgents).mockReturnValueOnce(old.promise);
    await user.click(screen.getByRole("button", { name: "刷新配置" }));
    await waitFor(() => expect(listAgents).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByLabelText("Agent 名称")).toBeEnabled());
    await user.type(screen.getByLabelText("Agent 名称"), "NEW"); await user.click(screen.getByRole("button", { name: "保存 Agent" }));
    await waitFor(() => expect(onAgentsChange).toHaveBeenLastCalledWith([expect.objectContaining({ name: "助手 aNEW" })]));
    await act(async () => old.resolve([{ ...agentFixture("stale", "active"), name: "STALE" }]));
    expect(onAgentsChange).toHaveBeenLastCalledWith([expect.objectContaining({ name: "助手 aNEW" })]);
  });
  it("drops old detail responses after choosing a new Agent", async () => {
    agents.push(agentFixture("b")); const request = deferred<AgentConfiguration>(); vi.mocked(getAgent).mockReturnValueOnce(request.promise);
    render(<AgentToolAdmin {...props} />); await screen.findByRole("button", { name: /助手 b/ });
    // Initial list load awaits detail, so use the tab to start a new scoped read.
    const user = userEvent.setup(); await user.click(screen.getByRole("button", { name: "工具配置" })); await screen.findByLabelText("工具名称");
    await user.click(screen.getByRole("button", { name: "Agent 配置" })); await waitFor(() => expect(screen.getByLabelText("Agent 名称")).toBeEnabled());
    await user.click(screen.getByRole("button", { name: /助手 b/ })); await waitFor(() => expect(screen.getByLabelText("Agent 名称")).toHaveValue("助手 b"));
    await act(async () => request.resolve({ ...agentFixture(), system_prompt: "STALE" })); expect(screen.getByLabelText("系统提示词")).toHaveValue("Scope b");
  });
  it("invalidates old Workspace A data through A-B-A remounts", async () => {
    const request = deferred<AgentSummary[]>(); vi.mocked(listManagedAgents).mockReturnValueOnce(request.promise);
    const view = render(<AgentToolAdmin {...props} />);
    await waitFor(() => expect(listManagedAgents).toHaveBeenCalledTimes(1));
    view.rerender(<AgentToolAdmin {...props} workspaceId="b" />);
    await waitFor(() => expect(screen.getByLabelText("Agent 名称")).toBeEnabled());
    view.rerender(<AgentToolAdmin {...props} />); await waitFor(() => expect(screen.getByLabelText("Agent 名称")).toBeEnabled());
    await act(async () => request.resolve([{ ...agentFixture("stale"), name: "STALE" }])); expect(screen.queryByText("STALE")).not.toBeInTheDocument();
  });
  it.each(["role", "token"])("clears current drafts when %s changes", async context => {
    const { user, rerender } = await mount(); await user.type(screen.getByLabelText("系统提示词"), "PRIVATE");
    rerender(<AgentToolAdmin {...props} role={context === "role" ? "employee" : "agent_admin"} accessToken={context === "token" ? "new-token" : "token"} />);
    if (context === "role") expect(screen.queryByLabelText("系统提示词")).not.toBeInTheDocument();
    else await waitFor(() => expect(screen.getByLabelText("系统提示词")).toHaveValue("Scope a"));
  });
  it("renders configuration as literal text", async () => {
    agents[0].name = "<img onerror='alert(1)' src=x>"; const { user } = await mount();
    expect(screen.getByLabelText("Agent 名称")).toHaveValue(agents[0].name);
    expect(screen.queryByRole("img")).not.toBeInTheDocument(); await toolTab(user);
    expect(within(screen.getByRole("region", { name: "能力限制" })).getByText(/仅查询登录员工/)).toBeInTheDocument();
  });
});
