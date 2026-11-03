import type { SearchHit } from "../api/types";

export const MAX_QUESTION = 200;

/** Where a search hit lives on the site, when it has a page of its own. */
export function hitHref(hit: Pick<SearchHit, "kind" | "slug">, to: (path: string) => string): string | null {
  if (hit.kind === "project") return to(`/work/${hit.slug}`);
  if (hit.kind === "experience") return to("/#experience");
  if (hit.kind === "profile") return to("/#top");
  if (hit.kind === "writing" && hit.slug === "integrations") return to("/integrations");
  return null;
}

export function ms(value: number): string {
  return value >= 1000 ? `${(value / 1000).toFixed(2)}s` : `${Math.round(value)}ms`;
}

/** The start of a passage, cut at a word. */
export function snippet(text: string, max = 170): string {
  const clean = text.replace(/\s+/g, " ").trim();
  return clean.length > max ? `${clean.slice(0, max).replace(/\s+\S*$/, "")}…` : clean;
}
