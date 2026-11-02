import type { ContactAccepted, ContactRequest, Entry, Lang, Profile, Skill } from "./types";

export const DEFAULT_TIMEOUT_MS = 8000;
export const LANG: Lang = "en";

export type ApiErrorKind = "not_found" | "rate_limited" | "invalid" | "http" | "network" | "timeout" | "aborted";

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number | null;
  readonly detail: string | null;

  constructor(kind: ApiErrorKind, status: number | null = null, detail: string | null = null) {
    super(detail ?? kind);
    this.name = "ApiError";
    this.kind = kind;
    this.status = status;
    this.detail = detail;
  }
}

/** VITE_API_URL is read at build time; empty means the API is served from the same origin. */
export function apiBase(raw: string | undefined = import.meta.env.VITE_API_URL): string {
  return (raw ?? "").trim().replace(/\/+$/, "");
}

/** Where the MCP server lives: next to the API (same origin when no API URL is configured). */
export function mcpUrl(base: string = apiBase()): string {
  return `${base || window.location.origin}/mcp`;
}

interface RequestOptions {
  signal?: AbortSignal;
  timeoutMs?: number;
  method?: "GET" | "POST";
  body?: unknown;
  headers?: Record<string, string>;
}

function kindForStatus(status: number): ApiErrorKind {
  if (status === 404) return "not_found";
  if (status === 429) return "rate_limited";
  if (status === 422) return "invalid";
  return "http";
}

async function readDetail(response: Response): Promise<string | null> {
  try {
    const body: unknown = await response.json();
    if (body && typeof body === "object" && "detail" in body) {
      const detail = (body as { detail: unknown }).detail;
      // FastAPI validation errors are a list; only plain messages are meant for people.
      return typeof detail === "string" ? detail : null;
    }
  } catch {
    // not JSON: no detail
  }
  return null;
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { signal, timeoutMs = DEFAULT_TIMEOUT_MS, method = "GET", body, headers = {} } = options;
  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  const onAbort = () => controller.abort();
  signal?.addEventListener("abort", onAbort, { once: true });

  try {
    const init: RequestInit = {
      method,
      signal: controller.signal,
      headers: { Accept: "application/json", ...headers },
    };
    if (body !== undefined) {
      init.body = JSON.stringify(body);
      init.headers = { ...init.headers, "Content-Type": "application/json" };
    }
    let response: Response;
    try {
      response = await fetch(`${apiBase()}${path}`, init);
    } catch {
      if (timedOut) throw new ApiError("timeout");
      if (signal?.aborted) throw new ApiError("aborted");
      throw new ApiError("network");
    }
    if (!response.ok) {
      throw new ApiError(kindForStatus(response.status), response.status, await readDetail(response));
    }
    return (await response.json()) as T;
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", onAbort);
  }
}

function withLang(path: string, params: Record<string, string> = {}): string {
  const query = new URLSearchParams({ lang: LANG, ...params });
  return `${path}?${query.toString()}`;
}

type Opts = Pick<RequestOptions, "signal" | "timeoutMs">;

export const api = {
  profile: (o?: Opts) => request<Profile>(withLang("/api/profile"), o),
  experience: (o?: Opts) => request<Entry[]>(withLang("/api/experience"), o),
  education: (o?: Opts) => request<Entry[]>(withLang("/api/education"), o),
  certificates: (o?: Opts) => request<Entry[]>(withLang("/api/certificates"), o),
  studies: (o?: Opts) => request<Entry[]>(withLang("/api/studies"), o),
  skills: (o?: Opts) => request<Skill[]>(withLang("/api/skills"), o),
  project: (slug: string, o?: Opts) =>
    request<Entry>(withLang(`/api/projects/${encodeURIComponent(slug)}`), o),
  contact: (body: ContactRequest, idempotencyKey: string, o?: Opts) =>
    request<ContactAccepted>("/api/contact", {
      ...o,
      method: "POST",
      body,
      headers: { "Idempotency-Key": idempotencyKey },
    }),
};
