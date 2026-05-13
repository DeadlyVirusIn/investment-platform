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


export default function OptionsOverviewPage() {
  return (
    <div className="opt-overview" data-test="options-overview-page">
      {/* 1. Research Pulse Hero — the make-or-break headline */}
      <OptionsResearchPulseHero />

      {/* 2. Top 3 observations — equal-weight curated row */}
      <OptionsResearchCandidates />

      {/* 3. Editorial doorway strip — three calm exits to depth */}
      <OptionsDoorwayStrip />

      {/* The page ends here. By design. */}
    </div>
  );
}
