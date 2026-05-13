// Phase 6b-3-b — Learning surface placeholder. Body lands in 6b-3-f.

import OptionsSurfacePlaceholder from
  "@/components/options/OptionsSurfacePlaceholder";

export default function OptionsLearningShell() {
  return (
    <OptionsSurfacePlaceholder
      surface="Learning"
      question="What is the system learning?"
      shipsIn="6b-3-f"
      one_liner={
        "Honest, gated readiness desk. Each insight unlocks only " +
        "after enough real evidence accumulates — never before. " +
        "No estimated, no promised, no AI-magic theatre."
      }
      willContain={[
        "Seven readiness gates with live progress (closed trades, " +
          "strategy diversity, batch coherence, feature coverage, " +
          "provider stability, universe consistency, trading days)",
        "Provider stability time series (last 30 days)",
        "Universe consistency time series (last 30 days)",
        "When all gates pass: win rate per strategy with 95% CI, " +
          "calibration plot, best/worst contributors, rejection-" +
          "reason historical accuracy",
      ]}
    />
  );
}
