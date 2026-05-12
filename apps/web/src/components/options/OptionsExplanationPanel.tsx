// Phase Opt-A — Options Explanation Panel.
//
// Plain-English answer to "why is nothing showing?" and "what
// needs to happen?". Renders ONLY when the engine is dormant or
// unscheduled (active engines don't need this guidance).

import { useOptionsPipelineStatus } from "@/lib/options/hooks";


export default function OptionsExplanationPanel() {
  const { data } = useOptionsPipelineStatus();

  if (!data) return null;
  // Only render when engine is dormant / unscheduled.
  if (data.engine_state === "active" || data.engine_state === "starting") {
    return null;
  }

  return (
    <section className="u-card opt-card" data-test="options-explanation">
      <header className="opt-card-header">
        <span className="opt-card-eyebrow">Why nothing is showing</span>
      </header>

      <div className="opt-explain-block">
        <p className="opt-explain-headline">
          The options subsystem is built but not running.
        </p>
        <p className="opt-explain-body">
          Backend routes, DB schema, frontend pages, and operator
          scripts all exist. What's missing is{" "}
          <strong>the daily cron wiring + the master flag flip</strong>{" "}
          that would activate the pipeline.
        </p>
      </div>

      <div className="opt-explain-block">
        <p className="opt-explain-headline">
          What needs to happen before trades appear
        </p>
        <ol className="opt-explain-list">
          <li>
            Operator approves Phase Opt-B (separate decision after this
            page redesign lands).
          </li>
          <li>
            <code>OPTIONS_ENABLED=true</code> set in <code>.env</code>.
          </li>
          <li>
            ThetaData API key verified.
          </li>
          <li>
            Three new <code>job_schedule</code> rows added (chain
            snapshot, shadow eval, paper exec) with Mon-Fri cron
            expressions.
          </li>
          <li>
            One full daily cycle completes successfully — chain
            snapshot → shadow decisions → paper exec.
          </li>
        </ol>
      </div>

      <div className="opt-explain-block">
        <p className="opt-explain-body opt-explain-foot">
          <strong>This is paper-only.</strong>{" "}
          <code>OPTIONS_ML_CAN_AFFECT_TRADES</code> is locked off. No
          live broker integration exists in the codebase.
        </p>
      </div>
    </section>
  );
}
