import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { KnowledgeQA } from "@/app/components/knowledge-qa";
import { KnowledgeBase } from "@/utils/api";

const knowledgeBase: KnowledgeBase = {
  id: "kb-policies",
  workspace_id: "workspace-1",
  name: "Employee policies",
  description: "Approved people policies.",
  status: "active",
  created_by: "user-1",
  created_at: "2026-09-01T00:00:00Z",
  updated_at: "2026-09-01T00:00:00Z",
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("maps an answer endpoint 409 to the disabled Knowledge Base state", async () => {
  const fetchMock = vi.fn(async () =>
    new Response(JSON.stringify({ detail: "Knowledge base is disabled" }), {
      status: 409,
      headers: { "Content-Type": "application/json" },
    }),
  );
  vi.stubGlobal("fetch", fetchMock);
  const user = userEvent.setup();

  render(
    <KnowledgeQA
      workspaceId="workspace-1"
      workspaceName="Northstar Group"
      knowledgeBases={[knowledgeBase]}
      knowledgeBasesPending={false}
      knowledgeBasesError={null}
      accessToken="test-token"
      onUnauthorized={vi.fn()}
      onPendingChange={vi.fn()}
    />,
  );

  await user.type(screen.getByLabelText("Question"), "What is the travel limit?");
  await user.click(screen.getByRole("button", { name: /ask knowledge/i }));

  expect(
    await screen.findByText("Questions are disabled for this source"),
  ).toBeInTheDocument();
  expect(screen.getByText(/disabled or unavailable/i)).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledOnce();
});
