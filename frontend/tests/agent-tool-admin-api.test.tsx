import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, listAgents } from "@/utils/api";
import {
  assignTool, createAgent, createTool, getAgent, getTool, listAgentTools, listManagedAgents,
  listTools, unassignTool, updateAgent, updateTool, usableConfiguration,
} from "@/utils/agent-tool-admin";
import { toolFixture } from "./agent-tool-fixtures";

afterEach(() => vi.unstubAllGlobals());
describe("Agent and Tool administration API", () => {
  it("uses all eleven scoped contracts without changing the employee Agent list", async () => {
    const fetch = vi.fn().mockImplementation(async (_url, init) => init?.method === "DELETE"
      ? new Response(null, { status: 204 }) : new Response(JSON.stringify({ id: "result" }), { status: init?.method === "POST" ? 201 : 200 }));
    vi.stubGlobal("fetch", fetch);
    await listManagedAgents("w", "token"); await getAgent("w", "a", "token");
    await createAgent("w", { name: "Agent", system_prompt: "Scope", description: null }, "token");
    await updateAgent("w", "a", { description: null }, "token");
    await listTools("w", "token"); await getTool("w", "t", "token");
    await createTool("w", { tool_key: "get_reimbursement_status", name: "Tool", description: "Description" }, "token");
    await updateTool("w", "t", { status: "active" }, "token");
    await listAgentTools("w", "a", "token"); await assignTool("w", "a", "t", "token");
    await expect(unassignTool("w", "a", "t", "token")).resolves.toBeUndefined();
    await listAgents("w", "token");
    expect(fetch.mock.calls.map(([url, init]) => [url.replace("http://localhost:8000/api/workspaces/w", ""), init.method ?? "GET"])).toEqual([
      ["/agents?include_inactive=true", "GET"], ["/agents/a", "GET"], ["/agents", "POST"], ["/agents/a", "PATCH"],
      ["/tools", "GET"], ["/tools/t", "GET"], ["/tools", "POST"], ["/tools/t", "PATCH"],
      ["/agents/a/tools", "GET"], ["/agents/a/tools/t", "PUT"], ["/agents/a/tools/t", "DELETE"], ["/agents", "GET"],
    ]);
    for (const [, init] of fetch.mock.calls) {
      expect(init.headers.get("Authorization")).toBe("Bearer token"); expect(init.headers.get("Accept")).toBe("application/json");
      expect(init.headers.get("Content-Type")).toBe(init.body === undefined ? null : "application/json");
    }
    expect(JSON.parse(fetch.mock.calls[2][1].body)).toEqual({ name: "Agent", system_prompt: "Scope", description: null });
    expect(JSON.parse(fetch.mock.calls[3][1].body)).toEqual({ description: null });
    expect(JSON.parse(fetch.mock.calls[7][1].body)).toEqual({ status: "active" });
    expect(fetch.mock.calls[9][1].body).toBeUndefined(); expect(fetch.mock.calls[10][1].body).toBeUndefined();
  });
  it("does not parse the 204 body", async () => {
    const response = new Response(null, { status: 204 }); const json = vi.spyOn(response, "json");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));
    await unassignTool("w", "a", "t", "token"); expect(json).not.toHaveBeenCalled();
  });
  it.each([401, 403, 404, 409, 422, 503])("preserves %s errors without validation content", async status => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: [{ input: "private-prompt" }] }), { status })));
    await expect(getAgent("w", "a", "token")).rejects.toEqual(new ApiError(`Request failed (${status})`, status));
  });
  it("propagates an ambiguous network failure without replaying a create", async () => {
    const fetch = vi.fn().mockRejectedValue(new Error("private transport details")); vi.stubGlobal("fetch", fetch);
    await expect(createAgent("w", { name: "A", system_prompt: "Scope" }, "token")).rejects.toEqual(new ApiError("Unable to reach the Enterprise AI API.", 0));
    expect(fetch).toHaveBeenCalledTimes(1);
  });
  it("reports malformed successful JSON as unconfirmed rather than success", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("invalid", { status: 201 })));
    await expect(createTool("w", { tool_key: "get_employee_information", name: "Self", description: "Self" }, "token")).rejects.toBeInstanceOf(SyntaxError);
  });
  it.each([
    { tool_key: "unknown" }, { risk_level: "high" as const }, { operation_type: "write_sensitive" as const },
  ])("rejects unknown or inconsistent UI capability metadata %j", overrides => {
    expect(usableConfiguration({ ...toolFixture(), ...overrides })).toBe(false);
  });
});
