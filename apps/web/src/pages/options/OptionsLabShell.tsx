// Phase 6b-3-b — Lab surface placeholder. Body lands in 6b-3-g.

import OptionsSurfacePlaceholder from
  "@/components/options/OptionsSurfacePlaceholder";

export default function OptionsLabShell() {
  return (
    <OptionsSurfacePlaceholder
      surface="Lab"
      question="What can the engine evaluate?"
      shipsIn="6b-3-g"
      one_liner={
        "Strategy templates and the evaluation flow that takes a " +
        "raw chain to a ranked observation. Educational and " +
        "reference — not where today's decisions live."
      }
      willContain={[
        "Strategy catalog (3 supported families with per-strategy " +
          "criteria)",
        "Six-step evaluation pipeline visualisation",
        "Per-strategy historical performance (gated on learning " +
          "readiness)",
        "Strategy observatory deep-dive",
      ]}
    />
  );
}
