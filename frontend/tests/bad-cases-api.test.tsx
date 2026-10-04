import { afterEach, describe, expect, it, vi } from "vitest";
import { createBadCase, getBadCase, getBadCaseHistory, listBadCases, updateBadCase } from "@/utils/bad-cases";
import { RunCaseDetail } from "@/utils/evaluation-runs";

afterEach(() => vi.unstubAllGlobals());
describe("Bad Case API", () => {
  it("uses scoped paths, encoded fixed filters, pagination and bearer headers", async () => {
    const fetch = vi.fn().mockImplementation(async () => new Response(JSON.stringify({ items: [], limit: 50, offset: 0 }), { status: 200 }));
    vi.stubGlobal("fetch", fetch);
    await listBadCases("workspace", { status: "open", source_run_case_id: "source", category: "routing" }, 50, "token");
    expect(fetch.mock.calls[0][0]).toContain("/api/workspaces/workspace/bad-cases?limit=50&offset=50&status=open&source_run_case_id=source&category=routing");
    expect(fetch.mock.calls[0][1].headers.get("Authorization")).toBe("Bearer token");
    await getBadCase("workspace", "issue", "token");
    await getBadCaseHistory("workspace", "issue", 100, "token");
    expect(fetch.mock.calls[2][0]).toContain("/bad-cases/issue/history?limit=50&offset=100");
  });
  it("sends source only in path and includes expected revision on patch", async () => {
    const fetch = vi.fn().mockImplementation(async () => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetch);
    const source = { id: "source", run_id: "run" } as RunCaseDetail;
    const body = { title: "Synthetic", description: "Redacted", category: "unclassified" as const, possible_cause: null };
    await createBadCase("workspace", source, body, "token");
    expect(fetch.mock.calls[0][0]).toContain("/evaluation-runs/run/cases/source/bad-case");
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual(body);
    await updateBadCase("workspace", "issue", { expected_revision: 2, status: "resolved", resolution_note: "Human", change_reason: "Review" }, "token");
    expect(fetch.mock.calls[1][1].method).toBe("PATCH");
    expect(JSON.parse(fetch.mock.calls[1][1].body).expected_revision).toBe(2);
  });
});
