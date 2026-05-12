// New frontend shell — SideNav + TopStrip + MarketTicker + main content.
// Replaces the old Layout component.

import { useEffect, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import SideNav from "./SideNav";
import TopStrip from "./TopStrip";
import MarketTicker from "./MarketTicker";
import StatusRail from "./StatusRail";

// Phase 15h.5 — route-aware Market Tape slot mode.
// Replaces the Phase 15b3 hard hide-on-/overview rule. The slot
// itself currently renders an honest disabled state (no provider
// integrated; see docs/research/MARKET_QUOTE_PROVIDER_EVAL.md), but
// the route → mode map is preserved so that when a real delayed-
// quote provider lands, the slot density is already correct on every
// surface with no further routing change.
//
// Density rules (per Phase 15h.5 brief):
//   compact — /, /overview, /risk, /signal-lab, /decisions,
//             /strategies (executive context surfaces; tape sits
//             below TopStrip without competing with the page's
//             biggest answer)
//   full    — /action-queue, /events, /portfolio*, /options/*
//             (trade-flow surfaces where the tape is one of the
//             primary scanning surfaces)
//   null    — /ops, /research, /alpha-lab (deep work surfaces;
//             tape would interrupt focus)
//   default — compact (least-surprise for any unmapped route)
type TickerMode = "full" | "compact" | null;

function tickerModeForRoute(pathname: string): TickerMode {
  if (pathname === "/ops"
      || pathname.startsWith("/research")
      || pathname.startsWith("/alpha-lab")) {
    return null;
  }
  if (pathname === "/action-queue"
      || pathname === "/events"
      || pathname.startsWith("/portfolio")
      || pathname.startsWith("/options")) {
    return "full";
  }
  return "compact";
}

export default function Shell() {
  // Phase 14f-A — mobile drawer state. SideNav becomes a slide-in
  // overlay at <=768; on desktop it remains a static sibling. State
  // lives in Shell so the hamburger toggle in TopStrip can flip it
  // and the overlay can dismiss it.
  const [navOpen, setNavOpen] = useState(false);
  const { pathname } = useLocation();

  // Auto-close drawer on route change (user navigated; surface should
  // not stay covered by the overlay).
  useEffect(() => { setNavOpen(false); }, [pathname]);

  // Esc closes drawer.
  useEffect(() => {
    if (!navOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setNavOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [navOpen]);

  // Body scroll lock while drawer open (so background page doesn't
  // scroll behind the overlay on iOS).
  useEffect(() => {
    if (navOpen) {
      const prev = document.body.style.overflow;
      document.body.style.overflow = "hidden";
      return () => { document.body.style.overflow = prev; };
    }
  }, [navOpen]);

  return (
    <div className="shell-root flex min-h-screen"
         data-mobile-nav-open={navOpen ? "true" : "false"}
         style={{ background: "var(--bg)" }}>
      {/* WCAG 2.4.1 — skip-link to main content. Visually hidden until focused. */}
      <a href="#main-content" className="skip-link">
        Skip to main content
      </a>

      {/* Hamburger — visible only at <=768 via CSS. Toggles SideNav drawer. */}
      <button
        type="button"
        className="shell-nav-toggle"
        aria-label={navOpen ? "Close navigation" : "Open navigation"}
        aria-expanded={navOpen}
        aria-controls="shell-sidenav"
        onClick={() => setNavOpen(o => !o)}
      >
        <span className="shell-nav-toggle-bars" aria-hidden="true">
          <span /><span /><span />
        </span>
      </button>

      {/* Overlay backdrop — only rendered when drawer is open on mobile. */}
      {navOpen && (
        <div
          className="shell-nav-overlay"
          onClick={() => setNavOpen(false)}
          aria-hidden="true"
        />
      )}

      <SideNav onNavigate={() => setNavOpen(false)} />

      <div className="flex-1 flex flex-col min-w-0">
        <div className="sticky top-0 z-20">
          <TopStrip />
          {/* Phase 15h.5 — route-aware Market Tape slot. Map lives in
              tickerModeForRoute. Slot currently renders an honest
              disabled state (no provider integrated). */}
          {(() => {
            const tm = tickerModeForRoute(pathname);
            return tm === null ? null : <MarketTicker mode={tm} />;
          })()}
          <StatusRail />
        </div>
        <main id="main-content" className="flex-1 overflow-auto">
          <Outlet />
        </main>
        {/* Phase 11K.1 — persistent global guardrail footer */}
        <footer className="shell-footer border-t border-b1 px-4 py-2 text-[11px] text-fg-3
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
