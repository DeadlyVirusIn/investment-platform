// Phase 11J — Decision Framing page (read-only).
// Five-banner stack: paper-only / observation-only / evaluation /
// decision-support / decision-framing disclaimer.

import { useMemo, useState } from 'react';
import OptionsPaperOnlyBanner from '@/components/options/OptionsPaperOnlyBanner';
import OptionsObservationOnlyBanner from '@/components/options/OptionsObservationOnlyBanner';
import OptionsEvaluationDisclaimer from '@/components/options/OptionsEvaluationDisclaimer';
import OptionsDecisionSupportDisclaimer from '@/components/options/OptionsDecisionSupportDisclaimer';
import OptionsDecisionFramingDisclaimer from '@/components/options/OptionsDecisionFramingDisclaimer';
import OptionsReviewNarrativeCards from '@/components/options/OptionsReviewNarrativeCards';
import OptionsNarrativeDetailDrawer from '@/components/options/OptionsNarrativeDetailDrawer';
import OptionsScenarioComparisonPanel from '@/components/options/OptionsScenarioComparisonPanel';
import {
  useOptionsDecisionFramingNarratives,
  useOptionsDecisionFramingSummary,
  useOptionsSymbols,
} from '@/lib/options/hooks';
import {
  BUCKET_DATA_QUALITY_REVIEW,
  BUCKET_EXCLUDED,
  BUCKET_HIGH_REVIEW_PRIORITY,
  BUCKET_MODEL_LIMITATION_REVIEW,
  BUCKET_NEUTRAL,
} from '@/lib/options/optionsApi';

export default function OptionsDecisionFramingPage() {
  const symbols = useOptionsSymbols();
  const [underlying, setUnderlying] = useState<string | undefined>(undefined);
  const [bucket, setBucket] = useState<string | undefined>(undefined);
  const [strategy, setStrategy] = useState<string | undefined>(undefined);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [compareA, setCompareA] = useState<string | null>(null);
  const [compareB, setCompareB] = useState<string | null>(null);

  const summary = useOptionsDecisionFramingSummary(14);
  const narratives = useOptionsDecisionFramingNarratives({
    underlying, bucket, strategy, lookback_days: 14, limit: 50,
  });

  const compareOptions = useMemo(
    () => (narratives.data?.narratives ?? []).map((n) => ({
      id: n.id,
      label: `${n.underlying} ${n.rule_id} (${n.as_of_date}) — score ${n.total_score}`,
    })),
    [narratives.data],
  );

  return (
    <div className="space-y-4">
      <OptionsPaperOnlyBanner />
      <OptionsObservationOnlyBanner />
      <OptionsEvaluationDisclaimer />
      <OptionsDecisionSupportDisclaimer />
      <OptionsDecisionFramingDisclaimer />

      <header>
        <h1 className="text-xl font-semibold text-zinc-100">Decision Framing</h1>
        <p className="mt-1 text-xs text-zinc-400">
          Template-based review narratives and comparison context for
          paper-only observations.
        </p>
      </header>

      <section className="flex flex-wrap items-end gap-3">
        <label className="text-xs">
          <div className="mb-1 uppercase tracking-wide text-zinc-400">Underlying</div>
          <select
            value={underlying ?? ''}
            onChange={(e) => setUnderlying(e.target.value || undefined)}
            className="rounded-md border border-zinc-700 bg-zinc-950 px-2 py-1 text-sm"
          >
            <option value="">(any)</option>
            {(symbols.data?.symbols ?? []).map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </label>
        <label className="text-xs">
          <div className="mb-1 uppercase tracking-wide text-zinc-400">Strategy</div>
          <select
            value={strategy ?? ''}
            onChange={(e) => setStrategy(e.target.value || undefined)}
            className="rounded-md border border-zinc-700 bg-zinc-950 px-2 py-1 text-sm"
          >
            <option value="">(all)</option>
            <option value="SHORT_PUT_CREDIT_SPREAD">Short put credit spread</option>
            <option value="SHORT_CALL_CREDIT_SPREAD">Short call credit spread</option>
            <option value="IRON_CONDOR">Iron condor</option>
          </select>
        </label>
        <label className="text-xs">
          <div className="mb-1 uppercase tracking-wide text-zinc-400">Bucket</div>
          <select
            value={bucket ?? ''}
            onChange={(e) => setBucket(e.target.value || undefined)}
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
      </section>

      {summary.data ? (
        <div className="rounded-md border border-zinc-800 bg-zinc-950/50 p-3 text-xs text-zinc-300">
          <span className="font-semibold">Total observations:</span>{' '}
          {summary.data.n_total_observations} · split by bucket:{' '}
          {summary.data.by_bucket.map((b) =>
            `${b.bucket}=${b.count}`).join(' · ')}
        </div>
      ) : null}

      <section>
        <h2 className="mb-2 text-sm font-semibold text-zinc-100">
          Review narrative cards
        </h2>
        {narratives.isLoading ? (
          <p className="text-sm text-zinc-400">Loading narratives…</p>
        ) : narratives.data ? (
          <OptionsReviewNarrativeCards
            narratives={narratives.data.narratives}
            onSelect={setSelectedId}
          />
        ) : null}
      </section>

      <section>
        <h2 className="mb-2 text-sm font-semibold text-zinc-100">
          Scenario comparison
        </h2>
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-xs">
            <div className="mb-1 uppercase tracking-wide text-zinc-400">Observation A</div>
            <select
              value={compareA ?? ''}
              onChange={(e) => setCompareA(e.target.value || null)}
              className="w-[28rem] max-w-full rounded-md border border-zinc-700 bg-zinc-950 px-2 py-1 text-sm"
            >
              <option value="">(pick one)</option>
              {compareOptions.map((o) => (
                <option key={o.id} value={o.id}>{o.label}</option>
              ))}
            </select>
          </label>
          <label className="text-xs">
            <div className="mb-1 uppercase tracking-wide text-zinc-400">Observation B</div>
            <select
              value={compareB ?? ''}
              onChange={(e) => setCompareB(e.target.value || null)}
              className="w-[28rem] max-w-full rounded-md border border-zinc-700 bg-zinc-950 px-2 py-1 text-sm"
            >
              <option value="">(pick one)</option>
              {compareOptions.map((o) => (
                <option key={o.id} value={o.id}>{o.label}</option>
              ))}
            </select>
          </label>
        </div>
        <div className="mt-3">
          <OptionsScenarioComparisonPanel idA={compareA} idB={compareB} />
        </div>
      </section>

      <OptionsNarrativeDetailDrawer
        observationId={selectedId}
        onClose={() => setSelectedId(null)}
      />
    </div>
  );
}
