// Phase 6b-3-e — Evaluator history layer (longitudinal memory).
//
// Per-day chronology of evaluation cycles. Communicates "the system
// has memory" through real run_date entries from
// /analytics/daily-counts. Currently sparse (typically 1-2 rows of
// real history) — the sparseness IS the truth.
//
// Calm vertical list. No bars. No charts. Just:
//   date · contracts · would_trade · underlyings
//
// Discipline:
//   * Honest empty state if zero rows.
//   * Sparse rows render as-is — no padding to fake density.
//   * Each row carries the same provenance comment in code as the
//     analytics endpoint that produced it.

import { useQuery } from "@tanstack/react-query";

import { apiGet } from "@/lib/api";


interface DailyCountsResponse {
  days:  number;
  count: number;
  series: Array<{
    run_date:    string;
    total:       number;
    would_trade: number;
    blocked:     number;
    underlyings: number;
    strategies:  number;
  }>;
}


function _humanDate(iso: string): string {
  const d = new Date(iso + "T12:00:00Z");
  return d.toLocaleDateString(undefined, {
    weekday: "short", day: "numeric", month: "short", year: "numeric",
  });
}


export default function OptionsJournalEvaluatorHistory() {
  const { data, isLoading } = useQuery<DailyCountsResponse>({
    queryKey: ["options", "analytics", "daily-counts", 30],
    queryFn:  () => apiGet("/options/analytics/daily-counts?days=30"),
    staleTime: 60_000, refetchOnWindowFocus: false,
  });

  const series = data?.series ?? [];

  return (
    <section
      className="u-card opt-journal-history"
      data-test="options-journal-evaluator-history"
    >
      <header className="opt-card-header" style={{ marginBottom: 12 }}>
        <span className="opt-card-eyebrow">Evaluator history</span>
        <span className="opt-card-meta">
          {isLoading
            ? "loading…"
            : `${series.length} cycle${series.length === 1 ? "" : "s"} on record`}
        </span>
      </header>

      {!isLoading && series.length === 0 && (
        <p className="u-body" style={{ color: "var(--fg-3)" }}>
          The evaluator has not yet produced a persisted run on
          record. The first cycle to fire (after OPTIONS_SHADOW_EVAL_ENABLED
          becomes True and a scheduler row exists) will appear here.
        </p>
      )}

      {series.length > 0 && (
        <ul className="opt-journal-history-list">
          {series.map((row) => (
            <li key={row.run_date} className="opt-journal-history-row">
              <span className="opt-journal-history-date">
                {_humanDate(row.run_date)}
              </span>
              <span className="opt-journal-history-meta">
                <span className="opt-journal-history-num">
                  {row.total.toLocaleString()}
                </span>{" "}
                contracts evaluated
              </span>
              <span className="opt-journal-history-meta">
                <span className="opt-journal-history-num">
                  {row.would_trade.toLocaleString()}
                </span>{" "}
                passed all filters
              </span>
              <span className="opt-journal-history-meta opt-journal-history-meta-sub">
                {row.underlyings} underlying{row.underlyings === 1 ? "" : "s"} ·
                {" "}{row.strategies} strateg{row.strategies === 1 ? "y" : "ies"}
              </span>
            </li>
          ))}
        </ul>
      )}

      {series.length > 0 && series.length < 7 && (
        <p
          className="u-caption-2"
          style={{ marginTop: 14, color: "var(--fg-3)" }}
        >
          Sparse history is the truth — observation began
          {" "}{series.length === 1
              ? "this cycle"
              : "recently"}.
          {" "}Cycles accumulate one entry per weekday at 21:45 UTC.
        </p>
      )}
    </section>
  );
}
