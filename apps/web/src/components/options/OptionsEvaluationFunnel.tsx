// Phase 6b-3-h — Today's evaluation funnel (methodological proof point).
//
// Calm narrative funnel. NOT a chart. NOT a sankey. NOT animated.
// Each stage is a labelled row showing how the chain population
// reduces from raw quotes to ranked candidates today.
//
// Renders the most recent qualifying day's funnel using
// /analytics/daily-counts + /analytics/by-rejection. Honest sparseness:
// if today has no run yet, surface the most recent.

import { useQuery } from "@tanstack/react-query";

import { apiGet } from "@/lib/api";


interface DailyCountsShape {
  series: Array<{
    run_date:    string;
    total:       number;
    would_trade: number;
    blocked:     number;
    underlyings: number;
  }>;
}

interface RejectionShape {
  run_date:   string;
  rejections: Array<{ reason: string; today: number }>;
}


function _humanDate(iso: string): string {
  const d = new Date(iso + "T12:00:00Z");
  return d.toLocaleDateString(undefined, {
    weekday: "short", day: "numeric", month: "short", year: "numeric",
  });
}


export default function OptionsEvaluationFunnel() {
  const dailyQ = useQuery<DailyCountsShape>({
    queryKey: ["options", "analytics", "daily-counts", 7],
    queryFn:  () => apiGet("/options/analytics/daily-counts?days=7"),
    staleTime: 60_000, refetchOnWindowFocus: false,
  });

  const recent = dailyQ.data?.series?.[0];
  const dateForRej = recent?.run_date;

  const rejQ = useQuery<RejectionShape>({
    queryKey: ["options", "analytics", "by-rejection-funnel", dateForRej],
    queryFn:  () => apiGet(
      `/options/analytics/by-rejection?date=${dateForRej}&days=1`),
    staleTime: 60_000, refetchOnWindowFocus: false,
    enabled: !!dateForRej,
  });

  const topReason = rejQ.data?.rejections?.[0];

  return (
    <section
      className="u-card opt-lab-funnel"
      data-test="options-evaluation-funnel"
    >
      <header className="opt-card-header" style={{ marginBottom: 14 }}>
        <span className="opt-card-eyebrow">
          Today's evaluation funnel
        </span>
        <span className="opt-card-meta">
          {recent ? _humanDate(recent.run_date) : "no cycle on record"}
        </span>
      </header>

      {!recent && (
        <p className="u-body" style={{ color: "var(--fg-3)" }}>
          The evaluator has not yet produced a persisted run. The
          first cycle to fire will appear here as a labelled
          reduction from raw chain rows down to ranked candidates.
        </p>
      )}

      {recent && (
        <ol className="opt-funnel-list">
          <li className="opt-funnel-row">
            <div className="opt-funnel-num">
              {recent.total.toLocaleString()}
            </div>
            <div className="opt-funnel-body">
              <div className="opt-funnel-stage">Contract decisions</div>
              <div className="opt-funnel-detail">
                Every chain quote that survived ingest is evaluated
                against every applicable strategy template.
              </div>
            </div>
          </li>
          <li className="opt-funnel-row">
            <div className="opt-funnel-num opt-funnel-num-warn">
              {recent.blocked.toLocaleString()}
            </div>
            <div className="opt-funnel-body">
              <div className="opt-funnel-stage">Filtered out</div>
              <div className="opt-funnel-detail">
                {topReason
                  ? <>Top reason: <code>{topReason.reason
                      .replace("blocked:", "")}</code> ({topReason.today.toLocaleString()} blocked).</>
                  : "Per-reason breakdown lives on Research."}
              </div>
            </div>
          </li>
          <li className="opt-funnel-row">
            <div className="opt-funnel-num opt-funnel-num-ok">
              {recent.would_trade.toLocaleString()}
            </div>
            <div className="opt-funnel-body">
              <div className="opt-funnel-stage">Cleared every filter</div>
              <div className="opt-funnel-detail">
                Ranked by per-strategy setup quality and capped at
                top-N per underlying.
              </div>
            </div>
          </li>
        </ol>
      )}

      <p
        className="u-caption-2"
        style={{ marginTop: 16, color: "var(--fg-3)" }}
      >
        The funnel is deterministic. Same chain data + same filter
        thresholds always reduces to the same number — no model
        sampling, no probabilistic skipping.
      </p>
    </section>
  );
}
