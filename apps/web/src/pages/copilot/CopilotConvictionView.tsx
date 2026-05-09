// UX-10 Phase 10D — parallel Conviction view at /overview?view=conviction.
//
// Default /overview UNCHANGED. /overview?view=working UNCHANGED.
// /overview?view=stream (UX-9) UNCHANGED. This is an isolated
// parallel route for visual + emotional validation BEFORE any
// full cutover (Phase 10I).
//
// Source of truth: docs/research/UX_10_CONVICTION_ENGINE.md
//
// Mounts ConvictionHero with PROOF fixtures from
// composeConvictionHero(). Quiet-day state is exposed via
// ?quiet=1 for visual validation.

import { useMemo } from "react";
import { Link, useLocation } from "react-router-dom";

import ConvictionHero from "@/components/copilot/ConvictionHero";
import { composeConvictionHero } from "@/lib/copilot/conviction_compose";


export default function CopilotConvictionView() {
  const { search } = useLocation();
  const params = new URLSearchParams(search);
  const forceQuiet = params.get("quiet") === "1";

  const heroData = useMemo(
    () => composeConvictionHero({ forceQuiet }),
    [forceQuiet],
  );

  return (
    <div className="ux10-conviction" data-test="ux10-conviction-root">
      <div
        style={{
          maxWidth: "var(--ux10-page-max)",
          margin: "0 auto",
          padding: "var(--ux10-page-pad-y) var(--ux10-page-pad-x)",
        }}
      >
        {/* Page header */}
        <header
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "baseline",
            marginBottom: "var(--ux10-block-gap)",
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
              {heroData.date}
            </p>
          </div>
          <div style={{ display: "flex", gap: 16, alignItems: "baseline" }}>
            <Link
              to="/overview?view=conviction&quiet=1"
              style={{
                fontSize: "var(--ux10-fs-meta)",
                color: "var(--ux10-fg-tertiary)",
                textDecoration: "underline",
                textUnderlineOffset: 3,
              }}
              data-test="ux10-toggle-quiet"
            >
              {forceQuiet ? "Active day" : "Quiet day proof"}
            </Link>
            <Link
              to="/overview?view=conviction"
              style={{
                fontSize: "var(--ux10-fs-meta)",
                color: "var(--ux10-fg-tertiary)",
                textDecoration: "underline",
                textUnderlineOffset: 3,
                visibility: forceQuiet ? "visible" : "hidden",
              }}
            >
              ← back to active
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

        {/* Hero */}
        <ConvictionHero
          data={heroData}
          onCardReasoning={(t) => console.info("[ux10] reasoning click", t)}
          onCardBear={(t) => console.info("[ux10] bear click", t)}
          onCardSnooze={(t) => console.info("[ux10] snooze click", t)}
        />

        {/* Footer — read-only research notice */}
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
          Read-only research — paper trading only. Nothing on this
          page places orders. Not financial advice.
          <br />
          <span style={{ opacity: 0.6 }}>
            UX-10 Conviction · Phase 10D parallel route · master at
            docs/research/UX_10_CONVICTION_ENGINE.md
          </span>
        </footer>
      </div>
    </div>
  );
}
