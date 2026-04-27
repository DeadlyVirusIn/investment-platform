// Phase 11H — Strategy Evaluation page (read-only).
// Three-banner stack: paper-only, observation-only, evaluation
// disclaimer. Fixed rule-based scoring of historical observations.
// No "recommended" / "best" / "execute" wording.

import { useState } from 'react';
import OptionsPaperOnlyBanner from '@/components/options/OptionsPaperOnlyBanner';
import OptionsObservationOnlyBanner from '@/components/options/OptionsObservationOnlyBanner';
import OptionsEvaluationDisclaimer from '@/components/options/OptionsEvaluationDisclaimer';
import OptionsEvaluationSummaryCards from '@/components/options/OptionsEvaluationSummaryCards';
import OptionsEvaluationScoreTable from '@/components/options/OptionsEvaluationScoreTable';
import OptionsEvaluationDetailDrawer from '@/components/options/OptionsEvaluationDetailDrawer';
import OptionsEvaluationDiagnosticsPanel from '@/components/options/OptionsEvaluationDiagnosticsPanel';
import OptionsEvaluationDistribution from '@/components/options/OptionsEvaluationDistribution';
import {
  useOptionsEvaluationDiagnostics,
  useOptionsEvaluationDistribution,
  useOptionsEvaluationScores,
  useOptionsEvaluationSummary,
  useOptionsSymbols,
} from '@/lib/options/hooks';

export default function OptionsStrategyEvaluationPage() {
  const symbols = useOptionsSymbols();
  const [underlying, setUnderlying] = useState<string | undefined>(undefined);
  const [strategy, setStrategy] = useState<string | undefined>(undefined);
  const [minScore, setMinScore] = useState<number | undefined>(undefined);
  const [qualifiedOnly, setQualifiedOnly] = useState<boolean>(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const summary = useOptionsEvaluationSummary({
    underlying, strategy, lookback_days: 14,
  });
  const scores = useOptionsEvaluationScores({
    underlying, strategy, min_score: minScore,
    qualified_only: qualifiedOnly, lookback_days: 14, limit: 100,
  });
  const distribution = useOptionsEvaluationDistribution(14);
  const diagnostics = useOptionsEvaluationDiagnostics(14);

  return (
    <div className="space-y-4">
      <OptionsPaperOnlyBanner />
      <OptionsObservationOnlyBanner />
      <OptionsEvaluationDisclaimer />

      <header>
        <h1 className="text-xl font-semibold text-zinc-100">Strategy Evaluation</h1>
        <p className="mt-1 text-xs text-zinc-400">
          Paper-only, rule-based scoring of historical observations. Not
          investment advice or execution guidance.
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
          <div className="mb-1 uppercase tracking-wide text-zinc-400">Min score</div>
          <input
            type="number"
            min={0}
            max={100}
            value={minScore ?? ''}
            onChange={(e) =>
              setMinScore(e.target.value === '' ? undefined : Number(e.target.value))
            }
            className="w-20 rounded-md border border-zinc-700 bg-zinc-950 px-2 py-1 text-sm"
          />
        </label>
        <label className="flex items-center gap-1 text-xs text-zinc-300">
          <input
            type="checkbox"
            checked={qualifiedOnly}
            onChange={(e) => setQualifiedOnly(e.target.checked)}
          />
          Qualified only
        </label>
      </section>

      {summary.isLoading ? (
        <p className="text-sm text-zinc-400">Loading evaluation summary…</p>
      ) : summary.data ? (
        <OptionsEvaluationSummaryCards data={summary.data} />
      ) : null}

      <section>
        <h2 className="mb-2 text-sm font-semibold text-zinc-100">
          Score table
        </h2>
        {scores.isLoading ? (
          <p className="text-sm text-zinc-400">Loading scores…</p>
        ) : scores.data ? (
          <OptionsEvaluationScoreTable
            scores={scores.data.scores}
            onSelect={setSelectedId}
          />
        ) : null}
      </section>

      <section>
        <h2 className="mb-2 text-sm font-semibold text-zinc-100">
          Threshold diagnostics
        </h2>
        {diagnostics.isLoading ? (
          <p className="text-sm text-zinc-400">Loading diagnostics…</p>
        ) : diagnostics.data ? (
          <OptionsEvaluationDiagnosticsPanel data={diagnostics.data} />
        ) : null}
      </section>

      <section>
        <h2 className="mb-2 text-sm font-semibold text-zinc-100">
          Historical score distribution
        </h2>
        {distribution.isLoading ? (
          <p className="text-sm text-zinc-400">Loading distribution…</p>
        ) : distribution.data ? (
          <OptionsEvaluationDistribution data={distribution.data} />
        ) : null}
      </section>

      <OptionsEvaluationDetailDrawer
        observationId={selectedId}
        onClose={() => setSelectedId(null)}
      />
    </div>
  );
}
