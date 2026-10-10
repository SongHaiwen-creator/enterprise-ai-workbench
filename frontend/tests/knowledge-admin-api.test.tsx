import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, listKnowledgeBases, login, requestJson } from "@/utils/api";
import {
  createKnowledgeBase, getDocument, getKnowledgeBase, indexDocument, listDocuments,
  updateDocumentStatus, updateKnowledgeBase, uploadDocument,
} from "@/utils/knowledge-admin";

afterEach(() => vi.unstubAllGlobals());
describe("Knowledge administration API", () => {
  it("preserves scoped methods, body fields and bearer headers for all nine calls", async () => {
    const fetch = vi.fn().mockImplementation(async () => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetch);
    await listKnowledgeBases("w", "token"); await getKnowledgeBase("w", "kb", "token");
    await createKnowledgeBase("w", { name: "制度", description: null }, "token");
    await updateKnowledgeBase("w", "kb", { description: null }, "token");
    await listDocuments("w", "kb", "token"); await getDocument("w", "kb", "doc", "token");
    const file = new File(["Synthetic policy"], "policy.md", { type: "text/markdown" });
    await uploadDocument("w", "kb", file, "token");
    await updateDocumentStatus("w", "kb", "doc", "disabled", "token");
    await indexDocument("w", "kb", "doc", "token");
    const prefix = "/api/workspaces/w/knowledge-bases";
    const expected = [
      [prefix, "GET"], [`${prefix}/kb`, "GET"], [prefix, "POST"], [`${prefix}/kb`, "PATCH"],
      [`${prefix}/kb/documents`, "GET"], [`${prefix}/kb/documents/doc`, "GET"],
      [`${prefix}/kb/documents`, "POST"], [`${prefix}/kb/documents/doc`, "PATCH"],
      [`${prefix}/kb/documents/doc/index`, "POST"],
    ];
    for (const [i, [path, method]] of expected.entries()) {
      const [url, init] = fetch.mock.calls[i];
      expect(url).toBe(`http://localhost:8000${path}`);
      expect(init.method ?? "GET").toBe(method);
      expect(init.headers.get("Authorization")).toBe("Bearer token");
      expect(init.headers.get("Accept")).toBe("application/json");
    }
    expect(JSON.parse(fetch.mock.calls[2][1].body)).toEqual({ name: "制度", description: null });
    expect(JSON.parse(fetch.mock.calls[3][1].body)).toEqual({ description: null });
    expect(JSON.parse(fetch.mock.calls[7][1].body)).toEqual({ status: "disabled" });
    expect(fetch.mock.calls[8][1].body).toBeUndefined();
    const multipart = fetch.mock.calls[6][1];
    expect(multipart.body).toBeInstanceOf(FormData);
    expect(multipart.body.get("file")).toBe(file);
    expect(multipart.headers.has("Content-Type")).toBe(false);
  });
  it("lets the browser set a multipart boundary even with an obsolete supplied JSON header", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response("{}")); vi.stubGlobal("fetch", fetch);
    const body = new FormData(); body.append("file", new File(["text"], "text.txt"));
    await requestJson("/upload", { method: "POST", body, headers: { "Content-Type": "application/json" } }, "token");
    expect(fetch.mock.calls[0][1].headers.has("Content-Type")).toBe(false);
  });
  it("retains JSON content type for existing login and knowledge mutations", async () => {
    const fetch = vi.fn().mockImplementation(async () => new Response("{}")); vi.stubGlobal("fetch", fetch);
    await login("synthetic@example.com", "synthetic-test-password");
    await updateKnowledgeBase("w", "kb", { status: "active" }, "token");
    for (const call of fetch.mock.calls) expect(call[1].headers.get("Content-Type")).toBe("application/json");
  });
  it("returns a persisted failed document without converting 201 into usable success", async () => {
    const failed = { status: "failed", processing_error: "No extractable text" };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(failed), { status: 201 })));
    expect(await uploadDocument("w", "kb", new File(["bad"], "bad.pdf"), "token")).toEqual(failed);
  });
  it.each([401, 403, 404, 409, 413, 415, 422, 502, 503])("propagates HTTP %i safely", async status => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "Safe error" }), { status })));
    await expect(indexDocument("w", "kb", "doc", "token")).rejects.toMatchObject({ status, message: "Safe error" });
  });
  it("does not expose structured validation input or network error details", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ detail: [{ input: "sensitive" }] }), { status: 422 }))
      .mockRejectedValueOnce(new Error("secret network text"));
    vi.stubGlobal("fetch", fetch);
    await expect(listDocuments("w", "kb", "token")).rejects.toMatchObject({ message: "Request failed (422)" });
    await expect(listDocuments("w", "kb", "token")).rejects.toBeInstanceOf(ApiError);
  });
});
