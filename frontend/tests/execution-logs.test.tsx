import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { EXECUTION_LOG_PAGE_SIZE, ExecutionLogs } from "@/app/components/execution-logs";
import { ApiError, ExecutionLog, listExecutionLogs } from "@/utils/api";

vi.mock("@/utils/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/utils/api")>();
  return { ...actual, listExecutionLogs: vi.fn() };
});

const mockedList = vi.mocked(listExecutionLogs);

function log(overrides: Partial<ExecutionLog> = {}): ExecutionLog {
  return {
    id: "log-1",
    workspace_id: "workspace-1",
    operation: "agent_route",
    routing_intent: "tool_request",
    status: "succeeded",
    outcome: "tool_approval_required",
    error_category: null,
    http_status: 200,
    latency_ms: 1234,
    user: { id: "user-1", name: "<b>Employee One</b>" },
    agent: { id: "agent-1", name: "Employee Service Assistant" },
    tool: { tool_key: "create_it_access_request", name: "Create IT access request" },
    approval_id: "approval-1",
    knowledge_base: null,
    details: {},
    created_at: "2026-09-29T08:00:05Z",
    ...overrides,
  };
}

const failedKnowledgeLog = log({
  id: "log-2",
  operation: "knowledge_answer",
  routing_intent: null,
  status: "failed",
  outcome: null,
  error_category: "provider_error",
  http_status: 502,
  latency_ms: 87,
  agent: null,
  tool: null,
  approval_id: null,
  knowledge_base: { id: "kb-1", name: "Travel Policies" },
  details: { citation_count: 0, generation_model: "gpt-5.6-terra", input_tokens: null },
});

function renderLogs(onUnauthorized = vi.fn()) {
  render(
    <ExecutionLogs
      workspaceId="workspace-1"
      workspaceName="Acme"
      accessToken="token"
      onUnauthorized={onUnauthorized}
    />,
  );
  return { user: userEvent.setup(), onUnauthorized };
}

describe("执行日志", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(cleanup);

  it("lists records newest first with sanitized fields as plain text", async () => {
    mockedList.mockResolvedValue({ items: [log(), failedKnowledgeLog], limit: 50, offset: 0 });

    renderLogs();

    const table = await screen.findByRole("table");
    const rows = within(table).getAllByRole("row");
    expect(rows).toHaveLength(3);
    expect(within(rows[1]).getByText("助手请求")).toBeInTheDocument();
    expect(within(rows[1]).getByText("<b>Employee One</b>")).toBeInTheDocument();
    expect(within(rows[1]).getByText("Create IT access request")).toBeInTheDocument();
    expect(within(rows[1]).getByText("工具需要审批")).toBeInTheDocument();
    expect(within(rows[1]).getByText("1,234 毫秒")).toBeInTheDocument();
    expect(within(rows[1]).getByText("2026/09/29 16:00:05（北京时间）")).toBeInTheDocument();
    expect(within(rows[2]).getByText("失败")).toBeInTheDocument();
    expect(within(rows[2]).getByText("模型服务错误")).toBeInTheDocument();
    expect(mockedList).toHaveBeenCalledWith("workspace-1", {}, EXECUTION_LOG_PAGE_SIZE, 0, "token");
    expect(screen.queryByRole("button", { name: "加载更多" })).not.toBeInTheDocument();
  });

  it("expands one record to show recorded details only", async () => {
    mockedList.mockResolvedValue({ items: [failedKnowledgeLog], limit: 50, offset: 0 });
    const { user } = renderLogs();

    const toggle = await screen.findByRole("button", { name: "详情" });
    await user.click(toggle);

    expect(toggle).toHaveAttribute("aria-expanded", "true");
    const details = document.getElementById("execution-log-log-2");
    expect(details).not.toBeNull();
    const scope = within(details as HTMLElement);
    expect(scope.getByText("502")).toBeInTheDocument();
    expect(scope.getByText("Travel Policies")).toBeInTheDocument();
    expect(scope.getByText("gpt-5.6-terra")).toBeInTheDocument();
    expect(scope.getByText("引用来源")).toBeInTheDocument();
    expect(scope.getByText("未记录")).toBeInTheDocument();
    expect(scope.queryByText("提交的审批决定")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "收起" }));
    expect(document.getElementById("execution-log-log-2")).toBeNull();
  });

  it("reloads from the first page when filters change", async () => {
    mockedList.mockResolvedValue({ items: [log()], limit: 50, offset: 0 });
    const { user } = renderLogs();
    await screen.findByRole("table");

    await user.selectOptions(screen.getByLabelText("操作类型"), "approval_decision");
    await user.selectOptions(screen.getByLabelText("状态"), "failed");

    await waitFor(() => {
      expect(mockedList).toHaveBeenLastCalledWith(
        "workspace-1",
        { operation: "approval_decision", status: "failed" },
        EXECUTION_LOG_PAGE_SIZE,
        0,
        "token",
      );
    });
  });

  it("appends the next page on load more", async () => {
    const firstPage = Array.from({ length: EXECUTION_LOG_PAGE_SIZE }, (_, index) =>
      log({ id: `log-${index}` }),
    );
    mockedList
      .mockResolvedValueOnce({ items: firstPage, limit: 50, offset: 0 })
      .mockResolvedValueOnce({ items: [log({ id: "log-last" })], limit: 50, offset: 50 });
    const { user } = renderLogs();

    await user.click(await screen.findByRole("button", { name: "加载更多" }));

    await waitFor(() => {
      expect(within(screen.getByRole("table")).getAllByRole("row")).toHaveLength(
        EXECUTION_LOG_PAGE_SIZE + 2,
      );
    });
    expect(mockedList).toHaveBeenLastCalledWith(
      "workspace-1", {}, EXECUTION_LOG_PAGE_SIZE, EXECUTION_LOG_PAGE_SIZE, "token",
    );
    expect(screen.queryByRole("button", { name: "加载更多" })).not.toBeInTheDocument();
  });

  it("shows empty, access-denied, and session-expired states", async () => {
    mockedList.mockResolvedValueOnce({ items: [], limit: 50, offset: 0 });
    renderLogs();
    expect(await screen.findByText("暂无符合筛选条件的执行日志。")).toBeInTheDocument();
    cleanup();

    mockedList.mockRejectedValueOnce(new ApiError("Agent administrator role required", 403));
    renderLogs();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("没有执行日志访问权限");
    expect(alert).toHaveTextContent("你没有执行此操作的权限。");
    cleanup();

    mockedList.mockRejectedValueOnce(new ApiError("Not authenticated", 401));
    const { onUnauthorized } = renderLogs();
    await waitFor(() => expect(onUnauthorized).toHaveBeenCalledTimes(1));
  });
});
