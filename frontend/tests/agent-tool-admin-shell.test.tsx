import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import Workbench from "@/app/app/page";
import {
  ApiError, type AgentSummary, type MembershipRole, getCurrentUser, getWorkspace, listAgents,
  listKnowledgeBases, listWorkspaceMembers, listWorkspaces, login,
} from "@/utils/api";
import { type AgentConfiguration, getAgent, listAgentTools, listManagedAgents, listTools, updateAgent } from "@/utils/agent-tool-admin";
import { agentFixture, agentSummary, deferred } from "./agent-tool-fixtures";

vi.mock("@/utils/api", async original => ({
  ...await original<typeof import("@/utils/api")>(), login: vi.fn(), getCurrentUser: vi.fn(), getWorkspace: vi.fn(),
  listAgents: vi.fn(), listKnowledgeBases: vi.fn(), listWorkspaceMembers: vi.fn(), listWorkspaces: vi.fn(),
}));
vi.mock("@/utils/agent-tool-admin", async original => ({
  ...await original<typeof import("@/utils/agent-tool-admin")>(), getAgent: vi.fn(), listAgentTools: vi.fn(),
  listManagedAgents: vi.fn(), listTools: vi.fn(), updateAgent: vi.fn(),
}));
let agents: AgentConfiguration[];
function workspace(id: string, role: MembershipRole) {
  return { id, name: `空间 ${id}`, slug: id, role, status: "active" as const, joined_at: null, created_at: "2026-10-10T00:00:00Z", updated_at: "2026-10-10T00:00:00Z" };
}
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
  vi.resetAllMocks(); agents = [agentFixture("a", "active"), agentFixture("b", "active"), agentFixture("draft")];
  vi.mocked(login).mockResolvedValue({ access_token: "token", token_type: "bearer", expires_in: 1800 });
  vi.mocked(getCurrentUser).mockResolvedValue({ id: "u", name: "合成用户", email: "synthetic@example.com", status: "active" });
  vi.mocked(listWorkspaces).mockResolvedValue([workspace("w", "agent_admin"), workspace("other", "employee")]);
  vi.mocked(getWorkspace).mockImplementation(async id => workspace(id, "agent_admin"));
  vi.mocked(listWorkspaceMembers).mockResolvedValue([]); vi.mocked(listKnowledgeBases).mockResolvedValue([]);
  vi.mocked(listAgents).mockImplementation(async () => agents.filter(item => item.status === "active").map(agentSummary));
  vi.mocked(listManagedAgents).mockImplementation(async () => agents.map(agentSummary));
  vi.mocked(getAgent).mockImplementation(async (_w, id) => agents.find(item => item.id === id)!);
  vi.mocked(listAgentTools).mockResolvedValue([]); vi.mocked(listTools).mockResolvedValue([]);
  vi.mocked(updateAgent).mockImplementation(async (_w, id, patch) => {
    agents = agents.map(item => item.id === id ? { ...item, ...patch } as AgentConfiguration : item); return agents.find(item => item.id === id)!;
  });
});
afterEach(cleanup);
async function signIn() {
  render(<Workbench />); const user = userEvent.setup(); await user.type(screen.getByLabelText("工作邮箱"), "synthetic@example.com");
  await user.type(screen.getByLabelText("密码"), "synthetic-test-password"); await user.click(screen.getByRole("button", { name: "登录", exact: true }));
  await screen.findByRole("button", { name: "智能助手" }); return user;
}
async function openAdmin(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: "Agent 与工具", exact: true }));
  await waitFor(() => expect(screen.getByLabelText("Agent 名称")).toBeEnabled());
}
describe("Agent management shell", () => {
  it.each(["employee", "knowledge_admin", "agent_admin", "system_admin"] as const)("shows management only for allowed %s", async role => {
    vi.mocked(listWorkspaces).mockResolvedValue([workspace("w", role)]); await signIn();
    expect(!!screen.queryByRole("button", { name: "Agent 与工具", exact: true })).toBe(["agent_admin", "system_admin"].includes(role));
    expect(listManagedAgents).not.toHaveBeenCalled(); expect(getAgent).not.toHaveBeenCalled();
  });
  it("preserves a still-active Assistant selection after editing another Agent", async () => {
    const user = await signIn(); await user.selectOptions(await screen.findByLabelText("智能体"), "b");
    await openAdmin(user); await user.clear(screen.getByLabelText("Agent 名称")); await user.type(screen.getByLabelText("Agent 名称"), "改名助手");
    await user.click(screen.getByRole("button", { name: "保存 Agent" })); await screen.findByText("Agent 已保存。");
    await waitFor(() => expect(screen.getByRole("button", { name: "智能助手" })).toBeEnabled());
    await user.click(screen.getByRole("button", { name: "智能助手" }));
    expect(screen.getByLabelText("智能体")).toHaveValue("b"); expect(screen.getByRole("option", { name: "改名助手" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "助手 draft" })).not.toBeInTheDocument(); expect(screen.queryByLabelText("系统提示词")).not.toBeInTheDocument();
  });
  it("removes an inactive Assistant selection and keeps drafts out of the employee list", async () => {
    const user = await signIn(); await openAdmin(user); await user.click(screen.getByRole("button", { name: "禁用 Agent" }));
    await user.click(screen.getByRole("button", { name: "确认继续" })); await screen.findByText("Agent 状态已更新。");
    await waitFor(() => expect(screen.getByRole("button", { name: "智能助手" })).toBeEnabled()); await user.click(screen.getByRole("button", { name: "智能助手" }));
    expect(screen.queryByRole("option", { name: "助手 a" })).not.toBeInTheDocument(); expect(screen.getByLabelText("智能体")).toHaveValue("b");
  });
  it("locks navigation during a write but logout still clears a late result", async () => {
    const request = deferred<AgentConfiguration>(); const user = await signIn(); await openAdmin(user);
    vi.mocked(updateAgent).mockReturnValue(request.promise); await user.type(screen.getByLabelText("Agent 名称"), "Late");
    const form = screen.getByRole("button", { name: "保存 Agent" }).closest("form")!; fireEvent.submit(form); fireEvent.submit(form);
    expect(updateAgent).toHaveBeenCalledTimes(1); expect(screen.getByRole("combobox", { name: "当前工作空间" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "智能助手" })).toBeDisabled(); await user.click(screen.getByRole("button", { name: "退出登录" }));
    await act(async () => request.resolve(agentFixture())); expect(screen.getByRole("button", { name: "登录", exact: true })).toBeInTheDocument();
    expect(screen.queryByLabelText("系统提示词")).not.toBeInTheDocument();
  });
  it("drops management area when switching to a workspace with an employee role", async () => {
    const user = await signIn(); await openAdmin(user); await user.selectOptions(screen.getByRole("combobox", { name: "当前工作空间" }), "other");
    expect(screen.queryByLabelText("系统提示词")).not.toBeInTheDocument(); expect(screen.queryByRole("button", { name: "Agent 与工具" })).not.toBeInTheDocument();
  });
  it("ignores an initial active-Agent response that arrives after a management refresh", async () => {
    const old = deferred<AgentSummary[]>(); vi.mocked(listAgents).mockReturnValueOnce(old.promise);
    const user = await signIn(); await openAdmin(user); await user.type(screen.getByLabelText("Agent 名称"), "Updated");
    await user.click(screen.getByRole("button", { name: "保存 Agent" })); await screen.findByText("Agent 已保存。");
    await waitFor(() => expect(screen.getByRole("button", { name: "智能助手" })).toBeEnabled());
    await act(async () => old.resolve([agentSummary({ ...agentFixture("stale", "active"), name: "STALE" })]));
    await user.click(screen.getByRole("button", { name: "智能助手" })); expect(screen.queryByRole("option", { name: "STALE" })).not.toBeInTheDocument();
    expect(screen.getByRole("option", { name: "助手 aUpdated" })).toBeInTheDocument();
  });
  it("clears the shell session after an admin configuration 401", async () => {
    const user = await signIn(); vi.mocked(getAgent).mockRejectedValue(new ApiError("Expired", 401));
    await user.click(screen.getByRole("button", { name: "Agent 与工具", exact: true }));
    await screen.findByRole("button", { name: "登录", exact: true }); expect(screen.queryByLabelText("系统提示词")).not.toBeInTheDocument();
  });
  it("does not offer stale Assistant capabilities after a failed shared refresh", async () => {
    const user = await signIn(); await openAdmin(user); vi.mocked(listAgents).mockRejectedValue(new ApiError("Unavailable", 500));
    await user.type(screen.getByLabelText("Agent 名称"), "Change"); await user.click(screen.getByRole("button", { name: "保存 Agent" }));
    await screen.findByText(/操作已完成，列表刷新失败/); await user.click(screen.getByRole("button", { name: "智能助手" }));
    expect(screen.queryByLabelText("智能体")).not.toBeInTheDocument(); expect(screen.getByRole("heading", { name: "无法加载可用智能体" })).toBeInTheDocument();
  });
});
