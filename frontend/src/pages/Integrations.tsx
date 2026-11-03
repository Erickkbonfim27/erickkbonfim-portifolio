import { api } from "../api/client";
import { Body } from "../components/blocks/Body";
import { Layout } from "../components/Layout";
import { useI18n } from "../i18n";
import { useApi } from "../lib/useApi";
import { NotFoundContent } from "./NotFound";

/** /integrations: a written page from the API (writing/integrations), not a case study. */
export function Integrations() {
  const { lang, t } = useI18n();
  const page = useApi(`writing:${lang}:integrations`, (signal) => api.writing("integrations", lang, { signal }));
  const entry = page.data;
  return (
    <Layout onHome={false} cv={null} title={t.titles.integrations}>
      {page.error?.kind === "not_found" ? (
        <NotFoundContent />
      ) : (
        <article className="wrap case" aria-labelledby="case-title" aria-busy={page.loading}>
          <header id="top" className="card case-head">
            <span className="label mono">{t.nav.integrations}</span>
            <h1 id="case-title" className="case-title">
              {entry?.title ?? t.nav.integrations}
            </h1>
            {entry?.summary && <p className="case-summary">{entry.summary}</p>}
            {page.error && (
              <p className="case-summary" role="alert">
                {t.case.errorText}
              </p>
            )}
          </header>
          {entry && (
            <div className="card case-body">
              <Body segments={entry.body} fallbackHtml={entry.body_html} />
            </div>
          )}
        </article>
      )}
    </Layout>
  );
}
