// New frontend shell — SideNav + TopStrip + MarketTicker + main content.
// Replaces the old Layout component.

import { Outlet } from "react-router-dom";
import SideNav from "./SideNav";
import TopStrip from "./TopStrip";
import MarketTicker from "./MarketTicker";
import StatusRail from "./StatusRail";

export default function Shell() {
  return (
    <div className="flex min-h-screen"
         style={{ background: "var(--bg)" }}>
      {/* WCAG 2.4.1 — skip-link to main content. Visually hidden until focused. */}
      <a href="#main-content" className="skip-link">
        Skip to main content
      </a>
      <SideNav />
      <div className="flex-1 flex flex-col min-w-0">
        <div className="sticky top-0 z-20">
          <TopStrip />
          <MarketTicker />
          <StatusRail />
        </div>
        <main id="main-content" className="flex-1 overflow-auto">
          <Outlet />
        </main>
        {/* Phase 11K.1 — persistent global guardrail footer */}
        <footer className="border-t border-b1 px-4 py-2 text-[11px] text-fg-3
                            bg-ink/95 backdrop-blur">
          This system provides AI-generated research, signals, and
          paper-trading guidance for educational and analytical use only.
          It does not provide personalized financial advice, investment
          advisory services, guaranteed outcomes, or live trade execution.
        </footer>
      </div>
    </div>
  );
}
