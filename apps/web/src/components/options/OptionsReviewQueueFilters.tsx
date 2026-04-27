// Phase 11I — Review Queue filter controls.
// Local frontend state only — no server-side persistence.

import {
  BUCKET_DATA_QUALITY_REVIEW,
  BUCKET_EXCLUDED,
  BUCKET_HIGH_REVIEW_PRIORITY,
  BUCKET_MODEL_LIMITATION_REVIEW,
  BUCKET_NEUTRAL,
} from '@/lib/options/optionsApi';

export interface ReviewFilters {
  underlying: string | undefined;
  strategy: string | undefined;
  minScore: number | undefined;
  qualifiedOnly: boolean;
  excludeSevereFlags: boolean;
  bucket: string | undefined;
  lookbackDays: number;
}

export const DEFAULT_FILTERS: ReviewFilters = {
  underlying: undefined,
  strategy: undefined,
  minScore: undefined,
  qualifiedOnly: false,
  excludeSevereFlags: false,
  bucket: undefined,
  lookbackDays: 14,
};

export default function OptionsReviewQueueFilters({
  symbols, value, onChange,
}: {
  symbols: string[];
  value: ReviewFilters;
  onChange: (next: ReviewFilters) => void;
}) {
  const set = <K extends keyof ReviewFilters>(k: K, v: ReviewFilters[K]) =>
    onChange({ ...value, [k]: v });

  return (
    <section className="flex flex-wrap items-end gap-3">
      <label className="text-xs">
        <div className="mb-1 uppercase tracking-wide text-zinc-400">Underlying</div>
        <select
          value={value.underlying ?? ''}
          onChange={(e) => set('underlying', e.target.value || undefined)}
          className="rounded-md border border-zinc-700 bg-zinc-950 px-2 py-1 text-sm"
        >
          <option value="">(any)</option>
          {symbols.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
      </label>
      <label className="text-xs">
        <div className="mb-1 uppercase tracking-wide text-zinc-400">Strategy</div>
        <select
          value={value.strategy ?? ''}
          onChange={(e) => set('strategy', e.target.value || undefined)}
          className="rounded-md border border-zinc-700 bg-zinc-950 px-2 py-1 text-sm"
        >
          <option value="">(all)</option>
          <option value="SHORT_PUT_CREDIT_SPREAD">Short put credit spread</option>
          <option value="SHORT_CALL_CREDIT_SPREAD">Short call credit spread</option>
          <option value="IRON_CONDOR">Iron condor</option>
        </select>
      </label>
      <label className="text-xs">
        <div className="mb-1 uppercase tracking-wide text-zinc-400">Min score</div>
        <input
          type="number"
          min={0}
          max={100}
          value={value.minScore ?? ''}
          onChange={(e) => set('minScore',
            e.target.value === '' ? undefined : Number(e.target.value))}
          className="w-20 rounded-md border border-zinc-700 bg-zinc-950 px-2 py-1 text-sm"
        />
      </label>
      <label className="text-xs">
        <div className="mb-1 uppercase tracking-wide text-zinc-400">Bucket</div>
        <select
          value={value.bucket ?? ''}
          onChange={(e) => set('bucket', e.target.value || undefined)}
          className="rounded-md border border-zinc-700 bg-zinc-950 px-2 py-1 text-sm"
        >
          <option value="">(all)</option>
          <option value={BUCKET_HIGH_REVIEW_PRIORITY}>High review priority</option>
          <option value={BUCKET_DATA_QUALITY_REVIEW}>Needs review — data quality</option>
          <option value={BUCKET_MODEL_LIMITATION_REVIEW}>Needs review — model limitation</option>
          <option value={BUCKET_NEUTRAL}>Neutral — needs human review</option>
          <option value={BUCKET_EXCLUDED}>Excluded by review rules</option>
        </select>
      </label>
      <label className="text-xs">
        <div className="mb-1 uppercase tracking-wide text-zinc-400">Lookback</div>
        <select
          value={value.lookbackDays}
          onChange={(e) => set('lookbackDays', Number(e.target.value))}
          className="rounded-md border border-zinc-700 bg-zinc-950 px-2 py-1 text-sm"
        >
          {[7, 14, 30, 60, 90].map((n) => (
            <option key={n} value={n}>{n} days</option>
          ))}
        </select>
      </label>
      <label className="flex items-center gap-1 text-xs text-zinc-300">
        <input
          type="checkbox"
          checked={value.qualifiedOnly}
          onChange={(e) => set('qualifiedOnly', e.target.checked)}
        />
        Qualified only
      </label>
      <label className="flex items-center gap-1 text-xs text-zinc-300">
        <input
          type="checkbox"
          checked={value.excludeSevereFlags}
          onChange={(e) => set('excludeSevereFlags', e.target.checked)}
        />
        Exclude severe flags
      </label>
    </section>
  );
}
