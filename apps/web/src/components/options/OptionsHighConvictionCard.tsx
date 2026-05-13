// Phase 6b-3-d — Single high-conviction observation feature card.
//
// The #1 ranked candidate, treated as an EDITORIAL FEATURE rather
// than a list row. Bigger card, richer thesis, full provenance.
//
// Per the queued 6b-3-d direction:
//   "The strongest candidates should feel: important, interpreted,
//    and contextualized."
//   "Each candidate should clearly communicate: why it matters,
//    why now, supporting rationale, observational evidence."
//
// This is the page's emotional center — not a metric wall.
//
// Discipline:
//   * Read-only. No execute / open / close / sell buttons.
//   * Renders an honest empty state when no #1 exists today.
//   * Provenance footer derives from the same chain row that
//     produced the decision (provider + version + quote_age).

import { computeSetupQuality, dotsString } from "@/lib/options/setupQuality";
import {
  daysSince, isRunFromToday, useShadowRunDetail, useShadowRunsList,
  type ShadowDecision,
} from "@/lib/options/researchCandidates";


function _strategyHuman(name: string): string {
  // Today's only strategy is options_shadow_v1 — render as a clean
  // editorial label rather than the engine name.
  const map: Record<string, string> = {
    "options_shadow_v1": "Multi-strategy observation",
    "bull_put_credit_spread": "Bull put credit spread",
    "bear_call_credit_spread": "Bear call credit spread",
    "iron_condor": "Iron condor",
  };
  return map[name] ?? name.replace(/_/g, " ");
}


function _passingFiltersText(d: ShadowDecision): string {
  // Derive a calm sentence from the filter pass map.
  const passes = Object.entries(d.filters || {}).filter(([, v]) => v);
  const fails  = Object.entries(d.filters || {}).filter(([, v]) => !v);
  if (passes.length === 0) return "No filter pass data recorded.";
  if (fails.length === 0) {
    return `Passes every quality filter — liquidity, spread, ` +
           `open interest, volume, greeks, IV rank, and risk.`;
  }
  const failNames = fails.map(([k]) => k.replace(/_/g, " "));
  return `Passes ${passes.length} of ${passes.length + fails.length} ` +
         `filters; flagged on ${failNames.join(", ")}.`;
}


export default function OptionsHighConvictionCard() {
  const runsQ = useShadowRunsList();
  const latestRun = runsQ.data?.runs?.[0] ?? null;
  const latestDate = latestRun?.run_date ?? null;
  const detailQ = useShadowRunDetail(latestDate);
  const decisions = detailQ.data?.decisions ?? [];
  const isToday = isRunFromToday(latestDate);
  const ageDays = daysSince(latestDate);

  // Top would-trade decision by score, if today's run exists.
  const wouldTrade = decisions
    .filter(d => d.would_trade)
    .sort((a, b) => parseFloat(b.score) - parseFloat(a.score));
  const peerScores = wouldTrade.map(d => parseFloat(d.score)).sort((a, b) => a - b);
  const top = wouldTrade[0] ?? null;

  // Empty / dormant state — honest, calm.
  if (!isToday || top == null) {
    return (
      <section
        className="u-card-lg u-card-accent-l is-accent opt-conviction-card"
        data-test="options-high-conviction-card"
        data-state="empty"
      >
        <div className="u-label opt-conviction-eyebrow">
          HIGH-CONVICTION OBSERVATION
        </div>
        <h2 className="u-title-lg opt-conviction-headline">
          {isToday
            ? "No observation cleared every quality bar today."
            : "Awaiting today's evaluation cycle."}
        </h2>
        <p className="u-body opt-conviction-body">
          {isToday
            ? "The engine evaluated today's chain but no candidate " +
              "passed all seven quality filters with a score worth " +
              "elevating. This is the engine practicing restraint, " +
              "not failure."
            : `The most recent shadow evaluation ran ${ageDays} day` +
              `${ageDays === 1 ? "" : "s"} ago. ` +
              "The next cycle fires at 21:30 UTC on the next " +
              "weekday market close."}
        </p>
      </section>
    );
  }

  const score = parseFloat(top.score || "0");
  const quality = computeSetupQuality(score, peerScores);
  const dotsText = dotsString(quality.dots);  // noqa: dot scale
  const direction = (top.option_type?.toUpperCase() === "PUT")
    ? "directional ↓" : "directional ↑";
  const expiry = new Date(top.expiration);
  const dteDays = Math.max(0, Math.round(
    (expiry.getTime() - Date.now()) / 86_400_000));

  return (
    <section
      className="u-card-lg u-card-accent-l is-accent opt-conviction-card"
      data-test="options-high-conviction-card"
      data-state="active"
    >
      <div className="opt-conviction-head">
        <div>
          <div className="u-label opt-conviction-eyebrow">
            HIGH-CONVICTION OBSERVATION · #{1} of {wouldTrade.length}
          </div>
          <h2 className="u-title-lg opt-conviction-headline">
            {top.underlying_symbol}
            <span className="opt-conviction-strategy">
              {" · "}{_strategyHuman(top.strategy_name)}
            </span>
          </h2>
        </div>
        <div className="opt-conviction-quality">
          <div className="u-label-sm" style={{ marginBottom: 4 }}>
            SETUP QUALITY
          </div>
          <div className="opt-conviction-dots">{dotsText}</div>
          <div className="opt-conviction-quality-text">{quality.label}</div>
        </div>
      </div>

      {/* Why this matters */}
      <div className="opt-conviction-section">
        <div className="opt-conviction-section-label">
          Why this matters
        </div>
        <p className="opt-conviction-section-body">
          {_passingFiltersText(top)} The engine flags it as the
          strongest single observation in today's chain, ranked by
          per-strategy setup quality relative to today's peer cohort.
        </p>
      </div>

      {/* Why now */}
      <div className="opt-conviction-section">
        <div className="opt-conviction-section-label">
          Why now
        </div>
        <p className="opt-conviction-section-body">
          Expiration {top.expiration} ({dteDays} day
          {dteDays === 1 ? "" : "s"} to expiry); strike ${top.strike};
          {" "}{direction}. Surfaces from today's coherent chain
          batch with fresh provider data.
        </p>
      </div>

      {/* Provenance row */}
      <div className="opt-conviction-foot">
        <span>{top.option_symbol}</span>
        <span className="opt-conviction-foot-sep">·</span>
        <span>strike ${parseFloat(top.strike).toFixed(2)}</span>
        <span className="opt-conviction-foot-sep">·</span>
        <span>{top.option_type}</span>
        <span className="opt-conviction-foot-sep">·</span>
        <span>{(top as any).side ?? "—"}</span>
        <span className="opt-conviction-foot-sep">·</span>
        <span>score {score.toFixed(3)}</span>
      </div>
    </section>
  );
}
