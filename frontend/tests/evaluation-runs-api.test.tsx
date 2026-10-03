import { afterEach, expect, it, vi } from "vitest";
import { activeRunCases, createEvaluationRun, getEvaluationRun, getRunCase, listEvaluationRuns, listRunCases } from "@/utils/evaluation-runs";

afterEach(() => vi.unstubAllGlobals());
it("uses exact five API routes, strict create payload, Bearer and bounded client signal", async () => {
  const fetch = vi.fn().mockImplementation(async () => new Response(JSON.stringify({ items: [] }), { status: 200 }));
  vi.stubGlobal("fetch", fetch);
  await createEvaluationRun("w", "d", "a", true, "token");
  await listEvaluationRuns("w", "d", 50, "token");
  await getEvaluationRun("w", "r", "token");
  await listRunCases("w", "r", "token");
  await getRunCase("w", "r", "c", "token");
  expect(fetch.mock.calls.map(call => new URL(call[0]).pathname + new URL(call[0]).search)).toEqual([
    "/api/workspaces/w/evaluation-datasets/d/runs", "/api/workspaces/w/evaluation-runs?dataset_id=d&limit=50&offset=50",
    "/api/workspaces/w/evaluation-runs/r", "/api/workspaces/w/evaluation-runs/r/cases?limit=100&offset=0", "/api/workspaces/w/evaluation-runs/r/cases/c",
  ]);
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ agent_id: "a", provider_egress_acknowledged: true });
  expect(fetch.mock.calls[0][1].signal).toBeInstanceOf(AbortSignal);
  expect(fetch.mock.calls[0][1].headers.get("Authorization")).toBe("Bearer token");
});
it("counts every active page rather than only the visible Dataset page", async () => {
  const fetch = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ items: Array.from({ length: 100 }, (_, i) => ({ id: `${i}` })) })))
    .mockResolvedValueOnce(new Response(JSON.stringify({ items: [{ id: "last" }] })));
  vi.stubGlobal("fetch", fetch);
  expect(await activeRunCases("w", "d", "token")).toHaveLength(101);
  expect(fetch.mock.calls[1][0]).toContain("status=active&limit=100&offset=100");
});
