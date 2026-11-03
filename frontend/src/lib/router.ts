// A minimal history router: a handful of routes (home, case study, MCP) do not need a library.
// English lives at the root, Portuguese under /pt: every page has one URL per language.

import { useSyncExternalStore } from "react";
import type { Lang } from "../api/types";

const listeners = new Set<() => void>();

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  window.addEventListener("popstate", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("popstate", listener);
  };
}

/** Goes to `to` in the app. A new page starts at the top unless `to` has a #hash, or
 * `keepScroll` is set (the same page in another language). */
export function navigate(to: string, { keepScroll = false }: { keepScroll?: boolean } = {}): void {
  window.history.pushState({}, "", to);
  listeners.forEach((listener) => listener());
  const hash = new URL(to, window.location.origin).hash;
  if (!hash && !keepScroll) window.scrollTo({ top: 0 });
}

export function usePathname(): string {
  return useSyncExternalStore(subscribe, () => window.location.pathname);
}

/** "/pt/work/rhye" -> pt and "/work/rhye"; anything else is English. */
export function splitLang(pathname: string): { lang: Lang; path: string } {
  const match = /^\/pt(?=\/|$)(.*)$/.exec(pathname);
  if (!match) return { lang: "en", path: pathname || "/" };
  return { lang: "pt", path: match[1] || "/" };
}

/** The same page in `lang`: localize("/#work", "pt") -> "/pt#work". */
export function localize(path: string, lang: Lang): string {
  if (lang === "en") return path;
  if (path === "/" || path.startsWith("/#")) return `/pt${path.slice(1)}`;
  return `/pt${path}`;
}

export function useLang(): Lang {
  return splitLang(usePathname()).lang;
}

export type Route =
  | { name: "home" }
  | { name: "case"; slug: string }
  | { name: "mcp" }
  | { name: "integrations" }
  | { name: "not-found" };

export function matchRoute(pathname: string): Route & { lang: Lang } {
  const { lang, path: raw } = splitLang(pathname);
  const path = raw.replace(/\/+$/, "") || "/";
  if (path === "/") return { lang, name: "home" };
  if (path === "/mcp") return { lang, name: "mcp" };
  if (path === "/integrations") return { lang, name: "integrations" };
  const match = /^\/work\/([a-z0-9]+(?:-[a-z0-9]+)*)$/.exec(path);
  if (match?.[1]) return { lang, name: "case", slug: match[1] };
  return { lang, name: "not-found" };
}
