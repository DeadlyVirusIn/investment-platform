// Phase 11I — Decision Support disclaimer.
// Sits below paper-only / observation-only / evaluation banners.
// Reinforces: review queues are observational, NEVER recommendations.

export default function OptionsDecisionSupportDisclaimer() {
  return (
    <div
      role="status"
      className="mb-3 flex items-center gap-2 rounded-md border border-zinc-700/60 bg-zinc-800/40 px-3 py-2 text-xs text-zinc-300"
    >
      <span aria-hidden="true">⚑</span>
      <span className="font-semibold">
        Review queues are for human inspection only. They are not trade
        recommendations or execution guidance.
      </span>
    </div>
  );
}
