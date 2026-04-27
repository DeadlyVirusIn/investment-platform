// Phase 11H — Evaluation summary cards.
// Counts + average + median + threshold splits.
// Neutral visual language. No green "approved" styling for high scores.

import type { EvaluationSummary } from '@/lib/options/optionsApi';

function Card({
  label, value, hint,
}: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-md border border-zinc-800 bg-zinc-950/50 px-3 py-2">
      <div className="text-xs uppercase tracking-wide text-zinc-400">{label}</div>
      <div className="mt-1 text-lg font-semibold text-zinc-100 tabular-nums">{value}</div>
      {hint ? <div className="mt-1 text-[11px] text-zinc-500">{hint}</div> : null}
    </div>
  );
}

function _val(v: string | null | number, nullText = 'Insufficient data'): string {
  if (v === null || v === undefined) return nullText;
  return String(v);
}

export default function OptionsEvaluationSummaryCards({
  data,
}: { data: EvaluationSummary }) {
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2 md:grid-cols-3 xl:grid-cols-6">
        <Card
          label="Observations scored"
          value={String(data.n_observations_scored)}
        />
        <Card label="Included by filter"  value={String(data.n_included_by_filter)} />
        <Card label="Excluded by filter"  value={String(data.n_excluded_by_filter)} />
        <Card label="Average score"       value={_val(data.average_score)} />
        <Card label="Median score"        value={_val(data.median_score)} />
        <Card
          label={`At or above threshold (${data.threshold})`}
          value={String(data.n_at_or_above_threshold)}
          hint={`${data.n_below_threshold} below threshold`}
        />
      </div>
      <section>
        <header className="mb-1 text-xs uppercase tracking-wide text-zinc-400">
          Score distribution
        </header>
        <div className="grid grid-cols-5 gap-2">
          {data.score_distribution_buckets.map((b) => (
            <div
              key={`${b.lo}-${b.hi}`}
              className="rounded-md border border-zinc-800 bg-zinc-950/50 p-2 text-center"
            >
              <div className="text-[11px] text-zinc-400">
                {b.lo}-{b.hi}
              </div>
              <div className="mt-1 text-lg font-semibold tabular-nums text-zinc-100">
                {b.count}
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
