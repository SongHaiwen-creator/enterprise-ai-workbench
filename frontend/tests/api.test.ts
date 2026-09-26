import assert from "node:assert/strict";
import test from "node:test";

import {
  ApiError,
  answerKnowledgeQuestion,
  listAgents,
  listKnowledgeBases,
  normalizeBaseUrl,
  requestJson,
  routeAgentRequest,
} from "../utils/api.ts";
import { formatEnumLabel, initials } from "../utils/presentation.ts";

test("normalizes the configured API base URL", () => {
  assert.equal(normalizeBaseUrl(" https://api.example.com/// "), "https://api.example.com");
});

test("sends JSON requests with a Bearer token", async () => {
  const originalFetch = globalThis.fetch;
  let capturedInit: RequestInit | undefined;

  globalThis.fetch = (async (_input: string | URL | Request, init?: RequestInit) => {
    capturedInit = init;
    return new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }) as typeof fetch;

  try {
    const result = await requestJson<{ ok: boolean }>(
      "/api/example",
      { method: "POST", body: JSON.stringify({ value: 1 }) },
      "test-token",
    );
    const headers = new Headers(capturedInit?.headers);
    assert.deepEqual(result, { ok: true });
    assert.equal(headers.get("Authorization"), "Bearer test-token");
    assert.equal(headers.get("Content-Type"), "application/json");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("surfaces FastAPI error details", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () => new Response(
    JSON.stringify({ detail: "Incorrect email or password" }),
    { status: 401, headers: { "Content-Type": "application/json" } },
  )) as typeof fetch;

  try {
    await assert.rejects(
      requestJson("/api/auth/login"),
      (error: unknown) =>
        error instanceof ApiError &&
        error.status === 401 &&
        error.message === "Incorrect email or password",
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("normalizes non-JSON and network failures", async (context) => {
  const originalFetch = globalThis.fetch;
  context.after(() => { globalThis.fetch = originalFetch; });

  globalThis.fetch = (async () => new Response("Unavailable", { status: 503 })) as typeof fetch;
  await assert.rejects(
    requestJson("/api/workspaces"),
    (error: unknown) => error instanceof ApiError && error.message === "Request failed (503)",
  );

  globalThis.fetch = (async () => { throw new Error("socket failure"); }) as typeof fetch;
  await assert.rejects(
    requestJson("/api/workspaces"),
    (error: unknown) => error instanceof ApiError && error.status === 0,
  );
});

test("uses workspace-scoped Knowledge Base and answer endpoints", async (context) => {
  const originalFetch = globalThis.fetch;
  const requests: Array<{ url: string; init?: RequestInit }> = [];
  context.after(() => { globalThis.fetch = originalFetch; });

  globalThis.fetch = (async (input: string | URL | Request, init?: RequestInit) => {
    requests.push({ url: String(input), init });
    return new Response(JSON.stringify([]), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }) as typeof fetch;

  await listKnowledgeBases("workspace-1", "test-token");
  await answerKnowledgeQuestion("workspace-1", "kb-1", "  What is policy?  ", "test-token");

  assert.equal(
    requests[0].url,
    "http://localhost:8000/api/workspaces/workspace-1/knowledge-bases",
  );
  assert.equal(
    requests[1].url,
    "http://localhost:8000/api/workspaces/workspace-1/knowledge-bases/kb-1/answer",
  );
  assert.equal(requests[1].init?.method, "POST");
  assert.deepEqual(JSON.parse(String(requests[1].init?.body)), {
    question: "  What is policy?  ",
  });
});

test("uses scoped Agent endpoints and omits absent knowledge context", async (context) => {
  const originalFetch = globalThis.fetch;
  const requests: Array<{ url: string; init?: RequestInit }> = [];
  context.after(() => { globalThis.fetch = originalFetch; });

  globalThis.fetch = (async (input: string | URL | Request, init?: RequestInit) => {
    requests.push({ url: String(input), init });
    const response = requests.length === 1
      ? [{ id: "agent-1", workspace_id: "workspace-1", name: "Assistant", status: "active" }]
      : requests.length === 2
        ? {
            request: "Check my claim",
            intent: "tool_request",
            outcome: {
              status: "not_executed",
              required_capability: "enterprise_tool",
              message: "This request requires an enterprise tool. No action was executed.",
            },
          }
        : {
            request: "What is the policy?",
            intent: "knowledge_qa",
            outcome: {
              question: "What is the policy?",
              status: "unsupported",
              answer: null,
              message: "Insufficient evidence.",
              citations: [],
              generation: {},
            },
          };
    return new Response(JSON.stringify(response), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }) as typeof fetch;

  const agents = await listAgents("workspace-1", "test-token");
  const tool = await routeAgentRequest(
    "workspace-1", "agent-1", "Check my claim", null, "test-token",
  );
  const knowledge = await routeAgentRequest(
    "workspace-1", "agent-1", "What is the policy?", "kb-1", "test-token",
  );

  assert.equal(agents[0].name, "Assistant");
  assert.equal(tool.intent, "tool_request");
  if (tool.intent === "tool_request") {
    assert.equal(tool.outcome.status, "not_executed");
  }
  assert.equal(knowledge.intent, "knowledge_qa");
  assert.equal(requests[0].url, "http://localhost:8000/api/workspaces/workspace-1/agents");
  assert.equal(requests[0].init?.method, undefined);
  assert.equal(
    requests[1].url,
    "http://localhost:8000/api/workspaces/workspace-1/agents/agent-1/route",
  );
  assert.equal(requests[1].init?.method, "POST");
  assert.deepEqual(JSON.parse(String(requests[1].init?.body)), {
    request: "Check my claim",
  });
  assert.deepEqual(JSON.parse(String(requests[2].init?.body)), {
    request: "What is the policy?",
    knowledge_base_id: "kb-1",
  });
  for (const { init } of requests) {
    assert.equal(new Headers(init?.headers).get("Authorization"), "Bearer test-token");
  }
});

test("formats API enum labels and initials for display", () => {
  assert.equal(formatEnumLabel("system_admin"), "System Admin");
  assert.equal(formatEnumLabel("invited"), "Invited");
  assert.equal(initials("Alice Zhang"), "AZ");
  assert.equal(initials(" "), "?");
});
