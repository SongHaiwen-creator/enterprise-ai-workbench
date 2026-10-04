import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { EvaluationRuns } from "@/app/components/evaluation-runs";
import { AgentSummary } from "@/utils/api";
import { EvaluationCaseSummary, EvaluationDataset } from "@/utils/evaluation";
import * as api from "@/utils/evaluation-runs";

vi.mock("@/utils/evaluation-runs", async importOriginal => ({
  ...await importOriginal<typeof import("@/utils/evaluation-runs")>(),
  activeRunCases: vi.fn(), createEvaluationRun: vi.fn(), listEvaluationRuns: vi.fn(),
  getEvaluationRun: vi.fn(), listRunCases: vi.fn(), getRunCase: vi.fn(),
}));
const dataset: EvaluationDataset = { id: "dataset", workspace_id: "workspace", name: "Synthetic Dataset",
  description: null, status: "active", created_by: "user", created_at: "2026-10-02T00:00:00Z", updated_at: "2026-10-02T00:00:00Z" };
const agents: AgentSummary[] = [{ ...dataset, id: "agent", name: "Active Agent" },
  { ...dataset, id: "draft", name: "Draft Agent", status: "draft" }];
const item: EvaluationCaseSummary = { ...dataset, id: "case", dataset_id: dataset.id,
  case_type: "tool_calling", schema_version: 1, agent_id: null, knowledge_base_id: null, tool_id: null };
const empty = { matched: 0, eligible: 0, value: null };
const full = { matched: 1, eligible: 1, value: 1 };
const run: api.EvaluationRun = { id: "run", workspace_id: "workspace", dataset_id: "dataset", agent_id: "agent", created_by: "user",
  dataset_name: "Captured Dataset", agent_name: "Captured Agent", status: "completed", created_at: dataset.created_at,
  started_at: dataset.created_at, deadline_at: dataset.created_at, completed_at: dataset.created_at,
  total_cases: 1, passed_cases: 1, failed_cases: 0, error_cases: 0, pending_cases: 0, failure_category: null,
  metrics: { overall_pass_rate: full, evaluation_coverage: full, error_rate: { ...full, matched: 0, value: 0 },
    category_pass_rate: { knowledge_qa: empty, tool_calling: full, permission_boundary: empty, refusal_behavior: empty },
    routing_match_rate: full, tool_selection_match_rate: full, tool_outcome_match_rate: full, permission_boundary_pass_rate: empty,
    refusal_behavior_pass_rate: empty, citation_requirement_compliance: empty,
    latency_ms: { count: 1, error_count: 0, min: 12, max: 12, mean: 12, median: 12 } },
};
const result: api.RunCase = { id: "result", workspace_id: "workspace", run_id: "run", case_id: "case", ordinal: 1,
  case_type: "tool_calling", name: "<script>Synthetic case</script>", result: "passed", attempted: true,
  latency_ms: 12, error_category: null, started_at: dataset.created_at, completed_at: dataset.created_at };
const props = { workspaceId: "workspace", accessToken: "token", dataset, agents, onUnauthorized: vi.fn() };

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.activeRunCases).mockResolvedValue([item]);
  vi.mocked(api.listEvaluationRuns).mockResolvedValue({ items: [], limit: 50, offset: 0 });
  vi.mocked(api.createEvaluationRun).mockResolvedValue(run);
  vi.mocked(api.getEvaluationRun).mockResolvedValue({ ...run, dataset_snapshot: {}, agent_snapshot: {}, config_snapshot: {},
    configuration_sha256: "digest", snapshot_version: 1, scorer_version: "evaluation-scorer-v1", provider_egress_acknowledged: true });
  vi.mocked(api.listRunCases).mockResolvedValue({ items: [result], limit: 100, offset: 0 });
  vi.mocked(api.getRunCase).mockResolvedValue({ ...result, case_snapshot: {}, context_snapshot: {},
    test_input_snapshot: "<b>Captured synthetic input</b>", expected_behavior_snapshot: {
      routing_intent: "tool_request", outcome: "executed", tool_key: "get_employee_information", approval_required: false, non_execution_reason: null },
    actual_behavior: { execution_mode: "dry_run", adapter_executed: false, would_outcome: "executed" }, comparison_checks: { outcome: true } });
});
afterEach(cleanup);
async function ready() {
  await waitFor(() => expect(screen.getByRole("button", { name: "刷新运行记录" })).toBeEnabled());
  const user = userEvent.setup();
  await user.selectOptions(screen.getByLabelText("评测智能体"), "agent");
  return user;
}
describe("Evaluation Runs", () => {
  it("requires explicit egress consent and renders dry-run history and literal details", async () => {
    render(<EvaluationRuns {...props} />);
    const user = await ready();
    expect(screen.queryByRole("option", { name: "Draft Agent" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "运行评测" })).toBeDisabled();
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "运行评测" }));
    await screen.findByText(/运行概览： Captured Dataset/);
    expect(api.createEvaluationRun).toHaveBeenCalledWith("workspace", "dataset", "agent", true, "token");
    expect(screen.getByText(/通过 1，未通过 0，错误 0，待处理 0/)).toBeInTheDocument();
    expect(screen.getByText(/知识问答: 未评测/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: result.name }));
    await screen.findByText(/工具评测仅进行模拟验证/);
    expect(screen.getByText("<b>Captured synthetic input</b>")).toBeInTheDocument();
    expect(document.querySelector("script")).toBeNull();
    expect(api.getRunCase).toHaveBeenCalledWith("workspace", "run", "result", "token");
  });
  it.each([0, 6])("blocks an invalid active count of %i", async count => {
    vi.mocked(api.activeRunCases).mockResolvedValue(Array.from({ length: count }, () => item));
    render(<EvaluationRuns {...props} />);
    await ready();
    expect(screen.getByRole("button", { name: "运行评测" })).toBeDisabled();
    expect(api.createEvaluationRun).not.toHaveBeenCalled();
  });
  it("allows local permission cases without provider consent", async () => {
    vi.mocked(api.activeRunCases).mockResolvedValue([{ ...item, case_type: "permission_boundary" }]);
    render(<EvaluationRuns {...props} />);
    const user = await ready();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "运行评测" }));
    await waitFor(() => expect(api.createEvaluationRun).toHaveBeenCalledWith("workspace", "dataset", "agent", false, "token"));
  });
  it("blocks duplicate submit and uses history recovery after an ambiguous timeout", async () => {
    let reject: (error: Error) => void = () => {};
    vi.mocked(api.createEvaluationRun).mockImplementation(() => new Promise((_, failure) => { reject = failure; }));
    render(<EvaluationRuns {...props} />);
    const user = await ready(); await user.click(screen.getByRole("checkbox"));
    const submit = screen.getByRole("button", { name: "运行评测" });
    await user.dblClick(submit);
    expect(api.createEvaluationRun).toHaveBeenCalledTimes(1);
    expect(submit).toBeDisabled();
    await act(async () => reject(new Error("timeout")));
    await screen.findByRole("alert");
    expect(screen.getByRole("alert")).toHaveTextContent("请先刷新运行记录");
    await user.click(screen.getByRole("button", { name: "刷新运行记录" }));
    expect(api.createEvaluationRun).toHaveBeenCalledTimes(1);
  });
  it("discards old Workspace responses and clears confidential state", async () => {
    let resolve: (value: api.EvaluationRun) => void = () => {};
    vi.mocked(api.createEvaluationRun).mockImplementation(() => new Promise(success => { resolve = success; }));
    const { rerender } = render(<EvaluationRuns {...props} />);
    const user = await ready(); await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "运行评测" }));
    rerender(<EvaluationRuns {...props} workspaceId="other-workspace" />);
    await act(async () => resolve(run));
    expect(screen.queryByText(/运行概览/)).not.toBeInTheDocument();
    expect(screen.getByLabelText("评测智能体")).toHaveValue("");
    expect(api.getEvaluationRun).not.toHaveBeenCalled();
  });
});
