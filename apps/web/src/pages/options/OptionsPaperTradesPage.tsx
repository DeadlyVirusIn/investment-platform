// Phase 11F — Paper trades page (read-only).
// Tab over status (open / closed / expired / assigned). Trade detail
// drawer on row click. Flag chips visible in table + drawer.

import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import OptionsPaperOnlyBanner from '@/components/options/OptionsPaperOnlyBanner';
import OptionsTradesTable from '@/components/options/OptionsTradesTable';
import OptionsTradeDetailDrawer from '@/components/options/OptionsTradeDetailDrawer';
import { optionsApi } from '@/lib/options/optionsApi';
import { useOptionsPaperTrades } from '@/lib/options/hooks';

const STATUS_TABS = ['open', 'closed', 'expired', 'assigned'] as const;
type StatusTab = (typeof STATUS_TABS)[number];

export default function OptionsPaperTradesPage() {
  const [tab, setTab] = useState<StatusTab>('open');
  const trades = useOptionsPaperTrades({ status: tab });
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const ids = useMemo(
    () => (trades.data?.trades ?? []).map((t) => t.id),
    [trades.data],
  );
  // Fetch detail for each trade in the current view to extract flags.
  // For dev volumes (≤200 trades) this is fine; production-scale later
  // can move flag aggregation to a single endpoint.
  const flagsBatch = useQuery({
    queryKey: ['options', 'paper-trades-flags', ids.join(',')],
    queryFn: async () => {
      const out: Record<number, string[]> = {};
      for (const id of ids) {
        try {
          const d = await optionsApi.paperTradeDetail(id);
          out[id] = d.data_quality_flags ?? [];
        } catch {
          out[id] = [];
        }
      }
      return out;
    },
    enabled: ids.length > 0,
    staleTime: 30_000,
  });

  return (
    <div className="space-y-3">
      <OptionsPaperOnlyBanner />

      <div className="flex gap-1 border-b border-zinc-800 text-sm">
        {STATUS_TABS.map((s) => (
          <button
            key={s}
            onClick={() => setTab(s)}
            className={`px-3 py-1 ${
              tab === s
                ? 'border-b-2 border-amber-400 text-zinc-100'
                : 'text-zinc-400 hover:text-zinc-200'
            }`}
          >
            {s.charAt(0).toUpperCase() + s.slice(1)}
          </button>
        ))}
      </div>

      {trades.isLoading ? (
        <p className="text-sm text-zinc-400">Loading paper trades…</p>
      ) : trades.error ? (
        <p className="text-sm text-red-400">Error loading paper trades.</p>
      ) : (
        <OptionsTradesTable
          trades={trades.data?.trades ?? []}
          flagsById={flagsBatch.data ?? {}}
          onSelect={setSelectedId}
        />
      )}

      <OptionsTradeDetailDrawer
        tradeId={selectedId}
        onClose={() => setSelectedId(null)}
      />
    </div>
  );
}
