import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, apiBase, request } from "../src/api/client";
import { json, mockFetch } from "./helpers";

describe("apiBase", () => {
  it("trims whitespace and trailing slashes; empty means same origin", () => {
    expect(apiBase(" https://api.erick.dev/// ")).toBe("https://api.erick.dev");
    expect(apiBase("")).toBe("");
  });

  it("reads VITE_API_URL by default, whatever a local .env says", () => {
    vi.stubEnv("VITE_API_URL", "");
    expect(apiBase()).toBe("");
    vi.stubEnv("VITE_API_URL", "https://api.erick.dev/");
    expect(apiBase()).toBe("https://api.erick.dev");
    vi.unstubAllEnvs();
  });
});

describe("request", () => {
  afterEach(() => vi.useRealTimers());

  it("returns parsed JSON and asks for the English content", async () => {
    const { calls } = mockFetch({ "/api/experience": [{ slug: "loopia" }] });
    await expect(api.experience()).resolves.toEqual([{ slug: "loopia" }]);
    expect(calls[0]?.url.searchParams.get("lang")).toBe("en");
  });

  it("maps 404 to not_found", async () => {
    mockFetch({});
    await expect(api.project("nope")).rejects.toMatchObject({ kind: "not_found", status: 404 });
  });

  it("keeps a plain-string detail and drops validation lists", async () => {
    mockFetch({
      "/a": () => json({ detail: "brief needs 10 to 4000 characters" }, 422),
      "/b": () => json({ detail: [{ loc: ["body"], msg: "x" }] }, 422),
      "/c": () => new Response("oops", { status: 500 }),
    });
    await expect(request("/a")).rejects.toMatchObject({ kind: "invalid", detail: "brief needs 10 to 4000 characters" });
    await expect(request("/b")).rejects.toMatchObject({ kind: "invalid", detail: null });
    await expect(request("/c")).rejects.toMatchObject({ kind: "http", status: 500, detail: null });
  });

  it("maps 429 to rate_limited", async () => {
    mockFetch({ "/x": () => json({ detail: "slow down" }, 429) });
    await expect(request("/x")).rejects.toMatchObject({ kind: "rate_limited" });
  });

  it("maps a failed fetch to network", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const error = await request("/x").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ kind: "network", status: null });
  });

  it("times out a request that never answers", async () => {
    vi.useFakeTimers();
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (_input: unknown, init?: RequestInit) =>
          new Promise((_resolve, reject) => {
            init?.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
          }),
      ),
    );
    const pending = request("/slow", { timeoutMs: 50 }).catch((e: unknown) => e);
    await vi.advanceTimersByTimeAsync(60);
    await expect(pending).resolves.toMatchObject({ kind: "timeout" });
  });

  it("reports a caller abort as aborted, not timeout", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (_input: unknown, init?: RequestInit) =>
          new Promise((_resolve, reject) => {
            init?.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
          }),
      ),
    );
    const controller = new AbortController();
    const pending = request("/slow", { signal: controller.signal }).catch((e: unknown) => e);
    controller.abort();
    await expect(pending).resolves.toMatchObject({ kind: "aborted" });
  });

  it("posts the contact with JSON and the idempotency key", async () => {
    const { calls } = mockFetch({ "/api/contact": () => json({ id: "42" }, 202) });
    const body = { from: "Ana", contact: "ana@corp.dev", brief: "AI role, remote", lang: "en" as const, website: "" };
    await expect(api.contact(body, "key-1")).resolves.toEqual({ id: "42" });
    const init = calls[0]?.init;
    expect(init?.method).toBe("POST");
    expect(init?.headers).toMatchObject({ "Idempotency-Key": "key-1", "Content-Type": "application/json" });
    expect(JSON.parse(String(init?.body))).toEqual(body);
  });
});
