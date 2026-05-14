// Phase 6b-3-h — Lab surface (inspectable methodology).
//
// Composition (5 layers, methodological):
//   1. Pulse strip            "3 templates · 5 criteria each · N evaluated, M passed"
//   2. Strategy catalog       OptionsStrategyCatalog (existing,
//                             real /strategies data — 3 templates,
//                             5 criteria each)
//   3. Evaluation flow        OptionsEvaluationFlow (existing
//                             6-step diagram, calm + educational)
//   4. Today's funnel         NEW — calm narrative reduction from
//                             chain to candidates; no chart theater
//   5. Pathways               three editorial doorways
//
// Per the queued direction:
//   "Lab = How the system evaluates observations.
//    NOT mystical or predictive. Educational over promotional.
//    Strategies should feel inspectable. Deterministic methodology
//    > impressive visuals. The page should feel like inspectable
//    research methodology, not a secret AI engine."
//
// Discipline:
//   * Read-only. No mutation.
//   * Deterministic methodology — funnel section explicitly states
//     "no model sampling, no probabilistic skipping".
//   * Reuses existing components for catalog + flow; the Lab page
//     is a curated composition, not a re-invention.

import OptionsLabPulse from
  "@/components/options/OptionsLabPulse";
import OptionsStrategyCatalog from
  "@/components/options/OptionsStrategyCatalog";
import OptionsEvaluationFlow from
  "@/components/options/OptionsEvaluationFlow";
import OptionsEvaluationFunnel from
  "@/components/options/OptionsEvaluationFunnel";
import OptionsLabPathways from
  "@/components/options/OptionsLabPathways";


export default function OptionsLabPage() {
  return (
    <div className="opt-lab" data-test="options-lab-page">
      {/* 1. Pulse — orientation: how many templates, how many
            evaluations today */}
      <OptionsLabPulse />

      {/* 2. Strategy catalog — what the engine CAN evaluate
            (3 inspectable templates with their per-strategy criteria) */}
      <OptionsStrategyCatalog />

      {/* 3. Evaluation flow — HOW an observation becomes a candidate
            (6-step pipeline diagram, calm + educational) */}
      <OptionsEvaluationFlow />

      {/* 4. Today's funnel — methodology proof point */}
      <OptionsEvaluationFunnel />

      {/* 5. Pathways */}
      <OptionsLabPathways />
    </div>
  );
}
