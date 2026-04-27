// Phase 11G — sub-banner shown on every observatory page below the
// paper-only banner. Reinforces the observation-only contract:
// the engine evaluates rules historically; it never recommends,
// ranks "best", or executes.

export default function OptionsObservationOnlyBanner() {
  return (
    <div
      role="status"
      className="mb-3 flex items-center gap-2 rounded-md border border-zinc-700/60 bg-zinc-800/50 px-3 py-2 text-xs text-zinc-200"
    >
      <span aria-hidden="true">ℹ</span>
      <span className="font-semibold">
        Observation only — not investment advice or execution guidance
      </span>
      <span className="text-zinc-400">
        · historical / simulated · candidate rule matches · diagnostic
      </span>
    </div>
  );
}
