import { useState, type AnchorHTMLAttributes } from "react";
import type { Attachment } from "../api/types";
import { usePathname } from "../lib/router";
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

export const MCP_PATH = "/mcp";

interface NavProps {
  /** "" on the home page (plain #hash anchors), "/" elsewhere (back to home). */
  base: Base;
  cv: Attachment | null;
}

// Layout lives in classes (app.css), never in inline styles: an inline `display`
// beats the container queries that hide the desktop links on small screens.
export function Nav({ base, cv }: NavProps) {
  const [open, setOpen] = useState(false);
  const close = () => setOpen(false);
  const onMcp = usePathname().replace(/\/+$/, "") === MCP_PATH;
  const current = onMcp ? "page" : undefined;

  return (
    <div className="navwrap">
      <div className="wrap">
        <header className="navbar">
          <SectionAnchor className="nav-home" base={base} id="top" aria-label="Erick Kopak Bonfim, back to top">
            <Mark />
            <span className="nav-name">
              <span className="nav-name-title">Erick Kopak Bonfim</span>
              <small className="mono nav-name-sub">AI · SOFTWARE ENGINEER</small>
            </span>
          </SectionAnchor>
          <nav className="navlinks" aria-label="Primary">
            {SECTIONS.map((s) => (
              <SectionAnchor key={s.id} className="navlink" base={base} id={s.id}>
                {s.label}
              </SectionAnchor>
            ))}
            <Link className="navlink nav-mcp" to={MCP_PATH} aria-current={current}>
              MCP
            </Link>
          </nav>
          <div className="nav-actions">
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
                <span className="mono mlink-n">{s.n}</span>
              </SectionAnchor>
            ))}
            <Link className="mlink" to={MCP_PATH} aria-current={current} onClick={close}>
              MCP server
              <span className="mono mlink-n">05</span>
            </Link>
            <div className="mmenu-actions">
              <SectionAnchor className="pillbtn pill-dark" base={base} id="contact" onClick={close}>
                Contact
                <span className="ab">
                  <ArrowUpRight />
                </span>
              </SectionAnchor>
              {cv && (
                <a className="pillbtn pill-line" href={cv.url} download={cv.filename} onClick={close}>
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
