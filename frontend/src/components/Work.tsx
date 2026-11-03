import type { Entry } from "../api/types";
import type { WorkSlug } from "../content/fallback";
import { useI18n } from "../i18n";
import { workText } from "../lib/derive";
import { buildCells } from "../lib/parcels";
import { Link } from "./Link";
import { ArrowRight, ArrowUpRight } from "./Icons";

const CELLS = buildCells();

function CaseLink({ to, label }: { to: string; label: string }) {
  return (
    <Link className="arrowbtn" to={to} aria-label={label}>
      <ArrowUpRight />
    </Link>
  );
}

export type WorkEntries = Partial<Record<WorkSlug, Entry | null>>;

export function Work({ entries }: { entries: WorkEntries }) {
  const { lang, t, to } = useI18n();
  const w = t.work;
  const vizzion = workText("vizzion", entries.vizzion, lang);
  const platform = workText("vizzion-data-platform", entries["vizzion-data-platform"], lang);
  const loopia = workText("loopia", entries.loopia, lang);
  const rhye = workText("rhye", entries.rhye, lang);
  const silpi = workText("silpi", entries.silpi, lang);
  const reuni = workText("reuni-challenge", entries["reuni-challenge"], lang);

  return (
    <section id="work" className="sec" aria-labelledby="work-title">
      <div className="wrap">
        <div className="shead reveal">
          <div className="l">
            <p className="eyebrow mono">
              <span className="n">01</span>
              {w.eyebrow}
            </p>
            <h2 id="work-title" className="h2">
              {w.title}
            </h2>
          </div>
          <p className="r">{w.intro}</p>
        </div>

        <div className="bento">
          <article className="card lift wcard s7 reveal" aria-labelledby="vizzion-title">
            <figure className="viz dkv" aria-label={w.vizzion.mapLabel}>
              <div style={{ width: "100%", display: "flex", flexDirection: "column", alignItems: "center" }} aria-hidden="true">
                <div className="parcels">
                  {CELLS.map((cell, index) => (
                    <span key={index} className={cell.cls} style={cell.style} />
                  ))}
                </div>
                <div className="legend mono">
                  <span>
                    <i style={{ background: "var(--acc-hi)" }} />
                    {w.vizzion.legend[0]}
                  </span>
                  <span>
                    <i style={{ background: "color-mix(in srgb, var(--accent) 42%, #1B1F26)" }} />
                    {w.vizzion.legend[1]}
                  </span>
                  <span>
                    <i style={{ background: "#2B313B" }} />
                    {w.vizzion.legend[2]}
                  </span>
                </div>
              </div>
            </figure>
            <div className="card-top">
              <div className="tagrow">
                <span className="tag acc">{w.vizzion.role}</span>
                <span className="tag">{w.vizzion.sector}</span>
              </div>
              <CaseLink to={to("/work/vizzion")} label={w.caseOf("Vizzion")} />
            </div>
            <div>
              <h3 id="vizzion-title" className="wtitle">
                {vizzion.title}
              </h3>
              <p className="wsub">{w.vizzion.sub}</p>
            </div>
            <p className="wbody">{vizzion.summary}</p>
            <ul className="ticks">
              {w.vizzion.ticks.map((tick) => (
                <li key={tick}>{tick}</li>
              ))}
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
                {w.platform.pipeline.map((node) => (
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
              {w.platform.metrics.map((metric) => (
                <div key={metric.v} className="mt">
                  <span className="mv">{metric.v}</span>
                  <span className="ml">{metric.l}</span>
                </div>
              ))}
            </div>
          </figure>

          <article className="card lift wcard s6 reveal" aria-labelledby="loopia-title">
            <figure
              className="viz"
              aria-label={w.loopia.diagram}
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
                    <span className="a1">{w.loopia.agent}</span>
                    <span className="a2 mono">{w.loopia.agentSub}</span>
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
                    {w.loopia.channel}
                  </span>
                </div>
                <div className="obs mono">{w.loopia.observability}</div>
              </div>
            </figure>
            <div className="card-top">
              <div className="tagrow">
                <span className="tag acc">{w.loopia.period}</span>
                <span className="tag">{w.loopia.role}</span>
              </div>
              <CaseLink to={to("/work/loopia")} label={w.caseOf("Loopia")} />
            </div>
            <h3 id="loopia-title" className="wtitle md">
              {loopia.title}
            </h3>
            <p className="wbody">{loopia.summary}</p>
            <ul className="ticks">
              {w.loopia.ticks.map((tick) => (
                <li key={tick}>{tick}</li>
              ))}
            </ul>
            <p className="nda mono" style={{ marginTop: "auto" }}>
              {w.loopia.nda}
            </p>
          </article>

          <article className="card lift wcard s6 reveal" aria-labelledby="rhye-title">
            <figure className="viz" aria-label={w.rhye.diagram}>
              <div style={{ width: "100%", display: "flex", flexDirection: "column", alignItems: "center" }} aria-hidden="true">
                <div className="mflow">
                  {w.rhye.flow.map((step, index) => (
                    <FlowStep key={step} step={step} index={index} />
                  ))}
                </div>
                <div className="fitrow">
                  <span className="mono" style={{ fontSize: 11, letterSpacing: "0.1em", color: "#A3AAB5" }}>
                    {w.rhye.fit}
                  </span>
                  <span className="fittrack">
                    <span className="fitbar" />
                  </span>
                  <span className="mono fitok">{w.rhye.done}</span>
                </div>
              </div>
            </figure>
            <div className="card-top">
              <div className="tagrow">
                <span className="tag acc">{w.rhye.role}</span>
                <span className="tag">
                  <span className="live" aria-hidden="true" />
                  {w.rhye.state}
                </span>
              </div>
              <CaseLink to={to("/work/rhye")} label={w.caseOf("Rhye")} />
            </div>
            <h3 id="rhye-title" className="wtitle md">
              {rhye.title}
            </h3>
            <p className="wbody">{rhye.summary}</p>
            <ul className="ticks">
              {w.rhye.ticks.map((tick) => (
                <li key={tick}>{tick}</li>
              ))}
            </ul>
            <p className="nda mono" style={{ marginTop: "auto" }}>
              {w.rhye.footer}
            </p>
          </article>

          <article className="card lift wcard s6 reveal" aria-labelledby="silpi-title">
            <figure className="viz" aria-label={w.silpi.diagram}>
              <div className="upg" aria-hidden="true">
                <span className="upg-pill old mono">{w.silpi.before}</span>
                <span className="upg-track">
                  <span className="upg-fill" />
                </span>
                <span className="upg-pill new mono">{w.silpi.after}</span>
              </div>
            </figure>
            <div className="card-top">
              <div className="tagrow">
                <span className="tag acc">{w.silpi.period}</span>
                <span className="tag">{w.silpi.role}</span>
              </div>
              <CaseLink to={to("/work/silpi")} label={w.caseOf("SILPI")} />
            </div>
            <h3 id="silpi-title" className="wtitle md">
              {silpi.title}
            </h3>
            <p className="wbody">{silpi.summary}</p>
            <ul className="ticks">
              {w.silpi.ticks.map((tick) => (
                <li key={tick}>{tick}</li>
              ))}
            </ul>
            <p className="nda mono" style={{ marginTop: "auto" }}>
              {w.silpi.footer}
            </p>
          </article>

          <article className="card lift wcard s6 reveal" aria-labelledby="reuni-title">
            <figure className="viz dkv" aria-label={w.reuni.diagram}>
              <div className="rstats" aria-hidden="true">
                {w.reuni.stats.map((stat) => (
                  <span key={stat.l} className="rstat">
                    <span className="rv">{stat.v}</span>
                    <span className="rl mono">{stat.l}</span>
                  </span>
                ))}
              </div>
            </figure>
            <div className="card-top">
              <div className="tagrow">
                <span className="tag acc">{w.reuni.period}</span>
                <span className="tag">{w.reuni.role}</span>
              </div>
              <CaseLink to={to("/work/reuni-challenge")} label={w.caseOf("Reuni Challenge")} />
            </div>
            <h3 id="reuni-title" className="wtitle md">
              {reuni.title}
            </h3>
            <p className="wbody">{reuni.summary}</p>
            <p className="nda mono" style={{ marginTop: "auto" }}>
              {w.reuni.footer}
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
