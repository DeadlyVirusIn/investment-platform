// Phase 11K — Bucket meaning panel.
// Read-only. Renders deterministic guardrail copy on what a
// review bucket label means + what it does NOT imply.

import { useOptionsGuardrailsBucket } from '@/lib/options/hooks';
import GuardrailsGate from './GuardrailsGate';

export default function BucketMeaningPanel({
  observationId,
}: { observationId: string | undefined }) {
  const { data, isLoading, error } = useOptionsGuardrailsBucket(observationId);
  if (!observationId) return null;
  if (isLoading) return (
    <p className="text-sm text-zinc-400">Loading bucket meaning…</p>
  );
  if (error) return (
    <p className="text-sm text-red-400">Error loading bucket meaning.</p>
  );
  if (!data) return null;
  const bi = data.bucket_interpretation;
  return (
    <GuardrailsGate>
      <section className="rounded-md border border-zinc-700/60 bg-zinc-800/40 p-3 text-sm text-zinc-200">
        <header className="mb-1 text-xs uppercase tracking-wide text-zinc-400">
          Bucket meaning
        </header>
        <div className="text-[11px] font-mono text-zinc-500">{data.bucket}</div>
        <p className="mt-1 font-semibold">{bi.headline}</p>
        <p className="mt-1 text-[12px] text-zinc-300">{bi.is_what}</p>
        <ul className="mt-2 list-disc list-inside text-[11px] text-zinc-300">
          {bi.is_not_what.map((line, i) => (<li key={i}>{line}</li>))}
        </ul>
        <p className="mt-2 text-[11px] text-zinc-400">{bi.review_only_footer}</p>
      </section>
    </GuardrailsGate>
  );
}
