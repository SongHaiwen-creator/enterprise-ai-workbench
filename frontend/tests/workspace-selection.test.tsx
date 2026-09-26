import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Home from "@/app/page";
import {
  AgentSummary,
  AgentRouteResponse,
  ApiError,
  KnowledgeBase,
  Workspace,
  WorkspaceListItem,
  getCurrentUser,
  getWorkspace,
  listAgents,
  listKnowledgeBases,
  listWorkspaceMembers,
  listWorkspaces,
  login,
  routeAgentRequest,
} from "@/utils/api";

vi.mock("@/utils/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/utils/api")>();
  return {
    ...actual,
    login: vi.fn(),
    getCurrentUser: vi.fn(),
    listWorkspaces: vi.fn(),
    getWorkspace: vi.fn(),
    listWorkspaceMembers: vi.fn(),
    listAgents: vi.fn(),
    listKnowledgeBases: vi.fn(),
    routeAgentRequest: vi.fn(),
  };
});

const mockedLogin = vi.mocked(login);
const mockedGetCurrentUser = vi.mocked(getCurrentUser);
const mockedListWorkspaces = vi.mocked(listWorkspaces);
const mockedGetWorkspace = vi.mocked(getWorkspace);
const mockedListWorkspaceMembers = vi.mocked(listWorkspaceMembers);
const mockedListAgents = vi.mocked(listAgents);
const mockedListKnowledgeBases = vi.mocked(listKnowledgeBases);
const mockedRouteAgentRequest = vi.mocked(routeAgentRequest);

const workspaceItems: WorkspaceListItem[] = [
  {
    id: "workspace-a",
    name: "Workspace A",
    slug: "workspace-a",
    status: "active",
    role: "employee",
    joined_at: "2026-09-01T00:00:00Z",
  },
  {
    id: "workspace-b",
    name: "Workspace B",
    slug: "workspace-b",
    status: "active",
    role: "employee",
    joined_at: "2026-09-02T00:00:00Z",
  },
];

function workspace(item: WorkspaceListItem): Workspace {
  return {
    id: item.id,
    name: item.name,
    slug: item.slug,
    status: item.status,
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
  };
}

function knowledgeBase(
  workspaceId: string,
  id: string,
  name: string,
): KnowledgeBase {
  return {
    id,
    workspace_id: workspaceId,
    name,
    description: `${name} description`,
    status: "active",
    created_by: "user-1",
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
  };
}

function agent(workspaceId: string, id: string, name: string): AgentSummary {
  return {
    id,
    workspace_id: workspaceId,
    name,
    description: null,
    status: "active",
    created_by: "user-1",
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

async function signIn() {
  const user = userEvent.setup();
  render(<Home />);
  await user.type(screen.getByLabelText("Work email"), "alex@example.com");
  await user.type(screen.getByLabelText("Password"), "correct-password");
  await user.click(screen.getByRole("button", { name: "Sign in" }));
  return user;
}

describe("Workspace selection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedLogin.mockResolvedValue({
      access_token: "test-token",
      token_type: "bearer",
      expires_in: 1800,
    });
    mockedGetCurrentUser.mockResolvedValue({
      id: "user-1",
      email: "alex@example.com",
      name: "Alex Morgan",
      status: "active",
    });
    mockedListWorkspaces.mockResolvedValue(workspaceItems);
    mockedListWorkspaceMembers.mockResolvedValue([]);
    mockedListAgents.mockResolvedValue([]);
  });

  afterEach(cleanup);

  it("ignores stale Workspace responses that finish after the latest selection", async () => {
    const workspaceA = deferred<Workspace>();
    const workspaceB = deferred<Workspace>();
    const knowledgeBasesA = deferred<KnowledgeBase[]>();
    const knowledgeBasesB = deferred<KnowledgeBase[]>();
    const agentsA = deferred<AgentSummary[]>();
    const agentsB = deferred<AgentSummary[]>();

    mockedGetWorkspace.mockImplementation((workspaceId) =>
      workspaceId === "workspace-a" ? workspaceA.promise : workspaceB.promise,
    );
    mockedListKnowledgeBases.mockImplementation((workspaceId) =>
      workspaceId === "workspace-a" ? knowledgeBasesA.promise : knowledgeBasesB.promise,
    );
    mockedListAgents.mockImplementation((workspaceId) =>
      workspaceId === "workspace-a" ? agentsA.promise : agentsB.promise,
    );

    const user = await signIn();
    const workspaceBButton = await screen.findByRole("button", { name: /Workspace B/i });
    await user.click(workspaceBButton);

    await act(async () => {
      workspaceB.resolve(workspace(workspaceItems[1]));
      knowledgeBasesB.resolve([
        knowledgeBase("workspace-b", "kb-b", "Beta policies"),
      ]);
      agentsB.resolve([agent("workspace-b", "agent-b", "Beta Assistant")]);
    });

    expect(await screen.findByText("Workspace B", { selector: ".topbar-context" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Beta policies" })).toBeInTheDocument();

    await act(async () => {
      workspaceA.resolve(workspace(workspaceItems[0]));
      knowledgeBasesA.resolve([
        knowledgeBase("workspace-a", "kb-a", "Alpha policies"),
      ]);
      agentsA.resolve([agent("workspace-a", "agent-a", "Alpha Assistant")]);
    });

    await waitFor(() => {
      expect(screen.getByText("Workspace B", { selector: ".topbar-context" })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: "Beta policies" })).toBeInTheDocument();
      expect(screen.queryByRole("option", { name: "Alpha policies" })).not.toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /Assistant.*Route a request/i }));
    expect(screen.getByRole("option", { name: "Beta Assistant" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "Alpha Assistant" })).not.toBeInTheDocument();
  });

  it("keeps Knowledge Q&A and Workspace available when Agent listing fails", async () => {
    mockedListWorkspaces.mockResolvedValue([workspaceItems[0]]);
    mockedGetWorkspace.mockResolvedValue(workspace(workspaceItems[0]));
    mockedListKnowledgeBases.mockResolvedValue([
      knowledgeBase("workspace-a", "kb-a", "Alpha policies"),
    ]);
    mockedListAgents.mockRejectedValue(new ApiError("Agent service unavailable", 503));

    const user = await signIn();
    expect(await screen.findByRole("option", { name: "Alpha policies" }))
      .toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Assistant.*Route a request/i }));
    expect(await screen.findByText("We could not load active agents")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Workspace.*Access & members/i }));
    expect(screen.getByRole("region", { name: "Workspace overview" })).toBeInTheDocument();
  });

  it("clears Assistant state and context on Workspace switching", async () => {
    mockedGetWorkspace.mockImplementation(async (workspaceId) =>
      workspace(workspaceItems.find((item) => item.id === workspaceId)!),
    );
    mockedListKnowledgeBases.mockImplementation(async (workspaceId) =>
      workspaceId === "workspace-a"
        ? [knowledgeBase("workspace-a", "kb-a", "Alpha policies")]
        : [knowledgeBase("workspace-b", "kb-b", "Beta policies")],
    );
    mockedListAgents.mockImplementation(async (workspaceId) =>
      workspaceId === "workspace-a"
        ? [agent("workspace-a", "agent-a", "Alpha Assistant")]
        : [agent("workspace-b", "agent-b", "Beta Assistant")],
    );
    const outcome: AgentRouteResponse = {
      request: "Check my claim",
      intent: "tool_request",
      outcome: {
        status: "not_executed",
        required_capability: "enterprise_tool",
        message: "This request requires an enterprise tool. No action was executed.",
      },
    };
    mockedRouteAgentRequest.mockResolvedValue(outcome);

    const user = await signIn();
    await user.click(await screen.findByRole("button", { name: /Assistant.*Route a request/i }));
    await user.type(screen.getByLabelText("Request"), outcome.request);
    await user.click(screen.getByRole("button", { name: "Route request" }));
    expect(await screen.findByText("No action was executed")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Workspace B/i }));
    expect(await screen.findByRole("option", { name: "Beta Assistant" })).toBeInTheDocument();
    expect(screen.getByLabelText("Knowledge context (optional)")).toHaveValue("kb-b");
    expect(screen.getByLabelText("Request")).toHaveValue("");
    expect(screen.getByText("Your Assistant result will appear here")).toBeInTheDocument();
  });

  it("clears the session when Agent listing returns 401", async () => {
    mockedListWorkspaces.mockResolvedValue([workspaceItems[0]]);
    mockedGetWorkspace.mockResolvedValue(workspace(workspaceItems[0]));
    mockedListKnowledgeBases.mockResolvedValue([]);
    mockedListAgents.mockRejectedValue(new ApiError("Could not validate credentials", 401));

    await signIn();
    expect(await screen.findByText("Your session expired. Sign in again to continue."))
      .toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
  });

  it("renders an explicit access-denied state when Knowledge Base listing returns 403", async () => {
    mockedListWorkspaces.mockResolvedValue([workspaceItems[0]]);
    mockedGetWorkspace.mockResolvedValue(workspace(workspaceItems[0]));
    mockedListKnowledgeBases.mockRejectedValue(
      new ApiError("Not authorized for this workspace", 403),
    );

    await signIn();

    expect(
      await screen.findByText("You cannot access Knowledge Q&A in this workspace"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("You do not have access to knowledge bases in this workspace."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign out" })).toBeInTheDocument();
  });

  it("clears the session when Knowledge Base listing returns 401", async () => {
    mockedListWorkspaces.mockResolvedValue([workspaceItems[0]]);
    mockedGetWorkspace.mockResolvedValue(workspace(workspaceItems[0]));
    mockedListKnowledgeBases.mockRejectedValue(
      new ApiError("Could not validate credentials", 401),
    );

    await signIn();

    expect(
      await screen.findByText("Your session expired. Sign in again to continue."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sign out" })).not.toBeInTheDocument();
  });
});
