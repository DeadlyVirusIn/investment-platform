// Phase 6b-3-f — Evidence chronology layer.
//
// Per-day accumulation log. Renders the sparse real history (today
// = 2 rows). Quietly scientific tone — no badges, no celebration,
// no streaks.

import { useQuery } from "@tanstack/react-query";

import { apiGet } from "@/lib/api";


interface DailyCountsResponse {
  series: Array<{
    run_date:    string;
    total:       number;
    would_trade: number;
    underlyings: number;
    strategies:  number;
  }>;
  count: number;
}


function _humanDate(iso: string): string {
  const d = new Date(iso + "T12:00:00Z");
  return d.toLocaleDateString(undefined, {
    weekday: "short", day: "numeric", month: "short", year: "numeric",
  });
}


export default function OptionsLearningChronology() {
  const { data } = useQuery<DailyCountsResponse>({
    queryKey: ["options", "analytics", "daily-counts", 30],
    queryFn:  () => apiGet("/options/analytics/daily-counts?days=30"),
    staleTime: 60_000, refetchOnWindowFocus: false,
  });

  const series = data?.series ?? [];

  return (
    <section
      className="u-card opt-learning-chronology"
      data-test="options-learning-chronology"
    >
      <header className="opt-card-header" style={{ marginBottom: 14 }}>
        <span className="opt-card-eyebrow">Evidence chronology</span>
        <span className="opt-card-meta">
          {series.length} qualifying day{series.length === 1 ? "" : "s"} on record
        </span>
      </header>

      {series.length === 0 && (
        <p className="u-body" style={{ color: "var(--fg-3)" }}>
          No coherent observation cycles yet on record.
        </p>
      )}

      {series.length > 0 && (
        <ol className="opt-chronology-list">
          {series.map((row) => (
            <li key={row.run_date} className="opt-chronology-row">
              <div className="opt-chronology-date">
                {_humanDate(row.run_date)}
              </div>
              <div className="opt-chronology-body">
                Coherent batch observed; evaluator persisted{" "}
                <span className="opt-chronology-num">
                  {row.total.toLocaleString()}
                </span>{" "}
                contract decisions
                {row.would_trade > 0 && (
                  <>
                    {" "}of which{" "}
                    <span className="opt-chronology-num">
                      {row.would_trade.toLocaleString()}
                    </span>{" "}
                    cleared all filters
                  </>
                )}
                .
              </div>
            </li>
          ))}
        </ol>
      )}

      <p
        className="u-caption-2"
        style={{ marginTop: 16, color: "var(--fg-3)" }}
      >
        Each entry is one qualifying observation cycle. Cycles
        accumulate one per weekday at 21:45 UTC. The system requires
        a minimum number of these before any learning gate can pass.
      </p>
    </section>
  );
}
