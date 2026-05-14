// Phase 6b-3-f — Readiness gates as a scientific table.
//
// Replaces the progress-bar OptionsLearningGate (Step 12). Per the
// queued direction:
//   "Avoid progress-bar psychology. No gamification energy. No
//    achievement-system feeling. No celebratory UI."
//
// Each gate is a row in a calm 4-column table:
//
//   GATE                     | THRESHOLD | OBSERVED | STATUS
//   Closed paper trades       | >= 30      | 0        | insufficient evidence
//   Distinct strategies (>=3) | >= 3       | 0        | insufficient evidence
//   ...
//
// No bars. No progress fill. No green-arrow-up. Just facts and a
// neutral status word.

import { useQuery } from "@tanstack/react-query";

import { apiGet } from "@/lib/api";


interface GateBase {
  pass: boolean;
}

interface SimpleGate extends GateBase {
  value:  number;
  target: number;
}

interface DistinctStratGate extends GateBase {
  value:                       number;
  target:                      number;
  per_strategy_target:         number;
  top_strategy_closed_count:   number;
}

interface ProviderStabilityGate extends GateBase {
  provider_versions_in_30d: number;
  days_observed:            number;
  target_days:              number;
}

interface UniverseConsistencyGate extends GateBase {
  out_of_universe_rows_30d: number;
}

interface ReadinessResponse {
  all_gates_pass: boolean;
  ml_options_learning_enabled: boolean;
  gates: {
    closed_trades:                     SimpleGate;
    distinct_strategies_meeting_floor: DistinctStratGate;
    trading_days:                      SimpleGate;
    coherent_batch_days:               SimpleGate;
    feature_daily_coverage_days:       SimpleGate;
    provider_stability_window:         ProviderStabilityGate;
    universe_consistency:              UniverseConsistencyGate;
  };
}


interface RowSpec {
  gate:        string;
  threshold:   string;
  observed:    string;
  pass:        boolean;
  rationale:   string;
}


function _rows(r: ReadinessResponse): RowSpec[] {
  const g = r.gates;
  return [
    {
      gate:      "Closed paper trades",
      threshold: `≥ ${g.closed_trades.target}`,
      observed:  String(g.closed_trades.value),
      pass:      g.closed_trades.pass,
      rationale: "Calibration requires real outcome distribution.",
    },
    {
      gate:      "Distinct strategies meeting per-strategy floor",
      threshold: `≥ ${g.distinct_strategies_meeting_floor.target}` +
                 ` strategies × ` +
                 `${g.distinct_strategies_meeting_floor.per_strategy_target}` +
                 ` closed each`,
      observed:  `${g.distinct_strategies_meeting_floor.value}` +
                 ` (top: ${g.distinct_strategies_meeting_floor.top_strategy_closed_count})`,
      pass:      g.distinct_strategies_meeting_floor.pass,
      rationale: "Avoids overfitting to one strategy template.",
    },
    {
      gate:      "Trading-day coverage",
      threshold: `≥ ${g.trading_days.target}`,
      observed:  String(g.trading_days.value),
      pass:      g.trading_days.pass,
      rationale: "Spans regime variation (>= 6 weeks).",
    },
    {
      gate:      "Coherent-batch days",
      threshold: `≥ ${g.coherent_batch_days.target}`,
      observed:  String(g.coherent_batch_days.value),
      pass:      g.coherent_batch_days.pass,
      rationale: "Phase B invariant must hold across enough days " +
                 "for the dataset to be trainable.",
    },
    {
      gate:      "Feature-daily coverage",
      threshold: `≥ ${g.feature_daily_coverage_days.target}`,
      observed:  String(g.feature_daily_coverage_days.value),
      pass:      g.feature_daily_coverage_days.pass,
      rationale: "iv_rank and similar features need rolling history.",
    },
    {
      gate:      "Provider stability window",
      threshold: `single provider_version for ≥ ` +
                 `${g.provider_stability_window.target_days} days`,
      observed:  `${g.provider_stability_window.days_observed} days · ` +
                 `${g.provider_stability_window.provider_versions_in_30d}` +
                 ` version${
                   g.provider_stability_window.provider_versions_in_30d === 1
                     ? "" : "s"} in window`,
      pass:      g.provider_stability_window.pass,
      rationale: "Prevents learning across provider regimes.",
    },
    {
      gate:      "Universe consistency",
      threshold: "0 out-of-universe rows in trailing 30 days",
      observed:  `${g.universe_consistency.out_of_universe_rows_30d.toLocaleString()}` +
                 " out-of-universe rows",
      pass:      g.universe_consistency.pass,
      rationale: "Guarantees evaluation pool stable across the " +
                 "training window.",
    },
  ];
}


export default function OptionsReadinessGatesTable() {
  const { data, isLoading } = useQuery<ReadinessResponse>({
    queryKey: ["options", "analytics", "learning-readiness"],
    queryFn:  () => apiGet("/options/analytics/learning-readiness"),
    staleTime: 60_000, refetchOnWindowFocus: false,
  });

  if (isLoading || !data) {
    return (
      <section className="u-card opt-readiness-card">
        <div className="u-label">READINESS GATES</div>
        <p className="u-body" style={{ color: "var(--fg-3)" }}>
          loading…
        </p>
      </section>
    );
  }

  const rows = _rows(data);

  return (
    <section
      className="u-card opt-readiness-card"
      data-test="options-readiness-gates-table"
    >
      <header className="opt-card-header" style={{ marginBottom: 16 }}>
        <span className="opt-card-eyebrow">Readiness gates</span>
        <span className="opt-card-meta">
          {data.all_gates_pass
            ? "all gates satisfied · awaiting operator flag"
            : "advisory · no claim of intelligence yet"}
        </span>
      </header>

      <table className="opt-readiness-table" role="table">
        <thead>
          <tr>
            <th scope="col" className="opt-readiness-th">Gate</th>
            <th scope="col" className="opt-readiness-th">Threshold</th>
            <th scope="col" className="opt-readiness-th">Observed</th>
            <th scope="col" className="opt-readiness-th">Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr
              key={r.gate}
              className="opt-readiness-tr"
              data-pass={r.pass ? "true" : "false"}
            >
              <td className="opt-readiness-td-gate">
                <div className="opt-readiness-gate-name">{r.gate}</div>
                <div className="opt-readiness-gate-rationale">
                  {r.rationale}
                </div>
              </td>
              <td className="opt-readiness-td-threshold">{r.threshold}</td>
              <td className="opt-readiness-td-observed">{r.observed}</td>
              <td className="opt-readiness-td-status">
                {r.pass ? "satisfied" : "insufficient evidence"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
