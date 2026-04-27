// Phase 11I — Review Queue summary cards.
// Counts per bucket + median score. Neutral language only.

import type { DecisionSupportSummary } from '@/lib/options/optionsApi';

function Card({
  label, value, hint,
}: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-md border border-zinc-800 bg-zinc-950/50 px-3 py-2">
      <div className="text-xs uppercase tracking-wide text-zinc-400">{label}</div>
      <div className="mt-1 text-lg font-semibold tabular-nums text-zinc-100">
        {value}
      </div>
      {hint ? <div className="mt-1 text-[11px] text-zinc-500">{hint}</div> : null}
    </div>
  );
}

function _val(v: string | number | null | undefined,
              nullText = 'Insufficient data'): string {
  if (v === null || v === undefined) return nullText;
  return String(v);
}

export default function OptionsReviewQueueSummaryCards({
  data,
}: { data: DecisionSupportSummary }) {
  return (
    <div className="grid grid-cols-2 gap-2 md:grid-cols-3 xl:grid-cols-6">
      <Card label="Total observations"          value={String(data.n_total)} />
      <Card label="High review priority"        value={String(data.n_high_review_priority)} />
      <Card label="Data quality review"         value={String(data.n_data_quality_review)} />
      <Card label="Model limitation review"     value={String(data.n_model_limitation_review)} />
      <Card label="Excluded by review rules"    value={String(data.n_excluded)} />
      <Card label="Median score"                value={_val(data.median_score)} />
    </div>
  );
}
