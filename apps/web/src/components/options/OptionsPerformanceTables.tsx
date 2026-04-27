// Phase 11G — by-strategy + by-underlying breakdown tables.

import type { PerformanceSummary } from '@/lib/options/optionsApi';
import { fmtMoney, fmtPct } from './format';

export function ByStrategyTable({ data }: { data: PerformanceSummary }) {
  if (data.by_strategy.length === 0) {
    return <div className="text-sm text-zinc-400">No strategy breakdown.</div>;
  }
  return (
    <table className="w-full text-xs">
      <thead className="text-zinc-500">
        <tr>
          <th className="px-2 py-1 text-left">Strategy</th>
          <th className="px-2 py-1 text-right">N</th>
          <th className="px-2 py-1 text-right">Wins</th>
          <th className="px-2 py-1 text-right">Win rate</th>
          <th className="px-2 py-1 text-right">Assigned</th>
          <th className="px-2 py-1 text-right">Total PnL</th>
          <th className="px-2 py-1 text-right">Total fees</th>
        </tr>
      </thead>
      <tbody>
        {data.by_strategy.map((r) => (
          <tr key={r.strategy_name} className="border-b border-zinc-800">
            <td className="px-2 py-1">{r.strategy_name}</td>
            <td className="px-2 py-1 text-right">{r.n}</td>
            <td className="px-2 py-1 text-right">{r.n_wins}</td>
            <td className="px-2 py-1 text-right tabular-nums">{fmtPct(r.win_rate)}</td>
            <td className="px-2 py-1 text-right">{r.n_assigned}</td>
            <td className="px-2 py-1 text-right tabular-nums">{fmtMoney(r.total_pnl_dollars)}</td>
            <td className="px-2 py-1 text-right tabular-nums">{fmtMoney(r.total_fees_dollars)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function ByUnderlyingTable({ data }: { data: PerformanceSummary }) {
  if (data.by_underlying.length === 0) {
    return <div className="text-sm text-zinc-400">No underlying breakdown.</div>;
  }
  return (
    <table className="w-full text-xs">
      <thead className="text-zinc-500">
        <tr>
          <th className="px-2 py-1 text-left">Underlying</th>
          <th className="px-2 py-1 text-right">N</th>
          <th className="px-2 py-1 text-right">Wins</th>
          <th className="px-2 py-1 text-right">Win rate</th>
          <th className="px-2 py-1 text-right">Total PnL</th>
        </tr>
      </thead>
      <tbody>
        {data.by_underlying.map((r) => (
          <tr key={r.underlying} className="border-b border-zinc-800">
            <td className="px-2 py-1">{r.underlying}</td>
            <td className="px-2 py-1 text-right">{r.n}</td>
            <td className="px-2 py-1 text-right">{r.n_wins}</td>
            <td className="px-2 py-1 text-right tabular-nums">{fmtPct(r.win_rate)}</td>
            <td className="px-2 py-1 text-right tabular-nums">{fmtMoney(r.total_pnl_dollars)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
