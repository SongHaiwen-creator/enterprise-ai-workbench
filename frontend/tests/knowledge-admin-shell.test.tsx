import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Workbench from "@/app/app/page";
import {
  ApiError, type KnowledgeBase, type MembershipRole, getCurrentUser, getWorkspace, listAgents,
  listKnowledgeBases, listWorkspaceMembers, listWorkspaces, login,
} from "@/utils/api";
import { getKnowledgeBase, listDocuments, updateKnowledgeBase } from "@/utils/knowledge-admin";

vi.mock("@/utils/api", async importOriginal => ({
  ...await importOriginal<typeof import("@/utils/api")>(), login: vi.fn(), getCurrentUser: vi.fn(),
  getWorkspace: vi.fn(), listAgents: vi.fn(), listKnowledgeBases: vi.fn(), listWorkspaceMembers: vi.fn(), listWorkspaces: vi.fn(),
}));
vi.mock("@/utils/knowledge-admin", async importOriginal => ({
  ...await importOriginal<typeof import("@/utils/knowledge-admin")>(), getKnowledgeBase: vi.fn(), listDocuments: vi.fn(), updateKnowledgeBase: vi.fn(),
}));
let base: KnowledgeBase;
function workspace(id: string, role: MembershipRole) {
  return { id, name: `空间 ${id}`, slug: id, status: "active" as const, role, joined_at: null, created_at: "2026-10-01T00:00:00Z", updated_at: "2026-10-01T00:00:00Z" };
}
async function signIn() {
  render(<Workbench />); const user = userEvent.setup();
  await user.type(screen.getByLabelText("工作邮箱"), "synthetic@example.com");
  await user.type(screen.getByLabelText("密码"), "synthetic-test-password");
  await user.click(screen.getByRole("button", { name: "登录" }));
  await screen.findByRole("button", { name: "知识问答" }); return user;
}
beforeEach(() => {
  vi.resetAllMocks();
  base = { id: "kb", workspace_id: "a", name: "初始制度", description: null, status: "active", created_by: "u", created_at: "2026-10-01T00:00:00Z", updated_at: "2026-10-01T00:00:00Z" };
  vi.mocked(login).mockResolvedValue({ access_token: "token", token_type: "bearer", expires_in: 1800 });
  vi.mocked(getCurrentUser).mockResolvedValue({ id: "u", name: "合成用户", email: "synthetic@example.com", status: "active" });
  vi.mocked(listWorkspaces).mockResolvedValue([workspace("a", "knowledge_admin"), workspace("b", "employee")]);
  vi.mocked(getWorkspace).mockImplementation(async id => workspace(id, "knowledge_admin"));
  vi.mocked(listWorkspaceMembers).mockResolvedValue([]); vi.mocked(listAgents).mockResolvedValue([]);
  vi.mocked(listKnowledgeBases).mockImplementation(async () => [base]);
  vi.mocked(getKnowledgeBase).mockImplementation(async () => base);
  vi.mocked(listDocuments).mockResolvedValue([]);
  vi.mocked(updateKnowledgeBase).mockImplementation(async (_w, _id, values) => { base = { ...base, ...values } as KnowledgeBase; return base; });
});
afterEach(cleanup);
describe("Knowledge management shell", () => {
  it.each([
    ["employee", false, false], ["agent_admin", false, true], ["knowledge_admin", true, false], ["system_admin", true, true],
  ] as const)("keeps knowledge and operation navigation separate for %s", async (role, knowledge, operations) => {
    vi.mocked(listWorkspaces).mockResolvedValue([workspace("a", role)]);
    await signIn();
    expect(!!screen.queryByRole("button", { name: "知识管理" })).toBe(knowledge);
    expect(!!screen.queryByRole("button", { name: "执行日志" })).toBe(operations);
    expect(!!screen.queryByRole("button", { name: "评测数据集" })).toBe(operations);
  });
  it("refreshes names and availability shared with knowledge Q&A after management", async () => {
    const user = await signIn(); await user.click(screen.getByRole("button", { name: "知识管理" }));
    await waitFor(() => expect(screen.getByLabelText("知识库名称")).toBeEnabled());
    await user.clear(screen.getByLabelText("知识库名称")); await user.type(screen.getByLabelText("知识库名称"), "新制度");
    await user.click(screen.getByRole("button", { name: "保存知识库" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "知识问答" })).toBeEnabled());
    await user.click(screen.getByRole("button", { name: "知识问答" }));
    expect(screen.getByRole("option", { name: "新制度" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "初始制度" })).not.toBeInTheDocument();
    base = { ...base, status: "disabled" };
    await user.click(screen.getByRole("button", { name: "知识管理" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "启用知识库" })).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "知识问答" }));
    expect(screen.queryByLabelText("问题")).not.toBeInTheDocument();
    expect(screen.getByText("知识库已停用", { selector: "strong" })).toBeInTheDocument();
  });
  it("locks navigation during writes while allowing logout, then discards a late result", async () => {
    let resolve!: (value: KnowledgeBase) => void;
    vi.mocked(updateKnowledgeBase).mockReturnValue(new Promise<KnowledgeBase>(yes => { resolve = yes; }));
    const user = await signIn(); await user.click(screen.getByRole("button", { name: "知识管理" }));
    await waitFor(() => expect(screen.getByLabelText("知识库名称")).toBeEnabled());
    await user.type(screen.getByLabelText("知识库名称"), "新");
    const form = screen.getByRole("button", { name: "保存知识库" }).closest("form")!;
    fireEvent.submit(form); fireEvent.submit(form);
    expect(updateKnowledgeBase).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("combobox", { name: "当前工作空间" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "知识问答" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "退出登录" }));
    await act(async () => resolve(base));
    expect(screen.getByRole("button", { name: "登录" })).toBeInTheDocument();
    expect(screen.queryByText("知识库已保存。")).not.toBeInTheDocument();
  });
  it("resets the area when the next workspace has an employee role", async () => {
    const user = await signIn(); await user.click(screen.getByRole("button", { name: "知识管理" }));
    await screen.findByLabelText("知识库名称");
    await user.selectOptions(screen.getByRole("combobox", { name: "当前工作空间" }), "b");
    expect(screen.queryByLabelText("知识库名称")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "知识管理" })).not.toBeInTheDocument();
  });
  it("clears the entire session for a management 401", async () => {
    const user = await signIn(); vi.mocked(getKnowledgeBase).mockRejectedValue(new ApiError("Expired", 401));
    await user.click(screen.getByRole("button", { name: "知识管理" }));
    await screen.findByRole("button", { name: "登录" });
    expect(screen.queryByLabelText("知识库名称")).not.toBeInTheDocument();
  });
});
