// Phase 11F — Options Chain page (read-only).
// Symbol + expiry selector → Calls/Puts tables. No trade actions.

import { useMemo, useState } from 'react';
import OptionsPaperOnlyBanner from '@/components/options/OptionsPaperOnlyBanner';
import OptionsChainTable from '@/components/options/OptionsChainTable';
import {
  useOptionsChain,
  useOptionsExpiries,
  useOptionsSymbols,
} from '@/lib/options/hooks';
import { fmtTimestamp } from '@/components/options/format';

export default function OptionsChainPage() {
  const symbols = useOptionsSymbols();
  const [symbol, setSymbol] = useState<string | undefined>(undefined);
  const effectiveSymbol = symbol ?? symbols.data?.symbols[0];

  const expiries = useOptionsExpiries(effectiveSymbol);
  const [expiry, setExpiry] = useState<string | undefined>(undefined);
  const effectiveExpiry = expiry ?? expiries.data?.expiries[0];

  const chain = useOptionsChain(effectiveSymbol, effectiveExpiry);

  const empty = useMemo(
    () => !chain.data || (chain.data.calls.length === 0 && chain.data.puts.length === 0),
    [chain.data],
  );

  return (
    <div className="space-y-3">
      <OptionsPaperOnlyBanner />

      {/* UX-1 Commit O — quiet intro telegraphs page intent      */}
      {/* without redesigning the page or hiding any control.     */}
      <header data-test="options-chain-intro" className="mb-1">
        <div className="u-caption-2 text-fg-3 uppercase tracking-wide mb-1">
          Pro view · Options chain
        </div>
        <h2 className="text-base font-semibold text-zinc-100">
          Strikes, expirations, and quoted prices
        </h2>
        <p className="u-caption-2 text-fg-3 mt-0.5 max-w-3xl">
          Raw options chain for the selected symbol and expiry.
          Read-only research surface — most users never need this.
        </p>
      </header>

      <section className="flex flex-wrap items-end gap-3">
        <label className="text-xs">
          <div className="mb-1 uppercase tracking-wide text-zinc-400">Symbol</div>
          <select
            value={effectiveSymbol ?? ''}
            onChange={(e) => { setSymbol(e.target.value); setExpiry(undefined); }}
            className="rounded-md border border-zinc-700 bg-zinc-950 px-2 py-1 text-sm"
          >
            {(symbols.data?.symbols ?? []).map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </label>
        <label className="text-xs">
          <div className="mb-1 uppercase tracking-wide text-zinc-400">Expiry</div>
          <select
            value={effectiveExpiry ?? ''}
            onChange={(e) => setExpiry(e.target.value)}
            className="rounded-md border border-zinc-700 bg-zinc-950 px-2 py-1 text-sm"
          >
            {(expiries.data?.expiries ?? []).map((d) => (
              <option key={d} value={d}>{d}</option>
            ))}
          </select>
        </label>
        <div className="ml-auto text-xs text-zinc-500">
          Last updated: {fmtTimestamp(chain.data?.as_of_utc ?? null)}
        </div>
      </section>

      {chain.isLoading ? <p className="text-sm text-zinc-400">Loading chain…</p> : null}
      {chain.error ? <p className="text-sm text-red-400">Error loading chain.</p> : null}
      {empty && !chain.isLoading ? (
        <p className="text-sm text-zinc-400">
          No accepted quotes in the latest snapshot. The liquidity filter
          may have rejected all rows, or no chain snapshot exists yet for
          this symbol/expiry.
        </p>
      ) : null}
      {chain.data ? (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          <OptionsChainTable side="CALLS" rows={chain.data.calls} />
          <OptionsChainTable side="PUTS"  rows={chain.data.puts}  />
        </div>
      ) : null}
    </div>
  );
}
