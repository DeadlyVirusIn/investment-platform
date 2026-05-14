// Phase 6b-3-e — Journal pulse strip.
//
// Single-line orientation. Real counts only. NO inflated framing.
//
// Renders:
//   "{N} paper observation(s) · {M} lifecycle transitions · {D} days
//    of evaluator history"
//
// Where:
//   N = options_paper_trade rows               (via /paper-trades)
//   M = options_trade_lifecycle_event rows     (computed from /paper-trades + lifecycle endpoint;
//                                               for now, simplified — counts via per-trade hook
//                                               could be expensive, so we display a static
//                                               summary line and let the lifecycle timeline
//                                               below carry the truth)
//   D = distinct run_date in shadow_decision_log (via /analytics/daily-counts)
//
// Discipline:
//   * Honest scarcity — if N=1 and M=0, the strip says "1 · 0 · 2 days".
//   * No gamification language. No proclamations.

import { useQuery } from "@tanstack/react-query";

import { useOptionsPaperTrades } from "@/lib/options/hooks";
import { apiGet } from "@/lib/api";


interface DailyCountsResponse {
  series: Array<{ run_date: string; total: number; would_trade: number }>;
  count: number;
}


export default function OptionsJournalPulse() {
  const tradesQ = useOptionsPaperTrades({});
  const dailyQ = useQuery<DailyCountsResponse>({
    queryKey: ["options", "analytics", "daily-counts", 30],
    queryFn:  () => apiGet("/options/analytics/daily-counts?days=30"),
    staleTime: 60_000, refetchOnWindowFocus: false,
  });

  const trades = tradesQ.data?.trades ?? [];
  const tradeCount = trades.length;
  const closedCount = trades.filter(
    t => t.status === "CLOSED" || t.status === "EXPIRED" ||
         t.status === "ASSIGNED").length;
  const evaluatorDays = dailyQ.data?.count ?? 0;

  // Earliest paper observation date — communicates "since when"
  const earliestOpen = trades
    .filter(t => t.opened_at)
    .map(t => t.opened_at!)
    .sort()[0];
  const sinceText = earliestOpen
    ? `since ${earliestOpen.slice(0, 10)}`
    : "no observations on record";

  return (
    <div
      className="opt-research-pulse-strip opt-journal-pulse"
      data-test="options-journal-pulse"
    >
      <span className="opt-pulse-eyebrow">JOURNAL</span>
      <span className="opt-pulse-sep">·</span>
      <span className="opt-pulse-text">
        <strong className="opt-pulse-num">{tradeCount}</strong>
        {" "}paper observation{tradeCount === 1 ? "" : "s"}
      </span>
      <span className="opt-pulse-sep">·</span>
      <span className="opt-pulse-text">
        <strong className="opt-pulse-num">{closedCount}</strong>
        {" "}closed
      </span>
      <span className="opt-pulse-sep">·</span>
      <span className="opt-pulse-text">
        <strong className="opt-pulse-num">{evaluatorDays}</strong>
        {" "}day{evaluatorDays === 1 ? "" : "s"} of evaluator history
      </span>
      <span className="opt-pulse-sep">·</span>
      <span className="opt-pulse-text">{sinceText}</span>
    </div>
  );
}
