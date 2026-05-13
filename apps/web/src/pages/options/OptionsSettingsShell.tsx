// Phase 6b-3-b — Settings surface placeholder. Body lands in 6b-3-i.
// Stays minimal by design — no settings-product bloat.

import OptionsSurfacePlaceholder from
  "@/components/options/OptionsSurfacePlaceholder";

export default function OptionsSettingsShell() {
  return (
    <OptionsSurfacePlaceholder
      surface="Settings"
      question="How is the engine configured?"
      shipsIn="6b-3-i"
      one_liner={
        "Read-only configuration audit. Universe, provider, " +
        "liquidity profile thresholds, scheduler rows. Operator " +
        "knobs are intentionally absent until they earn their place."
      }
      willContain={[
        "Active universe (5 ETFs, read-only)",
        "Active provider + provider_version",
        "Liquidity profile thresholds (per provider)",
        "Scheduler row table (read-only audit view)",
      ]}
    />
  );
}
