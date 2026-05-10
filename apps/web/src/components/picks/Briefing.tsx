// Briefing — premium hero panel above the grid.
//
// Honest summary derived from actual picks data:
//   - posture (defensive / cautious / neutral / constructive)
//   - headline + body
//   - chips: high-confidence trims/holds, freshness, stale, thin data
//   - 1 primary CTA + 1 secondary CTA (filter the grid)

import type { Briefing as BriefingT } from "@/lib/picks/copilot";
import type { PicksFilter } from "@/lib/picks/copilot";


export interface BriefingProps {
  briefing: BriefingT;
  onFilterChange: (filter: PicksFilter) => void;
}


function fmtRelTime(iso: string | null): string {
  if (!iso) return "—";
  const ms = Date.now() - Date.parse(iso);
  const hours = ms / 3_600_000;
  if (hours < 1) return `${Math.max(1, Math.round(hours * 60))}m ago`;
  if (hours < 24) return `${Math.round(hours)}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}


export default function Briefing({ briefing, onFilterChange }: BriefingProps) {
  const primaryFilter: PicksFilter = briefing.highConfidenceTrims > 0
    ? "highest-risk"
    : briefing.highConfidenceHolds > 0
      ? "high-confidence"
      : "all";

  return (
    <section
      className="picks-briefing"
      data-test="picks-briefing"
      data-posture={briefing.posture}
    >
      <div className="picks-briefing-row1">
        <span className="picks-briefing-eyebrow">Today's AI briefing</span>
        <span className="picks-briefing-posture" data-posture={briefing.posture}>
          <span className="picks-briefing-posture-dot" />
          Posture: {briefing.postureLabel}
        </span>
      </div>

      <h2 className="picks-briefing-headline">{briefing.headline}</h2>
      <p className="picks-briefing-body">{briefing.body}</p>

      <div className="picks-briefing-chips">
        {briefing.highConfidenceTrims > 0 && (
          <span className="picks-briefing-chip" data-tone="trim">
            <strong>{briefing.highConfidenceTrims}</strong> high-confidence trim{briefing.highConfidenceTrims === 1 ? "" : "s"}
          </span>
        )}
        {briefing.highConfidenceHolds > 0 && (
          <span className="picks-briefing-chip" data-tone="hold">
            <strong>{briefing.highConfidenceHolds}</strong> strong hold{briefing.highConfidenceHolds === 1 ? "" : "s"}
          </span>
        )}
        {briefing.staleCount > 0 && (
          <span className="picks-briefing-chip" data-tone="warn">
            <strong>{briefing.staleCount}</strong> stale
          </span>
        )}
        {briefing.thinDataCount > 0 && (
          <span className="picks-briefing-chip" data-tone="warn">
            <strong>{briefing.thinDataCount}</strong> thin data
          </span>
        )}
        {briefing.freshestAtIso && (
          <span className="picks-briefing-chip" data-tone="meta">
            Latest signal {fmtRelTime(briefing.freshestAtIso)}
          </span>
        )}
      </div>

      <div className="picks-briefing-actions">
        <button
          type="button"
          className="picks-briefing-cta picks-briefing-cta-primary"
          onClick={() => onFilterChange(primaryFilter)}
        >
          {briefing.recommendedAction} →
        </button>
        {briefing.highConfidenceHolds > 0 && primaryFilter !== "high-confidence" && (
          <button
            type="button"
            className="picks-briefing-cta picks-briefing-cta-secondary"
            onClick={() => onFilterChange("hold")}
          >
            Show watchlist holds
          </button>
        )}
      </div>
    </section>
  );
}
