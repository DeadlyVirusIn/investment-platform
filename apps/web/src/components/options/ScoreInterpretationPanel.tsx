// Phase 11K — Score interpretation panel.
// Read-only. Renders deterministic guardrail copy on what an
// evaluation score IS and IS NOT.

import { useOptionsGuardrailsScore } from '@/lib/options/hooks';

export default function ScoreInterpretationPanel({
  observationId,
}: { observationId: string | undefined }) {
  const { data, isLoading, error } = useOptionsGuardrailsScore(observationId);
  if (!observationId) return null;
  if (isLoading) return (
    <p className="text-sm text-zinc-400">Loading score interpretation…</p>
  );
  if (error) return (
    <p className="text-sm text-red-400">Error loading score interpretation.</p>
  );
  if (!data) return null;
  const si = data.score_interpretation;
  return (
    <section className="rounded-md border border-zinc-700/60 bg-zinc-800/40 p-3 text-sm text-zinc-200">
      <header className="mb-1 text-xs uppercase tracking-wide text-zinc-400">
        Score interpretation
      </header>
      <p className="font-semibold">{si.headline}</p>
      <p className="mt-1 text-[12px] text-zinc-300">{si.is_what}</p>
      <ul className="mt-2 list-disc list-inside text-[11px] text-zinc-300">
        {si.is_not_what.map((line, i) => (<li key={i}>{line}</li>))}
      </ul>
      <p className="mt-2 text-[11px] text-zinc-400">{si.review_only_footer}</p>
    </section>
  );
}
