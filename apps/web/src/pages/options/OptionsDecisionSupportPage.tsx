// Phase 11I — Decision Support page (read-only).
// Four-banner stack: paper-only / observation-only / evaluation
// disclaimer / decision-support disclaimer.

import { useState } from 'react';
import OptionsPaperOnlyBanner from '@/components/options/OptionsPaperOnlyBanner';
import OptionsObservationOnlyBanner from '@/components/options/OptionsObservationOnlyBanner';
import OptionsEvaluationDisclaimer from '@/components/options/OptionsEvaluationDisclaimer';
import OptionsDecisionSupportDisclaimer from '@/components/options/OptionsDecisionSupportDisclaimer';
import OptionsReviewQueueSummaryCards from '@/components/options/OptionsReviewQueueSummaryCards';
import OptionsReviewQueueFilters, {
  DEFAULT_FILTERS,
  type ReviewFilters,
} from '@/components/options/OptionsReviewQueueFilters';
import OptionsReviewQueueTable from '@/components/options/OptionsReviewQueueTable';
import OptionsShortlistBuckets from '@/components/options/OptionsShortlistBuckets';
import OptionsReviewDetailDrawer from '@/components/options/OptionsReviewDetailDrawer';
import {
  useOptionsDecisionSupportBuckets,
  useOptionsDecisionSupportReviewQueue,
  useOptionsDecisionSupportSummary,
  useOptionsSymbols,
} from '@/lib/options/hooks';

export default function OptionsDecisionSupportPage() {
  const symbols = useOptionsSymbols();
  const [filters, setFilters] = useState<ReviewFilters>(DEFAULT_FILTERS);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const summary = useOptionsDecisionSupportSummary(filters.lookbackDays);
  const reviewQueue = useOptionsDecisionSupportReviewQueue({
    underlying: filters.underlying,
    strategy: filters.strategy,
    min_score: filters.minScore,
    qualified_only: filters.qualifiedOnly,
    exclude_severe_flags: filters.excludeSevereFlags,
    bucket: filters.bucket,
    lookback_days: filters.lookbackDays,
    limit: 100,
  });
  const buckets = useOptionsDecisionSupportBuckets(filters.lookbackDays);

  return (
    <div className="space-y-4">
      <OptionsPaperOnlyBanner />
      <OptionsObservationOnlyBanner />
      <OptionsEvaluationDisclaimer />
      <OptionsDecisionSupportDisclaimer />

      <header>
        <h1 className="text-xl font-semibold text-zinc-100">Decision Support</h1>
        <p className="mt-1 text-xs text-zinc-400">
          Read-only review queues built from paper-only rule-based scores.
          Not trade recommendations.
        </p>
      </header>

      <OptionsReviewQueueFilters
        symbols={symbols.data?.symbols ?? []}
        value={filters}
        onChange={setFilters}
      />

      {summary.isLoading ? (
        <p className="text-sm text-zinc-400">Loading review queue summary…</p>
      ) : summary.data ? (
        <OptionsReviewQueueSummaryCards data={summary.data} />
      ) : null}

      <section>
        <header className="mb-2 flex items-baseline justify-between">
          <h2 className="text-sm font-semibold text-zinc-100">Review queue</h2>
          {reviewQueue.data ? (
            <span className="text-[11px] text-zinc-500">
              {reviewQueue.data.count} included · {reviewQueue.data.excluded_count} excluded by filter
            </span>
          ) : null}
        </header>
        {reviewQueue.isLoading ? (
          <p className="text-sm text-zinc-400">Loading review queue…</p>
        ) : reviewQueue.data ? (
          <OptionsReviewQueueTable
            rows={reviewQueue.data.review_queue}
            onSelect={setSelectedId}
          />
        ) : null}
      </section>

      <section>
        <header className="mb-2">
          <h2 className="text-sm font-semibold text-zinc-100">Shortlist buckets</h2>
          <p className="text-[11px] text-zinc-500">
            Computed views only — never persisted server-side, never mutated by user actions.
          </p>
        </header>
        {buckets.isLoading ? (
          <p className="text-sm text-zinc-400">Loading buckets…</p>
        ) : buckets.data ? (
          <OptionsShortlistBuckets data={buckets.data} onSelect={setSelectedId} />
        ) : null}
      </section>

      <OptionsReviewDetailDrawer
        observationId={selectedId}
        onClose={() => setSelectedId(null)}
      />
    </div>
  );
}
