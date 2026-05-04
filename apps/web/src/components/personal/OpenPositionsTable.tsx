// Personal-Analytics — read-only Open Positions table.
//
// Per-position detail with toggle between live-only (default) and
// live + recovered replay. No action buttons. Replay rows carry the
// "Recovered replay — not live trading activity" warning chip.

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiGet } from '@/lib/api';

interface PositionRow {
  position_id: string;
  symbol: string;
  source: string;
  is_replay: boolean;
  entry_date: string | null;
  entry_price: number;
  quantity: number;
  notional_at_entry_usd: number;
  latest_price: number | null;
  latest_price_date: string | null;
  unrealized_pnl_usd: number | null;
  unrealized_return_pct: number | null;
  unrealized_status: 'ok' | 'unavailable';
  days_open: number | null;
  outcome_status: 'open_pending' | 'closed';
  data_quality: {
    latest_price_available: boolean;
    stale_price: boolean | null;
    missing_price: boolean;
    stale_threshold_days: number;
  };
}

interface OpenPositionsResponse {
  include_replay: boolean;
  stale_threshold_days: number;
  as_of: string;
  count: number;
  live_count: number;
  replay_count: number;
  positions: PositionRow[];
}

const fmtUsd = (n: number | null | undefined) =>
  n == null ? '—' : `$${n.toFixed(2)}`;
const fmtPct = (n: number | null | undefined) =>
  n == null ? '—' : `${(n * 100).toFixed(2)}%`;
const fmtQty = (n: number | null | undefined) =>
  n == null ? '—' : n.toFixed(4);

export default function OpenPositionsTable() {
  const [includeReplay, setIncludeReplay] = useState(false);
  const q = useQuery<OpenPositionsResponse>({
    queryKey: ['perf-paper', 'open-positions', includeReplay],
    queryFn: () => apiGet<OpenPositionsResponse>(
      `/performance/paper/open-positions${
        includeReplay ? '?include_replay=true' : ''}`,
    ),
    staleTime: 30_000,
  });
  const rows = q.data?.positions ?? [];

  return (
    <section
      data-test="open-positions-table"
      className="rounded-md border border-zinc-700 bg-zinc-900/40 p-4 mb-4"
    >
      <header className="flex items-baseline justify-between mb-3">
        <h3 className="text-sm font-semibold text-zinc-100">
          Open Positions — per-position detail
        </h3>
        <label className="text-xs flex items-center gap-2">
          <input
            type="checkbox"
            checked={includeReplay}
            onChange={e => setIncludeReplay(e.target.checked)}
          />
          <span>Show recovered replay data</span>
        </label>
      </header>

      <div className="text-[11px] text-zinc-500 mb-2">
        live={q.data?.live_count ?? 0} ·
        recovered replay={q.data?.replay_count ?? 0} ·
        showing={rows.length} ·
        stale threshold={q.data?.stale_threshold_days ?? '—'}d
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="text-zinc-500">
            <tr>
              <th className="text-left py-1">Symbol</th>
              <th className="text-left">Source</th>
              <th className="text-left">Entry</th>
              <th className="text-right">Qty</th>
              <th className="text-right">Entry $</th>
              <th className="text-right">Latest $</th>
              <th className="text-right">Unrealized</th>
              <th className="text-right">Return %</th>
              <th className="text-right">Days open</th>
              <th className="text-left">Freshness</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={10}
                    className="py-3 text-zinc-500 text-center">
                  {includeReplay
                    ? 'No open positions (live or replay).'
                    : 'No live open positions. Toggle to inspect recovered replay.'}
                </td>
              </tr>
            ) : (
              rows.map(p => (
                <tr key={p.position_id} className="border-t border-zinc-800">
                  <td className="py-1 font-mono">{p.symbol}</td>
                  <td>
                    {p.is_replay ? (
                      <span
                        data-test="replay-row-chip"
                        className="text-[10px] px-1.5 py-0.5 rounded bg-amber-900/40 text-amber-300"
                        title="Recovered replay — not live trading activity"
                      >
                        Recovered replay — not live trading activity
                      </span>
                    ) : (
                      <span className="text-[10px] text-zinc-400">{p.source}</span>
                    )}
                  </td>
                  <td className="text-zinc-400">{p.entry_date ?? '—'}</td>
                  <td className="text-right font-mono">{fmtQty(p.quantity)}</td>
                  <td className="text-right font-mono">{fmtUsd(p.entry_price)}</td>
                  <td className="text-right font-mono">
                    {p.latest_price == null ? (
                      <span className="text-zinc-500">unavailable</span>
                    ) : fmtUsd(p.latest_price)}
                  </td>
                  <td className={
                    'text-right font-mono ' +
                    (p.unrealized_pnl_usd == null ? 'text-zinc-500'
                     : p.unrealized_pnl_usd >= 0 ? 'text-emerald-300'
                     : 'text-rose-300')
                  }>
                    {p.unrealized_pnl_usd == null
                      ? 'unavailable'
                      : fmtUsd(p.unrealized_pnl_usd)}
                  </td>
                  <td className={
                    'text-right ' +
                    (p.unrealized_return_pct == null ? 'text-zinc-500'
                     : p.unrealized_return_pct >= 0 ? 'text-emerald-300'
                     : 'text-rose-300')
                  }>
                    {fmtPct(p.unrealized_return_pct)}
                  </td>
                  <td className="text-right text-zinc-400">
                    {p.days_open == null ? '—' : p.days_open.toFixed(1)}
                  </td>
                  <td>
                    <FreshnessChip dq={p.data_quality} />
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function FreshnessChip({
  dq,
}: { dq: PositionRow['data_quality'] }) {
  if (dq.missing_price) {
    return (
      <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400">
        Missing price
      </span>
    );
  }
  if (dq.stale_price) {
    return (
      <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-900/40 text-amber-300">
        Price data stale
      </span>
    );
  }
  return (
    <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-900/30 text-emerald-300">
      Price data current
    </span>
  );
}
