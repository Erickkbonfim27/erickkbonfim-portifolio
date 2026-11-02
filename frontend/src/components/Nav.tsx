import { useState, type AnchorHTMLAttributes } from "react";
import type { Attachment } from "../api/types";
import { Link } from "./Link";
import { ArrowUpRight, Mark } from "./Icons";

export type Base = "" | "/";

type SectionAnchorProps = AnchorHTMLAttributes<HTMLAnchorElement> & { base: Base; id: string };

/** A link to a home-page section: a plain #hash on the home page, an in-app link elsewhere. */
export function SectionAnchor({ base, id, ...rest }: SectionAnchorProps) {
  return base ? <Link to={`/#${id}`} {...rest} /> : <a href={`#${id}`} {...rest} />;
}

const SECTIONS = [
  { id: "work", label: "Work", n: "01" },
  { id: "approach", label: "Approach", n: "02" },
  { id: "experience", label: "Experience", n: "03" },
  { id: "stack", label: "Stack", n: "04" },
];

interface NavProps {
  /** "" on the home page (plain #hash anchors), "/" elsewhere (back to home). */
  base: Base;
  cv: Attachment | null;
}

export function Nav({ base, cv }: NavProps) {
  const [open, setOpen] = useState(false);
  const close = () => setOpen(false);

  return (
    <div className="navwrap">
      <div className="wrap">
        <header className="navbar">
          <SectionAnchor
            base={base} id="top"
            aria-label="Erick Kopak Bonfim, back to top"
            style={{ display: "flex", alignItems: "center", gap: 12, minHeight: 44, minWidth: 0 }}
          >
            <Mark />
            <span className="nav-name" style={{ display: "flex", flexDirection: "column", lineHeight: 1.2, minWidth: 0 }}>
              <span style={{ fontWeight: 600, fontSize: 14, letterSpacing: "-0.01em", whiteSpace: "nowrap" }}>
                Erick Kopak Bonfim
              </span>
              <small className="mono" style={{ fontSize: 10.5, color: "#5F6670", letterSpacing: "0.08em", whiteSpace: "nowrap" }}>
                AI · SOFTWARE ENGINEER
              </small>
            </span>
          </SectionAnchor>
          <nav className="navlinks" aria-label="Primary" style={{ display: "flex", alignItems: "center", gap: 2 }}>
            {SECTIONS.map((s) => (
              <SectionAnchor key={s.id} className="navlink" base={base} id={s.id}>
                {s.label}
              </SectionAnchor>
            ))}
          </nav>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            {cv && (
              <a className="pillbtn pill-line sm nav-cv" href={cv.url} download={cv.filename}>
                Download CV
              </a>
            )}
            <SectionAnchor className="pillbtn pill-dark sm nav-cta" base={base} id="contact">
              Contact
              <span className="ab">
                <ArrowUpRight size={15} />
              </span>
            </SectionAnchor>
            <button
              className="menu-btn"
              type="button"
              aria-controls="mmenu"
              aria-expanded={open}
              aria-label={open ? "Close menu" : "Open menu"}
              onClick={() => setOpen(!open)}
            >
              {open ? (
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
                  <path d="M6 6l12 12" />
                  <path d="M18 6 6 18" />
                </svg>
              ) : (
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
                  <path d="M4 9h16" />
                  <path d="M4 15h16" />
                </svg>
              )}
            </button>
          </div>
        </header>
        {open && (
          <nav id="mmenu" className="mmenu" aria-label="Mobile">
            {SECTIONS.map((s) => (
              <SectionAnchor key={s.id} className="mlink" base={base} id={s.id} onClick={close}>
                {s.label}
                <span className="mono" style={{ fontSize: 12, color: "#5F6670" }}>
                  {s.n}
                </span>
              </SectionAnchor>
            ))}
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, padding: "10px 10px 6px" }}>
              <SectionAnchor
                className="pillbtn pill-dark"
                base={base} id="contact"
                onClick={close}
                style={{ flex: "1 1 auto", justifyContent: "space-between" }}
              >
                Contact
                <span className="ab">
                  <ArrowUpRight />
                </span>
              </SectionAnchor>
              {cv && (
                <a
                  className="pillbtn pill-line"
                  href={cv.url}
                  download={cv.filename}
                  onClick={close}
                  style={{ flex: "1 1 auto", justifyContent: "center" }}
                >
                  Download CV
                </a>
              )}
            </div>
          </nav>
        )}
      </div>
    </div>
  );
}
