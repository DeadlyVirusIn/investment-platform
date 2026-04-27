// Phase 11F — Options Features page (read-only).

import { useState } from 'react';
import OptionsPaperOnlyBanner from '@/components/options/OptionsPaperOnlyBanner';
import OptionsFeatureCards from '@/components/options/OptionsFeatureCards';
import {
  useOptionsFeatures,
  useOptionsSymbols,
} from '@/lib/options/hooks';

export default function OptionsFeaturesPage() {
  const symbols = useOptionsSymbols();
  const [symbol, setSymbol] = useState<string | undefined>(undefined);
  const effectiveSymbol = symbol ?? symbols.data?.symbols[0];
  const features = useOptionsFeatures(effectiveSymbol);

  return (
    <div className="space-y-3">
      <OptionsPaperOnlyBanner />

      <section className="flex flex-wrap items-end gap-3">
        <label className="text-xs">
          <div className="mb-1 uppercase tracking-wide text-zinc-400">Symbol</div>
          <select
            value={effectiveSymbol ?? ''}
            onChange={(e) => setSymbol(e.target.value)}
            className="rounded-md border border-zinc-700 bg-zinc-950 px-2 py-1 text-sm"
          >
            {(symbols.data?.symbols ?? []).map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </label>
        {features.data?.features?.as_of_date ? (
          <div className="ml-auto text-xs text-zinc-500">
            As of: {features.data.features.as_of_date}
          </div>
        ) : null}
      </section>

      {features.isLoading ? (
        <p className="text-sm text-zinc-400">Loading features…</p>
      ) : features.error ? (
        <p className="text-sm text-red-400">Error loading features.</p>
      ) : features.data ? (
        <OptionsFeatureCards data={features.data} />
      ) : null}
    </div>
  );
}
