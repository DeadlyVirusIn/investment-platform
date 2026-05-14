// Phase 6b-3-i — Settings pulse strip.
//
// Single line. Governance-toned, not admin-panel-toned.
//
//   "GOVERNANCE · paper-only · execution disabled · shadow active"

import { useOptionsPipelineStatus } from "@/lib/options/hooks";


export default function OptionsSettingsPulse() {
  const { data } = useOptionsPipelineStatus();

  const paperOnly = data?.options_paper_only ?? false;
  const execEnabled = data?.options_enabled ?? false;
  const shadowOn = data?.options_shadow_eval_enabled ?? false;

  return (
    <div
      className="opt-research-pulse-strip opt-settings-pulse"
      data-test="options-settings-pulse"
    >
      <span className="opt-pulse-eyebrow">GOVERNANCE</span>
      <span className="opt-pulse-sep">·</span>
      <span className="opt-pulse-text">
        {paperOnly ? "paper-only" : "live-capable"}
      </span>
      <span className="opt-pulse-sep">·</span>
      <span className="opt-pulse-text">
        execution {execEnabled ? (
          <strong className="opt-pulse-warn">enabled</strong>
        ) : (
          "disabled"
        )}
      </span>
      <span className="opt-pulse-sep">·</span>
      <span className="opt-pulse-text">
        shadow log{" "}
        {shadowOn ? (
          <span className="opt-pulse-ok">active</span>
        ) : (
          "paused"
        )}
      </span>
    </div>
  );
}
