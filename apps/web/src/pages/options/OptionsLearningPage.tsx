// Phase 6b-3-f — Learning surface (anti-gamification, evidence-bound).
//
// The system refuses to claim intelligence before evidence exists.
// Every value comes from /analytics/learning-readiness — the same
// endpoint that backs the operator-only training gate.
//
// Composition (5 layers, quietly scientific):
//   1. Pulse strip            "N of 7 gates satisfied · D days of evidence"
//   2. Readiness gates table  4-column scientific table (NO progress bars)
//   3. Evidence chronology    per-day accumulation log
//   4. Methodological rationale  why gates exist + what unlocks
//   5. Pathways               three editorial doorways
//
// Per the queued direction:
//   "Earned, skeptical, evidence-bound, institutional. NOT motivational,
//    gamified, optimistic, or AI-awakening."
//   "Avoid progress-bar psychology. No gamification energy. No
//    achievement-system feeling. No celebratory UI."
//   "The system should appear reluctant to claim intelligence
//    before evidence truly exists."

import OptionsLearningPulse from
  "@/components/options/OptionsLearningPulse";
import OptionsReadinessGatesTable from
  "@/components/options/OptionsReadinessGatesTable";
import OptionsLearningChronology from
  "@/components/options/OptionsLearningChronology";
import OptionsLearningRationale from
  "@/components/options/OptionsLearningRationale";
import OptionsLearningPathways from
  "@/components/options/OptionsLearningPathways";


export default function OptionsLearningPage() {
  return (
    <div className="opt-learning" data-test="options-learning-page">
      {/* 1. Pulse — quietly scientific orientation */}
      <OptionsLearningPulse />

      {/* 2. Readiness gates table — scientific 4-column layout */}
      <OptionsReadinessGatesTable />

      {/* 3. Evidence chronology — per-day accumulation log */}
      <OptionsLearningChronology />

      {/* 4. Methodological rationale — why gates exist */}
      <OptionsLearningRationale />

      {/* 5. Pathways — three editorial doorways */}
      <OptionsLearningPathways />
    </div>
  );
}
