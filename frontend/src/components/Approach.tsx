const LOOP = [
  { idx: "01", st: "Define", sd: "Agree on the problem and how we'll measure it." },
  { idx: "02", st: "Prototype", sd: "Build the smallest version that works on real data." },
  { idx: "03", st: "Trace", sd: "Add tracing before adding features." },
  { idx: "04", st: "Evaluate", sd: "Test changes against an eval set before release." },
  { idx: "05", st: "Ship", sd: "Deploy with infrastructure as code, then repeat." },
];

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
  return (
    <section id="approach" className="sec" aria-labelledby="approach-title">
      <div className="wrap">
        <div className="shead reveal">
          <div className="l">
            <p className="eyebrow mono">
              <span className="n">02</span>How I work
            </p>
            <h2 id="approach-title" className="h2">
              How I think about agents
            </h2>
          </div>
          <p className="r">The steps I follow, and a few opinions I picked up shipping agents at Vizzion and Loopia.</p>
        </div>
        <div className="bento">
          <div className="card flow s12 reveal">
            <div className="card-top">
              <span className="label mono">Process</span>
              <span className="mono" style={{ fontSize: 11.5, color: "#5F6670" }}>
                for each feature
              </span>
            </div>
            <ol className="loop" aria-label="Build loop">
              {LOOP.map((step) => (
                <li key={step.idx} className="stg">
                  <span className="idx mono">{step.idx}</span>
                  <span className="st">{step.st}</span>
                  <span className="sd">{step.sd}</span>
                </li>
              ))}
            </ol>
            <div className="loopback" aria-hidden="true">
              <span className="mono">REPEAT</span>
            </div>
          </div>

          <article className="card cob pcard s3 reveal">
            <span className="pic" aria-hidden="true">
              <svg {...svg}>
                <path d="M12 3 4.5 6v5.5c0 4.6 3.2 8.4 7.5 9.5 4.3-1.1 7.5-4.9 7.5-9.5V6L12 3Z" />
                <path d="m9 12 2 2 4-4" />
              </svg>
            </span>
            <h3 className="ptitle">The model only sees what the user can see.</h3>
            <p className="ptext">
              At Vizzion, agent tools queried Postgres through Row-Level Security. If a user couldn't read a row, the
              agent working for them couldn't either.
            </p>
            <p className="pfoot mono">LEARNED AT VIZZION</p>
          </article>
          <article className="card pcard s3 reveal">
            <span className="pic" aria-hidden="true">
              <svg {...svg}>
                <rect x="3.5" y="3.5" width="17" height="17" rx="4" />
                <path d="m8 12 3 3 5-6" />
              </svg>
            </span>
            <h3 className="ptitle">No eval set, no prompt changes.</h3>
            <p className="ptext">
              Changing a prompt without examples to compare against is guessing. I build the eval set first, even if it
              starts as a small spreadsheet.
            </p>
            <p className="pfoot mono">LANGFUSE · LANGSMITH</p>
          </article>
          <article className="card pcard s3 reveal">
            <span className="pic" aria-hidden="true">
              <svg {...svg}>
                <path d="m12 3 9 5-9 5-9-5 9-5Z" />
                <path d="m3 13 9 5 9-5" />
              </svg>
            </span>
            <h3 className="ptitle">Product search needs both kinds of vectors.</h3>
            <p className="ptext">
              Customers type SKUs and brand names, and dense vectors are bad at exact matches. At Loopia the index
              combines dense and sparse.
            </p>
            <p className="pfoot mono">LEARNED AT LOOPIA</p>
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
            <h3 className="ptitle">Ask who pays for it first.</h3>
            <p className="ptext">Four years in sales taught me to ask that before I ask which model to use.</p>
            <p className="pfoot mono">LEARNED AT GRUPO MELLO</p>
          </article>
        </div>
      </div>
    </section>
  );
}
