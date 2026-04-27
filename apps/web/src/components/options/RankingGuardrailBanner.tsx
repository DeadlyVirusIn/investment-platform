// Phase 11K — Ranking guardrail banner.
// Read-only. Surfaces deterministic-ordering phrase. NEVER says
// "ranked above", "better", "worse", "prefer", "choose".

import { useOptionsGuardrailsRanking } from '@/lib/options/hooks';
import GuardrailsGate from './GuardrailsGate';

export default function RankingGuardrailBanner({
  observationId,
}: { observationId: string | undefined }) {
  const { data, isLoading } = useOptionsGuardrailsRanking(observationId);
  if (!observationId) return null;
  if (isLoading) return (
    <div className="rounded-md border border-zinc-700/60 bg-zinc-800/40 p-2 text-xs text-zinc-400">
      Loading ranking guardrail…
    </div>
  );
  if (!data) return null;
  const ri = data.ranking_interpretation;
  return (
    <GuardrailsGate>
      <section className="rounded-md border border-zinc-700/60 bg-zinc-800/40 p-3 text-sm text-zinc-200">
        <header className="mb-1 text-xs uppercase tracking-wide text-zinc-400">
          Ranking guardrail
        </header>
        <p className="font-semibold">{ri.headline}</p>
        <p className="mt-1 text-[12px] text-zinc-300">{ri.is_what}</p>
        <p className="mt-2 text-[11px] italic text-zinc-300">
          Phrasing: a row "{ri.deterministic_ordering_phrase}".
        </p>
        <ul className="mt-2 list-disc list-inside text-[11px] text-zinc-300">
          {ri.is_not_what.map((line, i) => (<li key={i}>{line}</li>))}
        </ul>
        <p className="mt-2 text-[11px] text-zinc-400">{ri.review_only_footer}</p>
      </section>
    </GuardrailsGate>
  );
}
