// UX-11 Phase 11D — parallel Interactive Copilot view at
// /overview?view=copilot.
//
// Default /overview UNCHANGED. ?view=working UNCHANGED.
// ?view=stream UNCHANGED. ?view=conviction UNCHANGED.
//
// Source of truth: docs/research/UX_11_INTERACTIVE_COPILOT.md
//
// Mounts AIReadHero + ConvictionTile rail. Drawer opens via
// URL state (?drawer=<TICKER>). PROOF fixtures via
// composeCopilotPage(). Quiet-day state via &quiet=1.

import { useMemo } from "react";
import { Link, useLocation } from "react-router-dom";

import AIReadHero from "@/components/copilot/AIReadHero";
import ConvictionTile from "@/components/copilot/ConvictionTile";
import ReasoningDrawer from "@/components/copilot/ReasoningDrawer";

import { composeCopilotPage } from "@/lib/copilot/copilot_compose";
import { useDrawerUrlState } from "@/lib/copilot/useDrawerUrlState";


export default function CopilotInteractiveView() {
  const { search } = useLocation();
  const params = new URLSearchParams(search);
  const forceQuiet = params.get("quiet") === "1";

  const data = useMemo(
    () => composeCopilotPage({ forceQuiet }),
    [forceQuiet],
  );

  const { openTicker, openDrawer, closeDrawer } = useDrawerUrlState();
  const openCard = openTicker ? data.drawerByTicker[openTicker] ?? null : null;
  const isOpen = openCard !== null;

  return (
    <div className="ux11-copilot" data-test="ux11-copilot-root">
      <div
        style={{
          maxWidth: "var(--ux11-page-max)",
          margin: "0 auto",
          padding: "var(--ux11-page-pad-y) var(--ux11-page-pad-x)",
        }}
      >
        {/* Page header */}
        <header
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "baseline",
            marginBottom: 32,
          }}
        >
          <div>
            <h1
              style={{
                margin: 0,
                fontSize: "var(--ux10-fs-h1)",
                fontWeight: 500,
                color: "var(--ux10-fg-primary)",
                letterSpacing: "-0.01em",
              }}
            >
              Today
            </h1>
            <p
              style={{
                margin: "4px 0 0",
                fontSize: "var(--ux10-fs-meta)",
                color: "var(--ux10-fg-tertiary)",
                fontFamily: "var(--ux10-font-mono)",
              }}
            >
              {data.date}
            </p>
          </div>
          <div style={{ display: "flex", gap: 16, alignItems: "baseline" }}>
            <Link
              to={forceQuiet ? "/overview?view=copilot" : "/overview?view=copilot&quiet=1"}
              style={{
                fontSize: "var(--ux10-fs-meta)",
                color: "var(--ux10-fg-tertiary)",
                textDecoration: "underline",
                textUnderlineOffset: 3,
              }}
              data-test="ux11-toggle-quiet"
            >
              {forceQuiet ? "← back to active" : "Quiet day proof"}
            </Link>
            <Link
              to="/overview?view=working"
              style={{
                fontSize: "var(--ux10-fs-meta)",
                color: "var(--ux10-fg-tertiary)",
                textDecoration: "underline",
                textUnderlineOffset: 3,
              }}
            >
              See the working →
            </Link>
          </div>
        </header>

        {/* AIReadHero */}
        <AIReadHero text={data.heroText} isQuiet={data.isQuiet} />

        {/* ConvictionTile rail */}
        {!data.isQuiet && (
          <div className="ux11-tile-rail" data-test="ux11-tile-rail">
            {data.tiles.map(tile => (
              <ConvictionTile
                key={tile.ticker}
                tile={tile}
                isActive={openTicker === tile.ticker}
                isDimmed={isOpen && openTicker !== tile.ticker}
                onClick={openDrawer}
              />
            ))}
          </div>
        )}

        {/* Footer */}
        <footer
          style={{
            marginTop: 64,
            paddingTop: 24,
            borderTop: "1px solid var(--ux10-border-card)",
            fontSize: "var(--ux10-fs-meta)",
            color: "var(--ux10-fg-tertiary)",
            lineHeight: 1.6,
          }}
        >
          AI-generated research and paper-trading guidance · educational
          use only · nothing on this page places live orders · not financial advice.
          <br />
          <span style={{ opacity: 0.6 }}>
            UX-11 Interactive Copilot · Phase 11D parallel route ·
            master at docs/research/UX_11_INTERACTIVE_COPILOT.md
          </span>
        </footer>
      </div>

      {/* Reasoning drawer (mounted always; visibility via isOpen) */}
      <ReasoningDrawer card={openCard} isOpen={isOpen} onClose={closeDrawer} />
    </div>
  );
}
