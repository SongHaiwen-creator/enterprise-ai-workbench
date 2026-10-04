import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { EvaluationDatasets } from "@/app/components/evaluation-datasets";
import { ApiError } from "@/utils/api";
import * as api from "@/utils/evaluation";

// Definition forms remain independently verified; Run behavior has its own suite.
vi.mock("@/app/components/evaluation-runs", () => ({ EvaluationRuns: () => null }));

vi.mock("@/utils/evaluation", async importOriginal => {
  const original = await importOriginal<typeof import("@/utils/evaluation")>();
  return { ...original, listEvaluationDatasets: vi.fn(), listEvaluationCases: vi.fn(),
    createEvaluationDataset: vi.fn(), updateEvaluationDataset: vi.fn(),
    createEvaluationCase: vi.fn(), updateEvaluationCase: vi.fn(), getEvaluationCase: vi.fn(),
    evaluationResources: vi.fn() };
});
const dataset: api.EvaluationDataset = {
  id: "dataset-1", workspace_id: "workspace-1", name: "Synthetic dataset", description: "Synthetic description",
  status: "active", created_by: "user-1", created_at: "2026-10-01T00:00:00Z", updated_at: "2026-10-01T00:00:00Z",
};
const item: api.EvaluationCase = { ...dataset, id: "case-1", dataset_id: dataset.id,
  name: "<script>alert(1)</script>", case_type: "refusal_behavior", schema_version: 1,
  agent_id: null, knowledge_base_id: null, tool_id: null, test_input: "<b>Synthetic input</b>",
  expected_behavior: { routing_intent: "unsupported", response_category: "unsupported_request", safe_response_required: true },
};
const props = { workspaceId: "workspace-1", workspaceName: "Synthetic Workspace", accessToken: "token", onUnauthorized: vi.fn() };
const page = <T,>(items: T[], offset = 0) => ({ items, limit: 50, offset });

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.listEvaluationDatasets).mockResolvedValue(page([dataset]));
  vi.mocked(api.listEvaluationCases).mockResolvedValue(page([item]));
  vi.mocked(api.getEvaluationCase).mockResolvedValue(item);
  vi.mocked(api.evaluationResources).mockResolvedValue({
    agents: [{ ...dataset, id: "agent-1", name: "Draft agent", status: "draft" }],
    knowledgeBases: [{ ...dataset, id: "kb-1", name: "Disabled KB", status: "disabled" }],
    tools: [{ id: "tool-1", name: "Read tool", status: "disabled", tool_key: "get_reimbursement_status" },
      { id: "tool-2", name: "Write tool", status: "active", tool_key: "create_it_access_request" }],
  });
  vi.mocked(api.createEvaluationCase).mockResolvedValue(item);
  vi.mocked(api.updateEvaluationCase).mockResolvedValue(item);
  vi.mocked(api.createEvaluationDataset).mockResolvedValue(dataset);
  vi.mocked(api.updateEvaluationDataset).mockResolvedValue(dataset);
});
afterEach(cleanup);

async function openDataset() {
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: "Synthetic dataset （已启用）" }));
  await screen.findByRole("button", { name: /alert\(1\).*拒绝行为/ });
  return user;
}

describe("Evaluation dataset administration", () => {
  it("creates and edits datasets with typed status and no server fields", async () => {
    render(<EvaluationDatasets {...props} />);
    const user = userEvent.setup();
    await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument());
    await user.type(screen.getByLabelText("数据集名称"), " New dataset ");
    await user.click(screen.getByRole("button", { name: "创建数据集" }));
    await waitFor(() => expect(api.createEvaluationDataset).toHaveBeenCalledWith("workspace-1", { name: "New dataset", description: null }, "token"));
    await screen.findByRole("button", { name: "保存数据集" });
    await user.selectOptions(screen.getByLabelText("数据集状态"), "disabled");
    await user.click(screen.getByRole("button", { name: "保存数据集" }));
    await waitFor(() => expect(api.updateEvaluationDataset).toHaveBeenCalledWith("workspace-1", "dataset-1", expect.objectContaining({ status: "disabled" }), "token"));
  });

  it.each(["knowledge_qa", "tool_calling", "permission_boundary", "refusal_behavior"] as const)("creates %s using its typed form", async category => {
    render(<EvaluationDatasets {...props} />);
    const user = await openDataset();
    await user.click(screen.getByRole("button", { name: "新建用例" }));
    await user.selectOptions(screen.getByLabelText("用例类型"), category);
    await user.type(screen.getByLabelText("用例名称"), "Synthetic case");
    await user.type(screen.getByLabelText("测试输入"), "Synthetic request");
    if (category === "knowledge_qa") {
      expect(screen.getByRole("option", { name: "Disabled KB （已停用）" })).toBeInTheDocument();
      await user.selectOptions(screen.getByLabelText("关联知识库"), "kb-1");
    }
    if (category === "tool_calling") {
      await user.selectOptions(screen.getByLabelText("预期工具结果"), "approval_required");
      expect(screen.queryByRole("option", { name: "Read tool （已停用）" })).not.toBeInTheDocument();
      await user.selectOptions(screen.getByLabelText("关联工具"), "tool-2");
    }
    await user.click(screen.getByRole("button", { name: "创建用例" }));
    await waitFor(() => expect(api.createEvaluationCase).toHaveBeenCalledTimes(1));
    const payload = vi.mocked(api.createEvaluationCase).mock.calls[0][2];
    expect(payload).toMatchObject({ case_type: category, name: "Synthetic case", test_input: "Synthetic request" });
    expect(payload).not.toHaveProperty("status");
    expect(payload).not.toHaveProperty("created_by");
    if (category === "tool_calling") expect(payload.expected_behavior).toMatchObject({ approval_required: true, tool_key: "create_it_access_request" });
    if (category === "permission_boundary") expect(payload.expected_behavior).toMatchObject({ access_denied: true, expected_http_status: 404 });
    expect(screen.queryByRole("button", { name: /运行|评分/ })).not.toBeInTheDocument();
  });

  it("loads literal content and edits status without changing category", async () => {
    const { container } = render(<EvaluationDatasets {...props} />);
    const user = await openDataset();
    expect(container.querySelector("script")).toBeNull();
    await user.click(screen.getByRole("button", { name: /alert\(1\).*拒绝行为/ }));
    expect(await screen.findByLabelText("测试输入")).toHaveValue("<b>Synthetic input</b>");
    expect(screen.queryByLabelText("用例类型")).not.toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("用例状态"), "disabled");
    await user.click(screen.getByRole("button", { name: "保存用例" }));
    await waitFor(() => expect(api.updateEvaluationCase).toHaveBeenCalled());
    const payload = vi.mocked(api.updateEvaluationCase).mock.calls[0][3];
    expect(payload.status).toBe("disabled");
    expect(payload).not.toHaveProperty("case_type");
    expect(payload).not.toHaveProperty("dataset_id");
  });

  it("disabled datasets prohibit new cases but retain edit controls", async () => {
    vi.mocked(api.listEvaluationDatasets).mockResolvedValue(page([{ ...dataset, status: "disabled" }]));
    render(<EvaluationDatasets {...props} />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Synthetic dataset （已停用）" }));
    await screen.findByRole("button", { name: /alert\(1\)/ });
    expect(screen.getByRole("button", { name: "新建用例" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: /alert\(1\)/ }));
    expect(await screen.findByRole("button", { name: "保存用例" })).toBeEnabled();
  });

  it.each([403, 404, 409, 422, 500, 0])("shows recoverable %s errors without erasing input", async status => {
    render(<EvaluationDatasets {...props} />);
    const user = await openDataset();
    await user.click(screen.getByRole("button", { name: /alert\(1\)/ }));
    await screen.findByRole("button", { name: "保存用例" });
    vi.mocked(api.updateEvaluationCase).mockRejectedValue(new ApiError("安全错误提示", status));
    await user.click(screen.getByRole("button", { name: "保存用例" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("安全错误提示");
    expect(screen.getByLabelText("测试输入")).toHaveValue(item.test_input);
  });

  it("clears authentication on 401", async () => {
    vi.mocked(api.listEvaluationDatasets).mockRejectedValue(new ApiError("Session expired", 401));
    render(<EvaluationDatasets {...props} />);
    await waitFor(() => expect(props.onUnauthorized).toHaveBeenCalledTimes(1));
  });

  it("shows empty lists and paginates both levels", async () => {
    vi.mocked(api.listEvaluationDatasets).mockResolvedValueOnce(page(Array.from({ length: 50 }, (_, index) => ({ ...dataset, id: `dataset-${index}` })))).mockResolvedValue(page([]));
    vi.mocked(api.listEvaluationCases).mockResolvedValueOnce(page(Array.from({ length: 50 }, (_, index) => ({ ...item, id: `case-${index}` })))).mockResolvedValue(page([]));
    render(<EvaluationDatasets {...props} />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "加载更多数据集" }));
    await waitFor(() => expect(api.listEvaluationDatasets).toHaveBeenCalledWith("workspace-1", 50, "token"));
    await user.click(screen.getAllByRole("button", { name: "Synthetic dataset （已启用）" })[0]);
    await user.click(await screen.findByRole("button", { name: "加载更多用例" }));
    await waitFor(() => expect(api.listEvaluationCases).toHaveBeenCalledWith("workspace-1", "dataset-0", 50, "token"));
    cleanup();
    render(<EvaluationDatasets {...props} />);
    expect(await screen.findByText("暂无评测数据集。")).toBeInTheDocument();
  });

  it("blocks duplicate submissions while a write is pending", async () => {
    let finish!: (value: api.EvaluationDataset) => void;
    vi.mocked(api.createEvaluationDataset).mockImplementation(() => new Promise(resolve => { finish = resolve; }));
    render(<EvaluationDatasets {...props} />);
    const user = userEvent.setup();
    await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument());
    await user.type(screen.getByLabelText("数据集名称"), "Synthetic");
    await user.dblClick(screen.getByRole("button", { name: "创建数据集" }));
    expect(api.createEvaluationDataset).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "创建数据集" })).toBeDisabled();
    await act(async () => finish(dataset));
  });

  it("clears content on Workspace/session change and ignores old detail responses", async () => {
    let finish!: (value: api.EvaluationCase) => void;
    vi.mocked(api.getEvaluationCase).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
    const { rerender } = render(<EvaluationDatasets {...props} />);
    const user = await openDataset();
    await user.click(screen.getByRole("button", { name: /alert\(1\)/ }));
    vi.mocked(api.listEvaluationDatasets).mockResolvedValue(page([]));
    rerender(<EvaluationDatasets {...props} workspaceId="workspace-2" />);
    await screen.findByText("暂无评测数据集。");
    await act(async () => finish(item));
    expect(screen.queryByLabelText("测试输入")).not.toBeInTheDocument();
    rerender(<EvaluationDatasets {...props} accessToken="new-session" />);
    await screen.findByText("暂无评测数据集。");
    expect(screen.queryByLabelText("测试输入")).not.toBeInTheDocument();
  });
});
