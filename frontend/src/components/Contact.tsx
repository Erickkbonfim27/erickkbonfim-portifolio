import { useEffect, useRef, useState } from "react";
import type { Attachment } from "../api/types";
import { EMAIL, GITHUB, LINKEDIN } from "../content/fallback";
import { ContactForm } from "./ContactForm";
import { ArrowUpRight } from "./Icons";

const LANGUAGES = ["PT · native", "EN · full professional", "IT · elementary", "RU · limited working"];

export function Contact({ cv }: { cv: Attachment | null }) {
  const [copied, setCopied] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => () => clearTimeout(timer.current), []);

  const copyEmail = () => {
    // The visible label changes even when the Clipboard API is blocked, as in the handoff;
    // the mailto link above stays the fallback.
    navigator.clipboard?.writeText(EMAIL).catch(() => undefined);
    setCopied(true);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setCopied(false), 2200);
  };

  return (
    <section id="contact" className="sec" aria-labelledby="contact-title">
      <div className="wrap">
        <div className="card dark contact reveal">
          <div className="floor" aria-hidden="true" />
          <h2
            id="contact-title"
            className="eyebrow mono"
            style={{ fontWeight: 500, color: "#EEF0F3", borderColor: "rgba(255,255,255,.22)", background: "rgba(255,255,255,.04)" }}
          >
            <span className="n" style={{ background: "#fff", color: "#0D0F12" }}>
              06
            </span>
            Contact
          </h2>
          <p className="hxl" style={{ fontSize: "clamp(20px, 4.8cqi, 68px)" }}>
            <a className="mailbig" href={`mailto:${EMAIL}`}>
              {EMAIL}{" "}
              <span className="inl orbbtn" aria-hidden="true">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M7 17 17 7" />
                  <path d="M8 7h9v9" />
                </svg>
              </span>
            </a>
          </p>
          <p style={{ maxWidth: 620, fontSize: "clamp(16px, 1.3cqi, 18px)", lineHeight: 1.7, color: "#A3AAB5" }}>
            I'm looking for AI Engineer or LLM Engineer roles, remote or in São Paulo. If you're building with agents,
            I'd like to hear about it.
          </p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
            <a className="pillbtn pill-light" href={LINKEDIN}>
              LinkedIn
              <span className="ab">
                <ArrowUpRight />
              </span>
            </a>
            <a className="pillbtn pill-ghost" href={GITHUB}>
              GitHub
            </a>
            {cv && (
              <a id="cv" className="pillbtn pill-ghost" href={cv.url} download={cv.filename}>
                Download CV
              </a>
            )}
          </div>
          <ContactForm />
          <div className="emailrow">
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, flex: "1 1 auto" }}>
              {LANGUAGES.map((lang) => (
                <span key={lang} className="tag mono" style={{ fontSize: 12 }}>
                  {lang}
                </span>
              ))}
            </div>
            <button className="copy" type="button" onClick={copyEmail}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <rect x="9" y="9" width="11" height="11" rx="2.5" />
                <path d="M5 15V6a2 2 0 0 1 2-2h8" />
              </svg>
              {copied ? <span style={{ color: "#5BE3A0" }}>Copied</span> : <span>Copy email</span>}
            </button>
            <span className="sr" aria-live="polite">
              {copied ? "Email copied to clipboard" : ""}
            </span>
          </div>
        </div>
      </div>
    </section>
  );
}
