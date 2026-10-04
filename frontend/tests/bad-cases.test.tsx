import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BadCases, RegisterBadCase } from "@/app/components/bad-cases";
import { ApiError } from "@/utils/api";
import * as api from "@/utils/bad-cases";
import { RunCaseDetail } from "@/utils/evaluation-runs";
import { PlatformNavigation } from "@/app/components/platform-navigation";

vi.mock("@/utils/bad-cases", async original => ({ ...await original<typeof import("@/utils/bad-cases")>(),
  listBadCases: vi.fn(), getBadCase: vi.fn(), getBadCaseHistory: vi.fn(), createBadCase: vi.fn(), updateBadCase: vi.fn(),
}));
const source: RunCaseDetail = { id: "source", workspace_id: "workspace", run_id: "run", case_id: "case", ordinal: 1,
  case_type: "tool_calling", name: "Synthetic case", result: "passed", attempted: true, latency_ms: 12,
  error_category: null, started_at: "2026-10-04T00:00:00Z", completed_at: "2026-10-04T00:00:01Z",
  case_snapshot: {}, context_snapshot: {}, test_input_snapshot: "<script>captured synthetic input</script>",
  expected_behavior_snapshot: { routing_intent: "tool_request", outcome: "not_executed", tool_key: null, approval_required: false, non_execution_reason: "no_available_tool" },
  actual_behavior: { execution_mode: "dry_run", adapter_executed: false }, comparison_checks: { routing_intent: true } };
const item: api.BadCaseDetail = { id: "issue", workspace_id: "workspace", source_run_case_id: "source", source_run_id: "run", source_case_id: "case",
  dataset_id: "dataset", agent_id: "agent", source_result: "passed", source_case_type: "tool_calling", origin_kind: "manual_review",
  title: "Synthetic concern", description: "Human concern", category: "unclassified", status: "open", possible_cause: null,
  handling_note: null, resolution_note: null, revision: 1, created_by: "user", updated_by: "user", created_at: source.started_at!, updated_at: source.started_at!, source_evidence: source };
const props = { workspaceId: "workspace", accessToken: "token", onUnauthorized: vi.fn() };
const history: api.HistoryItem = { id: "history", bad_case_id: "issue", workspace_id: "workspace", actor_id: "user", revision: 1, event: "created", created_at: item.created_at, change_reason: null, before_values: null, after_values: { title: item.title, description: item.description, category: item.category, status: item.status, possible_cause: null, handling_note: null, resolution_note: null } };
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.listBadCases).mockResolvedValue({ items: [item], limit: 50, offset: 0 });
  vi.mocked(api.getBadCase).mockResolvedValue(item);
  vi.mocked(api.getBadCaseHistory).mockResolvedValue({ items: [history], limit: 50, offset: 0 });
  vi.mocked(api.createBadCase).mockResolvedValue(item);
  vi.mocked(api.updateBadCase).mockResolvedValue({ ...item, revision: 2 });
});
afterEach(cleanup);
async function open() {
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: item.title }));
  await screen.findByLabelText("问题标题");
  return user;
}

describe("Bad Cases", () => {
  it("shows literal immutable evidence, manual labels and history, then sends revision", async () => {
    render(<BadCases {...props} />);
    const user = await open();
    expect(screen.getByText(source.test_input_snapshot)).toBeInTheDocument();
    expect(document.querySelector("script")).toBeNull();
    expect(screen.getByText(/dry run/)).toBeInTheDocument();
    expect(screen.getByText(/操作者 user/)).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("处理状态"), "resolved");
    await user.type(screen.getByLabelText("人工处理结论"), "Manually addressed");
    await user.type(screen.getByLabelText("变更理由"), "Reviewed");
    await user.click(screen.getByRole("button", { name: "保存问题" }));
    await waitFor(() => expect(api.updateBadCase).toHaveBeenCalledWith("workspace", "issue", expect.objectContaining({ expected_revision: 1, status: "resolved", resolution_note: "Manually addressed", change_reason: "Reviewed" }), "token"));
  });
  it("requires conclusion and reason and limits terminal-to-terminal transitions", async () => {
    vi.mocked(api.getBadCase).mockResolvedValue({ ...item, status: "resolved", resolution_note: "Original conclusion" });
    render(<BadCases {...props} />);
    const user = await open();
    expect(within(screen.getByLabelText("处理状态")).queryByRole("option", { name: "不处理（人工）" })).not.toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("处理状态"), "open");
    expect(screen.getByLabelText("变更理由")).toBeRequired();
    expect(screen.queryByLabelText("人工处理结论")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "保存问题" }));
    expect(api.updateBadCase).not.toHaveBeenCalled();
    await user.type(screen.getByLabelText("变更理由"), "Reopened");
    await user.click(screen.getByRole("button", { name: "保存问题" }));
    await waitFor(() => expect(api.updateBadCase).toHaveBeenCalledWith("workspace", "issue", expect.objectContaining({ status: "open", resolution_note: null }), "token"));
  });
  it.each([new ApiError("Bad case revision conflict", 409), new ApiError("Network", 0)])("preserves conflicting draft and blocks retry until explicit refresh (%s)", async reason => {
    vi.mocked(api.updateBadCase).mockRejectedValue(reason);
    render(<BadCases {...props} />);
    const user = await open();
    await user.clear(screen.getByLabelText("问题标题")); await user.type(screen.getByLabelText("问题标题"), "Unsaved draft");
    await user.click(screen.getByRole("button", { name: "保存问题" }));
    await screen.findByRole("alert");
    expect(screen.getByLabelText("问题标题")).toHaveValue("Unsaved draft");
    expect(screen.getByRole("button", { name: "保存问题" })).toBeDisabled();
    vi.mocked(api.getBadCase).mockResolvedValue({ ...item, title: "Latest", revision: 2 });
    await user.click(screen.getByRole("button", { name: "重新读取最新问题（替换草稿）" }));
    await waitFor(() => expect(screen.getByLabelText("问题标题")).toHaveValue("Latest"));
    expect(api.updateBadCase).toHaveBeenCalledTimes(1);
  });
  it("filters, paginates and protects duplicate save", async () => {
    vi.mocked(api.listBadCases).mockResolvedValue({ items: Array.from({ length: 50 }, (_, i) => ({ ...item, id: `issue-${i}`, title: `Concern ${i}` })), limit: 50, offset: 0 });
    render(<BadCases {...props} />);
    const user = userEvent.setup();
    await screen.findByRole("button", { name: "加载更多问题" });
    await user.click(screen.getByRole("button", { name: "加载更多问题" }));
    await waitFor(() => expect(api.listBadCases).toHaveBeenLastCalledWith("workspace", {}, 50, "token"));
    await user.selectOptions(screen.getByLabelText("来源筛选"), "execution_error");
    await waitFor(() => expect(api.listBadCases).toHaveBeenLastCalledWith("workspace", { origin_kind: "execution_error" }, 0, "token"));
  });
  it("explicit reread replaces an ambiguous draft even when revision is unchanged", async () => {
    vi.mocked(api.updateBadCase).mockRejectedValue(new ApiError("Network", 0));
    render(<BadCases {...props} />);
    const user = await open();
    await user.clear(screen.getByLabelText("问题标题"));
    await user.type(screen.getByLabelText("问题标题"), "Ambiguous draft");
    await user.click(screen.getByRole("button", { name: "保存问题" }));
    await screen.findByRole("alert");
    expect(screen.getByLabelText("问题标题")).toHaveValue("Ambiguous draft");
    await user.click(screen.getByRole("button", { name: "重新读取最新问题（替换草稿）" }));
    await waitFor(() => expect(screen.getByLabelText("问题标题")).toHaveValue(item.title));
    expect(api.updateBadCase).toHaveBeenCalledTimes(1);
  });
  it("drops late Workspace responses and unauthorized state", async () => {
    let resolve: (value: api.BadCaseDetail) => void = () => {};
    vi.mocked(api.getBadCase).mockImplementation(() => new Promise(success => { resolve = success; }));
    const { rerender } = render(<BadCases {...props} />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: item.title }));
    vi.mocked(api.listBadCases).mockResolvedValue({ items: [], limit: 50, offset: 0 });
    rerender(<BadCases {...props} workspaceId="other" />);
    await act(async () => resolve(item));
    expect(screen.queryByLabelText("问题标题")).not.toBeInTheDocument();
    expect(screen.queryByText(source.test_input_snapshot)).not.toBeInTheDocument();
    vi.mocked(api.listBadCases).mockRejectedValue(new ApiError("Unauthorized", 401));
    await user.click(screen.getByRole("button", { name: "刷新问题列表" }));
    await waitFor(() => expect(props.onUnauthorized).toHaveBeenCalled());
  });
});

describe("Register Bad Case", () => {
  it.each(["passed", "failed", "error"] as const)("registers %s manually, sends only human fields", async result => {
    vi.mocked(api.listBadCases).mockResolvedValue({ items: [], limit: 50, offset: 0 });
    render(<RegisterBadCase {...props} source={{ ...source, result }} runTerminal />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "登记问题 / 刷新核查" }));
    await screen.findByLabelText("问题描述");
    await user.type(screen.getByLabelText("问题描述"), "Redacted concern");
    await user.click(screen.getByRole("button", { name: "提交登记" }));
    await waitFor(() => expect(api.createBadCase).toHaveBeenCalledWith("workspace", { ...source, result }, { title: source.name, description: "Redacted concern", category: "unclassified", possible_cause: null }, "token"));
    await screen.findByText(`已登记：${item.title}`);
  });
  it("finds an existing issue instead of creating a duplicate", async () => {
    render(<RegisterBadCase {...props} source={source} runTerminal />);
    await userEvent.click(screen.getByRole("button", { name: "登记问题 / 刷新核查" }));
    await screen.findByText(`已登记：${item.title}`);
    expect(screen.queryByRole("button", { name: "提交登记" })).not.toBeInTheDocument();
    expect(api.createBadCase).not.toHaveBeenCalled();
  });
  it("blocks pending/running results", () => {
    const { rerender } = render(<RegisterBadCase {...props} source={source} runTerminal={false} />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    rerender(<RegisterBadCase {...props} source={{ ...source, result: null }} runTerminal />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
  it("does not retry ambiguous writes or double clicks and lets user inspect existing record", async () => {
    vi.mocked(api.listBadCases).mockResolvedValue({ items: [], limit: 50, offset: 0 });
    let reject: (reason: Error) => void = () => {};
    vi.mocked(api.createBadCase).mockImplementation(() => new Promise((_, failure) => { reject = failure; }));
    render(<RegisterBadCase {...props} source={source} runTerminal />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "登记问题 / 刷新核查" }));
    await user.type(await screen.findByLabelText("问题描述"), "Redacted");
    await user.dblClick(screen.getByRole("button", { name: "提交登记" }));
    expect(api.createBadCase).toHaveBeenCalledTimes(1);
    await act(async () => reject(new ApiError("Bad case already exists", 409)));
    await screen.findByRole("alert");
    expect(screen.getByRole("button", { name: "提交登记" })).toBeDisabled();
    vi.mocked(api.listBadCases).mockResolvedValue({ items: [item], limit: 50, offset: 0 });
    await user.click(screen.getByRole("button", { name: "登记问题 / 刷新核查" }));
    await screen.findByText(`已登记：${item.title}`);
    expect(api.createBadCase).toHaveBeenCalledTimes(1);
  });
});

it("shows the operations entry only for administrative navigation", () => {
  const navProps = { workspaces: [], selectedId: null, currentUser: { id: "user", name: "User", email: "synthetic@example.test", status: "active" as const }, area: "bad-cases" as const, canManageOperations: false, pending: false, onWorkspace: vi.fn(), onArea: vi.fn(), onLogout: vi.fn() };
  const { rerender } = render(<PlatformNavigation {...navProps} />);
  expect(screen.queryByRole("button", { name: "问题案例" })).not.toBeInTheDocument();
  rerender(<PlatformNavigation {...navProps} canManageOperations />);
  expect(screen.getByRole("button", { name: "问题案例" })).toBeInTheDocument();
});
