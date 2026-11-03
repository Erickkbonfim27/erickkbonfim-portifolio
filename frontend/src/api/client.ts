import type { AgentEvent, ChatTurn, ContactAccepted, ContactRequest, Entry, Explained, Lang, Profile, Skill } from "./types";

export const DEFAULT_TIMEOUT_MS = 8000;

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

function withLang(path: string, lang: Lang, params: Record<string, string> = {}): string {
  return `${path}?${new URLSearchParams({ ...params, lang }).toString()}`;
}

type Opts = Pick<RequestOptions, "signal" | "timeoutMs">;

export const api = {
  profile: (lang: Lang, o?: Opts) => request<Profile>(withLang("/api/profile", lang), o),
  experience: (lang: Lang, o?: Opts) => request<Entry[]>(withLang("/api/experience", lang), o),
  education: (lang: Lang, o?: Opts) => request<Entry[]>(withLang("/api/education", lang), o),
  certificates: (lang: Lang, o?: Opts) => request<Entry[]>(withLang("/api/certificates", lang), o),
  studies: (lang: Lang, o?: Opts) => request<Entry[]>(withLang("/api/studies", lang), o),
  skills: (lang: Lang, o?: Opts) => request<Skill[]>(withLang("/api/skills", lang), o),
  project: (slug: string, lang: Lang, o?: Opts) =>
    request<Entry>(withLang(`/api/projects/${encodeURIComponent(slug)}`, lang), o),
  projects: (lang: Lang, o?: Opts) => request<Entry[]>(withLang("/api/projects", lang), o),
  writing: (slug: string, lang: Lang, o?: Opts) =>
    request<Entry>(withLang(`/api/writing/${encodeURIComponent(slug)}`, lang), o),
  explain: (q: string, lang: Lang, o?: Opts) => request<Explained>(withLang("/api/search/explain", lang, { q }), o),
  contact: (body: ContactRequest, idempotencyKey: string, o?: Opts) =>
    request<ContactAccepted>("/api/contact", {
      ...o,
      method: "POST",
      body,
      headers: { "Idempotency-Key": idempotencyKey },
    }),
};

/** Ask the site's agent. Each Server-Sent Event is handed to `onEvent` as it arrives. */
export async function streamChat(
  body: { message: string; history: ChatTurn[]; lang: Lang },
  onEvent: (event: AgentEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`${apiBase()}/api/chat`, {
      method: "POST",
      headers: { Accept: "text/event-stream", "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: signal ?? null,
    });
  } catch {
    throw new ApiError(signal?.aborted ? "aborted" : "network");
  }
  if (!response.ok || !response.body) {
    throw new ApiError(kindForStatus(response.status), response.status, await readDetail(response));
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (value) buffer += decoder.decode(value, { stream: true });
    let end = buffer.indexOf("\n\n");
    while (end >= 0) {
      const block = buffer.slice(0, end);
      buffer = buffer.slice(end + 2);
      const kind = /^event: (\w+)/m.exec(block)?.[1];
      const data = /^data: (.*)$/m.exec(block)?.[1];
      if (kind && data) onEvent({ kind, data: JSON.parse(data) } as AgentEvent);
      end = buffer.indexOf("\n\n");
    }
    if (done) return;
  }
}
