import type { Entry } from "../api/types";
import { useI18n } from "../i18n";
import { Body } from "./blocks/Body";

/** The road book on the home page. Without it (API down, not published) the section is left out. */
export function Ecosystem({ entry }: { entry: Entry | null }) {
  const { t } = useI18n();
  if (!entry) return null;
  return (
    <section id="ecosystem" className="sec" aria-labelledby="eco-title">
      <div className="wrap">
        <div className="shead reveal">
          <div className="l">
            <p className="eyebrow mono">{t.ecosystem.eyebrow}</p>
            <h2 id="eco-title" className="h2">
              {entry.title}
            </h2>
          </div>
          <p className="r">{entry.summary}</p>
        </div>
        <Body segments={entry.body} fallbackHtml={entry.body_html} />
      </div>
    </section>
  );
}
