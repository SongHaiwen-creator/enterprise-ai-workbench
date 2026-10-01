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

describe("Execution logs", () => {
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
    expect(within(rows[1]).getByText("Agent request")).toBeInTheDocument();
    expect(within(rows[1]).getByText("<b>Employee One</b>")).toBeInTheDocument();
    expect(within(rows[1]).getByText("Create IT access request")).toBeInTheDocument();
    expect(within(rows[1]).getByText("Tool Approval Required")).toBeInTheDocument();
    expect(within(rows[1]).getByText("1,234 ms")).toBeInTheDocument();
    expect(within(rows[1]).getByText("2026-09-29 08:00:05 UTC")).toBeInTheDocument();
    expect(within(rows[2]).getByText("Failed")).toBeInTheDocument();
    expect(within(rows[2]).getByText("Provider Error")).toBeInTheDocument();
    expect(mockedList).toHaveBeenCalledWith("workspace-1", {}, EXECUTION_LOG_PAGE_SIZE, 0, "token");
    expect(screen.queryByRole("button", { name: "Load more" })).not.toBeInTheDocument();
  });

  it("expands one record to show recorded details only", async () => {
    mockedList.mockResolvedValue({ items: [failedKnowledgeLog], limit: 50, offset: 0 });
    const { user } = renderLogs();

    const toggle = await screen.findByRole("button", { name: "Details" });
    await user.click(toggle);

    expect(toggle).toHaveAttribute("aria-expanded", "true");
    const details = document.getElementById("execution-log-log-2");
    expect(details).not.toBeNull();
    const scope = within(details as HTMLElement);
    expect(scope.getByText("502")).toBeInTheDocument();
    expect(scope.getByText("Travel Policies")).toBeInTheDocument();
    expect(scope.getByText("gpt-5.6-terra")).toBeInTheDocument();
    expect(scope.getByText("Citations")).toBeInTheDocument();
    expect(scope.getByText("Not reported")).toBeInTheDocument();
    expect(scope.queryByText("Requested decision")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Hide" }));
    expect(document.getElementById("execution-log-log-2")).toBeNull();
  });

  it("reloads from the first page when filters change", async () => {
    mockedList.mockResolvedValue({ items: [log()], limit: 50, offset: 0 });
    const { user } = renderLogs();
    await screen.findByRole("table");

    await user.selectOptions(screen.getByLabelText("Operation"), "approval_decision");
    await user.selectOptions(screen.getByLabelText("Status"), "failed");

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

    await user.click(await screen.findByRole("button", { name: "Load more" }));

    await waitFor(() => {
      expect(within(screen.getByRole("table")).getAllByRole("row")).toHaveLength(
        EXECUTION_LOG_PAGE_SIZE + 2,
      );
    });
    expect(mockedList).toHaveBeenLastCalledWith(
      "workspace-1", {}, EXECUTION_LOG_PAGE_SIZE, EXECUTION_LOG_PAGE_SIZE, "token",
    );
    expect(screen.queryByRole("button", { name: "Load more" })).not.toBeInTheDocument();
  });

  it("shows empty, access-denied, and session-expired states", async () => {
    mockedList.mockResolvedValueOnce({ items: [], limit: 50, offset: 0 });
    renderLogs();
    expect(await screen.findByText("No execution logs match these filters.")).toBeInTheDocument();
    cleanup();

    mockedList.mockRejectedValueOnce(new ApiError("Agent administrator role required", 403));
    renderLogs();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Execution log access denied");
    expect(alert).toHaveTextContent("Agent administrator role required");
    cleanup();

    mockedList.mockRejectedValueOnce(new ApiError("Not authenticated", 401));
    const { onUnauthorized } = renderLogs();
    await waitFor(() => expect(onUnauthorized).toHaveBeenCalledTimes(1));
  });
});
