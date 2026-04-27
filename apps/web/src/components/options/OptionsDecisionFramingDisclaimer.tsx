// Phase 11J — Decision Framing disclaimer.
// Sits below paper-only / observation-only / evaluation /
// decision-support disclaimers. Reinforces: framing is review
// context only, NEVER advice.

export default function OptionsDecisionFramingDisclaimer() {
  return (
    <div
      role="status"
      className="mb-3 flex items-center gap-2 rounded-md border border-zinc-700/60 bg-zinc-800/40 px-3 py-2 text-xs text-zinc-300"
    >
      <span aria-hidden="true">≡</span>
      <span className="font-semibold">
        Decision framing provides deterministic review context only.
        It is not advice, recommendation, or execution guidance.
      </span>
    </div>
  );
}
