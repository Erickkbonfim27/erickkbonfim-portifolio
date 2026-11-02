import type { CSSProperties, ReactNode } from "react";
import type { Attachment } from "../api/types";
import { Mark } from "./Icons";
import { Nav, type Base } from "./Nav";

const ACCENT = "#2E4BFF";

interface LayoutProps {
  base: Base;
  cv: Attachment | null;
  children: ReactNode;
}

/** The `.ekb` page shell from the handoff: starfield, slab, sticky nav, footer. */
export function Layout({ base, cv, children }: LayoutProps) {
  return (
    <div className="ekb" style={{ "--accent": ACCENT } as CSSProperties}>
      <a className="skip" href="#main">
        Skip to content
      </a>
      <div className="slab">
        <Nav base={base} cv={cv} />
        <main id="main">{children}</main>
        <footer className="wrap foot">
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <Mark small />
            <p style={{ fontSize: 14, color: "#4A505A" }}>© 2026 Erick Kopak Bonfim</p>
          </div>
          <p className="mono" style={{ fontSize: 11.5, letterSpacing: "0.04em", color: "#5F6670" }}>
            Designed and coded by Erick in Brusque, SC
          </p>
          {/* Every page has a #top, so this stays a same-page anchor. */}
          <a className="pillbtn pill-line sm" href="#top">
            Back to top
          </a>
        </footer>
      </div>
    </div>
  );
}
