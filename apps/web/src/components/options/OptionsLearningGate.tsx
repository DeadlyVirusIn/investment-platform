// Phase Opt-C1 Step 12 — Learning Desk gate UI.
//
// Communicates "the system earns intelligence over time" via 4
// progress bars showing distance to learning threshold. Calm,
// statistical, non-predictive.
//
// Reads /api/options/learning/summary (Step 13). When enabled=false,
// shows progress bars + reasoning. When enabled=true (post-threshold +
// flag), shows aggregates (placeholder shape until Phase Opt-C2 wires
// real Wilson-CI computation).

import { useQuery } from "@tanstack/react-query";

import { apiGet } from "@/lib/api";


interface LearningGate {
  closed_trades: number;
  closed_trades_target: number;
  distinct_strategies_meeting_floor: number;
  distinct_strategies_target: number;
  top_strategy_closed_count: number;
  per_strategy_target: number;
  trading_days: number;
  trading_days_target: number;
}


interface LearningSummary {
  enabled: boolean;
  ml_options_learning_enabled: boolean;
  thresholds_met: boolean;
  gate?: LearningGate;
  per_strategy_breakdown?: Array<{ strategy_name: string; closed_count: number }>;
  reason?: string;
  notice: string;
  // When enabled — placeholders for forward-compat
  win_rate_by_strategy?: unknown[];
  calibration?: unknown[];
}


function useOptionsLearningSummary() {
  return useQuery<LearningSummary>({
    queryKey: ["options", "learning", "summary"],
    queryFn: () => apiGet<LearningSummary>("/options/learning/summary"),
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });
}


function _Bar({
  k, v, target,
}: { k: string; v: number; target: number }) {
  const pct = target > 0 ? Math.min(100, (v / target) * 100) : 0;
  const met = v >= target;
  return (
    <div className="opt-learning-bar-row">
      <div className="opt-learning-bar-head">
        <span className="opt-learning-bar-k">{k}</span>
        <span className={"opt-learning-bar-v" + (met ? " is-met" : "")}>
          {v} / {target}{met && " ✓"}
        </span>
      </div>
      <div className="opt-learning-bar-track">
        <div
          className="opt-learning-bar-fill"
          data-met={met ? "true" : "false"}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}


export default function OptionsLearningGate() {
  const { data, isLoading } = useOptionsLearningSummary();

  if (isLoading || !data) {
    return (
      <section className="u-card opt-card" data-test="options-learning-gate">
        <header className="opt-card-header">
          <span className="opt-card-eyebrow">Learning desk</span>
        </header>
        <p className="opt-empty-body">loading…</p>
      </section>
    );
  }

  // Enabled → aggregate display (placeholder until Opt-C2)
  if (data.enabled) {
    return (
      <section className="u-card opt-card" data-test="options-learning-gate">
        <header className="opt-card-header">
          <span className="opt-card-eyebrow">Learning desk</span>
          <span className="opt-card-meta is-pos">active</span>
        </header>
        <p className="opt-explain-body">
          Learning thresholds met. Aggregate insights are computed at
          runtime in a later phase. For now the page acknowledges
          activation without displaying placeholder numbers.
        </p>
      </section>
    );
  }

  // Below threshold → gate UI
  const g = data.gate!;
  return (
    <section className="u-card opt-card" data-test="options-learning-gate">
      <header className="opt-card-header">
        <span className="opt-card-eyebrow">Learning desk</span>
        <span className="opt-card-meta">
          {`${g.closed_trades}/${g.closed_trades_target} closed · gated`}
        </span>
      </header>

      <p className="opt-explain-body" style={{ marginBottom: 10 }}>
        Insights unlock after the engine produces a meaningful sample
        of closed paper trades. The system reports calibrated metrics
        (win rate per strategy with 95% confidence interval, calibration
        plot, strategy scoreboard) only when all four gates pass.
      </p>

      <div className="opt-learning-bars">
        <_Bar
          k="Closed trades"
          v={g.closed_trades}
          target={g.closed_trades_target}
        />
        <_Bar
          k="Distinct strategies meeting floor"
          v={g.distinct_strategies_meeting_floor}
          target={g.distinct_strategies_target}
        />
        <_Bar
          k="Per-strategy floor (top strategy)"
          v={g.top_strategy_closed_count}
          target={g.per_strategy_target}
        />
        <_Bar
          k="Trading-day coverage"
          v={g.trading_days}
          target={g.trading_days_target}
        />
      </div>

      {data.reason && (
        <p className="opt-empty-body" style={{ marginTop: 10 }}>
          {data.reason}
        </p>
      )}

      <div className="opt-learning-foot">
        <strong>When all gates pass</strong>, this section will surface:
        win rate per strategy with 95% CI · calibration plot
        (predicted vs realized · 5 bins, ≥10 samples per bin) ·
        best/worst strategy contributors · rejection-reason
        historical accuracy.
      </div>
    </section>
  );
}
