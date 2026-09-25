import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { KnowledgeQA } from "@/app/components/knowledge-qa";
import {
  ApiError,
  GroundedAnswerResponse,
  KnowledgeBase,
  answerKnowledgeQuestion,
} from "@/utils/api";

vi.mock("@/utils/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/utils/api")>();
  return { ...actual, answerKnowledgeQuestion: vi.fn() };
});

const mockedAnswer = vi.mocked(answerKnowledgeQuestion);

const knowledgeBases: KnowledgeBase[] = [
  {
    id: "kb-policies",
    workspace_id: "workspace-1",
    name: "Employee policies",
    description: "Approved people and travel policies.",
    status: "active",
    created_by: "user-1",
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
  },
  {
    id: "kb-operations",
    workspace_id: "workspace-1",
    name: "Operations handbook",
    description: "Internal operating procedures.",
    status: "active",
    created_by: "user-1",
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
  },
];

const answeredResponse: GroundedAnswerResponse = {
  question: "What is the travel reimbursement limit?",
  status: "answered",
  answer: "The daily travel reimbursement limit is $100.",
  message: null,
  citations: [
    {
      document_id: "document-1",
      file_name: "travel-policy.md",
      document_version: 2,
      chunk_id: "chunk-1",
      chunk_index: 3,
      excerpt: "Employees may claim up to $100 per day for approved travel.",
    },
    {
      document_id: "document-2",
      file_name: "expense-guide.pdf",
      document_version: 1,
      chunk_id: "chunk-2",
      chunk_index: 7,
      excerpt: "Receipts are required for individual expenses over $25.",
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

function renderKnowledgeQA(overrides: Partial<React.ComponentProps<typeof KnowledgeQA>> = {}) {
  const props: React.ComponentProps<typeof KnowledgeQA> = {
    workspaceId: "workspace-1",
    workspaceName: "Northstar Group",
    knowledgeBases,
    knowledgeBasesPending: false,
    knowledgeBasesError: null,
    accessToken: "test-token",
    onUnauthorized: vi.fn(),
    onPendingChange: vi.fn(),
    ...overrides,
  };
  return { ...render(<KnowledgeQA {...props} />), props };
}

async function askQuestion(question = answeredResponse.question) {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Question"), question);
  await user.click(screen.getByRole("button", { name: /ask knowledge/i }));
  return user;
}

describe("Knowledge Q&A", () => {
  beforeEach(() => mockedAnswer.mockReset());
  afterEach(cleanup);

  it("renders a successful grounded answer with citation metadata", async () => {
    mockedAnswer.mockResolvedValue(answeredResponse);
    renderKnowledgeQA();

    await askQuestion();

    expect(await screen.findByText(answeredResponse.answer!)).toBeInTheDocument();
    expect(screen.getAllByText("travel-policy.md")).toHaveLength(2);
    expect(screen.getByText("Chunk 4 · Version 2")).toBeInTheDocument();
    expect(screen.getByText(/2 sources/i)).toBeInTheDocument();
    expect(mockedAnswer).toHaveBeenCalledWith(
      "workspace-1",
      "kb-policies",
      answeredResponse.question,
      "test-token",
    );
  });

  it("renders an explicit unsupported result without citations", async () => {
    mockedAnswer.mockResolvedValue({
      ...answeredResponse,
      status: "unsupported",
      answer: null,
      message: "The retrieved knowledge does not contain enough evidence to answer this question.",
      citations: [],
    });
    renderKnowledgeQA();

    await askQuestion("What is not documented?");

    expect(await screen.findByText("This knowledge base cannot support an answer")).toBeInTheDocument();
    expect(screen.getByText(/does not contain enough evidence/i)).toBeInTheDocument();
    expect(screen.queryByText("travel-policy.md")).not.toBeInTheDocument();
  });

  it("shows loading and prevents duplicate submission while pending", async () => {
    let resolveAnswer!: (value: GroundedAnswerResponse) => void;
    mockedAnswer.mockReturnValue(new Promise((resolve) => { resolveAnswer = resolve; }));
    const { props } = renderKnowledgeQA();

    const user = await askQuestion();
    const pendingButton = screen.getByRole("button", { name: /finding answer/i });

    expect(pendingButton).toBeDisabled();
    expect(screen.getByLabelText("Question")).toBeDisabled();
    expect(screen.getByText("Building a grounded answer")).toBeInTheDocument();
    await user.click(pendingButton);
    expect(mockedAnswer).toHaveBeenCalledTimes(1);
    expect(props.onPendingChange).toHaveBeenCalledWith(true);

    resolveAnswer(answeredResponse);
    expect(await screen.findByText(answeredResponse.answer!)).toBeInTheDocument();
    expect(props.onPendingChange).toHaveBeenLastCalledWith(false);
  });

  it("renders a recoverable API or network error", () => {
    renderKnowledgeQA({
      knowledgeBasesError: { kind: "error", message: "Service temporarily unavailable." },
    });

    expect(screen.getByText("We could not load your knowledge bases")).toBeInTheDocument();
    expect(screen.getByText("Service temporarily unavailable.")).toBeInTheDocument();
  });

  it("uses the selected accessible knowledge base", async () => {
    mockedAnswer.mockResolvedValue(answeredResponse);
    renderKnowledgeQA();
    const user = userEvent.setup();

    await user.selectOptions(screen.getByLabelText("Knowledge base"), "kb-operations");
    await user.type(screen.getByLabelText("Question"), "How do operations work?");
    await user.click(screen.getByRole("button", { name: /ask knowledge/i }));

    expect(mockedAnswer).toHaveBeenCalledWith(
      "workspace-1",
      "kb-operations",
      "How do operations work?",
      "test-token",
    );
  });

  it("resets selection and answer state when the Workspace changes", async () => {
    mockedAnswer.mockResolvedValue(answeredResponse);
    const first = renderKnowledgeQA();
    const user = userEvent.setup();
    await user.selectOptions(screen.getByLabelText("Knowledge base"), "kb-operations");
    await askQuestion();
    expect(await screen.findByText(answeredResponse.answer!)).toBeInTheDocument();

    const nextKnowledgeBase = {
      ...knowledgeBases[0],
      id: "kb-finance",
      workspace_id: "workspace-2",
      name: "Finance guidance",
    };
    first.rerender(
      <KnowledgeQA
        {...first.props}
        key="workspace-2"
        workspaceId="workspace-2"
        workspaceName="Finance Operations"
        knowledgeBases={[nextKnowledgeBase]}
      />,
    );

    expect(screen.getByLabelText("Knowledge base")).toHaveValue("kb-finance");
    expect(screen.getByText("Your grounded answer will appear here")).toBeInTheDocument();
    expect(screen.queryByText(answeredResponse.answer!)).not.toBeInTheDocument();
  });

  it("updates the source inspector when a citation is selected", async () => {
    mockedAnswer.mockResolvedValue(answeredResponse);
    renderKnowledgeQA();
    const user = await askQuestion();

    const inspector = await screen.findByRole("region", { name: "travel-policy.md" });
    expect(within(inspector).getByText(answeredResponse.citations[0].excerpt)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /expense-guide\.pdf/i }));
    const updatedInspector = screen.getByRole("region", { name: "expense-guide.pdf" });
    expect(within(updatedInspector).getByText(answeredResponse.citations[1].excerpt)).toBeInTheDocument();
    expect(within(updatedInspector).getByText(/Chunk 8/)).toBeInTheDocument();
  });

  it("distinguishes forbidden and expired authorization", async () => {
    mockedAnswer.mockRejectedValueOnce(new ApiError("Not authorized for this workspace", 403));
    const first = renderKnowledgeQA();
    await askQuestion();
    expect(await screen.findByText("You cannot use this knowledge base")).toBeInTheDocument();
    expect(first.props.onUnauthorized).not.toHaveBeenCalled();
    first.unmount();

    mockedAnswer.mockRejectedValueOnce(new ApiError("Could not validate credentials", 401));
    const second = renderKnowledgeQA();
    await askQuestion();
    expect(second.props.onUnauthorized).toHaveBeenCalledOnce();
  });

  it("prevents questions against a disabled knowledge base", () => {
    renderKnowledgeQA({
      knowledgeBases: [{ ...knowledgeBases[0], status: "disabled" }],
    });

    expect(screen.getByText("Knowledge base disabled")).toBeInTheDocument();
    expect(screen.queryByLabelText("Question")).not.toBeInTheDocument();
    expect(mockedAnswer).not.toHaveBeenCalled();
  });

  it("validates an empty question before calling the API", async () => {
    renderKnowledgeQA();
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: /ask knowledge/i }));

    expect(screen.getByRole("alert")).toHaveTextContent("Enter a question");
    expect(mockedAnswer).not.toHaveBeenCalled();
  });
});
