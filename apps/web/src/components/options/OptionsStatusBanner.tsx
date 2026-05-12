// Phase Opt-A — Options Engine State Banner.
//
// Single truthful sentence at the top of /options. Renders one of:
//   - dormant      → "Options engine is dormant — OPTIONS_ENABLED is off…"
//   - unscheduled  → "Options flag is on but no daily jobs are scheduled…"
//   - starting     → "Options pipeline is scheduled — collection in progress…"
//   - active       → "Options engine is active — N shadow decisions, M paper trades…"
//
// No flashing, no panic colors. Tone modulated by engine_state:
//   - dormant      → neutral (calm, factual)
//   - unscheduled  → warning (operator action expected)
//   - starting     → neutral
//   - active       → success
//
// The sentence comes from the backend's engine_state_sentence field
// — single source of truth so UI never drifts from server reality.

import { useOptionsPipelineStatus } from "@/lib/options/hooks";


export default function OptionsStatusBanner() {
  const { data, isLoading, isError } = useOptionsPipelineStatus();

  if (isLoading || !data) {
    return (
      <div className="opt-status-banner opt-status-banner--neutral" role="status">
        <span className="opt-status-banner-eyebrow">Engine state</span>
        <span className="opt-status-banner-sentence">checking…</span>
      </div>
    );
  }
  if (isError) {
    return (
      <div className="opt-status-banner opt-status-banner--neutral" role="status">
        <span className="opt-status-banner-eyebrow">Engine state</span>
        <span className="opt-status-banner-sentence">
          /api/options/pipeline-status unreachable
        </span>
      </div>
    );
  }

  const tone =
    data.engine_state === "active"      ? "success"
    : data.engine_state === "unscheduled" ? "warning"
    :                                       "neutral";

  return (
    <div
      className={`opt-status-banner opt-status-banner--${tone}`}
      role="status"
      data-engine-state={data.engine_state}
    >
      <span className="opt-status-banner-eyebrow">Engine state</span>
      <span className="opt-status-banner-sentence">
        {data.engine_state_sentence}
      </span>
    </div>
  );
}
