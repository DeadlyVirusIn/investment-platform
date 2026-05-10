// UX-9 Phase 9D — parallel Stream view at /overview?view=stream.
//
// Default /overview is UNCHANGED. This is an isolated parallel
// route for visual iteration + emotional validation BEFORE any
// full cutover. Mounts HeroCard + IntelligenceGrid using fixture
// data composed via hero_compose + grid_compose. Admin overlay
// (Ctrl+Shift+A) reveals per-card lineage tooltips.

import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import HeroCard from "@/components/copilot/HeroCard";
import IntelligenceGrid, {
  type SlotName,
} from "@/components/copilot/IntelligenceGrid";
import { composeHero } from "@/lib/copilot/hero_compose";
import { composeGrid } from "@/lib/copilot/grid_compose";


// Per-card lineage shown in the admin tooltip.
const LINEAGE: Record<SlotName | "HERO", {
  composer: string;
  template: string;
  sources: string[];
  triggers: string;
  raw: string;
}> = {
  "HERO": {
    composer: "hero_compose.composeHero()",
    template: "tech-heavy-day",
    sources: ["paper_position", "paper_summary.daily_pnl"],
    triggers: "3-of-7 in tech sector + 1 near target",
    raw: "/overview?view=working",
  },
  "OPPORTUNITY": {
    composer: "grid_compose.composeGrid().opportunity",
    template: "ideas-worth-watching",
    sources: ["candidate_idea", "recommendation"],
    triggers: "candidate.accepted=true count >= 1",
    raw: "/ideas",
  },
  "WHAT CHANGED": {
    composer: "grid_compose.composeGrid().whatChanged",
    template: "tech-rotation",
    sources: ["candidate_idea (24h delta)", "regime_snapshot"],
    triggers: "new_count_24h > 0",
    raw: "/overview?view=working",
  },
  "WATCHLIST": {
    composer: "grid_compose.composeGrid().watchlist",
    template: "warming",
    sources: ["watchlist", "factor_snapshot"],
    triggers: "≥ 2 watchlist items moved bands",
    raw: "/legacy/watchlist",
  },
  "CATALYSTS THIS WEEK": {
    composer: "grid_compose.composeGrid().catalysts",
    template: "earnings-and-macro",
    sources: ["catalyst_calendar"],
    triggers: "events in next 7 days",
    raw: "/overview?view=working",
  },
  "RISK": {
    composer: "grid_compose.composeGrid().risk",
    template: "concentration",
    sources: ["paper_position", "summary.max_drawdown_pct"],
    triggers: "sector_concentration > 0.5",
    raw: "/risk",
  },
  "YOUR DAY": {
    composer: "grid_compose.composeGrid().yourDay",
    template: "summary",
    sources: ["paper_position", "candidate_idea"],
    triggers: "always",
    raw: "/overview?view=working",
  },
};


/** YYYY-MM-DD HH:MM display for admin tooltip timestamps. */
function _stamp(): string {
  return new Date().toISOString().slice(0, 16).replace("T", " ");
}


export default function CopilotStreamView() {
  // Admin mode toggled by Ctrl+Shift+A. sessionStorage so
  // refreshing the tab keeps it on. Never persisted.
  const [adminMode, setAdminMode] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    return window.sessionStorage.getItem("ux9_admin") === "1";
  });

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.ctrlKey && e.shiftKey && (e.key === "A" || e.key === "a")) {
        e.preventDefault();
        setAdminMode(v => {
          const next = !v;
          window.sessionStorage.setItem("ux9_admin", next ? "1" : "0");
          return next;
        });
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Tooltip anchor + content
  const [tip, setTip] = useState<{
    slot: SlotName | "HERO";
    rect: DOMRect;
  } | null>(null);

  const onHeroHover = useCallback((anchor: HTMLElement) => {
    if (!adminMode) return;
    setTip({ slot: "HERO", rect: anchor.getBoundingClientRect() });
  }, [adminMode]);

  const onCardHover = useCallback((slot: SlotName, anchor: HTMLElement) => {
    if (!adminMode) return;
    setTip({ slot, rect: anchor.getBoundingClientRect() });
  }, [adminMode]);

  const onLeaveSurface = useCallback(() => {
    setTip(null);
  }, []);

  const hero = useMemo(() => composeHero({}), []);
  const grid = useMemo(() => composeGrid(), []);

  // Position the tooltip just to the right of the anchor card,
  // clamped to viewport. Falls below the anchor on narrow
  // viewports.
  const tipStyle: React.CSSProperties | null = tip ? (() => {
    const margin = 12;
    const tooltipWidth = 360;
    const viewport = typeof window !== "undefined" ? window.innerWidth : 1280;
    const rightEdge = tip.rect.right + margin + tooltipWidth;
    const fitsRight = rightEdge < viewport;
    return {
      top: tip.rect.top,
      left: fitsRight
        ? tip.rect.right + margin
        : Math.max(margin, tip.rect.left - tooltipWidth - margin),
      maxWidth: tooltipWidth,
    };
  })() : null;

  const lineage = tip ? LINEAGE[tip.slot] : null;

  return (
    <div
      className="ux9-stream"
      data-test="ux9-stream"
      onMouseLeave={onLeaveSurface}
    >
      <div
        style={{
          maxWidth: "var(--ux9-page-max)",
          margin: "0 auto",
          padding: "var(--ux9-page-pad-y) var(--ux9-page-pad-x)",
        }}
      >
        <header
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "baseline",
            marginBottom: 24,
          }}
        >
          <div>
            <h1
              style={{
                margin: 0,
                fontSize: 24,
                fontWeight: 500,
                letterSpacing: "-0.01em",
              }}
            >
              Today
            </h1>
            <p
              style={{
                margin: "6px 0 0",
                fontSize: 13,
                color: "var(--ux9-fg-tertiary)",
              }}
            >
              {new Date().toLocaleDateString("en-US", {
                weekday: "long",
                month: "long",
                day: "numeric",
              })}
            </p>
          </div>
          <Link
            to="/overview?view=working"
            style={{
              fontSize: 12,
              color: "var(--ux9-fg-tertiary)",
              textDecoration: "underline",
              textUnderlineOffset: 3,
            }}
          >
            See the working →
          </Link>
        </header>

        <HeroCard
          {...hero}
          onLineageHover={onHeroHover}
        />

        <IntelligenceGrid
          slots={grid.slots}
          onCardHover={onCardHover}
        />

        <footer
          style={{
            marginTop: 48,
            paddingTop: 24,
            borderTop: "1px solid var(--ux9-card-border)",
            fontSize: 12,
            color: "var(--ux9-fg-quaternary)",
            lineHeight: 1.5,
          }}
        >
          AI-generated research and paper-trading guidance · educational
          use only · nothing on this page places live orders · not financial advice.
        </footer>
      </div>

      {adminMode && (
        <div className="ux9-admin-banner" data-test="ux9-admin-banner">
          ADMIN MODE · Ctrl+Shift+A toggles
        </div>
      )}

      {adminMode && tip && lineage && tipStyle && (
        <aside
          className="ux9-admin-tooltip"
          style={tipStyle}
          data-test="ux9-admin-tooltip"
        >
          <h4>CARD: {tip.slot}</h4>
          <dl>
            <dt>RENDERED FROM</dt>
            <dd>{lineage.sources.join(", ")}</dd>
            <dt>COMPOSER</dt>
            <dd>{lineage.composer}</dd>
            <dt>TEMPLATE</dt>
            <dd>{lineage.template}</dd>
            <dt>TRIGGERS</dt>
            <dd>{lineage.triggers}</dd>
            <dt>LAST UPDATE</dt>
            <dd>{_stamp()} UTC</dd>
            <dt>RAW</dt>
            <dd>
              <a href={lineage.raw}>See raw data →</a>
            </dd>
          </dl>
        </aside>
      )}
    </div>
  );
}
