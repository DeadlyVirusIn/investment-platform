// Phase Opt-C1 Step 5 — Today's Research Candidates (top 3).
//
// Discipline:
//   - "Today" means today (UTC). Never represents stale data as today's.
//   - Top 3 equal-weight cards (no oversized hero).
//   - Setup quality: dot scale via percentile mapping (lib/options/setupQuality).
//     Dormant + sparse-cohort → "early read" + 1 dot ("underpowered").
//   - Reading: 1-2 sentence narrative derived from filter evidence.
//   - NO win probability. NO "Top Pick". NO authority-coded copy.

import OptionsSuggestionCard, {
  type SuggestionCardData,
  type SuggestionLeg,
} from "./OptionsSuggestionCard";
import { computeSetupQuality } from "@/lib/options/setupQuality";
import {
  daysSince,
  isRunFromToday,
  useShadowRunDetail,
  useShadowRunsList,
  type ShadowDecision,
} from "@/lib/options/researchCandidates";


function _legSpec(d: ShadowDecision): SuggestionLeg[] {
  // Shadow decisions are single-leg in v1. Multi-leg strategies
  // would emit multiple decisions per (run, strategy, structure).
  const side: "BUY" | "SELL" =
    (d.side?.toUpperCase() === "SELL") ? "SELL" : "BUY";
  const option_type: "CALL" | "PUT" =
    (d.option_type?.toUpperCase() === "PUT") ? "PUT" : "CALL";
  return [{
    side,
    option_type,
    strike: String(parseFloat(d.strike || "0").toFixed(2)),
  }];
}


function _readingFor(d: ShadowDecision): string {
  // Calm 1-sentence narrative from filter pass evidence + reason.
  // Never authoritative.
  if (d.would_trade && d.reason === "all_filters_pass") {
    return `Passed all 7 quality checks for ${d.strategy_name}.`;
  }
  return d.reason || "Setup evaluated.";
}


function _decisionToCard(
  d: ShadowDecision,
  rank: number,
  totalToday: number,
  peer_scores_sorted_asc: number[],
): SuggestionCardData {
  const score = parseFloat(d.score || "0");
  const setup = computeSetupQuality(score, peer_scores_sorted_asc);
  const filterPasses =
    d.diagnostics?.filter_results?.map(fr => ({
      code: fr.name,
      label: fr.name.replace(/_/g, " "),
      passed: fr.passed,
    })) ?? Object.entries(d.filters).map(([code, passed]) => ({
      code, label: code.replace(/_/g, " "), passed,
    }));
  return {
    ticker: d.underlying_symbol,
    strategy_name: d.strategy_name,
    rule_id: d.strategy_name,
    expiry: d.expiration,
    legs: _legSpec(d),
    max_risk_dollars: null,
    max_profit_dollars: null,
    breakeven: null,
    reading: _readingFor(d),
    setup_quality: setup,
    rank,
    total_today: totalToday,
    lifecycle_status: "candidate",
    filter_passes: filterPasses,
  };
}


export default function OptionsResearchCandidates() {
  const runsQ = useShadowRunsList();
  const runs = runsQ.data?.runs ?? [];
  const latestRun = runs[0] ?? null;
  const latestDate = latestRun?.run_date ?? null;
  const detailQ = useShadowRunDetail(latestDate);
  const decisions = detailQ.data?.decisions ?? [];

  const todayHasRun = isRunFromToday(latestDate);
  const lastRunAgeDays = daysSince(latestDate);
  const wouldTrade = decisions
    .filter(d => d.would_trade)
    .sort((a, b) => parseFloat(b.score) - parseFloat(a.score));
  const peer_scores = wouldTrade.map(d => parseFloat(d.score)).sort((a, b) => a - b);
  const top3 = wouldTrade.slice(0, 3);

  return (
    <section className="u-card opt-card" data-test="options-research-candidates">
      <header className="opt-card-header">
        <span className="opt-card-eyebrow">Today's research candidates</span>
        <span className="opt-card-meta">
          {runsQ.isLoading || detailQ.isLoading
            ? "loading…"
            : todayHasRun
              ? `${top3.length} candidates · ${decisions.length} evaluated · ${
                  decisions.length - wouldTrade.length} filtered out`
              : "no shadow run today"}
        </span>
      </header>

      {/* Empty state — engine dormant or no run today */}
      {!todayHasRun && (
        <div className="opt-empty">
          <p className="opt-empty-headline">
            AI options research is paused.
          </p>
          <p className="opt-empty-body">
            {latestDate
              ? `Last shadow evaluation ran ${lastRunAgeDays}d ago (${latestDate}). `
              : "No shadow evaluations on record yet. "}
            Engine activates with Phase Opt-B3. When live, this section
            shows the top 3 candidates that passed all 7 quality checks
            today, ranked by setup quality.
          </p>
          <ul className="opt-explain-list" style={{ marginTop: 8 }}>
            <li>Each card: ticker, strategy, legs, risk/reward, breakeven</li>
            <li>Setup quality dot scale (relative, not win probability)</li>
            <li>Lifecycle pill ties candidate to its paper trade if filled</li>
            <li>"Why this passed" disclosure shows all 7 quality checks</li>
          </ul>
        </div>
      )}

      {/* Active state — top 3 candidate cards */}
      {todayHasRun && top3.length > 0 && (
        <div className="opt-suggestion-grid">
          {top3.map((d, i) => (
            <OptionsSuggestionCard
              key={`${d.option_symbol}-${i}`}
              data={_decisionToCard(d, i + 1, top3.length, peer_scores)}
            />
          ))}
        </div>
      )}

      {/* Active but zero passed filters today */}
      {todayHasRun && top3.length === 0 && (
        <div className="opt-empty">
          <p className="opt-empty-headline">
            No candidates passed today's quality bar.
          </p>
          <p className="opt-empty-body">
            {decisions.length > 0
              ? `${decisions.length} setups evaluated; all filtered out. `
              : "No decisions recorded today. "}
            See "Filtered Out Today" below for the rejection breakdown.
          </p>
        </div>
      )}
    </section>
  );
}
