import type { Lang } from "../api/types";
import { readPref, writePref } from "./prefs";
import { localize, splitLang } from "./router";

const KEY = "lang";

export function rememberLang(lang: Lang): void {
  writePref(KEY, lang);
}

function browserLang(): Lang {
  const first = window.navigator.languages?.[0] ?? window.navigator.language ?? "";
  return first.toLowerCase().startsWith("pt") ? "pt" : "en";
}

/** Where to send a visitor who lands on an English URL: the Portuguese page when they
 * chose Portuguese before, or when their browser asks for it and they never chose.
 * Null means stay. A /pt URL is always respected. */
export function landingRedirect(location: Pick<Location, "pathname" | "search" | "hash">): string | null {
  const { lang, path } = splitLang(location.pathname);
  if (lang === "pt") return null;
  const stored = readPref(KEY);
  const wanted = stored === "pt" || stored === "en" ? stored : browserLang();
  if (wanted === "en") return null;
  return `${localize(path, "pt")}${location.search}${location.hash}`;
}
