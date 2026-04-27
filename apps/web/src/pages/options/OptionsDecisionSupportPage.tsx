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
// Phase 11K guardrails — append-only integration
import SelectionBiasNotice from '@/components/options/SelectionBiasNotice';
import WhatThisDoesNotMean from '@/components/options/WhatThisDoesNotMean';
// Phase 11M — clarity lanes (visual grouping, no behaviour change)
import OptionsLane from '@/components/options/OptionsLane';
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

      {/* Phase 11K: selection-bias notice when filter view is narrow */}
      <SelectionBiasNotice
        state={{
          bucketFilter: filters.bucket,
          sortMode: 'SCORE_DESC',
        }}
      />

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

      {/* Phase 11M: EVALUATION lane — review queue */}
      <OptionsLane
        lane="EVALUATION"
        title="Review queue"
        caption={reviewQueue.data
          ? `${reviewQueue.data.count} included · ${reviewQueue.data.excluded_count} excluded by filter`
          : undefined}
      >
        {reviewQueue.isLoading ? (
          <p className="text-sm text-zinc-400">Loading review queue…</p>
        ) : reviewQueue.data ? (
          <OptionsReviewQueueTable
            rows={reviewQueue.data.review_queue}
            onSelect={setSelectedId}
          />
        ) : null}
      </OptionsLane>

      {/* Phase 11M: ATTRIBUTION lane — shortlist buckets */}
      <OptionsLane
        lane="ATTRIBUTION"
        title="Shortlist buckets"
        caption="Computed views only — never persisted server-side, never mutated by user actions."
      >
        {buckets.isLoading ? (
          <p className="text-sm text-zinc-400">Loading buckets…</p>
        ) : buckets.data ? (
          <OptionsShortlistBuckets data={buckets.data} onSelect={setSelectedId} />
        ) : null}
      </OptionsLane>

      {/* Phase 11K: universal "What this does NOT mean" page-level panel */}
      <WhatThisDoesNotMean />

      <OptionsReviewDetailDrawer
        observationId={selectedId}
        onClose={() => setSelectedId(null)}
      />
    </div>
  );
}
