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

describe("Approvals", () => {
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
    expect(within(item).getByText("Pending review")).toBeInTheDocument();
    expect(within(item).getByText("Not executed")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Review queue" })).toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "My requests" }));
    expect(mockedList).toHaveBeenLastCalledWith("workspace-1", "mine", "test-token");
  });

  it("shows only the member's own requests and no decision controls to non-reviewers", async () => {
    renderApprovals({ canReview: false, currentUserId: "employee-1" });
    await openFirst();

    expect(mockedList).toHaveBeenCalledWith("workspace-1", "mine", "test-token");
    expect(screen.queryByRole("button", { name: "Review queue" })).not.toBeInTheDocument();
    expect(await screen.findByText("Employee Service Assistant")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reject" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /cancel/i })).not.toBeInTheDocument();
  });

  it("hides decision controls on a reviewer's own request", async () => {
    mockedGet.mockResolvedValue(approval({ requester: { id: REVIEWER_ID, name: "Admin One" } }));
    renderApprovals();
    await openFirst();

    expect(await screen.findByText("Employee Service Assistant")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
  });

  it("renders arguments as literal text", async () => {
    const { container } = renderApprovals();
    await openFirst();

    expect(await screen.findByText(
      "<img src=x onerror=alert(1)> Investigate incidents.",
    )).toBeInTheDocument();
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByText("production database")).toBeInTheDocument();
    expect(screen.getByText("14 days")).toBeInTheDocument();
  });

  it("approves with a note, locks while pending, and re-reads server state", async () => {
    const pending = deferred<ApprovalResponse>();
    mockedDecide.mockReturnValue(pending.promise);
    const { props } = renderApprovals();
    const user = await openFirst();
    await user.type(await screen.findByLabelText("Note (optional)"), "  Approved for INC-1042.  ");
    await user.click(screen.getByRole("button", { name: "Approve" }));

    expect(mockedDecide).toHaveBeenCalledWith(
      "workspace-1", "approval-1", "approve", "Approved for INC-1042.", "test-token",
    );
    expect(screen.getByRole("button", { name: "Saving…" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Reject" })).toBeDisabled();
    expect(props.onPendingChange).toHaveBeenLastCalledWith(true);

    mockedGet.mockResolvedValue(approvedSucceeded);
    mockedList.mockResolvedValue({ items: [approvedSucceeded], limit: 50, offset: 0 });
    pending.resolve(approvedSucceeded);

    expect(await screen.findByText("Approval recorded")).toBeInTheDocument();
    expect(await screen.findByText(/ITAR-3FA91C07B2D4 recorded/)).toBeInTheDocument();
    expect(screen.getByText("Approved for INC-1042.")).toBeInTheDocument();
    expect(props.onPendingChange).toHaveBeenLastCalledWith(false);
    expect(mockedGet).toHaveBeenCalledTimes(2);
    expect(mockedList).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
  });

  it("sends a reject decision without a note", async () => {
    mockedDecide.mockResolvedValue(approval({ decision_status: "rejected" }));
    renderApprovals();
    const user = await openFirst();
    await user.click(await screen.findByRole("button", { name: "Reject" }));

    expect(mockedDecide).toHaveBeenCalledWith(
      "workspace-1", "approval-1", "reject", null, "test-token",
    );
  });

  it("distinguishes approved + failed from invalidated", async () => {
    mockedGet.mockResolvedValue(approvedFailed);
    renderApprovals();
    await openFirst();
    const detail = screen.getByRole("complementary", { name: "Approval" });
    expect(await within(detail).findByText("Execution failed")).toBeInTheDocument();
    expect(within(detail).getByText("Approved")).toBeInTheDocument();
    expect(within(detail).getByText(/could not be executed \(adapter error\)/)).toBeInTheDocument();

    cleanup();
    mockedGet.mockResolvedValue(invalidated);
    renderApprovals();
    await openFirst();
    const invalidatedDetail = screen.getByRole("complementary", { name: "Approval" });
    expect(await within(invalidatedDetail).findByText("Invalidated")).toBeInTheDocument();
    expect(within(invalidatedDetail).getByText("Not executed")).toBeInTheDocument();
    expect(within(invalidatedDetail).getByText(/The Agent or Tool is no longer available/))
      .toBeInTheDocument();
    expect(within(invalidatedDetail).getByText(/Invalidated by the system/)).toBeInTheDocument();
  });

  it.each([
    [403, "Approval access denied"],
    [404, "Approval not found"],
    [409, "Approval changed"],
    [422, "Decision needs revision"],
    [502, "Execution failed"],
    [503, "Approval service unavailable"],
    [0, "Connection unavailable"],
  ])("handles a %s decision error and re-reads the Approval", async (status, title) => {
    mockedDecide.mockRejectedValue(new ApiError("Server detail", status));
    renderApprovals();
    const user = await openFirst();
    await user.click(await screen.findByRole("button", { name: "Approve" }));

    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText(title)).toBeInTheDocument();
    expect(within(alert).getByText("Server detail")).toBeInTheDocument();
    await waitFor(() => expect(mockedGet).toHaveBeenCalledTimes(2));
    expect(mockedList).toHaveBeenCalledTimes(2);
  });

  it("signs out on 401 without re-reading", async () => {
    mockedDecide.mockRejectedValue(new ApiError("Could not validate credentials", 401));
    const { props } = renderApprovals();
    const user = await openFirst();
    await user.click(await screen.findByRole("button", { name: "Approve" }));

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

    expect(await screen.findByText("No approvals to show.")).toBeInTheDocument();
    expect(mockedList).toHaveBeenLastCalledWith("workspace-2", "review", "test-token");
    expect(screen.queryByText("Employee Service Assistant")).not.toBeInTheDocument();
  });
});
