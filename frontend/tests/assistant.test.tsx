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
  await user.type(screen.getByLabelText("请求内容"), request);
  await user.click(screen.getByRole("button", { name: "发送请求" }));
  return user;
}

describe("智能助手", () => {
  beforeEach(() => mockedRoute.mockReset());
  afterEach(cleanup);

  it("defaults to active scoped resources and renders knowledge citations", async () => {
    mockedRoute.mockResolvedValue(knowledgeResponse);
    renderAssistant();

    expect(screen.getByRole("option", { name: "Employee Assistant" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "Draft Agent" })).not.toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "Archived guide" })).not.toBeInTheDocument();
    expect(screen.getByLabelText("知识库（可选）")).toHaveValue("kb-1");

    const user = await submitRequest(answer.question);
    expect(await screen.findByText(answer.answer!)).toBeInTheDocument();
    expect(mockedRoute).toHaveBeenCalledWith(
      "workspace-1", "agent-1", answer.question, "kb-1", "test-token",
    );
    expect(screen.getByText("片段 4 · 版本 2")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "travel-policy.md" }))
      .getByText(answer.citations[0].excerpt)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /expense-guide\.pdf/i }));
    expect(within(screen.getByRole("region", { name: "expense-guide.pdf" }))
      .getByText(answer.citations[1].excerpt)).toBeInTheDocument();
  });

  it("routes tool requests without a knowledge base and shows no fabricated result", async () => {
    mockedRoute.mockResolvedValue(toolResponse);
    renderAssistant({ knowledgeBases: [] });

    expect(screen.getByText(/暂无已启用的知识库/)).toBeInTheDocument();
    await submitRequest(toolResponse.request);

    expect(await screen.findByText("未执行任何操作")).toBeInTheDocument();
    expect(screen.getByText("没有已授权的企业工具能够安全处理此请求。")).toBeInTheDocument();
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

    expect(await screen.findByText("业务查询已完成")).toBeInTheDocument();
    expect(screen.getByText("REIM-2F40A831")).toBeInTheDocument();
    expect(screen.getByText("128.00 CNY")).toBeInTheDocument();
    expect(screen.getByText("审核中")).toBeInTheDocument();
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

    expect(await screen.findByText("等待人工审批 · 尚未执行")).toBeInTheDocument();
    expect(screen.getByText("生产数据库")).toBeInTheDocument();
    expect(screen.getByText("14 天")).toBeInTheDocument();
    expect(screen.getByText("Investigate approved production incidents.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /批准|拒绝|取消/ }))
      .not.toBeInTheDocument();
    expect(screen.getByText(
      "审批编号 approval-123 · 审批决定 待处理 · 执行状态 未执行",
    )).toBeInTheDocument();
    expect(screen.getByText(
      "申请已提交，等待人工审核。尚未执行任何操作。",
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
    expect(await screen.findByText("当前智能体无法处理此请求")).toBeInTheDocument();
    expect(screen.getByText("此请求超出了当前智能体配置的能力范围。"))
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

    await user.selectOptions(screen.getByLabelText("知识库（可选）"), "");
    await submitRequest(answer.question);
    expect(await screen.findByText("请为此问题选择知识库"))
      .toBeInTheDocument();
    expect(screen.getByLabelText("请求内容")).toHaveValue(answer.question);
    expect(mockedRoute).toHaveBeenNthCalledWith(
      1, "workspace-1", "agent-1", answer.question, null, "test-token",
    );

    await user.selectOptions(screen.getByLabelText("知识库（可选）"), "kb-2");
    await user.click(screen.getByRole("button", { name: "发送请求" }));
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

    expect(await screen.findByText("当前知识库没有足够资料支持回答"))
      .toBeInTheDocument();
    expect(screen.getByText(/does not contain enough evidence/i)).toBeInTheDocument();
    expect(screen.queryByText("当前智能体无法处理此请求")).not.toBeInTheDocument();
  });

  it("blocks duplicate submissions and selection changes while routing", async () => {
    let resolveRoute!: (response: AgentRouteResponse) => void;
    mockedRoute.mockReturnValue(new Promise((resolve) => { resolveRoute = resolve; }));
    const { props } = renderAssistant();
    const user = await submitRequest("Check my claim");

    expect(screen.getByRole("button", { name: "正在处理…" })).toBeDisabled();
    expect(screen.getByLabelText("请求内容")).toBeDisabled();
    expect(screen.getByLabelText("智能体")).toBeDisabled();
    expect(screen.getByLabelText("知识库（可选）")).toBeDisabled();
    expect(props.onPendingChange).toHaveBeenCalledWith(true);
    await user.click(screen.getByRole("button", { name: "正在处理…" }));
    expect(mockedRoute).toHaveBeenCalledTimes(1);

    resolveRoute(toolResponse);
    expect(await screen.findByText("未执行任何操作")).toBeInTheDocument();
    await waitFor(() => expect(props.onPendingChange).toHaveBeenLastCalledWith(false));
  });

  it("shows an empty Agent state, list failure, and retry control", async () => {
    const first = renderAssistant({ agents: [] });
    expect(screen.getByText("暂无已启用的智能体")).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "刷新智能体" }));
    expect(first.props.onRetryAgents).toHaveBeenCalledOnce();
    first.unmount();

    const second = renderAssistant({
      agents: [],
      agentsError: { kind: "forbidden", message: "No access" },
    });
    expect(screen.getByText("没有智能助手访问权限")).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "重试" }));
    expect(second.props.onRetryAgents).toHaveBeenCalledOnce();
  });

  it.each([
    [403, "没有智能助手访问权限"],
    [404, "智能体或知识库不存在"],
    [409, "智能体或知识库暂不可用"],
    [422, "请检查请求内容"],
    [502, "智能助手服务暂不可用"],
    [503, "智能助手服务暂不可用"],
    [0, "无法连接服务"],
  ])("renders a recoverable %i routing error", async (status, title) => {
    mockedRoute.mockRejectedValueOnce(new ApiError("服务端安全提示", status));
    renderAssistant();
    await submitRequest("Check my claim");

    expect(await screen.findByText(title)).toBeInTheDocument();
    expect(screen.getByText("服务端安全提示")).toBeInTheDocument();
    expect(screen.getByLabelText("请求内容")).toHaveValue("Check my claim");
  });

  it("clears the session on 401 and validates request text before routing", async () => {
    mockedRoute.mockRejectedValueOnce(new ApiError("已过期", 401));
    const { props } = renderAssistant();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "发送请求" }));
    expect(screen.getByRole("alert")).toHaveTextContent("请先输入请求");
    expect(mockedRoute).not.toHaveBeenCalled();

    await user.type(screen.getByLabelText("请求内容"), "Check my claim");
    await user.click(screen.getByRole("button", { name: "发送请求" }));
    await waitFor(() => expect(props.onUnauthorized).toHaveBeenCalledOnce());
  });
});
