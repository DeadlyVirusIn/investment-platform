// Phase 11G — Strategy Diagnostics page.
// Counts of data-quality failures within configurable lookback.

import { useState } from 'react';
import OptionsPaperOnlyBanner from '@/components/options/OptionsPaperOnlyBanner';
import OptionsObservationOnlyBanner from '@/components/options/OptionsObservationOnlyBanner';
import OptionsDiagnosticsPanel from '@/components/options/OptionsDiagnosticsPanel';
import {
  useOptionsDiagnostics,
  useOptionsSymbols,
} from '@/lib/options/hooks';

const LOOKBACKS = [7, 14, 30, 60, 90] as const;

export default function OptionsStrategyDiagnosticsPage() {
  const symbols = useOptionsSymbols();
  const [lookback, setLookback] = useState<number>(30);
  const [underlying, setUnderlying] = useState<string | undefined>(undefined);
  const diag = useOptionsDiagnostics({ lookback_days: lookback, underlying });

  return (
    <div className="space-y-4">
      <OptionsPaperOnlyBanner />
      <OptionsObservationOnlyBanner />

      <section className="flex flex-wrap items-end gap-3">
        <label className="text-xs">
          <div className="mb-1 uppercase tracking-wide text-zinc-400">Lookback</div>
          <select
            value={lookback}
            onChange={(e) => setLookback(Number(e.target.value))}
            className="rounded-md border border-zinc-700 bg-zinc-950 px-2 py-1 text-sm"
          >
            {LOOKBACKS.map((n) => (
              <option key={n} value={n}>{n} days</option>
            ))}
          </select>
        </label>
        <label className="text-xs">
          <div className="mb-1 uppercase tracking-wide text-zinc-400">Underlying</div>
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

      {diag.isLoading ? (
        <p className="text-sm text-zinc-400">Loading diagnostics…</p>
      ) : diag.data ? (
        <OptionsDiagnosticsPanel data={diag.data} />
      ) : null}
    </div>
  );
}
