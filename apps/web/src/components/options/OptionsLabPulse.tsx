// Phase 6b-3-h — Lab pulse strip.
//
// Single line. Methodological orientation. Inspectable counts only.
//
// Renders:
//   "LAB · 3 strategy templates · 5 criteria each · {N} contracts
//    evaluated through this pipeline today, {M} cleared all filters"
//
// No "AI" language. No "alpha". No "discovery". Just method counts.

import { useQuery } from "@tanstack/react-query";

import { apiGet } from "@/lib/api";


interface StrategiesShape {
  strategies: Array<{ name: string; criteria: unknown[] }>;
}

interface DailyShape {
  series: Array<{ run_date: string; total: number; would_trade: number }>;
}


export default function OptionsLabPulse() {
  const { data: strats } = useQuery<StrategiesShape>({
    queryKey: ["options", "strategies-catalog"],
    queryFn:  () => apiGet("/options/strategies"),
    staleTime: 5 * 60_000, refetchOnWindowFocus: false,
  });
  const { data: daily } = useQuery<DailyShape>({
    queryKey: ["options", "analytics", "daily-counts", 7],
    queryFn:  () => apiGet("/options/analytics/daily-counts?days=7"),
    staleTime: 60_000, refetchOnWindowFocus: false,
  });

  const templates = strats?.strategies?.length ?? 0;
  const criteriaPerTemplate = strats?.strategies?.[0]?.criteria?.length ?? 0;

  // Most recent qualifying day — typically today; otherwise the
  // most recent in the rolling 7-day window.
  const recent = daily?.series?.[0];

  return (
    <div
      className="opt-research-pulse-strip opt-lab-pulse"
      data-test="options-lab-pulse"
    >
      <span className="opt-pulse-eyebrow">LAB</span>
      <span className="opt-pulse-sep">·</span>
      <span className="opt-pulse-text">
        <strong className="opt-pulse-num">{templates}</strong>
        {" "}strategy template{templates === 1 ? "" : "s"}
      </span>
      <span className="opt-pulse-sep">·</span>
      <span className="opt-pulse-text">
        <strong className="opt-pulse-num">{criteriaPerTemplate}</strong>
        {" "}criteria each
      </span>
      <span className="opt-pulse-sep">·</span>
      <span className="opt-pulse-text">
        {recent ? (
          <>
            <strong className="opt-pulse-num">
              {recent.total.toLocaleString()}
            </strong>
            {" "}contracts evaluated{" "}
            {recent.run_date === new Date().toISOString().slice(0, 10)
              ? "today"
              : `on ${recent.run_date}`}
            {", "}
            <strong className="opt-pulse-num">
              {recent.would_trade.toLocaleString()}
            </strong>
            {" "}cleared all filters
          </>
        ) : (
          "no evaluation cycles on record"
        )}
      </span>
    </div>
  );
}
