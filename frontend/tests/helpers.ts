import { vi } from "vitest";
import type { Entry, Profile, Skill } from "../src/api/types";

export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

type Handler = (url: URL, init: RequestInit | undefined) => Response | Promise<Response>;

/** Stubs global fetch with a router over pathnames; unknown paths answer 404. */
export function mockFetch(routes: Record<string, Handler | unknown>) {
  const calls: { url: URL; init: RequestInit | undefined }[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://localhost");
    calls.push({ url, init });
    const route = routes[url.pathname];
    if (route === undefined) return json({ detail: "not found" }, 404);
    return typeof route === "function" ? (route as Handler)(url, init) : json(route);
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls, fetchMock };
}

export function entry(overrides: Partial<Entry> = {}): Entry {
  return {
    kind: "project",
    slug: "rhye",
    title: "Rhye",
    summary: "People intelligence.",
    tags: [],
    details: {},
    body_html: "",
    skills: [],
    attachments: [],
    published_at: "2026-11-01T00:00:00Z",
    updated_at: "2026-11-01T00:00:00Z",
    ...overrides,
  };
}

export function profile(overrides: Partial<Profile> = {}): Profile {
  return {
    name: "Erick Kopak Bonfim",
    headline: "AI Engineer",
    summary: "",
    bio_html: "",
    location: "Brusque, SC",
    email: "erickkbonfim@gmail.com",
    links: [],
    availability: { status: "open", open: true, updated_at: "2026-11-01" },
    attachments: [],
    ...overrides,
  };
}

export function skill(title: string, category: Skill["category"]): Skill {
  return { slug: title.toLowerCase(), title, category, evidence: [] };
}
