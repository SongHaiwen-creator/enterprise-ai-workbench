import assert from "node:assert/strict";
import test from "node:test";

import { ApiError, normalizeBaseUrl, requestJson } from "../utils/api.ts";
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

test("formats API enum labels and initials for display", () => {
  assert.equal(formatEnumLabel("system_admin"), "System Admin");
  assert.equal(formatEnumLabel("invited"), "Invited");
  assert.equal(initials("Alice Zhang"), "AZ");
  assert.equal(initials(" "), "?");
});
