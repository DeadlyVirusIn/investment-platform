// Phase 6b-3-c — Options Overview (executive briefing surface).
//
// Three sections only. The page intentionally ENDS EARLY.
//   1. Research Pulse Hero       (6b-3-a)
//   2. Top 3 candidate cards     (existing OptionsResearchCandidates)
//   3. Editorial doorway strip   (6b-3-c, sentence + arrow only)
//
// What this page no longer renders (relocated, not lost):
//   * OptionsStatusBanner          → deleted (superseded by hero)
//   * OptionsRejectionsSection     → /options/research (6b-3-d)
//   * OptionsTrackerWorkflow       → /options/journal  (6b-3-e)
//   * OptionsRejectedCandidatesGroup → /options/research (6b-3-d)
//   * OptionsLifecycleTimeline     → /options/journal  (6b-3-e drawer)
//   * OptionsLearningGate          → /options/learning (6b-3-f, replaced
//                                     by OptionsLearningReadinessGate)
//   * OptionsStrategyCatalog       → /options/lab      (6b-3-g)
//   * OptionsEvaluationFlow        → /options/lab      (6b-3-g)
//   * OptionsDiagnosticsAccordion  → /options/ops      (6b-3-h, no longer
//                                     surfaced from Overview)
//   * OptionsExplanationPanel      → deleted (superseded by hero
//                                     calm sentence)
//
// Discipline:
//   * Read-only. Zero mutation. Zero new endpoints.
//   * No buttons with handlers. Anchors and routes only.
//   * OPTIONS_ENABLED stays absent; paper-exec path unreachable.

import OptionsResearchPulseHero from
  "@/components/options/OptionsResearchPulseHero";
import OptionsResearchCandidates from
  "@/components/options/OptionsResearchCandidates";
import OptionsDoorwayStrip from
  "@/components/options/OptionsDoorwayStrip";

// Copilot Phase A — Today-page hero + top-opportunity spotlight.
// Both render from existing read-only endpoints. Zero execution
// coupling. Existing components (PulseHero, ResearchCandidates,
// DoorwayStrip) remain below as the secondary layer for now —
// they will be consolidated in Phase B (Opportunities surface).
import OptionsHeroPulse from
  "@/components/options/copilot/OptionsHeroPulse";
import OptionsOpportunitySpotlight from
  "@/components/options/copilot/OptionsOpportunitySpotlight";
import OptionsOrientationCard from
  "@/components/options/copilot/OptionsOrientationCard";


export default function OptionsOverviewPage() {
  // H-refine: legacy widgets gated behind ?view=working. Default
  // Today page = orientation + hero + spotlight only. The pre-Copilot
  // research pulse / candidates / doorway strip remain reachable for
  // engineers wanting the engine view without losing the components.
  const showLegacy = (() => {
    try {
      return new URLSearchParams(window.location.search).get("view") === "working";
    } catch {
      return false;
    }
  })();

  return (
    // Phase J — Today wrapped in `.opt-today` editorial container.
    // Contained measure + asymmetric padding + section pacing. All Phase J
    // typography and accent rules are scoped under this class so other
    // surfaces remain on the existing H sans system until they earn their
    // own art-direction pass.
    <div
      className="opt-overview opt-today"
      data-test="options-overview-page"
    >
      {/* H.6 — first-visit orientation. Dismisses permanently. */}
      <OptionsOrientationCard surface="today" />

      {/* Copilot hero — AI posture + premium environment + signal count */}
      <OptionsHeroPulse />

      {/* Top opportunities — Copilot card grid */}
      <OptionsOpportunitySpotlight limit={3} />

      {showLegacy && (
        <>
          {/* ───── engineer view (?view=working) ────────────────── */}
          {/* 1. Research Pulse Hero — quant-style headline (legacy)     */}
          <OptionsResearchPulseHero />

          {/* 2. Top 3 observations — equal-weight curated row (legacy) */}
          <OptionsResearchCandidates />

          {/* 3. Editorial doorway strip — three calm exits to depth     */}
          <OptionsDoorwayStrip />
        </>
      )}
    </div>
  );
}
