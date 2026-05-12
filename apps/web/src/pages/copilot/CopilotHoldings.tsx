// UX-2 Phase B — Holdings Brief view.
//
// Mounted at /portfolio?view=brief (and at /portfolio when no
// ?view= is set, since Phase A defaults to brief). The existing
// PortfolioTerminal stays at /portfolio?view=working — see
// App.tsx route switch.
//
// Pure composition of Phase A primitives + the new
// PositionStoryCard. NO new endpoint, NO new hook, NO new fetch.
// Reads useExecutedPositions (already used by PortfolioTerminal).

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import {
  PositionStoryCard, QuietDay,
} from "@/components/copilot";
import MarketTicker from "@/components/shell/MarketTicker";
import { COPILOT_BRAND, HOLDINGS_COPY, ONBOARDING_CLAUSES } from "@/lib/copilot/copy";
import { derivePositionStory } from "@/lib/copilot/derive";
import { hasSeen, markSeen } from "@/lib/copilot/onboarding";
import { useExecutedPositions } from "@/lib/operator/hooks";


/** YYYY-MM-DD for the user's local clock. Computed once at module
 *  load so render is deterministic during a session. CopilotHoldings
 *  re-mounts on route change, so this naturally refreshes per visit
 *  rather than per re-render. */
function _todayYMD(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${dd}`;
}


export default function CopilotHoldings() {
  // Default false (existing-user behaviour): never include replay.
  // Working view exposes the toggle. Brief view stays clean.
  const positionsQ = useExecutedPositions(false, true);
  const positions = positionsQ.data?.positions ?? [];
  const today = _todayYMD();

  // First-position onboarding clause — fires once via localStorage.
  // Resolved after mount so the value is correct in SSR/SSG paths.
  const [showOnboarding, setShowOnboarding] = useState(false);
  useEffect(() => {
    if (positions.length > 0 && !hasSeen("ux_seen_first_position")) {
      setShowOnboarding(true);
      markSeen("ux_seen_first_position");
    }
  }, [positions.length]);

  return (
    <div
      className="max-w-[1100px] mx-auto px-6 py-8"
      data-test="copilot-holdings"
    >
      <header style={{ marginBottom: 32 }}>
        <h1
          data-test="copilot-holdings-title"
          style={{
            fontSize: "var(--copilot-type-24)",
            fontWeight: 500,
            margin: 0,
            color: "inherit",
          }}
        >
          {HOLDINGS_COPY.pageTitle}
        </h1>
        <p
          data-test="copilot-holdings-subtitle"
          style={{
            margin: "8px 0 0",
            fontSize: "var(--copilot-type-15)",
            lineHeight: "var(--copilot-prose-line-height)",
            opacity: 0.85,
            maxWidth: "var(--copilot-prose-max-width)",
          }}
        >
          {HOLDINGS_COPY.pageSubtitle}
        </p>
        <div
          style={{
            marginTop: 12,
            fontSize: "var(--copilot-type-12)",
            opacity: 0.55,
          }}
        >
          <Link
            to="/portfolio?view=working"
            data-test="copilot-holdings-working-link"
            style={{ color: "inherit", textDecoration: "underline" }}
          >
            {HOLDINGS_COPY.workingViewLink} →
          </Link>
        </div>
      </header>

      {positionsQ.isLoading && (
        <p
          data-test="copilot-holdings-loading"
          style={{
            fontSize: "var(--copilot-type-13)",
            opacity: 0.55,
            fontStyle: "italic",
          }}
        >
          Loading holdings…
        </p>
      )}

      {!positionsQ.isLoading && positions.length === 0 && (
        <section data-test="copilot-holdings-empty">
          <QuietDay />
          <p
            style={{
              fontSize: "var(--copilot-type-15)",
              textAlign: "center",
              maxWidth: "var(--copilot-prose-max-width)",
              margin: "8px auto 0",
              opacity: 0.85,
              lineHeight: "var(--copilot-prose-line-height)",
            }}
            data-test="copilot-holdings-empty-body"
          >
            <strong>{HOLDINGS_COPY.emptyHeadline}</strong>
            {" "}
            {HOLDINGS_COPY.emptyBody}
          </p>
        </section>
      )}

      {positions.length > 0 && (
        <section
          data-test="copilot-holdings-tape"
          aria-label="Holdings tape — 15-min delayed prices for open positions"
          style={{ marginBottom: 18 }}
        >
          <div className="holdings-tape-label">Holdings tape</div>
          <MarketTicker kind="holdings" mode="full" />
        </section>
      )}

      {positions.length > 0 && (
        <section data-test="copilot-holdings-list">
          {showOnboarding && (
            <p
              data-test="copilot-holdings-onboarding"
              style={{
                marginBottom: 24,
                fontSize: "var(--copilot-type-13)",
                opacity: 0.55,
                lineHeight: "var(--copilot-prose-line-height)",
              }}
            >
              {ONBOARDING_CLAUSES.ux_seen_first_position}
            </p>
          )}
          {positions.map((p, idx) => (
            <PositionStoryCard
              key={p.position_id}
              story={derivePositionStory({
                symbol: p.symbol,
                quantity: p.quantity,
                avg_cost: p.avg_cost,
                opened_at: p.opened_at,
                source: p.source,
              }, today)}
              defaultOpen={idx === 0 && showOnboarding}
            />
          ))}
        </section>
      )}

      <footer
        style={{
          marginTop: 48,
          paddingTop: 24,
          borderTop: "1px solid var(--copilot-ambient-tint)",
          fontSize: "var(--copilot-type-12)",
          opacity: 0.55,
          lineHeight: "var(--copilot-prose-line-height)",
        }}
        data-test="copilot-holdings-footer"
      >
        {COPILOT_BRAND.readOnlyFooter}
      </footer>
    </div>
  );
}
