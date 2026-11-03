import { ApiError } from "../api/client";
import type { Lang } from "../api/types";
import { MESSAGES } from "../i18n/messages";

/** What to tell the sender. The API's own 422 detail is English, so it is shown only
 * on the English page; the Portuguese page gets the general message. */
export function errorMessage(error: unknown, lang: Lang = "en"): string {
  const copy = MESSAGES[lang].form;
  if (error instanceof ApiError) {
    if (error.kind === "invalid") return error.detail && lang === "en" ? `${capitalize(error.detail)}.` : copy.invalid;
    if (error.kind === "rate_limited") return copy.rateLimited;
  }
  return copy.network;
}

function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}
