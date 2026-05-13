// Phase 6b-3-b — Journal surface placeholder. Body lands in 6b-3-e.

import OptionsSurfacePlaceholder from
  "@/components/options/OptionsSurfacePlaceholder";

export default function OptionsJournalShell() {
  return (
    <OptionsSurfacePlaceholder
      surface="Journal"
      question="How are paper trades evolving?"
      shipsIn="6b-3-e"
      one_liner={
        "Institutional paper-trade journal. Every observation the " +
        "engine has produced, every lifecycle transition, every " +
        "outcome — held in one warm, narrative surface so the " +
        "history of the system is legible."
      }
      willContain={[
        "Paper-trade tracker (the 5-group workflow component)",
        "Per-trade lifecycle drawer (replaces hash deep-link)",
        "Performance attribution panel (gated on ≥10 closes)",
        "Outcome distribution and strategy-attribution view",
      ]}
    />
  );
}
