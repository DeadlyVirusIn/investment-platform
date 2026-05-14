// Phase 6b-3-i — Settings surface (declared governance).
//
// Smallest surface in the workspace by design.
//
// Composition (4 layers, calm institutional):
//   1. Pulse strip               "Governance · paper-only · execution
//                                 disabled · shadow active"
//   2. Operating boundaries      5 declared policies as institutional
//                                 trust primitives (immutable flags
//                                 explicitly labelled)
//   3. Declared configuration    Universe · Active provider ·
//                                 Freshness bound · Scheduler
//   4. Pathways                  two editorial doorways
//
// Per the queued direction:
//   "Settings should NOT feel like an admin panel. It should feel
//    like the declared operating assumptions and boundaries of the
//    system. Configuration should read like policy, not preferences.
//    The page should feel like system governance and declared
//    boundaries, not application settings."
//
// Discipline:
//   * Read-only. Zero mutation. Zero toggles. Zero forms.
//   * Every value sourced from existing endpoints.
//   * No new endpoints required.

import OptionsSettingsPulse from
  "@/components/options/OptionsSettingsPulse";
import OptionsOperatingBoundaries from
  "@/components/options/OptionsOperatingBoundaries";
import OptionsDeclaredConfig from
  "@/components/options/OptionsDeclaredConfig";
import OptionsSettingsPathways from
  "@/components/options/OptionsSettingsPathways";


export default function OptionsSettingsPage() {
  return (
    <div className="opt-settings" data-test="options-settings-page">
      {/* 1. Pulse — single line of governance posture */}
      <OptionsSettingsPulse />

      {/* 2. Operating boundaries — 5 declared policies as
            institutional trust primitives */}
      <OptionsOperatingBoundaries />

      {/* 3. Declared configuration — universe + provider +
            freshness bound + scheduler authorization */}
      <OptionsDeclaredConfig />

      {/* 4. Pathways — only two; Settings deliberately ends short */}
      <OptionsSettingsPathways />
    </div>
  );
}
