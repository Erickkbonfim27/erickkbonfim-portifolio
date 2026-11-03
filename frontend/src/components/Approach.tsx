import { useI18n } from "../i18n";

const svg = {
  width: 22,
  height: 22,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round",
  strokeLinejoin: "round",
} as const;

export function Approach() {
  const { t } = useI18n();
  const a = t.approach;
  const [rls, evals, vectors, sales] = a.principles;
  return (
    <section id="approach" className="sec" aria-labelledby="approach-title">
      <div className="wrap">
        <div className="shead reveal">
          <div className="l">
            <p className="eyebrow mono">
              <span className="n">02</span>
              {a.eyebrow}
            </p>
            <h2 id="approach-title" className="h2">
              {a.title}
            </h2>
          </div>
          <p className="r">{a.intro}</p>
        </div>
        <div className="bento">
          <div className="card flow s12 reveal">
            <div className="card-top">
              <span className="label mono">{a.process}</span>
              <span className="mono" style={{ fontSize: 11.5, color: "var(--ink3)" }}>
                {a.perFeature}
              </span>
            </div>
            <ol className="loop" aria-label={a.loopLabel}>
              {a.loop.map((step) => (
                <li key={step.idx} className="stg">
                  <span className="idx mono">{step.idx}</span>
                  <span className="st">{step.st}</span>
                  <span className="sd">{step.sd}</span>
                </li>
              ))}
            </ol>
            <div className="loopback" aria-hidden="true">
              <span className="mono">{a.repeat}</span>
            </div>
          </div>

          <article className="card cob pcard s3 reveal">
            <span className="pic" aria-hidden="true">
              <svg {...svg}>
                <path d="M12 3 4.5 6v5.5c0 4.6 3.2 8.4 7.5 9.5 4.3-1.1 7.5-4.9 7.5-9.5V6L12 3Z" />
                <path d="m9 12 2 2 4-4" />
              </svg>
            </span>
            <h3 className="ptitle">{rls.title}</h3>
            <p className="ptext">{rls.text}</p>
            <p className="pfoot mono">{rls.foot}</p>
          </article>
          <article className="card pcard s3 reveal">
            <span className="pic" aria-hidden="true">
              <svg {...svg}>
                <rect x="3.5" y="3.5" width="17" height="17" rx="4" />
                <path d="m8 12 3 3 5-6" />
              </svg>
            </span>
            <h3 className="ptitle">{evals.title}</h3>
            <p className="ptext">{evals.text}</p>
            <p className="pfoot mono">{evals.foot}</p>
          </article>
          <article className="card pcard s3 reveal">
            <span className="pic" aria-hidden="true">
              <svg {...svg}>
                <path d="m12 3 9 5-9 5-9-5 9-5Z" />
                <path d="m3 13 9 5 9-5" />
              </svg>
            </span>
            <h3 className="ptitle">{vectors.title}</h3>
            <p className="ptext">{vectors.text}</p>
            <p className="pfoot mono">{vectors.foot}</p>
          </article>
          <article className="card dark pcard s3 reveal">
            <span className="pic" aria-hidden="true">
              <svg {...svg}>
                <circle cx="12" cy="12" r="8.5" />
                <path d="M14.6 9.4c-.5-.9-1.5-1.4-2.6-1.4-1.4 0-2.5.8-2.5 2s1.1 1.6 2.5 2 2.5.8 2.5 2-1.1 2-2.5 2c-1.1 0-2.1-.5-2.6-1.4" />
                <path d="M12 6.5V8" />
                <path d="M12 16v1.5" />
              </svg>
            </span>
            <h3 className="ptitle">{sales.title}</h3>
            <p className="ptext">{sales.text}</p>
            <p className="pfoot mono">{sales.foot}</p>
          </article>
        </div>
      </div>
    </section>
  );
}
