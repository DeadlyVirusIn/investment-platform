// Phase 11G — Scenario Replay page.
// Pick (symbol, as_of). Show what the engine would have observed.
// Read-only. No execute / copy / create buttons.

import { useState } from 'react';
import OptionsPaperOnlyBanner from '@/components/options/OptionsPaperOnlyBanner';
import OptionsObservationOnlyBanner from '@/components/options/OptionsObservationOnlyBanner';
import OptionsReplayTimeline from '@/components/options/OptionsReplayTimeline';
import {
  useOptionsScenarioReplay,
  useOptionsSymbols,
} from '@/lib/options/hooks';

function _today(): string {
  return new Date().toISOString().slice(0, 10);
}

export default function OptionsScenarioReplayPage() {
  const symbols = useOptionsSymbols();
  const [symbol, setSymbol] = useState<string | undefined>(undefined);
  const [asOf, setAsOf] = useState<string>(_today());
  const effectiveSymbol = symbol ?? symbols.data?.symbols[0];
  const replay = useOptionsScenarioReplay(effectiveSymbol, asOf);

  return (
    <div className="space-y-4">
      <OptionsPaperOnlyBanner />
      <OptionsObservationOnlyBanner />

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
        <label className="text-xs">
          <div className="mb-1 uppercase tracking-wide text-zinc-400">As-of date</div>
          <input
            type="date"
            value={asOf}
            onChange={(e) => setAsOf(e.target.value)}
            className="rounded-md border border-zinc-700 bg-zinc-950 px-2 py-1 text-sm"
          />
        </label>
      </section>

      {replay.isLoading ? (
        <p className="text-sm text-zinc-400">Loading replay…</p>
      ) : replay.error ? (
        <p className="text-sm text-red-400">Error loading replay.</p>
      ) : replay.data ? (
        <OptionsReplayTimeline data={replay.data} />
      ) : null}
    </div>
  );
}
