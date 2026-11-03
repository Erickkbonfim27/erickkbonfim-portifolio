import { useState, type AnchorHTMLAttributes, type MouseEvent } from "react";
import type { Attachment } from "../api/types";
import { useI18n } from "../i18n";
import { rememberLang } from "../lib/locale";
import { localize, navigate, splitLang, usePathname } from "../lib/router";
import { setTheme, useTheme } from "../lib/theme";
import { Link } from "./Link";
import { ArrowUpRight, Mark, Moon, Sun } from "./Icons";

type SectionAnchorProps = AnchorHTMLAttributes<HTMLAnchorElement> & { onHome: boolean; id: string };

/** A link to a home-page section: a plain #hash on the home page, an in-app link elsewhere. */
export function SectionAnchor({ onHome, id, ...rest }: SectionAnchorProps) {
  const { to } = useI18n();
  return onHome ? <a href={`#${id}`} {...rest} /> : <Link to={to(`/#${id}`)} {...rest} />;
}

const SECTIONS = [
  { id: "work", n: "01" },
  { id: "approach", n: "02" },
  { id: "experience", n: "03" },
  { id: "stack", n: "04" },
] as const;

export const MCP_PATH = "/mcp";
export const INTEGRATIONS_PATH = "/integrations";

/** The same page in the other language, keeping the scroll position and the #hash. */
function LangSwitch({ onDone }: { onDone?: () => void }) {
  const { lang, t } = useI18n();
  const other = lang === "en" ? "pt" : "en";
  const href = localize(splitLang(usePathname()).path, other);
  const handle = (event: MouseEvent<HTMLAnchorElement>) => {
    rememberLang(other);
    onDone?.();
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    navigate(`${href}${window.location.hash}`, { keepScroll: true });
  };
  return (
    <a className="prefbtn mono" href={href} hrefLang={other === "pt" ? "pt-BR" : "en"} aria-label={t.nav.otherLang} onClick={handle}>
      {t.nav.otherLangShort}
    </a>
  );
}

function ThemeSwitch() {
  const { t } = useI18n();
  const theme = useTheme();
  const next = theme === "dark" ? "light" : "dark";
  return (
    <button className="prefbtn" type="button" aria-label={next === "dark" ? t.nav.toDark : t.nav.toLight} onClick={() => setTheme(next)}>
      {theme === "dark" ? <Sun /> : <Moon />}
    </button>
  );
}

interface NavProps {
  /** True on the home page: section links are plain #hash anchors there. */
  onHome: boolean;
  cv: Attachment | null;
}

// Layout lives in classes (app.css), never in inline styles: an inline `display`
// beats the container queries that hide the desktop links on small screens.
export function Nav({ onHome, cv }: NavProps) {
  const { t, to } = useI18n();
  const [open, setOpen] = useState(false);
  const close = () => setOpen(false);
  const path = splitLang(usePathname()).path.replace(/\/+$/, "");
  const current = path === MCP_PATH ? "page" : undefined;
  const onIntegrations = path === INTEGRATIONS_PATH ? "page" : undefined;

  return (
    <div className="navwrap">
      <div className="wrap">
        <header className="navbar">
          <SectionAnchor className="nav-home" onHome={onHome} id="top" aria-label={t.nav.home}>
            <Mark />
            <span className="nav-name">
              <span className="nav-name-title">Erick Kopak Bonfim</span>
              <small className="mono nav-name-sub">{t.nav.role}</small>
            </span>
          </SectionAnchor>
          <nav className="navlinks" aria-label={t.nav.primary}>
            {SECTIONS.map((s) => (
              <SectionAnchor key={s.id} className="navlink" onHome={onHome} id={s.id}>
                {t.nav.sections[s.id]}
              </SectionAnchor>
            ))}
            <Link className="navlink nav-int" to={to(INTEGRATIONS_PATH)} aria-current={onIntegrations}>
              {t.nav.integrations}
            </Link>
            <Link className="navlink nav-mcp" to={to(MCP_PATH)} aria-current={current}>
              {t.nav.mcp}
            </Link>
          </nav>
          <div className="nav-actions">
            <div className="nav-prefs">
              <LangSwitch />
              <ThemeSwitch />
            </div>
            {cv && (
              <a className="pillbtn pill-line sm nav-cv" href={cv.url} download={cv.filename}>
                {t.nav.cv}
              </a>
            )}
            <SectionAnchor className="pillbtn pill-dark sm nav-cta" onHome={onHome} id="contact">
              {t.nav.contact}
              <span className="ab">
                <ArrowUpRight size={15} />
              </span>
            </SectionAnchor>
            <button
              className="menu-btn"
              type="button"
              aria-controls="mmenu"
              aria-expanded={open}
              aria-label={open ? t.nav.closeMenu : t.nav.openMenu}
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
          <nav id="mmenu" className="mmenu" aria-label={t.nav.mobile}>
            {SECTIONS.map((s) => (
              <SectionAnchor key={s.id} className="mlink" onHome={onHome} id={s.id} onClick={close}>
                {t.nav.sections[s.id]}
                <span className="mono mlink-n">{s.n}</span>
              </SectionAnchor>
            ))}
            <Link className="mlink" to={to(INTEGRATIONS_PATH)} aria-current={onIntegrations} onClick={close}>
              {t.nav.integrations}
              <span className="mono mlink-n">05</span>
            </Link>
            <Link className="mlink" to={to(MCP_PATH)} aria-current={current} onClick={close}>
              {t.nav.mcpLong}
              <span className="mono mlink-n">06</span>
            </Link>
            <div className="mmenu-actions">
              <SectionAnchor className="pillbtn pill-dark" onHome={onHome} id="contact" onClick={close}>
                {t.nav.contact}
                <span className="ab">
                  <ArrowUpRight />
                </span>
              </SectionAnchor>
              {cv && (
                <a className="pillbtn pill-line" href={cv.url} download={cv.filename} onClick={close}>
                  {t.nav.cv}
                </a>
              )}
              <div className="mmenu-prefs" role="group" aria-label={t.nav.preferences}>
                <LangSwitch onDone={close} />
                <ThemeSwitch />
              </div>
            </div>
          </nav>
        )}
      </div>
    </div>
  );
}
