import type { Entry } from "../api/types";
import type { WorkSlug } from "../content/fallback";
import { workText } from "../lib/derive";
import { buildCells } from "../lib/parcels";
import { Link } from "./Link";
import { ArrowRight, ArrowUpRight } from "./Icons";

const CELLS = buildCells();

const PIPELINE = [
  { i: "01", t: "Ingest", m: "100+ APIs · GIS, satellite, mobility, gov" },
  { i: "02", t: "Queue", m: "Pub/Sub · idempotent, integrity-checked" },
  { i: "03", t: "Services", m: "Python on Cloud Run · Cloud SQL + RLS" },
  { i: "04", t: "Analytics & search", m: "BigQuery · Elasticsearch · Memorystore" },
  { i: "05", t: "Models & tools", m: "LlamaIndex · LoRA · RLS-safe tool calls" },
];

const FLOW = ["Resume", "Parse", "Retrieve", "Score fit", "Feedback"];

function CaseLink({ slug, label }: { slug: WorkSlug; label: string }) {
  return (
    <Link className="arrowbtn" to={`/work/${slug}`} aria-label={label}>
      <ArrowUpRight />
    </Link>
  );
}

export type WorkEntries = Partial<Record<WorkSlug, Entry | null>>;

export function Work({ entries }: { entries: WorkEntries }) {
  const vizzion = workText("vizzion", entries.vizzion);
  const platform = workText("vizzion-data-platform", entries["vizzion-data-platform"]);
  const loopia = workText("loopia", entries.loopia);
  const rhye = workText("rhye", entries.rhye);

  return (
    <section id="work" className="sec" aria-labelledby="work-title">
      <div className="wrap">
        <div className="shead reveal">
          <div className="l">
            <p className="eyebrow mono">
              <span className="n">01</span>Work
            </p>
            <h2 id="work-title" className="h2">
              Projects I built or led
            </h2>
          </div>
          <p className="r">
            Vizzion is where I learned to be a CTO. Loopia was my most recent job, so its numbers stay private. Rhye is
            my own project, where I try things before I'd risk them at work.
          </p>
        </div>

        <div className="bento">
          <article className="card lift wcard s7 reveal" aria-labelledby="vizzion-title">
            <figure className="viz dkv" aria-label="Abstract parcel map representing land-vocation analysis for urban and real-estate planning.">
              <div style={{ width: "100%", display: "flex", flexDirection: "column", alignItems: "center" }} aria-hidden="true">
                <div className="parcels">
                  {CELLS.map((cell, index) => (
                    <span key={index} className={cell.cls} style={cell.style} />
                  ))}
                </div>
                <div className="legend mono">
                  <span>
                    <i style={{ background: "var(--acc-hi)" }} />
                    High potential
                  </span>
                  <span>
                    <i style={{ background: "color-mix(in srgb, var(--accent) 42%, #1B1F26)" }} />
                    Zoned
                  </span>
                  <span>
                    <i style={{ background: "#2B313B" }} />
                    Parcels
                  </span>
                </div>
              </div>
            </figure>
            <div className="card-top">
              <div className="tagrow">
                <span className="tag acc">Co-founder &amp; CTO</span>
                <span className="tag">Proptech / govtech · 2024–25</span>
              </div>
              <CaseLink slug="vizzion" label="Vizzion case study" />
            </div>
            <div>
              <h3 id="vizzion-title" className="wtitle">
                {vizzion.title}
              </h3>
              <p className="wsub">Data analysis for real-estate developers and city governments.</p>
            </div>
            <p className="wbody">{vizzion.summary}</p>
            <ul className="ticks">
              <li>Land-use analysis based on space syntax, with 70+ indicators per site</li>
              <li>Wrote two municipal master plans; one won a national award</li>
              <li>Found a zoning clause that saved a housing development over R$75M in taxes</li>
            </ul>
          </article>

          <figure className="card dark wcard s5 reveal" aria-labelledby="pipe-cap">
            <div className="card-top">
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <span className="label mono">{platform.title}</span>
                <span id="pipe-cap" style={{ fontSize: 15, fontWeight: 600, letterSpacing: "-0.01em" }}>
                  {platform.summary}
                </span>
              </div>
              <span className="tag mono" style={{ fontSize: 11.5 }}>
                GCP
              </span>
            </div>
            <div className="pipe">
              <span className="rail" aria-hidden="true">
                <span className="pkt" />
              </span>
              <ol className="plist">
                {PIPELINE.map((node) => (
                  <li key={node.i} className="pnode">
                    <span className="i mono">{node.i}</span>
                    <span style={{ minWidth: 0 }}>
                      <span className="pt" style={{ display: "block" }}>
                        {node.t}
                      </span>
                      <span className="pm mono" style={{ display: "block" }}>
                        {node.m}
                      </span>
                    </span>
                  </li>
                ))}
              </ol>
            </div>
            <div className="metrics two">
              <div className="mt">
                <span className="mv">100+</span>
                <span className="ml">real-estate and government data APIs integrated</span>
              </div>
              <div className="mt">
                <span className="mv">3rd</span>
                <span className="ml">place nationally, PropVentures Lab by Brognoli</span>
              </div>
            </div>
          </figure>

          <article className="card lift wcard s6 reveal" aria-labelledby="loopia-title">
            <figure
              className="viz"
              aria-label="Loopia architecture: Nuvemshop, Magazord and Loja Integrada feed an AI agent that serves customers on WhatsApp, observed with Langfuse."
            >
              <div className="hub" aria-hidden="true">
                <div className="hubrow">
                  {["Nuvemshop", "Magazord", "Loja Integrada"].map((name) => (
                    <span key={name} className="hchip">
                      <span className="sync" />
                      {name}
                    </span>
                  ))}
                </div>
                <span className="vline">
                  <span className="vpkt" />
                </span>
                <div className="agent">
                  <span className="ic">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M3 12h4l2.5-6 5 12 2.5-6H21" />
                    </svg>
                  </span>
                  <span style={{ display: "flex", flexDirection: "column" }}>
                    <span className="a1">AI agent</span>
                    <span className="a2 mono">hybrid index · guardrails</span>
                  </span>
                </div>
                <span className="vline">
                  <span className="vpkt d2" />
                </span>
                <div className="hubrow">
                  <span className="hchip">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M21 12a8.5 8.5 0 0 1-12.6 7.4L3 21l1.6-5.2A8.5 8.5 0 1 1 21 12Z" />
                    </svg>
                    WhatsApp · customers
                  </span>
                </div>
                <div className="obs mono">LANGFUSE · TRACES · EVALS · HALLUCINATION CHECKS</div>
              </div>
            </figure>
            <div className="card-top">
              <div className="tagrow">
                <span className="tag acc">May — Oct 2026</span>
                <span className="tag">Software engineer · AI agents</span>
              </div>
              <CaseLink slug="loopia" label="Loopia case study" />
            </div>
            <h3 id="loopia-title" className="wtitle md">
              {loopia.title}
            </h3>
            <p className="wbody">{loopia.summary}</p>
            <ul className="ticks">
              <li>Set up Langfuse for tracing and evals, and built hallucination checks for the agents</li>
              <li>Helped design the hybrid (dense + sparse) index behind product search and recommendations</li>
              <li>Added interactive WhatsApp messages, which helped raise the agent's conversion rate</li>
            </ul>
            <p className="nda mono" style={{ marginTop: "auto" }}>
              METRICS UNDER NDA
            </p>
          </article>

          <article className="card lift wcard s6 reveal" aria-labelledby="rhye-title">
            <figure className="viz" aria-label="Rhye screening flow: resume, parse, retrieve, score fit and feedback, ending in an evaluated fit result.">
              <div style={{ width: "100%", display: "flex", flexDirection: "column", alignItems: "center" }} aria-hidden="true">
                <div className="mflow">
                  {FLOW.map((step, index) => (
                    <FlowStep key={step} step={step} index={index} />
                  ))}
                </div>
                <div className="fitrow">
                  <span className="mono" style={{ fontSize: 11, letterSpacing: "0.1em", color: "#A3AAB5" }}>
                    FIT
                  </span>
                  <span className="fittrack">
                    <span className="fitbar" />
                  </span>
                  <span className="mono fitok">eval ✓</span>
                </div>
              </div>
            </figure>
            <div className="card-top">
              <div className="tagrow">
                <span className="tag acc">Side project</span>
                <span className="tag">
                  <span className="live" aria-hidden="true" />
                  In progress
                </span>
              </div>
              <CaseLink slug="rhye" label="Rhye case study" />
            </div>
            <h3 id="rhye-title" className="wtitle md">
              {rhye.title}
            </h3>
            <p className="wbody">{rhye.summary}</p>
            <ul className="ticks">
              <li>LangGraph workflows behind a FastAPI backend</li>
              <li>Multi-tenant vector search on Qdrant with hybrid retrieval</li>
              <li>I use it to try agent techniques and post what I learn on LinkedIn</li>
            </ul>
            <p className="nda mono" style={{ marginTop: "auto" }}>
              LANGGRAPH · FASTAPI · QDRANT
            </p>
          </article>
        </div>
      </div>
    </section>
  );
}

function FlowStep({ step, index }: { step: string; index: number }) {
  return (
    <>
      {index > 0 && (
        <span className="mfa">
          <ArrowRight />
        </span>
      )}
      <span className={index === 0 ? "mf" : `mf m${index + 1}`}>
        <span className="mi mono">{String(index + 1).padStart(2, "0")}</span>
        {step}
      </span>
    </>
  );
}
