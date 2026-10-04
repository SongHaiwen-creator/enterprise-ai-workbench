import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Approvals } from "@/app/components/approvals";
import {
  ApiError,
  ApprovalResponse,
  decideApproval,
  getApproval,
  listApprovals,
} from "@/utils/api";

vi.mock("@/utils/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/utils/api")>();
  return {
    ...actual,
    listApprovals: vi.fn(),
    getApproval: vi.fn(),
    decideApproval: vi.fn(),
  };
});

const mockedList = vi.mocked(listApprovals);
const mockedGet = vi.mocked(getApproval);
const mockedDecide = vi.mocked(decideApproval);

const REVIEWER_ID = "reviewer-1";

function approval(overrides: Partial<ApprovalResponse> = {}): ApprovalResponse {
  return {
    id: "approval-1",
    workspace_id: "workspace-1",
    decision_status: "pending",
    execution_status: "not_started",
    action_type: "it_access_request.create",
    tool: { tool_key: "create_it_access_request", name: "Create IT access request" },
    agent: { id: "agent-1", name: "Employee Service Assistant" },
    requester: { id: "employee-1", name: "Employee One" },
    arguments: {
      system: "production_database",
      access_level: "read_only",
      business_justification: "<img src=x onerror=alert(1)> Investigate incidents.",
      duration_days: 14,
    },
    created_at: "2026-09-28T10:00:00Z",
    expires_at: "2026-10-01T10:00:00Z",
    decision: null,
    execution: null,
    ...overrides,
  };
}

const approvedSucceeded = approval({
  decision_status: "approved",
  execution_status: "succeeded",
  decision: {
    decided_by: { id: REVIEWER_ID, name: "Admin One" },
    decided_at: "2026-09-28T11:00:00Z",
    note: "Approved for INC-1042.",
    invalidation_reason: null,
  },
  execution: {
    executed_at: "2026-09-28T11:00:00Z",
    failure_category: null,
    result: {
      type: "it_access_request",
      reference: "ITAR-3FA91C07B2D4",
      system: "production_database",
      access_level: "read_only",
      duration_days: 14,
      status: "recorded",
    },
  },
});

const approvedFailed = approval({
  decision_status: "approved",
  execution_status: "failed",
  decision: {
    decided_by: { id: REVIEWER_ID, name: "Admin One" },
    decided_at: "2026-09-28T11:00:00Z",
    note: null,
    invalidation_reason: null,
  },
  execution: { executed_at: "2026-09-28T11:00:00Z", failure_category: "adapter_error", result: null },
});

const invalidated = approval({
  decision_status: "invalidated",
  decision: {
    decided_by: null,
    decided_at: "2026-09-28T11:00:00Z",
    note: null,
    invalidation_reason: "capability_unavailable",
  },
});

function renderApprovals(overrides: Partial<Parameters<typeof Approvals>[0]> = {}) {
  const props = {
    workspaceId: "workspace-1",
    workspaceName: "Acme",
    currentUserId: REVIEWER_ID,
    canReview: true,
    accessToken: "test-token",
    onUnauthorized: vi.fn(),
    onPendingChange: vi.fn(),
    ...overrides,
  };
  return { ...render(<Approvals {...props} />), props };
}

async function openFirst() {
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: /Create IT access request/ }));
  return user;
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((settle) => { resolve = settle; });
  return { promise, resolve };
}

describe("审批中心", () => {
  beforeEach(() => {
    mockedList.mockReset();
    mockedGet.mockReset();
    mockedDecide.mockReset();
    mockedList.mockResolvedValue({ items: [approval()], limit: 50, offset: 0 });
    mockedGet.mockResolvedValue(approval());
  });
  afterEach(cleanup);

  it("loads the review queue for reviewers and shows separate status labels", async () => {
    renderApprovals();

    const item = await screen.findByRole("button", { name: /Create IT access request/ });
    expect(mockedList).toHaveBeenCalledWith("workspace-1", "review", "test-token");
    expect(within(item).getByText("待审核")).toBeInTheDocument();
    expect(within(item).getByText("未执行")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "待我审核" })).toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "我的申请" }));
    expect(mockedList).toHaveBeenLastCalledWith("workspace-1", "mine", "test-token");
  });

  it("shows only the member's own requests and no decision controls to non-reviewers", async () => {
    renderApprovals({ canReview: false, currentUserId: "employee-1" });
    await openFirst();

    expect(mockedList).toHaveBeenCalledWith("workspace-1", "mine", "test-token");
    expect(screen.queryByRole("button", { name: "待我审核" })).not.toBeInTheDocument();
    expect(await screen.findByText("Employee Service Assistant")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "批准" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "拒绝" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /取消/ })).not.toBeInTheDocument();
  });

  it("hides decision controls on a reviewer's own request", async () => {
    mockedGet.mockResolvedValue(approval({ requester: { id: REVIEWER_ID, name: "Admin One" } }));
    renderApprovals();
    await openFirst();

    expect(await screen.findByText("Employee Service Assistant")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "批准" })).not.toBeInTheDocument();
  });

  it("renders arguments as literal text", async () => {
    const { container } = renderApprovals();
    await openFirst();

    expect(await screen.findByText(
      "<img src=x onerror=alert(1)> Investigate incidents.",
    )).toBeInTheDocument();
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByText("生产数据库")).toBeInTheDocument();
    expect(screen.getByText("14 天")).toBeInTheDocument();
  });

  it("approves with a note, locks while pending, and re-reads server state", async () => {
    const pending = deferred<ApprovalResponse>();
    mockedDecide.mockReturnValue(pending.promise);
    const { props } = renderApprovals();
    const user = await openFirst();
    await user.type(await screen.findByLabelText("审批意见（可选）"), "  Approved for INC-1042.  ");
    await user.click(screen.getByRole("button", { name: "批准" }));

    expect(mockedDecide).toHaveBeenCalledWith(
      "workspace-1", "approval-1", "approve", "Approved for INC-1042.", "test-token",
    );
    expect(screen.getByRole("button", { name: "正在保存…" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "拒绝" })).toBeDisabled();
    expect(props.onPendingChange).toHaveBeenLastCalledWith(true);

    mockedGet.mockResolvedValue(approvedSucceeded);
    mockedList.mockResolvedValue({ items: [approvedSucceeded], limit: 50, offset: 0 });
    pending.resolve(approvedSucceeded);

    expect(await screen.findByText("批准决定已保存")).toBeInTheDocument();
    expect(await screen.findByText(/ITAR-3FA91C07B2D4 已记录/)).toBeInTheDocument();
    expect(screen.getByText("Approved for INC-1042.")).toBeInTheDocument();
    expect(props.onPendingChange).toHaveBeenLastCalledWith(false);
    expect(mockedGet).toHaveBeenCalledTimes(2);
    expect(mockedList).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole("button", { name: "批准" })).not.toBeInTheDocument();
  });

  it("sends a reject decision without a note", async () => {
    mockedDecide.mockResolvedValue(approval({ decision_status: "rejected" }));
    renderApprovals();
    const user = await openFirst();
    await user.click(await screen.findByRole("button", { name: "拒绝" }));

    expect(mockedDecide).toHaveBeenCalledWith(
      "workspace-1", "approval-1", "reject", null, "test-token",
    );
  });

  it("distinguishes approved + failed from invalidated", async () => {
    mockedGet.mockResolvedValue(approvedFailed);
    renderApprovals();
    await openFirst();
    const detail = screen.getByRole("complementary", { name: "审批详情" });
    expect(await within(detail).findByText("执行失败")).toBeInTheDocument();
    expect(within(detail).getByText("已批准")).toBeInTheDocument();
    expect(within(detail).getByText(/执行服务返回错误/)).toBeInTheDocument();

    cleanup();
    mockedGet.mockResolvedValue(invalidated);
    renderApprovals();
    await openFirst();
    const invalidatedDetail = screen.getByRole("complementary", { name: "审批详情" });
    expect(await within(invalidatedDetail).findByText("已失效")).toBeInTheDocument();
    expect(within(invalidatedDetail).getByText("未执行")).toBeInTheDocument();
    expect(within(invalidatedDetail).getByText(/智能体或工具已不可用/))
      .toBeInTheDocument();
    expect(within(invalidatedDetail).getByText(/已失效 · 系统处理/)).toBeInTheDocument();
  });

  it.each([
    [403, "没有审批访问权限"],
    [404, "审批申请不存在"],
    [409, "审批状态已变化"],
    [422, "请检查审批意见"],
    [502, "执行失败"],
    [503, "审批服务暂不可用"],
    [0, "无法连接服务"],
  ])("handles a %s decision error and re-reads the Approval", async (status, title) => {
    mockedDecide.mockRejectedValue(new ApiError("服务端安全提示", status));
    renderApprovals();
    const user = await openFirst();
    await user.click(await screen.findByRole("button", { name: "批准" }));

    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText(title)).toBeInTheDocument();
    expect(within(alert).getByText("服务端安全提示")).toBeInTheDocument();
    await waitFor(() => expect(mockedGet).toHaveBeenCalledTimes(2));
    expect(mockedList).toHaveBeenCalledTimes(2);
  });

  it("signs out on 401 without re-reading", async () => {
    mockedDecide.mockRejectedValue(new ApiError("Could not validate credentials", 401));
    const { props } = renderApprovals();
    const user = await openFirst();
    await user.click(await screen.findByRole("button", { name: "批准" }));

    await waitFor(() => expect(props.onUnauthorized).toHaveBeenCalled());
    expect(mockedGet).toHaveBeenCalledTimes(1);
  });

  it("ignores a late detail response after another Approval is selected", async () => {
    const second = approval({
      id: "approval-2",
      agent: { id: "agent-2", name: "IT Assistant" },
      tool: { tool_key: "create_it_access_request", name: "Second request" },
    });
    mockedList.mockResolvedValue({ items: [approval(), second], limit: 50, offset: 0 });
    const late = deferred<ApprovalResponse>();
    mockedGet.mockReturnValueOnce(late.promise).mockResolvedValueOnce(second);
    renderApprovals();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /Create IT access request/ }));
    await user.click(screen.getByRole("button", { name: /Second request/ }));
    expect(await screen.findByText("IT Assistant")).toBeInTheDocument();

    late.resolve(approval());
    await Promise.resolve();
    expect(screen.queryByText("Employee Service Assistant")).not.toBeInTheDocument();
    expect(screen.getByText("IT Assistant")).toBeInTheDocument();
  });

  it("resets when remounted for another Workspace", async () => {
    const { rerender, props } = renderApprovals();
    await openFirst();
    expect(await screen.findByText("Employee Service Assistant")).toBeInTheDocument();

    mockedList.mockResolvedValue({ items: [], limit: 50, offset: 0 });
    rerender(<Approvals key="workspace-2" {...props} workspaceId="workspace-2" />);

    expect(await screen.findByText("暂无审批申请。")).toBeInTheDocument();
    expect(mockedList).toHaveBeenLastCalledWith("workspace-2", "review", "test-token");
    expect(screen.queryByText("Employee Service Assistant")).not.toBeInTheDocument();
  });
});
