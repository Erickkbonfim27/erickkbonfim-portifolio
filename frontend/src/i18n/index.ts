import type { Lang } from "../api/types";
import { localize, useLang } from "../lib/router";
import { MESSAGES, type Messages } from "./messages";

export { MESSAGES, type Messages };

/** The copy and the language of the page being shown, taken from its URL. */
export function useI18n(): { lang: Lang; t: Messages; to: (path: string) => string } {
  const lang = useLang();
  return { lang, t: MESSAGES[lang], to: (path: string) => localize(path, lang) };
}
