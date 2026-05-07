// Phase 11G — Paper Performance page.
// Aggregates over closed/expired/assigned trades. Read-only.

import { useState } from 'react';
import OptionsPaperOnlyBanner from '@/components/options/OptionsPaperOnlyBanner';
import OptionsObservationOnlyBanner from '@/components/options/OptionsObservationOnlyBanner';
import OptionsPerformanceCards from '@/components/options/OptionsPerformanceCards';
import {
  ByStrategyTable,
  ByUnderlyingTable,
} from '@/components/options/OptionsPerformanceTables';
import {
  useOptionsPerformanceSummary,
  useOptionsSymbols,
} from '@/lib/options/hooks';

export default function OptionsPaperPerformancePage() {
  const symbols = useOptionsSymbols();
  const [underlying, setUnderlying] = useState<string | undefined>(undefined);
  const perf = useOptionsPerformanceSummary({ underlying });

  return (
    <div className="space-y-4">
      <OptionsPaperOnlyBanner />
      <OptionsObservationOnlyBanner />

      {/* UX-1 Commit O — quiet intro. */}
      <header data-test="options-performance-intro" className="mb-1">
        <div className="u-caption-2 text-fg-3 uppercase tracking-wide mb-1">
          Pro view · Options paper performance
        </div>
        <h2 className="text-base font-semibold text-zinc-100">
          How closed paper options trades behaved
        </h2>
        <p className="u-caption-2 text-fg-3 mt-0.5 max-w-3xl">
          Aggregates over closed, expired, and assigned paper
          trades. Read-only — never affects future trading.
        </p>
      </header>

      <section className="flex flex-wrap items-end gap-3">
        <label className="text-xs">
          <div className="mb-1 uppercase tracking-wide text-zinc-400">Underlying filter</div>
          <select
            value={underlying ?? ''}
            onChange={(e) => setUnderlying(e.target.value || undefined)}
            className="rounded-md border border-zinc-700 bg-zinc-950 px-2 py-1 text-sm"
          >
            <option value="">(all)</option>
            {(symbols.data?.symbols ?? []).map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </label>
      </section>

      {perf.isLoading ? (
        <p className="text-sm text-zinc-400">Loading performance summary…</p>
      ) : perf.data ? (
        <>
          <OptionsPerformanceCards data={perf.data} />
          <section>
            <h2 className="mb-2 text-sm font-semibold text-zinc-100">By strategy</h2>
            <ByStrategyTable data={perf.data} />
          </section>
          <section>
            <h2 className="mb-2 text-sm font-semibold text-zinc-100">By underlying</h2>
            <ByUnderlyingTable data={perf.data} />
          </section>
        </>
      ) : null}
    </div>
  );
}
