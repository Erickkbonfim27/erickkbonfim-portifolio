import { useState, type FormEvent } from "react";
import { api } from "../api/client";
import type { Availability, Explained } from "../api/types";
import { EMAIL, GITHUB, LINKEDIN } from "../content/fallback";
import { useI18n } from "../i18n";
import { availabilityText, isOpen } from "../lib/derive";
import { useApi } from "../lib/useApi";
import { useInView } from "../lib/useInView";
import { MAX_QUESTION, hitHref, ms } from "../lib/search";
import { ArrowUpRight, Check } from "./Icons";
import { Link } from "./Link";
import { SearchAnswer } from "./SearchAnswer";

interface HeroProps {
  availability: Availability | null;
}

type Search = ReturnType<typeof useApi<Explained>>;

/** A small chat over this site's own search: the visitor asks, the site answers with the
 * passages it found. It returns excerpts, not a written answer; that is the agent's job. */
function Core({ search, query, onAsk }: { search: Search; query: string; onAsk: (question: string) => void }) {
  const { t } = useI18n();
  const h = t.hero;
  const [draft, setDraft] = useState("");
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const question = draft.trim();
    if (!question) return;
    onAsk(question.slice(0, MAX_QUESTION));
    setDraft("");
  };
  return (
    <section className="card dark h-core fade f4" aria-labelledby="core-title">
      <div className="card-top">
        <div className="core-head">
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <span className="label mono">{h.coreLabel}</span>
            <h2 id="core-title" style={{ fontSize: 15, fontWeight: 600, letterSpacing: "-0.01em" }}>
              {h.coreTitle}
            </h2>
          </div>
        </div>
        <a className="arrowbtn" href="#approach" aria-label={h.coreLink}>
          <ArrowUpRight />
        </a>
      </div>
      <div className="chat">
        {/* Absolutely placed: a long answer scrolls inside the card instead of stretching it. */}
        <div className="chat-scroll" aria-live="polite" data-clarity-mask="true">
          <p className="bubble me">{query}</p>
          <SearchAnswer search={search} />
        </div>
      </div>
      <div className="asks" role="group" aria-label={h.askLabel}>
        {h.presets.map((preset) => (
          <button key={preset} type="button" className="ask" aria-pressed={preset === query} onClick={() => onAsk(preset)}>
            {preset}
          </button>
        ))}
      </div>
      <form className="ask-form" onSubmit={submit} data-clarity-mask="true">
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          maxLength={MAX_QUESTION}
          placeholder={h.placeholder}
          aria-label={h.placeholder}
        />
        <button type="submit" className="ask-send" aria-label={h.send} disabled={!draft.trim()}>
          <ArrowUpRight size={16} />
        </button>
      </form>
      <p className="core-note mono">
        <span style={{ color: "var(--acc-hi)" }}>//</span> {h.coreCaption}
      </p>
    </section>
  );
}

function Trace({ search, query }: { search: Search; query: string }) {
  const { t, to } = useI18n();
  const h = t.hero;
  const data = search.data;
  const steps = data?.steps ?? [];
  const total = steps.reduce((sum, step) => sum + step.ms, 0) || 1;
  // Each span starts where the previous ones end: the steps run one after another.
  const starts = steps.map((_, index) => steps.slice(0, index).reduce((sum, step) => sum + step.ms, 0));
  const status = search.error ? "fail" : !data ? "run" : data.degraded ? "warn" : "pass";
  const label = { fail: h.failed, run: h.running, warn: h.degraded, pass: h.passed }[status];
  return (
    <figure className="card h-trace fade f5" aria-labelledby="trace-cap" aria-busy={status === "run"}>
      <div className="card-top">
        <div style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 0 }}>
          <span className="label mono">{h.traceLabel}</span>
          <span className="mono trace-q" data-clarity-mask="true">GET /api/search/explain?q={query}</span>
        </div>
        <span className={`trace-status mono ts-${status}`}>
          {status === "pass" && <Check size={12} />}
          {label}
        </span>
      </div>
      {search.error ? (
        <p className="trace-err" role="status">
          {h.traceError}
        </p>
      ) : (
        <div className="tw mono">
          <div className="tr thead" aria-hidden="true">
            <span>SPAN</span>
            <span>TIMELINE</span>
            <span style={{ textAlign: "right" }}>DUR</span>
          </div>
          {steps.map((step, index) => {
            const width = (step.ms / total) * 100;
            const left = ((starts[index] ?? 0) / total) * 100;
            return (
              <div key={step.name} className="tr tr-live">
                <span className="nm">
                  <span className="t">{step.name}</span>
                </span>
                <span className="wf" aria-hidden="true">
                  <span className={`bar${step.name.startsWith("rrf") ? " okc" : step.name.startsWith("dense") ? " acc" : ""}`} style={{ left: `${left}%`, width: `${Math.max(width, 1.5)}%` }} />
                </span>
                <span className="dur">{ms(step.ms)}</span>
              </div>
            );
          })}
        </div>
      )}
      {data && data.hits.length > 0 && (
        <div className="trace-hits">
          <span className="label mono">{h.results}</span>
          <ol>
            {data.hits.map((hit) => {
              const href = hitHref(hit, to);
              const text = (
                <>
                  <span className="th-title">{hit.title}</span>
                  {hit.heading && <span className="th-head"> · {hit.heading}</span>}
                </>
              );
              return (
                <li key={`${hit.entry_id}-${hit.heading}`}>
                  {href ? <Link to={href}>{text}</Link> : text}
                </li>
              );
            })}
          </ol>
        </div>
      )}
      <figcaption id="trace-cap" className="mono" style={{ fontSize: 12, lineHeight: 1.6, color: "var(--ink2)" }}>
        <span style={{ color: "var(--accent)" }}>//</span> {h.traceCaption}
      </figcaption>
    </figure>
  );
}

export function Hero({ availability }: HeroProps) {
  const { lang, t, to } = useI18n();
  const h = t.hero;
  // A preset by index (it follows the language), or the visitor's own question.
  const [chosen, setChosen] = useState<number | string>(0);
  const query = typeof chosen === "number" ? (h.presets[chosen] ?? h.presets[0]) : chosen;
  const ask = (question: string) => {
    const preset = h.presets.indexOf(question);
    setChosen(preset >= 0 ? preset : question);
  };
  const [ref, seen] = useInView<HTMLDivElement>(0.1);
  // Only once the cards are on screen: every search is a real request.
  const search = useApi<Explained>(seen ? `explain:${lang}:${query}` : null, (signal) =>
    api.explain(query, lang, { signal, timeoutMs: 12000 }),
  );

  return (
    <section id="top" aria-labelledby="hero-title">
      <div ref={ref} className="wrap hero">
        <div className="h-head">
          <div className="fade" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 10 }}>
            <span className="pill">
              {isOpen(availability) && <span className="live" aria-hidden="true" />}
              {availabilityText(availability, lang)}
            </span>
            <span className="mono" style={{ fontSize: 11.5, letterSpacing: "0.08em", color: "var(--ink3)" }}>
              {h.location}
            </span>
          </div>
          <h1 id="hero-title" className="h1">
            <span className="ln">
              <span className="in">
                {h.title}{" "}
                <span className="inl face" aria-hidden="true">
                  <span className="mono">EK</span>
                  <i />
                </span>
              </span>
            </span>{" "}
            <span className="ln tagline">
              <span className="in">{h.tagline}</span>
            </span>
          </h1>
          <p
            className="fade f1"
            style={{ maxWidth: 620, fontSize: "clamp(16px, 1.3cqi, 18px)", lineHeight: 1.7, color: "var(--ink2)", textWrap: "pretty" }}
          >
            {h.intro}
          </p>
          <div className="fade f2" style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
            <a className="pillbtn pill-dark" href={`mailto:${EMAIL}`}>
              {h.email}
              <span className="ab">
                <ArrowUpRight />
              </span>
            </a>
            <a className="pillbtn pill-line" href="#work">
              {h.seeWork}
            </a>
          </div>
          <div className="fade f3" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "4px 20px" }}>
            <a className="tlink" href={LINKEDIN}>
              LinkedIn
              <ArrowUpRight size={13} />
            </a>
            <a className="tlink" href={GITHUB}>
              GitHub
              <ArrowUpRight size={13} />
            </a>
          </div>
        </div>

        <Core search={search} query={query} onAsk={ask} />
        <Trace search={search} query={query} />

        <article className="card h-path fade f6" aria-labelledby="path-title">
          <div className="card-top">
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <span className="label mono">{h.pathLabel}</span>
              <h2 id="path-title" style={{ fontSize: 15, fontWeight: 600, letterSpacing: "-0.01em" }}>
                {h.pathTitle}
              </h2>
            </div>
            <a className="arrowbtn" href="#experience" aria-label={h.pathLink}>
              <ArrowUpRight />
            </a>
          </div>
          <ol className="path">
            {h.steps.map((step) => (
              <li key={step.org}>
                <Link className="path-step" to={to(step.to)}>
                  <span className="path-when mono">{step.when}</span>
                  <span className="path-dot" aria-hidden="true" />
                  <span className="path-tx">
                    <span className="path-t">{step.t}</span>
                    <span className="path-org">{step.org}</span>
                  </span>
                  <ArrowUpRight size={14} />
                </Link>
              </li>
            ))}
          </ol>
        </article>
      </div>
    </section>
  );
}
