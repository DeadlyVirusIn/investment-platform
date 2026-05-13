// Phase 6b-3-d — Supporting observations (the rest after #1).
//
// Compact list (NOT a table). Each row: rank · ticker · strategy ·
// dot scale · score. Click to expand into per-row detail. Built for
// scanning, not data dumping.
//
// Per the queued 6b-3-d direction:
//   "Display only a SMALL curated set. NOT large scanner tables."
//   "Avoid metric soup."
//
// We render at most 9 rows (#2 through #10). No pagination — if
// there are more, the page intentionally truncates and provides
// the doorway to a deeper view.

import { useState } from "react";

import { computeSetupQuality, dotsString } from "@/lib/options/setupQuality";
import {
  isRunFromToday, useShadowRunDetail, useShadowRunsList,
  type ShadowDecision,
} from "@/lib/options/researchCandidates";


const MAX_ROWS = 9;


function _Row({
  d, rank, peer_scores, expanded, onToggle,
}: {
  d:           ShadowDecision;
  rank:        number;
  peer_scores: number[];
  expanded:    boolean;
  onToggle:    () => void;
}) {
  const score = parseFloat(d.score || "0");
  const q = computeSetupQuality(score, peer_scores);
  const dteDays = Math.max(0, Math.round(
    (new Date(d.expiration).getTime() - Date.now()) / 86_400_000));

  return (
    <li className="opt-supp-row" data-expanded={expanded ? "true" : "false"}>
      <button
        type="button"
        className="opt-supp-row-head"
        onClick={onToggle}
        aria-expanded={expanded}
      >
        <span className="opt-supp-row-rank">#{rank}</span>
        <span className="opt-supp-row-ticker">{d.underlying_symbol}</span>
        <span className="opt-supp-row-meta">
          ${parseFloat(d.strike).toFixed(0)} {d.option_type}
        </span>
        <span className="opt-supp-row-meta">{dteDays}d</span>
        <span className="opt-supp-row-dots">{dotsString(q.dots)}</span>
        <span className="opt-supp-row-score">{score.toFixed(3)}</span>
        <span className="opt-supp-row-toggle">{expanded ? "▾" : "▸"}</span>
      </button>
      {expanded && (
        <div className="opt-supp-row-detail">
          <p className="opt-supp-row-detail-body">
            {d.reason === "all_filters_pass"
              ? "Passes every quality filter."
              : `Reason: ${d.reason.replace(/_/g, " ")}.`}
          </p>
          <div className="opt-supp-row-detail-meta">
            <span>{d.option_symbol}</span>
            <span> · </span>
            <span>expiry {d.expiration}</span>
            <span> · </span>
            <span>quality: {q.label}</span>
          </div>
        </div>
      )}
    </li>
  );
}


export default function OptionsSupportingObservations() {
  const [openRank, setOpenRank] = useState<number | null>(null);
  const runsQ = useShadowRunsList();
  const latestDate = runsQ.data?.runs?.[0]?.run_date ?? null;
  const detailQ = useShadowRunDetail(latestDate);
  const decisions = detailQ.data?.decisions ?? [];

  if (!isRunFromToday(latestDate)) return null;

  const wouldTrade = decisions
    .filter(d => d.would_trade)
    .sort((a, b) => parseFloat(b.score) - parseFloat(a.score));

  // Skip #1 — that lives in OptionsHighConvictionCard.
  const supporting = wouldTrade.slice(1, 1 + MAX_ROWS);

  if (supporting.length === 0) {
    return (
      <section
        className="u-card opt-supp-empty"
        data-test="options-supporting-observations"
        data-state="empty"
      >
        <div className="u-label">SUPPORTING OBSERVATIONS</div>
        <p className="u-body" style={{ marginTop: 8, color: "var(--fg-3)" }}>
          The single high-conviction observation above is the only
          candidate that cleared today's filters.
        </p>
      </section>
    );
  }

  const peer_scores = wouldTrade
    .map(d => parseFloat(d.score)).sort((a, b) => a - b);

  return (
    <section
      className="u-card opt-supp-section"
      data-test="options-supporting-observations"
    >
      <header className="opt-card-header" style={{ marginBottom: 10 }}>
        <span className="opt-card-eyebrow">
          Supporting observations
        </span>
        <span className="opt-card-meta">
          {supporting.length} of {wouldTrade.length - 1} shown · click to expand
        </span>
      </header>

      <ul className="opt-supp-list">
        {supporting.map((d, idx) => {
          const rank = idx + 2;
          return (
            <_Row
              key={d.option_symbol}
              d={d}
              rank={rank}
              peer_scores={peer_scores}
              expanded={openRank === rank}
              onToggle={() => setOpenRank(openRank === rank ? null : rank)}
            />
          );
        })}
      </ul>

      {wouldTrade.length - 1 > supporting.length && (
        <p className="u-caption-2" style={{
          marginTop: 12, color: "var(--fg-3)",
        }}>
          {wouldTrade.length - 1 - supporting.length} additional
          candidates exist; the page intentionally truncates to keep
          the surface scannable.
        </p>
      )}
    </section>
  );
}
