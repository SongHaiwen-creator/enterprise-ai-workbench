import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Home from "@/app/app/page";
import {
  AgentSummary,
  AgentRouteResponse,
  ApiError,
  KnowledgeBase,
  Workspace,
  WorkspaceListItem,
  getCurrentUser,
  getWorkspace,
  listAgents,
  listExecutionLogs,
  listKnowledgeBases,
  listWorkspaceMembers,
  listWorkspaces,
  login,
  routeAgentRequest,
} from "@/utils/api";

vi.mock("@/utils/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/utils/api")>();
  return {
    ...actual,
    login: vi.fn(),
    getCurrentUser: vi.fn(),
    listWorkspaces: vi.fn(),
    getWorkspace: vi.fn(),
    listWorkspaceMembers: vi.fn(),
    listAgents: vi.fn(),
    listKnowledgeBases: vi.fn(),
    routeAgentRequest: vi.fn(),
    listExecutionLogs: vi.fn(),
  };
});

const mockedLogin = vi.mocked(login);
const mockedGetCurrentUser = vi.mocked(getCurrentUser);
const mockedListWorkspaces = vi.mocked(listWorkspaces);
const mockedGetWorkspace = vi.mocked(getWorkspace);
const mockedListWorkspaceMembers = vi.mocked(listWorkspaceMembers);
const mockedListAgents = vi.mocked(listAgents);
const mockedListKnowledgeBases = vi.mocked(listKnowledgeBases);
const mockedRouteAgentRequest = vi.mocked(routeAgentRequest);
const mockedListExecutionLogs = vi.mocked(listExecutionLogs);

const workspaceItems: WorkspaceListItem[] = [
  {
    id: "workspace-a",
    name: "Workspace A",
    slug: "workspace-a",
    status: "active",
    role: "employee",
    joined_at: "2026-09-01T00:00:00Z",
  },
  {
    id: "workspace-b",
    name: "Workspace B",
    slug: "workspace-b",
    status: "active",
    role: "employee",
    joined_at: "2026-09-02T00:00:00Z",
  },
];

function workspace(item: WorkspaceListItem): Workspace {
  return {
    id: item.id,
    name: item.name,
    slug: item.slug,
    status: item.status,
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
  };
}

function knowledgeBase(
  workspaceId: string,
  id: string,
  name: string,
): KnowledgeBase {
  return {
    id,
    workspace_id: workspaceId,
    name,
    description: `${name} description`,
    status: "active",
    created_by: "user-1",
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
  };
}

function agent(workspaceId: string, id: string, name: string): AgentSummary {
  return {
    id,
    workspace_id: workspaceId,
    name,
    description: null,
    status: "active",
    created_by: "user-1",
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

async function signIn(knowledgeArea = true) {
  const user = userEvent.setup();
  render(<Home />);
  await user.type(screen.getByLabelText("工作邮箱"), "alex@example.com");
  await user.type(screen.getByLabelText("密码"), "correct-password");
  await user.click(screen.getByRole("button", { name: "登录" }));
  if (knowledgeArea && screen.queryByRole("button", { name: "知识问答" })) await user.click(screen.getByRole("button", { name: "知识问答" }));
  return user;
}

describe("Workspace selection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedLogin.mockResolvedValue({
      access_token: "test-token",
      token_type: "bearer",
      expires_in: 1800,
    });
    mockedGetCurrentUser.mockResolvedValue({
      id: "user-1",
      email: "alex@example.com",
      name: "Alex Morgan",
      status: "active",
    });
    mockedListWorkspaces.mockResolvedValue(workspaceItems);
    mockedListWorkspaceMembers.mockResolvedValue([]);
    mockedListAgents.mockResolvedValue([]);
  });

  afterEach(cleanup);

  it("opens the Assistant by default after login", async () => {
    mockedGetWorkspace.mockResolvedValue(workspace(workspaceItems[0]));
    mockedListKnowledgeBases.mockResolvedValue([knowledgeBase("workspace-a", "kb-a", "Alpha policies")]);
    mockedListAgents.mockResolvedValue([agent("workspace-a", "agent-a", "Alpha Assistant")]);
    await signIn(false);
    expect(await screen.findByRole("heading", { name: "智能助手", level: 1 })).toBeInTheDocument();
    expect(await screen.findByLabelText("请求内容")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "智能助手" })).toHaveAttribute("aria-current", "page");
  });

  it("ignores stale Workspace responses that finish after the latest selection", async () => {
    const workspaceA = deferred<Workspace>();
    const workspaceB = deferred<Workspace>();
    const knowledgeBasesA = deferred<KnowledgeBase[]>();
    const knowledgeBasesB = deferred<KnowledgeBase[]>();
    const agentsA = deferred<AgentSummary[]>();
    const agentsB = deferred<AgentSummary[]>();

    mockedGetWorkspace.mockImplementation((workspaceId) =>
      workspaceId === "workspace-a" ? workspaceA.promise : workspaceB.promise,
    );
    mockedListKnowledgeBases.mockImplementation((workspaceId) =>
      workspaceId === "workspace-a" ? knowledgeBasesA.promise : knowledgeBasesB.promise,
    );
    mockedListAgents.mockImplementation((workspaceId) =>
      workspaceId === "workspace-a" ? agentsA.promise : agentsB.promise,
    );

    const user = await signIn();
    const workspaceSwitcher = await screen.findByRole("combobox", { name: "当前工作空间" });
    await user.selectOptions(workspaceSwitcher, "workspace-b");

    await act(async () => {
      workspaceB.resolve(workspace(workspaceItems[1]));
      knowledgeBasesB.resolve([
        knowledgeBase("workspace-b", "kb-b", "Beta policies"),
      ]);
      agentsB.resolve([agent("workspace-b", "agent-b", "Beta Assistant")]);
    });

    expect(await screen.findByText("Workspace B", { selector: ".topbar-context" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Beta policies" })).toBeInTheDocument();

    await act(async () => {
      workspaceA.resolve(workspace(workspaceItems[0]));
      knowledgeBasesA.resolve([
        knowledgeBase("workspace-a", "kb-a", "Alpha policies"),
      ]);
      agentsA.resolve([agent("workspace-a", "agent-a", "Alpha Assistant")]);
    });

    await waitFor(() => {
      expect(screen.getByText("Workspace B", { selector: ".topbar-context" })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: "Beta policies" })).toBeInTheDocument();
      expect(screen.queryByRole("option", { name: "Alpha policies" })).not.toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: "智能助手" }));
    expect(screen.getByRole("option", { name: "Beta Assistant" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "Alpha Assistant" })).not.toBeInTheDocument();
  });

  it("shows Execution Logs only to agent and system administrators", async () => {
    const adminWorkspace = { ...workspaceItems[0], role: "agent_admin" as const };
    mockedListWorkspaces.mockResolvedValue([adminWorkspace, workspaceItems[1]]);
    mockedGetWorkspace.mockImplementation(async (workspaceId) =>
      workspace(workspaceId === "workspace-a" ? adminWorkspace : workspaceItems[1]),
    );
    mockedListKnowledgeBases.mockResolvedValue([]);
    mockedListExecutionLogs.mockResolvedValue({ items: [], limit: 50, offset: 0 });

    const user = await signIn();
    const logsLink = await screen.findByRole("button", { name: "执行日志" });
    await user.click(logsLink);
    expect(await screen.findByRole("heading", { name: "执行日志", level: 2 })).toBeInTheDocument();
    expect(mockedListExecutionLogs).toHaveBeenCalledWith("workspace-a", {}, 50, 0, "test-token");

    await user.selectOptions(screen.getByRole("combobox", { name: "当前工作空间" }), "workspace-b");
    await waitFor(() => {
      expect(
        screen.queryByRole("button", { name: "执行日志" }),
      ).not.toBeInTheDocument();
    });
    expect(screen.queryByRole("heading", { name: "执行日志", level: 2 })).not.toBeInTheDocument();
    expect(mockedListExecutionLogs).toHaveBeenCalledTimes(1);
  });

  it.each(["employee", "knowledge_admin", "agent_admin", "system_admin"] as const)(
    "gates Evaluation Dataset navigation for %s", async role => {
      const selected = { ...workspaceItems[0], role };
      mockedListWorkspaces.mockResolvedValue([selected]);
      mockedGetWorkspace.mockResolvedValue(workspace(selected));
      mockedListKnowledgeBases.mockResolvedValue([]);
      await signIn();
      await screen.findByRole("button", { name: "退出登录" });
      await waitFor(() => expect(mockedGetWorkspace).toHaveBeenCalled());
      const navigation = screen.queryByRole("button", { name: "评测数据集" });
      if (role === "agent_admin" || role === "system_admin") expect(navigation).toBeInTheDocument();
      else expect(navigation).not.toBeInTheDocument();
    },
  );

  it("keeps Knowledge Q&A and Workspace available when Agent listing fails", async () => {
    mockedListWorkspaces.mockResolvedValue([workspaceItems[0]]);
    mockedGetWorkspace.mockResolvedValue(workspace(workspaceItems[0]));
    mockedListKnowledgeBases.mockResolvedValue([
      knowledgeBase("workspace-a", "kb-a", "Alpha policies"),
    ]);
    mockedListAgents.mockRejectedValue(new ApiError("Agent service unavailable", 503));

    const user = await signIn();
    expect(await screen.findByRole("option", { name: "Alpha policies" }))
      .toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "智能助手" }));
    expect(await screen.findByText("无法加载可用智能体")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "空间与成员" }));
    expect(screen.getByRole("region", { name: "工作空间概览" })).toBeInTheDocument();
  });

  it("clears Assistant state and context on Workspace switching", async () => {
    mockedGetWorkspace.mockImplementation(async (workspaceId) =>
      workspace(workspaceItems.find((item) => item.id === workspaceId)!),
    );
    mockedListKnowledgeBases.mockImplementation(async (workspaceId) =>
      workspaceId === "workspace-a"
        ? [knowledgeBase("workspace-a", "kb-a", "Alpha policies")]
        : [knowledgeBase("workspace-b", "kb-b", "Beta policies")],
    );
    mockedListAgents.mockImplementation(async (workspaceId) =>
      workspaceId === "workspace-a"
        ? [agent("workspace-a", "agent-a", "Alpha Assistant")]
        : [agent("workspace-b", "agent-b", "Beta Assistant")],
    );
    const outcome: AgentRouteResponse = {
      request: "Check my claim",
      intent: "tool_request",
      outcome: {
        status: "not_executed",
        required_capability: "enterprise_tool",
        message: "This request requires an enterprise tool. No action was executed.",
      },
    };
    mockedRouteAgentRequest.mockResolvedValue(outcome);

    const user = await signIn();
    await user.click(await screen.findByRole("button", { name: "智能助手" }));
    await user.type(screen.getByLabelText("请求内容"), outcome.request);
    await user.click(screen.getByRole("button", { name: "发送请求" }));
    expect(await screen.findByText("未执行任何操作")).toBeInTheDocument();

    await user.selectOptions(screen.getByRole("combobox", { name: "当前工作空间" }), "workspace-b");
    expect(await screen.findByRole("option", { name: "Beta Assistant" })).toBeInTheDocument();
    expect(screen.getByLabelText("知识库（可选）")).toHaveValue("kb-b");
    expect(screen.getByLabelText("请求内容")).toHaveValue("");
    expect(screen.getByText("处理结果将显示在这里")).toBeInTheDocument();
  });

  it("clears the session when Agent listing returns 401", async () => {
    mockedListWorkspaces.mockResolvedValue([workspaceItems[0]]);
    mockedGetWorkspace.mockResolvedValue(workspace(workspaceItems[0]));
    mockedListKnowledgeBases.mockResolvedValue([]);
    mockedListAgents.mockRejectedValue(new ApiError("Could not validate credentials", 401));

    await signIn();
    expect(await screen.findByText("登录已过期，请重新登录。"))
      .toBeInTheDocument();
    expect(screen.getByRole("button", { name: "登录" })).toBeInTheDocument();
  });

  it("renders an explicit access-denied state when Knowledge Base listing returns 403", async () => {
    mockedListWorkspaces.mockResolvedValue([workspaceItems[0]]);
    mockedGetWorkspace.mockResolvedValue(workspace(workspaceItems[0]));
    mockedListKnowledgeBases.mockRejectedValue(
      new ApiError("Not authorized for this workspace", 403),
    );

    await signIn();

    expect(
      await screen.findByText("你没有当前空间的知识问答访问权限"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("你没有访问当前空间知识库的权限。"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "退出登录" })).toBeInTheDocument();
  });

  it("clears the session when Knowledge Base listing returns 401", async () => {
    mockedListWorkspaces.mockResolvedValue([workspaceItems[0]]);
    mockedGetWorkspace.mockResolvedValue(workspace(workspaceItems[0]));
    mockedListKnowledgeBases.mockRejectedValue(
      new ApiError("Could not validate credentials", 401),
    );

    await signIn();

    expect(
      await screen.findByText("登录已过期，请重新登录。"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "登录" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "退出登录" })).not.toBeInTheDocument();
  });
});
