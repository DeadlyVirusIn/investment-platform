// UX-5B Phase B-3 — Today (Overview) page mount.
//
// Composes the six block components from real engine state via
// existing hooks. NO new endpoints, NO new fetch. The page reads
// the same data the existing Elite Terminal already reads, but
// surfaces it through the deterministic Layer-1 composers from
// B-1 + the editorial block components from B-2.
//
// Editorial layout contract:
//   * Single column, max-width 720px, centered.
//   * Block rhythm: 40px between blocks, hairline divider
//     between for "continuous editorial" feel (NOT panel
//     separation).
//   * Greeting is the only h1; block headers are tertiary-rail
//     uppercase 11px (already styled inside each block).
//   * NO atmosphere, NO gradients, NO shadows, NO hover polish.
//   * NO charts, NO chips, NO counters above the fold.
//
// Quiet-day collapse (R-B): when EVERY block (holdings, ideas,
// what-changed, risk, watch) is empty, the page renders just the
// greeting + a calm one-sentence body + footer. This is the
// first-class "quiet" rendering, NOT a fallback empty-state.

import { Link } from "react-router-dom";

import {
  HoldingsSummary, RiskLine, TodayLine, TodaysIdeas,
  WatchThisWeek, WhatChangedBlock,
} from "@/components/copilot";
import {
  deriveHoldingsSummary, deriveQuietDay, deriveRiskLine,
  deriveTodayLine, deriveTodaysIdeas, deriveWatch,
  deriveWhatChanged,
} from "@/lib/copilot/overview_derive";
import { TODAY_FOOTER } from "@/lib/copilot/overview_copy";
import { usePaperSummary } from "@/lib/operator/hooks";


/** YYYY-MM-DD for the user's local clock. Computed once at module
 *  load so render is deterministic during a session. */
function _todayYMD(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${dd}`;
}


/** Map the engine's Regime literal to the calm key used by
 *  overview_copy.ts. The composer accepts these specific keys
 *  + falls through to silence when unknown — never narrates. */
function _regimeKey(
  regime: string | null | undefined,
  isDirectional: boolean | null | undefined,
): string | null {
  if (regime === "stress") return "stress";
  if (regime === "directional" || isDirectional) return "trending";
  if (regime === "none" || regime === null || regime === undefined) {
    return "calm";
  }
  return null;
}


export default function CopilotOverview() {
  const { data: summary } = usePaperSummary();

  const todayYMD = _todayYMD();
  const localHour = new Date().getHours();

  // Compose Block 1 — today line. Always present (worst case
  // greeting-only). Pipeline state derived from PaperSummary
  // (`pipeline_status: "success" | "partial" | "failed"`).
  const pipelineFailed = summary?.pipeline_status === "failed";
  const regimeKey = _regimeKey(summary?.regime ?? null, false);
  const todayLine = deriveTodayLine({
    todayYMD,
    localHour,
    regimeLabel: regimeKey,
    pipelineFailed,
  });

  // Compose Block 2 — holdings summary. State-clause stays null
  // until mark-price data is wired (R-E — omit clause rather
  // than fabricate state).
  const holdings = deriveHoldingsSummary({
    openCount: summary?.open_positions_count ?? 0,
    approachingTargetCount: null,
    needsAttentionCount: null,
  });

  // Block 3 — today's ideas. Wiring deferred to a follow-up
  // phase (needs candidate_idea + recommendation join shaped
  // for IdeaInput). For B-3 the block is silent so the page
  // doesn't fabricate ideas it can't truthfully observe.
  const todaysIdeas = deriveTodaysIdeas({ ideas: [] });

  // Block 4 — what changed. Pass empty input → composer
  // returns the quiet-fallback line ("Today looks much like
  // yesterday."). When other phases wire deltas, those will
  // override the fallback.
  const whatChanged = deriveWhatChanged({});

  // Block 5 — risk. Drawdown comes from PaperSummary; stress
  // from the same. Paused-strategy count not yet wired —
  // omitted (R-E). Block renders only when at least one
  // trigger fires.
  const riskLine = deriveRiskLine({
    drawdownFromPeak: summary?.max_drawdown_pct ?? 0,
    stressRegime: summary?.regime === "stress",
    pausedStrategiesToday: 0,
  });

  // Block 6 — watch this week. Catalyst calendar wiring
  // deferred (R-E); block omits.
  const watch = deriveWatch([]);

  // Quiet-day rendering (R-B). The full-page collapse fires
  // only when no engine summary is available at all — i.e. the
  // hook is still resolving, OR upstream data is unavailable.
  // The page renders greeting + one calm sentence + footer
  // rather than a skeleton or empty-state. R-B is explicit
  // that this is a FIRST-CLASS path; the page still feels
  // intentional. Once `summary` resolves, individual blocks
  // self-collapse via their own null returns; the today-line
  // always renders (worst case: greeting only).
  const quiet = !summary
    ? deriveQuietDay({ todayYMD, localHour })
    : null;

  return (
    <article
      data-test="copilot-overview"
      style={{
        // Editorial reading width. Centered. Single column.
        // Eye flows downward; never scanned like a terminal.
        maxWidth: 720,
        margin: "0 auto",
        // Generous breathing on top and bottom; the hairlines
        // between blocks give continuity, not boxing.
        padding: "56px 24px 80px",
        color: "inherit",
      }}
    >
      {quiet ? (
        // Quiet-day path — greeting + one calm sentence + footer.
        // R-B: this is intentional, not a fallback.
        <>
          <header data-test="copilot-overview-quiet">
            <h1
              style={{
                fontSize: "var(--copilot-type-24)",
                fontWeight: 500,
                margin: 0,
                letterSpacing: "-0.01em",
              }}
            >
              {quiet.greeting}
            </h1>
            <p
              style={{
                margin: "12px 0 0",
                fontSize: "var(--copilot-type-15)",
                lineHeight: "var(--copilot-prose-line-height)",
                opacity: 0.85,
                maxWidth: "var(--copilot-prose-max-width)",
              }}
              data-source={quiet.dataSource}
            >
              {quiet.body}
            </p>
          </header>
          <_HairlineDivider />
          <_PageFooter />
        </>
      ) : (
        // Active-day path — render every non-null block in order
        // with hairline dividers between. R-E: blocks that
        // returned null (todaysIdeas / watch on B-3) physically
        // do not render — no header, no placeholder.
        <>
          <TodayLine data={todayLine} />

          <_HairlineDivider />
          <HoldingsSummary data={holdings} />

          {todaysIdeas && (
            <>
              <_HairlineDivider />
              <TodaysIdeas data={todaysIdeas} />
            </>
          )}

          {whatChanged && !whatChanged.isQuietFallback && (
            <>
              <_HairlineDivider />
              <WhatChangedBlock data={whatChanged} />
            </>
          )}

          {riskLine && (
            <>
              <_HairlineDivider />
              <RiskLine data={riskLine} />
            </>
          )}

          {watch && (
            <>
              <_HairlineDivider />
              <WatchThisWeek data={watch} />
            </>
          )}

          <_HairlineDivider />
          <_PageFooter />
        </>
      )}
    </article>
  );
}


// ---------------------------------------------------------------------
// Internal — hairline divider between blocks.
//
// 1px line at 6% opacity. Reads as a paragraph break in an
// editorial layout, NOT as a panel separator. Generous vertical
// margin gives breathing room without making the page feel
// stretched.
// ---------------------------------------------------------------------

function _HairlineDivider() {
  return (
    <hr
      role="presentation"
      style={{
        border: 0,
        borderTop: "1px solid var(--copilot-ambient-tint)",
        margin: "40px 0",
        opacity: 1,
      }}
    />
  );
}


// ---------------------------------------------------------------------
// Internal — page footer (read-only notice + sole Layer-3 link).
// ---------------------------------------------------------------------

function _PageFooter() {
  return (
    <footer
      data-test="copilot-overview-footer"
      style={{
        fontSize: "var(--copilot-type-12)",
        opacity: 0.55,
        lineHeight: "var(--copilot-prose-line-height)",
      }}
    >
      <p style={{ margin: 0 }}>{TODAY_FOOTER.readOnly}</p>
      <div style={{ marginTop: 8 }}>
        <Link
          to="/overview?view=working"
          data-test="copilot-overview-working-link"
          style={{ color: "inherit", textDecoration: "underline" }}
        >
          {TODAY_FOOTER.workingLink} →
        </Link>
      </div>
    </footer>
  );
}
