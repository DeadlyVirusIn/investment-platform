// Phase 11H — evaluation disclaimer.
// Renders BELOW the paper-only banner and observation-only banner on
// every evaluation page. Reinforces: scores are fixed rule-based
// paper analytics, NEVER trade recommendations.

export default function OptionsEvaluationDisclaimer() {
  return (
    <div
      role="status"
      className="mb-3 flex items-center gap-2 rounded-md border border-zinc-700/60 bg-zinc-800/40 px-3 py-2 text-xs text-zinc-300"
    >
      <span aria-hidden="true">ⓘ</span>
      <span className="font-semibold">
        Evaluation scores are fixed rule-based paper analytics. They are
        not trade recommendations.
      </span>
    </div>
  );
}
