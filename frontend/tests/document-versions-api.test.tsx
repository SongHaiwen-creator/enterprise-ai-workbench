import { afterEach, expect, it, vi } from "vitest";
import { activateDocumentVersion, getDocumentFamily, listDocumentFamilies,
  listDocumentVersions, uploadDocumentVersion } from "@/utils/knowledge-admin";

afterEach(() => vi.unstubAllGlobals());
it("uses five scoped version calls, explicit revision and browser multipart boundary", async () => {
  const fetch = vi.fn().mockImplementation(async () => new Response("{}"));
  vi.stubGlobal("fetch", fetch);
  await listDocumentFamilies("a", "kb", "token");
  await getDocumentFamily("a", "kb", "family", "token");
  await listDocumentVersions("a", "kb", "family", "token");
  const file = new File(["Synthetic policy"], "policy.md");
  await uploadDocumentVersion("a", "kb", "family", file, "token");
  await activateDocumentVersion("a", "kb", "family", "v2", 8, "token");
  const prefix = "http://localhost:8000/api/workspaces/a/knowledge-bases/kb/document-families";
  expect(fetch.mock.calls.map(c => c[0])).toEqual([prefix, `${prefix}/family`,
    `${prefix}/family/versions`, `${prefix}/family/versions`, `${prefix}/family/activate`]);
  for (const [, init] of fetch.mock.calls) expect(init.headers.get("Authorization")).toBe("Bearer token");
  expect(fetch.mock.calls[3][1].body.get("file")).toBe(file);
  expect(fetch.mock.calls[3][1].headers.has("Content-Type")).toBe(false);
  expect(JSON.parse(fetch.mock.calls[4][1].body)).toEqual({ document_id: "v2", expected_revision: 8 });
  expect(fetch.mock.calls[4][1].method).toBe("POST");
});

it.each([401, 403, 404, 409, 422, 500])("preserves safe HTTP %i without replaying activation", async status => {
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "Safe version error" }), { status }));
  vi.stubGlobal("fetch", fetch);
  await expect(activateDocumentVersion("a", "kb", "f", "v", 1, "token")).rejects.toMatchObject({ status });
  expect(fetch).toHaveBeenCalledTimes(1);
});
