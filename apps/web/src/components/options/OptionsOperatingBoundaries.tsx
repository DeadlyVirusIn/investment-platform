// Phase 6b-3-i — Declared operating boundaries.
//
// 5 trust-primitive flags rendered as POLICY rows, not toggles.
// Each row has:
//   - the policy name
//   - its current value
//   - whether it is structurally immutable in v1
//   - a one-line policy explanation
//
// Per the queued direction:
//   "Constraints are trust primitives... Configuration should read
//    like policy, not preferences."

import { useOptionsPipelineStatus } from "@/lib/options/hooks";


interface PolicyRow {
  name:        string;
  value:       string;
  state:       "ok" | "warn" | "neutral";
  immutable:   boolean;
  explanation: string;
}


export default function OptionsOperatingBoundaries() {
  const { data, isLoading } = useOptionsPipelineStatus();

  if (isLoading || !data) {
    return (
      <section className="u-card opt-settings-boundaries">
        <div className="u-label">OPERATING BOUNDARIES</div>
        <p className="u-body" style={{ color: "var(--fg-3)" }}>
          loading…
        </p>
      </section>
    );
  }

  const rows: PolicyRow[] = [
    {
      name:        "Paper-only",
      value:       data.options_paper_only ? "true" : "false",
      state:       data.options_paper_only ? "ok" : "warn",
      immutable:   true,
      explanation: "All options activity routes through the paper " +
                   "broker. Live execution is structurally absent " +
                   "from the engine — no broker module exists.",
    },
    {
      name:        "Execution master gate",
      value:       data.options_enabled ? "enabled" : "disabled",
      state:       data.options_enabled ? "warn" : "ok",
      immutable:   false,
      explanation: "When enabled, scheduler-fired chain-ingest and " +
                   "shadow-eval jobs perform real work. When " +
                   "disabled, both jobs no-op skip with a logged " +
                   "reason.",
    },
    {
      name:        "ML can affect trades",
      value:       data.options_ml_can_affect_trades ? "true" : "false",
      state:       data.options_ml_can_affect_trades ? "warn" : "ok",
      immutable:   true,
      explanation: "Permanent v1 lock. ML output is observational " +
                   "only — it never adjusts position sizing, never " +
                   "promotes candidates, never modifies decisions.",
    },
    {
      name:        "Shadow persistence",
      value:       data.options_shadow_eval_enabled ? "active" : "paused",
      state:       "neutral",
      immutable:   false,
      explanation: "Persists shadow-eval decisions to " +
                   "options_shadow_decision_log when active. " +
                   "Independent of the execution master gate " +
                   "(decoupled in Phase 6a).",
    },
    {
      name:        "ML learning gate",
      value:       "disabled",
      state:       "ok",
      immutable:   false,
      explanation: "Even when all readiness gates pass on " +
                   "/options/learning, the ML output remains " +
                   "advisory until ML_OPTIONS_LEARNING_ENABLED is " +
                   "set by the operator AND the gate composition " +
                   "evaluates to True.",
    },
  ];

  return (
    <section
      className="u-card opt-settings-boundaries"
      data-test="options-operating-boundaries"
    >
      <header className="opt-card-header" style={{ marginBottom: 16 }}>
        <span className="opt-card-eyebrow">Operating boundaries</span>
        <span className="opt-card-meta">5 declared policies</span>
      </header>

      <ul className="opt-boundaries-list">
        {rows.map((r) => (
          <li
            key={r.name}
            className="opt-boundary-row"
            data-state={r.state}
          >
            <div className="opt-boundary-head">
              <span className="opt-boundary-name">{r.name}</span>
              {r.immutable && (
                <span className="opt-boundary-immutable">
                  immutable in v1
                </span>
              )}
              <span className="opt-boundary-value">{r.value}</span>
            </div>
            <p className="opt-boundary-explanation">{r.explanation}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}
