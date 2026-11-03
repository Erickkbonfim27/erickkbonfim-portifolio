import type { Explained } from "../api/types";
import { useI18n } from "../i18n";
import { hitHref, ms, snippet } from "../lib/search";
import type { ApiState } from "../lib/useApi";
import { Check } from "./Icons";
import { Link } from "./Link";

/** The site's reply to a question: the passages the hybrid search found, with links. */
export function SearchAnswer({ search, trace = false }: { search: ApiState<Explained>; trace?: boolean }) {
  const { t, to } = useI18n();
  const h = t.hero;
  const data = search.data;
  if (search.error) {
    return (
      <div className="bubble site">
        <p>{h.traceError}</p>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="bubble site">
        <p className="typing" aria-label={h.thinking}>
          <i />
          <i />
          <i />
        </p>
      </div>
    );
  }
  const total = data.steps.reduce((sum, step) => sum + step.ms, 0);
  return (
    <div className="bubble site">
      {data.hits.length === 0 ? (
        <p>{h.noResults}</p>
      ) : (
        <>
          <p>{h.found(data.hits.length)}</p>
          <ol className="answers">
            {data.hits.map((hit) => {
              const href = hitHref(hit, to);
              const title = (
                <>
                  <strong>{hit.title}</strong>
                  {hit.heading && <span> · {hit.heading}</span>}
                </>
              );
              return (
                <li key={`${hit.entry_id}-${hit.heading}`}>
                  {href ? <Link to={href}>{title}</Link> : <span>{title}</span>}
                  <p>{snippet(hit.text)}</p>
                </li>
              );
            })}
          </ol>
        </>
      )}
      <p className="answer-meta mono">
        <Check size={12} strokeWidth={2.6} stroke="#5BE3A0" /> {h.meta(ms(total), data.degraded)}
      </p>
      {trace && (
        <details className="answer-trace">
          <summary className="mono">{h.showSteps}</summary>
          <ol>
            {data.steps.map((step) => (
              <li key={step.name} className="mono">
                <span>{step.name}</span>
                <span>{ms(step.ms)}</span>
              </li>
            ))}
          </ol>
        </details>
      )}
    </div>
  );
}
