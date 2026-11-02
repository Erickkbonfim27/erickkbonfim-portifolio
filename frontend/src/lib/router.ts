// A minimal history router: two real routes (home, case study) do not need a library.

import { useSyncExternalStore } from "react";

const listeners = new Set<() => void>();

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  window.addEventListener("popstate", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("popstate", listener);
  };
}

export function navigate(to: string): void {
  window.history.pushState({}, "", to);
  listeners.forEach((listener) => listener());
  const hash = new URL(to, window.location.origin).hash;
  if (!hash) window.scrollTo({ top: 0 });
}

export function usePathname(): string {
  return useSyncExternalStore(subscribe, () => window.location.pathname);
}

export type Route = { name: "home" } | { name: "case"; slug: string } | { name: "not-found" };

export function matchRoute(pathname: string): Route {
  const path = pathname.replace(/\/+$/, "") || "/";
  if (path === "/") return { name: "home" };
  const match = /^\/work\/([a-z0-9]+(?:-[a-z0-9]+)*)$/.exec(path);
  if (match?.[1]) return { name: "case", slug: match[1] };
  return { name: "not-found" };
}
