import type { Attachment, Availability } from "../api/types";
import { EMAIL, GITHUB, LINKEDIN } from "../content/fallback";
import { availabilityText, isOpen } from "../lib/derive";
import { ArrowUpRight, Check, Download } from "./Icons";

const STEPS = [
  { n: "01", t: "Sold apartments", s: "Grupo Mello · 2019–23" },
  { n: "02", t: "Hackathon to startup", s: "ConEng · 2023" },
  { n: "03", t: "CTO", s: "Vizzion · 2024–25" },
  { n: "04", t: "Software engineer", s: "SILPI · 2024–26" },
  { n: "05", t: "AI agents", s: "Loopia · 2026" },
];

const TRACE = [
  { cls: "t1", tg: "├", t: "parse_resume", chip: null, bar: "", left: "0%", width: "14.1%", dur: "0.34s" },
  { cls: "t2", tg: "├", t: "retrieve.hybrid", chip: null, bar: "", left: "14.1%", width: "12%", dur: "0.29s" },
  { cls: "t3", tg: "├", t: "score_fit", chip: "llm", bar: "acc", left: "26.1%", width: "38.2%", dur: "0.92s" },
  { cls: "t4", tg: "├", t: "guard.grounding", chip: "pass", bar: "okc", left: "64.3%", width: "7.9%", dur: "0.19s" },
  { cls: "t5", tg: "├", t: "eval.rubric", chip: "pass", bar: "okc", left: "72.2%", width: "11.6%", dur: "0.28s" },
  { cls: "t6", tg: "└", t: "draft_feedback", chip: "llm", bar: "acc", left: "83.8%", width: "16.2%", dur: "0.39s" },
];

interface HeroProps {
  availability: Availability | null;
  cv: Attachment | null;
}

export function Hero({ availability, cv }: HeroProps) {
  return (
    <section id="top" aria-labelledby="hero-title">
      <div className="wrap hero">
        <div className="h-head">
          <div className="fade" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 10 }}>
            <span className="pill">
              {isOpen(availability) && <span className="live" aria-hidden="true" />}
              {availabilityText(availability)}
            </span>
            <span className="mono" style={{ fontSize: 11.5, letterSpacing: "0.08em", color: "#5F6670" }}>
              BRUSQUE, SC · REMOTE OR SÃO PAULO
            </span>
          </div>
          <h1 id="hero-title" className="h1">
            <span className="ln">
              <span className="in">I used to sell</span>
            </span>{" "}
            {/* The spaces between lines are what screen readers hear: the lines are blocks. */}
            <span className="ln">
              <span className="in">
                apartments.{" "}
                <span className="inl face" aria-hidden="true">
                  <span className="mono">EK</span>
                  <i />
                </span>
              </span>
            </span>{" "}
            <span className="ln">
              <span className="in">Now I build</span>
            </span>{" "}
            <span className="ln">
              <span className="in">
                <span className="hl">AI agents.</span>{" "}
                <span className="inl tick" aria-hidden="true">
                  <span className="d" />
                  <span className="win mono">
                    <span className="lst">
                      <span>planning…</span>
                      <span>retrieving…</span>
                      <span>evaluating…</span>
                      <span>passed ✓</span>
                      <span>planning…</span>
                    </span>
                  </span>
                </span>
              </span>
            </span>
          </h1>
          <p
            className="fade f1"
            style={{ maxWidth: 580, fontSize: "clamp(16px, 1.3cqi, 18px)", lineHeight: 1.7, color: "#4A505A", textWrap: "pretty" }}
          >
            I'm Erick Kopak Bonfim, a software engineer who most recently built LLM agents at Loopia that talk to
            e-commerce customers on WhatsApp. Between the apartments and the agents, I co-founded two startups and was
            CTO of both.
          </p>
          <div className="fade f2" style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
            <a className="pillbtn pill-dark" href={`mailto:${EMAIL}`}>
              Email me
              <span className="ab">
                <ArrowUpRight />
              </span>
            </a>
            <a className="pillbtn pill-line" href="#work">
              See work
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
            {cv && (
              <a className="tlink" href={cv.url} download={cv.filename}>
                CV (PDF)
                <Download />
              </a>
            )}
          </div>
        </div>

        <figure className="card dark h-core fade f4" aria-labelledby="core-cap">
          <div className="floor" aria-hidden="true" />
          <div className="card-top">
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <span className="label mono">Agent core</span>
              <span style={{ fontSize: 15, fontWeight: 600, letterSpacing: "-0.01em" }}>Agents, retrieval, evals</span>
            </div>
            <a className="arrowbtn" href="#approach" aria-label="How I work on agents">
              <ArrowUpRight />
            </a>
          </div>
          <div className="gyro" aria-hidden="true">
            <div className="scene">
              <div className="halo" />
              {["o1", "o2", "o3"].map((o) => (
                <div key={o} className={`orbit ${o}`}>
                  <div className="ring">
                    <span className="sat" />
                  </div>
                </div>
              ))}
              <div className="orb" />
            </div>
            <div className="gchip g1">
              <span className="k mono">graph.invoke</span>
              <span className="v">
                <Check size={14} strokeWidth={2.6} stroke="#5BE3A0" />
                2.41s
              </span>
            </div>
            <div className="gchip g2">
              <span className="k mono">evals</span>
              <span className="v">2 / 2 passed</span>
            </div>
            <div className="gchip g3">
              <span className="k mono">retrieval</span>
              <span className="v">hybrid · dense + sparse</span>
            </div>
          </div>
          <figcaption id="core-cap" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
            <span className="mono" style={{ fontSize: 12, color: "#A3AAB5" }}>
              <span style={{ color: "var(--acc-hi)" }}>//</span> pure CSS. no WebGL was harmed.
            </span>
            <span className="sr">
              Decorative animation: an orb with three orbiting rings, representing an agent core, with labels for a
              passed graph run, passing evals and hybrid retrieval.
            </span>
          </figcaption>
        </figure>

        <figure className="card h-trace fade f5" aria-labelledby="trace-cap">
          <div className="card-top">
            <div style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 0 }}>
              <span className="label mono">Trace</span>
              <span className="mono" style={{ fontSize: 13, fontWeight: 500, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                rhye.screening_graph
              </span>
            </div>
            <span className="status mono" aria-hidden="true">
              <span className="stc st-run">
                <i />
                running
              </span>
              <span className="stc st-pass">
                <Check />
                passed
              </span>
            </span>
          </div>
          <div className="tw mono" aria-hidden="true">
            <div className="tr thead">
              <span>SPAN</span>
              <span>TIMELINE</span>
              <span style={{ textAlign: "right" }}>DUR</span>
            </div>
            <div className="tr t0">
              <span className="nm">
                <span className="t">graph.invoke</span>
              </span>
              <span className="wf">
                <span className="bar root" style={{ left: "0%", width: "100%" }} />
              </span>
              <span className="dur">2.41s</span>
            </div>
            {TRACE.map((row) => (
              <div key={row.cls} className={`tr ${row.cls}`}>
                <span className="nm">
                  <span className="tg">{row.tg}</span>
                  <span className="t">{row.t}</span>
                  {row.chip && <span className={row.chip === "pass" ? "tchip ok" : "tchip"}>{row.chip}</span>}
                </span>
                <span className="wf">
                  <span className={row.bar ? `bar ${row.bar}` : "bar"} style={{ left: row.left, width: row.width }} />
                </span>
                <span className="dur">{row.dur}</span>
              </div>
            ))}
            <div className="phwrap">
              <span />
              <span className="phcell">
                <span className="phmove">
                  <span className="ph" />
                </span>
              </span>
              <span />
            </div>
          </div>
          <figcaption id="trace-cap" className="mono" style={{ fontSize: 12, lineHeight: 1.6, color: "#4A505A" }}>
            <span style={{ color: "var(--accent)" }}>//</span> sample trace, fake numbers. the habit of tracing every step
            is real.
          </figcaption>
        </figure>

        <article className="card h-path fade f6" aria-labelledby="path-title">
          <div className="card-top">
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <span className="label mono">Career</span>
              <h2 id="path-title" style={{ fontSize: 15, fontWeight: 600, letterSpacing: "-0.01em" }}>
                How I got here
              </h2>
            </div>
            <a className="arrowbtn" href="#experience" aria-label="See full experience">
              <ArrowUpRight />
            </a>
          </div>
          <ol className="steps">
            {STEPS.map((step) => (
              <li key={step.n} className="step">
                <span className="n mono">{step.n}</span>
                <span className="tx">
                  <span className="t">{step.t}</span>
                  <span className="s">{step.s}</span>
                </span>
              </li>
            ))}
          </ol>
        </article>
      </div>
    </section>
  );
}
