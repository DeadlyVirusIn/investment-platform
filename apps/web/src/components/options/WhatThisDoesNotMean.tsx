// Phase 11K — Universal "What this does NOT mean" panel.
// Pulls block from /interpretation-guardrails/page-context once and
// renders the 5 spec-mandated negation lines.

import { useOptionsGuardrailsPageContext } from '@/lib/options/hooks';

export default function WhatThisDoesNotMean() {
  const { data, isLoading } = useOptionsGuardrailsPageContext();
  if (isLoading) return null;
  if (!data) return null;
  const w = data.page_context.what_this_does_not_mean;
  return (
    <section className="rounded-md border border-zinc-700/60 bg-zinc-800/40 p-3 text-sm text-zinc-200">
      <header className="mb-1 text-xs uppercase tracking-wide text-zinc-400">
        What this does NOT mean
      </header>
      <ul className="space-y-1 text-[11px] text-zinc-300">
        <li className="flex gap-1"><span aria-hidden="true">⚠</span><span>{w.not_expected_profitability}</span></li>
        <li className="flex gap-1"><span aria-hidden="true">⚠</span><span>{w.not_probability_of_success}</span></li>
        <li className="flex gap-1"><span aria-hidden="true">⚠</span><span>{w.not_suitability_for_trading}</span></li>
        <li className="flex gap-1"><span aria-hidden="true">⚠</span><span>{w.not_instruction_to_act}</span></li>
        <li className="flex gap-1"><span aria-hidden="true">⚠</span><span>{w.not_live_market_signal}</span></li>
      </ul>
    </section>
  );
}
