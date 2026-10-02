import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { EvaluationDatasets } from "@/app/components/evaluation-datasets";
import { ApiError } from "@/utils/api";
import * as api from "@/utils/evaluation";

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
  await user.click(await screen.findByRole("button", { name: "Synthetic dataset (active)" }));
  await screen.findByRole("button", { name: /alert\(1\).*Refusal Behavior/ });
  return user;
}

describe("Evaluation dataset administration", () => {
  it("creates and edits datasets with typed status and no server fields", async () => {
    render(<EvaluationDatasets {...props} />);
    const user = userEvent.setup();
    await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument());
    await user.type(screen.getByLabelText("Dataset name"), " New dataset ");
    await user.click(screen.getByRole("button", { name: "Create dataset" }));
    await waitFor(() => expect(api.createEvaluationDataset).toHaveBeenCalledWith("workspace-1", { name: "New dataset", description: null }, "token"));
    await screen.findByRole("button", { name: "Save dataset" });
    await user.selectOptions(screen.getByLabelText("Dataset status"), "disabled");
    await user.click(screen.getByRole("button", { name: "Save dataset" }));
    await waitFor(() => expect(api.updateEvaluationDataset).toHaveBeenCalledWith("workspace-1", "dataset-1", expect.objectContaining({ status: "disabled" }), "token"));
  });

  it.each(["knowledge_qa", "tool_calling", "permission_boundary", "refusal_behavior"] as const)("creates %s using its typed form", async category => {
    render(<EvaluationDatasets {...props} />);
    const user = await openDataset();
    await user.click(screen.getByRole("button", { name: "New case" }));
    await user.selectOptions(screen.getByLabelText("Case category"), category);
    await user.type(screen.getByLabelText("Case name"), "Synthetic case");
    await user.type(screen.getByLabelText("Test input"), "Synthetic request");
    if (category === "knowledge_qa") {
      expect(screen.getByRole("option", { name: "Disabled KB (disabled)" })).toBeInTheDocument();
      await user.selectOptions(screen.getByLabelText("Knowledge base context"), "kb-1");
    }
    if (category === "tool_calling") {
      await user.selectOptions(screen.getByLabelText("Expected tool outcome"), "approval_required");
      expect(screen.queryByRole("option", { name: "Read tool (disabled)" })).not.toBeInTheDocument();
      await user.selectOptions(screen.getByLabelText("Tool context"), "tool-2");
    }
    await user.click(screen.getByRole("button", { name: "Create case" }));
    await waitFor(() => expect(api.createEvaluationCase).toHaveBeenCalledTimes(1));
    const payload = vi.mocked(api.createEvaluationCase).mock.calls[0][2];
    expect(payload).toMatchObject({ case_type: category, name: "Synthetic case", test_input: "Synthetic request" });
    expect(payload).not.toHaveProperty("status");
    expect(payload).not.toHaveProperty("created_by");
    if (category === "tool_calling") expect(payload.expected_behavior).toMatchObject({ approval_required: true, tool_key: "create_it_access_request" });
    if (category === "permission_boundary") expect(payload.expected_behavior).toMatchObject({ access_denied: true, expected_http_status: 404 });
    expect(screen.queryByRole("button", { name: /run|score/i })).not.toBeInTheDocument();
  });

  it("loads literal content and edits status without changing category", async () => {
    const { container } = render(<EvaluationDatasets {...props} />);
    const user = await openDataset();
    expect(container.querySelector("script")).toBeNull();
    await user.click(screen.getByRole("button", { name: /alert\(1\).*Refusal Behavior/ }));
    expect(await screen.findByLabelText("Test input")).toHaveValue("<b>Synthetic input</b>");
    expect(screen.queryByLabelText("Case category")).not.toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Case status"), "disabled");
    await user.click(screen.getByRole("button", { name: "Save case" }));
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
    await user.click(await screen.findByRole("button", { name: "Synthetic dataset (disabled)" }));
    await screen.findByRole("button", { name: /alert\(1\)/ });
    expect(screen.getByRole("button", { name: "New case" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: /alert\(1\)/ }));
    expect(await screen.findByRole("button", { name: "Save case" })).toBeEnabled();
  });

  it.each([403, 404, 409, 422, 500, 0])("shows recoverable %s errors without erasing input", async status => {
    render(<EvaluationDatasets {...props} />);
    const user = await openDataset();
    await user.click(screen.getByRole("button", { name: /alert\(1\)/ }));
    await screen.findByRole("button", { name: "Save case" });
    vi.mocked(api.updateEvaluationCase).mockRejectedValue(new ApiError("Safe error", status));
    await user.click(screen.getByRole("button", { name: "Save case" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Safe error");
    expect(screen.getByLabelText("Test input")).toHaveValue(item.test_input);
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
    await user.click(await screen.findByRole("button", { name: "More datasets" }));
    await waitFor(() => expect(api.listEvaluationDatasets).toHaveBeenCalledWith("workspace-1", 50, "token"));
    await user.click(screen.getAllByRole("button", { name: "Synthetic dataset (active)" })[0]);
    await user.click(await screen.findByRole("button", { name: "More cases" }));
    await waitFor(() => expect(api.listEvaluationCases).toHaveBeenCalledWith("workspace-1", "dataset-0", 50, "token"));
    cleanup();
    render(<EvaluationDatasets {...props} />);
    expect(await screen.findByText("No evaluation datasets yet.")).toBeInTheDocument();
  });

  it("blocks duplicate submissions while a write is pending", async () => {
    let finish!: (value: api.EvaluationDataset) => void;
    vi.mocked(api.createEvaluationDataset).mockImplementation(() => new Promise(resolve => { finish = resolve; }));
    render(<EvaluationDatasets {...props} />);
    const user = userEvent.setup();
    await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument());
    await user.type(screen.getByLabelText("Dataset name"), "Synthetic");
    await user.dblClick(screen.getByRole("button", { name: "Create dataset" }));
    expect(api.createEvaluationDataset).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Create dataset" })).toBeDisabled();
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
    await screen.findByText("No evaluation datasets yet.");
    await act(async () => finish(item));
    expect(screen.queryByLabelText("Test input")).not.toBeInTheDocument();
    rerender(<EvaluationDatasets {...props} accessToken="new-session" />);
    await screen.findByText("No evaluation datasets yet.");
    expect(screen.queryByLabelText("Test input")).not.toBeInTheDocument();
  });
});
