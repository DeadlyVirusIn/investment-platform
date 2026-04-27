// Phase 11G — Strategy Observatory page.
// Read-only. Shows rule definitions + recent observations.
// No "recommend" / "best" / "execute" wording anywhere.

import { useState } from 'react';
import OptionsPaperOnlyBanner from '@/components/options/OptionsPaperOnlyBanner';
import OptionsObservationOnlyBanner from '@/components/options/OptionsObservationOnlyBanner';
import OptionsRuleExplanationCard from '@/components/options/OptionsRuleExplanationCard';
import OptionsObservationsTable from '@/components/options/OptionsObservationsTable';
import OptionsObservationDetailPanel from '@/components/options/OptionsObservationDetailPanel';
import {
  useOptionsStrategies,
  useOptionsStrategyObservations,
  useOptionsSymbols,
} from '@/lib/options/hooks';

export default function OptionsStrategyObservatoryPage() {
  const strategies = useOptionsStrategies();
  const symbols = useOptionsSymbols();
  const [underlying, setUnderlying] = useState<string | undefined>(undefined);
  const [qualifiedOnly, setQualifiedOnly] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const observations = useOptionsStrategyObservations({
    underlying, qualified_only: qualifiedOnly, lookback_days: 14, limit: 50,
  });

  return (
    <div className="space-y-4">
      <OptionsPaperOnlyBanner />
      <OptionsObservationOnlyBanner />

      <section>
        <h2 className="mb-2 text-sm font-semibold text-zinc-100">
          Available paper strategies (rule definitions)
        </h2>
        {strategies.isLoading ? (
          <p className="text-sm text-zinc-400">Loading rule registry…</p>
        ) : strategies.data ? (
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
            {strategies.data.strategies.map((r) => (
              <OptionsRuleExplanationCard key={r.rule_id} rule={r} />
            ))}
          </div>
        ) : null}
      </section>

      <section className="space-y-2">
        <header className="flex flex-wrap items-end gap-3">
          <h2 className="text-sm font-semibold text-zinc-100">
            Historical observations
          </h2>
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
          <label className="flex items-center gap-1 text-xs text-zinc-300">
            <input
              type="checkbox"
              checked={qualifiedOnly}
              onChange={(e) => setQualifiedOnly(e.target.checked)}
            />
            Qualified only
          </label>
        </header>
        {observations.isLoading ? (
          <p className="text-sm text-zinc-400">Loading observations…</p>
        ) : observations.data ? (
          <OptionsObservationsTable
            observations={observations.data.observations}
            onSelect={setSelectedId}
          />
        ) : null}
      </section>

      <OptionsObservationDetailPanel
        observationId={selectedId}
        onClose={() => setSelectedId(null)}
      />
    </div>
  );
}
