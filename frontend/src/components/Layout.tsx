import { useEffect, type CSSProperties, type ReactNode } from "react";
import { useI18n } from "../i18n";
import { AssistantDot } from "./AssistantDot";
import { Mark } from "./Icons";
import { Nav } from "./Nav";

const ACCENT = "#2E4BFF";

interface LayoutProps {
  /** True on the home page: section links are plain #hash anchors there. */
  onHome: boolean;
  /** The browser tab title for this page. */
  title: string;
  children: ReactNode;
}

/** The `.ekb` page shell from the handoff: starfield, slab, sticky nav, footer. */
export function Layout({ onHome, title, children }: LayoutProps) {
  const { t } = useI18n();

  useEffect(() => {
    document.title = title;
    document.documentElement.lang = t.htmlLang;
  }, [title, t.htmlLang]);

  return (
    <div className="ekb" style={{ "--accent": ACCENT } as CSSProperties}>
      <a className="skip" href="#main">
        {t.layout.skip}
      </a>
      <div className="slab">
        <Nav onHome={onHome} />
        <main id="main">{children}</main>
        <footer className="wrap foot">
          <div className="foot-mark">
            <Mark small />
            <p className="foot-copy">© 2026 Erick Kopak Bonfim</p>
          </div>
          <p className="mono foot-note">{t.layout.madeBy}</p>
          {/* Every page has a #top, so this stays a same-page anchor. */}
          <a className="pillbtn pill-line sm" href="#top">
            {t.layout.backToTop}
          </a>
        </footer>
      </div>
      <AssistantDot />
    </div>
  );
}
