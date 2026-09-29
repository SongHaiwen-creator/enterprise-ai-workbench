import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Assistant } from "@/app/components/assistant";
import {
  AgentRouteResponse,
  AgentSummary,
  ApiError,
  GroundedAnswerResponse,
  KnowledgeBase,
  routeAgentRequest,
} from "@/utils/api";

vi.mock("@/utils/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/utils/api")>();
  return { ...actual, routeAgentRequest: vi.fn() };
});

const mockedRoute = vi.mocked(routeAgentRequest);

const agents: AgentSummary[] = [
  {
    id: "agent-1",
    workspace_id: "workspace-1",
    name: "Employee Assistant",
    description: "Routes internal employee requests.",
    status: "active",
    created_by: "user-1",
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
  },
  {
    id: "agent-2",
    workspace_id: "workspace-1",
    name: "IT Assistant",
    description: null,
    status: "active",
    created_by: "user-1",
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
  },
  {
    id: "agent-draft",
    workspace_id: "workspace-1",
    name: "Draft Agent",
    description: null,
    status: "draft",
    created_by: "user-1",
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
  },
];

const knowledgeBases: KnowledgeBase[] = [
  {
    id: "kb-1",
    workspace_id: "workspace-1",
    name: "Employee policies",
    description: "Current policy sources.",
    status: "active",
    created_by: "user-1",
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
  },
  {
    id: "kb-2",
    workspace_id: "workspace-1",
    name: "Operations guide",
    description: null,
    status: "active",
    created_by: "user-1",
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
  },
  {
    id: "kb-disabled",
    workspace_id: "workspace-1",
    name: "Archived guide",
    description: null,
    status: "disabled",
    created_by: "user-1",
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
  },
];

const answer: GroundedAnswerResponse = {
  question: "What is the travel policy?",
  status: "answered",
  answer: "Travel requires manager approval.",
  message: null,
  citations: [
    {
      document_id: "document-1",
      file_name: "travel-policy.md",
      document_version: 2,
      chunk_id: "chunk-1",
      chunk_index: 3,
      excerpt: "Obtain manager approval before booking travel.",
    },
    {
      document_id: "document-2",
      file_name: "expense-guide.pdf",
      document_version: 1,
      chunk_id: "chunk-2",
      chunk_index: 7,
      excerpt: "Travel requests must include an approved purpose.",
    },
  ],
  generation: {
    model: "test-model",
    reasoning_effort: "low",
    retrieval_limit: 5,
    prompt_version: "grounded-answer-v1",
    max_input_tokens: 12000,
    max_output_tokens: 1200,
    input_tokens: 100,
    output_tokens: 20,
    total_tokens: 120,
  },
};

const knowledgeResponse: AgentRouteResponse = {
  request: answer.question,
  intent: "knowledge_qa",
  outcome: answer,
};

const toolResponse: AgentRouteResponse = {
  request: "What is the status of my claim?",
  intent: "tool_request",
  outcome: {
    status: "not_executed",
    tool: null,
    executed: false,
    approval_required: false,
    reason: "no_available_tool",
    validated_arguments: null,
    result: null,
    message: "No permitted enterprise capability can safely handle this request.",
  },
};

function renderAssistant(overrides: Partial<React.ComponentProps<typeof Assistant>> = {}) {
  const props: React.ComponentProps<typeof Assistant> = {
    workspaceId: "workspace-1",
    workspaceName: "Northstar Group",
    agents,
    agentsPending: false,
    agentsError: null,
    knowledgeBases,
    knowledgeBasesError: null,
    accessToken: "test-token",
    onUnauthorized: vi.fn(),
    onPendingChange: vi.fn(),
    onRetryAgents: vi.fn(),
    ...overrides,
  };
  return { ...render(<Assistant {...props} />), props };
}

async function submitRequest(request: string) {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Request"), request);
  await user.click(screen.getByRole("button", { name: "Route request" }));
  return user;
}

describe("Assistant", () => {
  beforeEach(() => mockedRoute.mockReset());
  afterEach(cleanup);

  it("defaults to active scoped resources and renders knowledge citations", async () => {
    mockedRoute.mockResolvedValue(knowledgeResponse);
    renderAssistant();

    expect(screen.getByRole("option", { name: "Employee Assistant" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "Draft Agent" })).not.toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "Archived guide" })).not.toBeInTheDocument();
    expect(screen.getByLabelText("Knowledge context (optional)")).toHaveValue("kb-1");

    const user = await submitRequest(answer.question);
    expect(await screen.findByText(answer.answer!)).toBeInTheDocument();
    expect(mockedRoute).toHaveBeenCalledWith(
      "workspace-1", "agent-1", answer.question, "kb-1", "test-token",
    );
    expect(screen.getByText("Chunk 4 · Version 2")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "travel-policy.md" }))
      .getByText(answer.citations[0].excerpt)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /expense-guide\.pdf/i }));
    expect(within(screen.getByRole("region", { name: "expense-guide.pdf" }))
      .getByText(answer.citations[1].excerpt)).toBeInTheDocument();
  });

  it("routes tool requests without a knowledge base and shows no fabricated result", async () => {
    mockedRoute.mockResolvedValue(toolResponse);
    renderAssistant({ knowledgeBases: [] });

    expect(screen.getByText(/No active knowledge base is available/i)).toBeInTheDocument();
    await submitRequest(toolResponse.request);

    expect(await screen.findByText("No action was executed")).toBeInTheDocument();
    expect(screen.getByText(toolResponse.outcome.message)).toBeInTheDocument();
    expect(mockedRoute).toHaveBeenCalledWith(
      "workspace-1", "agent-1", toolResponse.request, null, "test-token",
    );
    expect(screen.queryByRole("button", { name: /travel-policy\.md/i })).not.toBeInTheDocument();
  });

  it("renders a typed reimbursement result without arbitrary JSON", async () => {
    mockedRoute.mockResolvedValue({
      request: "Check my reimbursement",
      intent: "tool_request",
      outcome: {
        status: "executed",
        tool: { tool_key: "get_reimbursement_status", name: "Reimbursement status" },
        executed: true,
        approval_required: false,
        validated_arguments: {},
        result: {
          type: "reimbursement_status",
          reimbursement_reference: "REIM-2F40A831",
          status: "under_review",
          amount_minor: 12800,
          currency: "CNY",
          submitted_on: "2026-09-15",
          last_updated_on: "2026-09-18",
        },
        message: "The read-only enterprise capability completed successfully.",
      },
    });
    renderAssistant({ knowledgeBases: [] });
    await submitRequest("Check my reimbursement");

    expect(await screen.findByText("Capability completed successfully")).toBeInTheDocument();
    expect(screen.getByText("REIM-2F40A831")).toBeInTheDocument();
    expect(screen.getByText("128.00 CNY")).toBeInTheDocument();
    expect(screen.getByText("under review")).toBeInTheDocument();
    expect(screen.queryByText(/tool_key/i)).not.toBeInTheDocument();
  });

  it("renders only the typed signed-in employee profile fields", async () => {
    mockedRoute.mockResolvedValue({
      request: "Show my profile",
      intent: "tool_request",
      outcome: {
        status: "executed",
        tool: { tool_key: "get_employee_information", name: "Employee information" },
        executed: true,
        approval_required: false,
        validated_arguments: { subject: "self" },
        result: {
          type: "employee_information",
          name: "Agent User",
          email: "agent.user@example.com",
          department: "Technology",
          job_title: "Software Engineer",
          employment_status: "active",
        },
        message: "The read-only enterprise capability completed successfully.",
      },
    });
    renderAssistant();
    await submitRequest("Show my profile");

    expect(await screen.findByText("agent.user@example.com")).toBeInTheDocument();
    expect(screen.getByText("Technology")).toBeInTheDocument();
    expect(screen.getByText("Software Engineer")).toBeInTheDocument();
  });

  it("shows validated IT fields and the Approval reference without decision controls", async () => {
    mockedRoute.mockResolvedValue({
      request: "Request production access",
      intent: "tool_request",
      outcome: {
        status: "approval_required",
        tool: { tool_key: "create_it_access_request", name: "Create IT access request" },
        executed: false,
        approval_required: true,
        validated_arguments: {
          system: "production_database",
          access_level: "read_only",
          business_justification: "Investigate approved production incidents.",
          duration_days: 14,
        },
        approval: {
          id: "approval-123",
          decision_status: "pending",
          execution_status: "not_started",
          created_at: "2026-09-28T10:00:00Z",
          expires_at: "2026-10-01T10:00:00Z",
        },
        result: null,
        message: "An approval request was submitted for human review. Nothing was executed.",
      },
    });
    renderAssistant();
    await submitRequest("Request production access");

    expect(await screen.findByText("Approval required — not executed")).toBeInTheDocument();
    expect(screen.getByText("production database")).toBeInTheDocument();
    expect(screen.getByText("14 days")).toBeInTheDocument();
    expect(screen.getByText("Investigate approved production incidents.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /approve|reject|cancel/i }))
      .not.toBeInTheDocument();
    expect(screen.getByText(
      "Approval ID approval-123 · Decision pending · Execution not started",
    )).toBeInTheDocument();
    expect(screen.getByText(
      "An approval request was submitted for human review. Nothing was executed.",
    )).toBeInTheDocument();
  });

  it("routes unsupported requests even when knowledge bases cannot be loaded", async () => {
    mockedRoute.mockResolvedValue({
      request: "Write a wedding speech",
      intent: "unsupported",
      outcome: {
        status: "unsupported",
        message: "This request is outside the configured Agent capabilities.",
      },
    });
    renderAssistant({
      knowledgeBases: [],
      knowledgeBasesError: { kind: "error", message: "Knowledge service unavailable" },
    });

    await submitRequest("Write a wedding speech");
    expect(await screen.findByText("This Agent cannot handle that request")).toBeInTheDocument();
    expect(screen.getByText("This request is outside the configured Agent capabilities."))
      .toBeInTheDocument();
    expect(mockedRoute).toHaveBeenCalledWith(
      "workspace-1", "agent-1", "Write a wedding speech", null, "test-token",
    );
  });

  it("keeps a knowledge question after the fixed 422 so context can be selected", async () => {
    mockedRoute
      .mockRejectedValueOnce(new ApiError(
        "Knowledge base context is required for knowledge questions.", 422,
      ))
      .mockResolvedValueOnce(knowledgeResponse);
    renderAssistant();
    const user = userEvent.setup();

    await user.selectOptions(screen.getByLabelText("Knowledge context (optional)"), "");
    await submitRequest(answer.question);
    expect(await screen.findByText("Select a knowledge base for this question"))
      .toBeInTheDocument();
    expect(screen.getByLabelText("Request")).toHaveValue(answer.question);
    expect(mockedRoute).toHaveBeenNthCalledWith(
      1, "workspace-1", "agent-1", answer.question, null, "test-token",
    );

    await user.selectOptions(screen.getByLabelText("Knowledge context (optional)"), "kb-2");
    await user.click(screen.getByRole("button", { name: "Route request" }));
    expect(await screen.findByText(answer.answer!)).toBeInTheDocument();
    expect(mockedRoute).toHaveBeenNthCalledWith(
      2, "workspace-1", "agent-1", answer.question, "kb-2", "test-token",
    );
  });

  it("distinguishes insufficient knowledge evidence from out-of-scope routing", async () => {
    mockedRoute.mockResolvedValue({
      ...knowledgeResponse,
      outcome: {
        ...answer,
        status: "unsupported",
        answer: null,
        message: "The retrieved knowledge does not contain enough evidence.",
        citations: [],
      },
    });
    renderAssistant();
    await submitRequest(answer.question);

    expect(await screen.findByText("The selected knowledge base cannot support an answer"))
      .toBeInTheDocument();
    expect(screen.getByText(/does not contain enough evidence/i)).toBeInTheDocument();
    expect(screen.queryByText("This Agent cannot handle that request")).not.toBeInTheDocument();
  });

  it("blocks duplicate submissions and selection changes while routing", async () => {
    let resolveRoute!: (response: AgentRouteResponse) => void;
    mockedRoute.mockReturnValue(new Promise((resolve) => { resolveRoute = resolve; }));
    const { props } = renderAssistant();
    const user = await submitRequest("Check my claim");

    expect(screen.getByRole("button", { name: "Routing request…" })).toBeDisabled();
    expect(screen.getByLabelText("Request")).toBeDisabled();
    expect(screen.getByLabelText("Agent")).toBeDisabled();
    expect(screen.getByLabelText("Knowledge context (optional)")).toBeDisabled();
    expect(props.onPendingChange).toHaveBeenCalledWith(true);
    await user.click(screen.getByRole("button", { name: "Routing request…" }));
    expect(mockedRoute).toHaveBeenCalledTimes(1);

    resolveRoute(toolResponse);
    expect(await screen.findByText("No action was executed")).toBeInTheDocument();
    await waitFor(() => expect(props.onPendingChange).toHaveBeenLastCalledWith(false));
  });

  it("shows an empty Agent state, list failure, and retry control", async () => {
    const first = renderAssistant({ agents: [] });
    expect(screen.getByText("No active agents are available")).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Refresh agents" }));
    expect(first.props.onRetryAgents).toHaveBeenCalledOnce();
    first.unmount();

    const second = renderAssistant({
      agents: [],
      agentsError: { kind: "forbidden", message: "No access" },
    });
    expect(screen.getByText("Assistant access denied")).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Try again" }));
    expect(second.props.onRetryAgents).toHaveBeenCalledOnce();
  });

  it.each([
    [403, "Assistant access denied"],
    [404, "Agent or knowledge context not found"],
    [409, "Agent or knowledge context unavailable"],
    [422, "Request needs revision"],
    [502, "Assistant service unavailable"],
    [503, "Assistant service unavailable"],
    [0, "Connection unavailable"],
  ])("renders a recoverable %i routing error", async (status, title) => {
    mockedRoute.mockRejectedValueOnce(new ApiError("Safe server detail", status));
    renderAssistant();
    await submitRequest("Check my claim");

    expect(await screen.findByText(title)).toBeInTheDocument();
    expect(screen.getByText("Safe server detail")).toBeInTheDocument();
    expect(screen.getByLabelText("Request")).toHaveValue("Check my claim");
  });

  it("clears the session on 401 and validates request text before routing", async () => {
    mockedRoute.mockRejectedValueOnce(new ApiError("Expired", 401));
    const { props } = renderAssistant();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Route request" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Enter a request");
    expect(mockedRoute).not.toHaveBeenCalled();

    await user.type(screen.getByLabelText("Request"), "Check my claim");
    await user.click(screen.getByRole("button", { name: "Route request" }));
    await waitFor(() => expect(props.onUnauthorized).toHaveBeenCalledOnce());
  });
});
