// Phase 6b-3-b — Research surface placeholder. Body lands in 6b-3-d.

import OptionsSurfacePlaceholder from
  "@/components/options/OptionsSurfacePlaceholder";

export default function OptionsResearchShell() {
  return (
    <OptionsSurfacePlaceholder
      surface="Research"
      question="What setups look strongest?"
      shipsIn="6b-3-d"
      one_liner={
        "Deep candidate workstation. The full ranked list with " +
        "thesis, provenance, rejection pressure, and decision " +
        "framing — all the depth that doesn't belong on the " +
        "Overview executive briefing."
      }
      willContain={[
        "Full 25-candidate ranked list (collapsible by strategy)",
        "Rejection-reason histogram with day-over-day deltas",
        "Decision support + decision framing per candidate",
        "Scenario replay (chain × strategy reproductions)",
        "Per-candidate detail drawer with full provenance",
      ]}
    />
  );
}
