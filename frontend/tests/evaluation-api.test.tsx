import { afterEach, expect, it, vi } from "vitest";
import * as api from "@/utils/evaluation";

afterEach(() => vi.unstubAllGlobals());

it("sends every Evaluation API contract with only supplied fields and Bearer auth", async () => {
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [] }), { status: 200 }));
  vi.stubGlobal("fetch", fetch);
  const payload: api.CaseCreate = { case_type: "refusal_behavior", name: "Synthetic", test_input: "Synthetic",
    expected_behavior: { routing_intent: "unsupported", response_category: "unsupported_request", safe_response_required: true } };
  const calls: [() => Promise<unknown>, string, string, unknown?][] = [
    [() => api.listEvaluationDatasets("w", 50, "token"), "/evaluation-datasets?limit=50&offset=50", "GET"],
    [() => api.getEvaluationDataset("w", "d", "token"), "/evaluation-datasets/d", "GET"],
    [() => api.createEvaluationDataset("w", { name: "Synthetic" }, "token"), "/evaluation-datasets", "POST", { name: "Synthetic" }],
    [() => api.updateEvaluationDataset("w", "d", { status: "disabled" }, "token"), "/evaluation-datasets/d", "PATCH", { status: "disabled" }],
    [() => api.listEvaluationCases("w", "d", 0, "token"), "/evaluation-datasets/d/cases?limit=50&offset=0", "GET"],
    [() => api.getEvaluationCase("w", "d", "c", "token"), "/evaluation-datasets/d/cases/c", "GET"],
    [() => api.createEvaluationCase("w", "d", payload, "token"), "/evaluation-datasets/d/cases", "POST", payload],
    [() => api.updateEvaluationCase("w", "d", "c", { description: null }, "token"), "/evaluation-datasets/d/cases/c", "PATCH", { description: null }],
  ];
  for (const [call, path, method, body] of calls) {
    fetch.mockResolvedValueOnce(new Response(JSON.stringify({ items: [] }), { status: 200 }));
    await call();
    const [url, init] = fetch.mock.calls.at(-1)!;
    expect(url).toContain(`/api/workspaces/w${path}`);
    expect(init.method ?? "GET").toBe(method);
    expect(new Headers(init.headers).get("Authorization")).toBe("Bearer token");
    if (body) expect(JSON.parse(init.body)).toEqual(body);
  }
});

it("loads same-Workspace resources including inactive Agents without invoking them", async () => {
  const fetch = vi.fn().mockImplementation(() => Promise.resolve(new Response("[]", { status: 200 })));
  vi.stubGlobal("fetch", fetch);
  expect(await api.evaluationResources("w", "token")).toEqual({ agents: [], knowledgeBases: [], tools: [] });
  expect(fetch.mock.calls.map(call => call[0])).toEqual([
    expect.stringContaining("/api/workspaces/w/agents?include_inactive=true"),
    expect.stringContaining("/api/workspaces/w/knowledge-bases"),
    expect.stringContaining("/api/workspaces/w/tools"),
  ]);
});
