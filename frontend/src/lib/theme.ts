// Light or dark: the visitor's choice when they made one, the system's otherwise.
// The theme is a `data-theme` attribute on <html>; the CSS swaps tokens on it.

import { useSyncExternalStore } from "react";
import { readPref, writePref } from "./prefs";

export type Theme = "light" | "dark";

const KEY = "theme";
const DARK_QUERY = "(prefers-color-scheme: dark)";
const listeners = new Set<() => void>();

function systemTheme(): Theme {
  return window.matchMedia?.(DARK_QUERY).matches ? "dark" : "light";
}

function chosenTheme(): Theme | null {
  const stored = readPref(KEY);
  return stored === "light" || stored === "dark" ? stored : null;
}

export function currentTheme(): Theme {
  return document.documentElement.dataset.theme === "dark" ? "dark" : "light";
}

function apply(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;
  listeners.forEach((listener) => listener());
}

/** Runs once before the first render, so the page never flashes the other theme. */
export function initTheme(): void {
  apply(chosenTheme() ?? systemTheme());
  window.matchMedia?.(DARK_QUERY).addEventListener?.("change", () => {
    if (!chosenTheme()) apply(systemTheme());
  });
}

export function setTheme(theme: Theme): void {
  writePref(KEY, theme);
  apply(theme);
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useTheme(): Theme {
  return useSyncExternalStore(subscribe, currentTheme);
}
