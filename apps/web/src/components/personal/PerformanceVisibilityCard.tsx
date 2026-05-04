// Personal-Analytics Phase — read-only paper-trading performance card.
//
// Reads /api/performance/paper/{summary,attribution} and renders:
//   * live + replay split counts (always-on)
//   * realized/win/loss with honest "no_closed_outcomes_yet" state
//   * by-source attribution showing replay vs live
//   * recovered-replay banner when applicable
//
// No buttons, no toggles that mutate. include_replay=false here so
// the headline stays live-only; the toggle for inspecting replay
// rows lives on PortfolioTerminal at /portfolio.

import { useQuery } from '@tanstack/react-query';
import { apiGet } from '@/lib/api';

interface PaperPerfSummary {
  include_replay: boolean;
  total_trades: number;
  open_trades: number;
  closed_trades: number;
  open_positions: number;
  win_count: number;
  loss_count: number;
  breakeven_count: number;
  win_rate: number | null;
  note: string | null;
  realized_pnl_total: number | null;
  avg_realized_pnl: number | null;
  best_realized_pnl: number | null;
  worst_realized_pnl: number | null;
  has_replay_recovered_rows: boolean;
  live_trades_count: number;
  replay_trades_count: number;
  source_breakdown: Record<string, number>;
  outcomes: { closed: number; open_pending: number };
}

interface AttributionRow {
  symbol?: string;
  source?: string;
  total_trades: number;
  closed_trades: number;
  open_pending_trades: number;
  realized_pnl_usd: number | null;
}

interface AttributionResponse {
  by_symbol: AttributionRow[];
  by_source: AttributionRow[];
}

const fmtUsd = (n: number | null | undefined) =>
  n == null ? '—' : `$${n.toFixed(2)}`;
const fmtPct = (n: number | null | undefined) =>
  n == null ? '—' : `${(n * 100).toFixed(1)}%`;

export default function PerformanceVisibilityCard() {
  const summaryQ = useQuery<PaperPerfSummary>({
    queryKey: ['perf-paper', 'summary'],
    queryFn: () => apiGet<PaperPerfSummary>('/performance/paper/summary'),
    staleTime: 60_000,
  });
  const attributionQ = useQuery<AttributionResponse>({
    queryKey: ['perf-paper', 'attribution'],
    queryFn: () => apiGet<AttributionResponse>(
      '/performance/paper/attribution',
    ),
    staleTime: 60_000,
  });

  const s = summaryQ.data;
  const a = attributionQ.data;

  return (
    <section
      data-test="perf-visibility-card"
      className="rounded-md border border-zinc-700 bg-zinc-900/40 p-4 mb-4"
    >
      <header className="flex items-baseline justify-between mb-3">
        <h3 className="text-sm font-semibold text-zinc-100">
          Paper Performance — read-only visibility
        </h3>
        <span className="text-[10px] uppercase tracking-wide text-zinc-500">
          GET-only · live = paper_trade not in replay manifest
        </span>
      </header>

      {/* Top strip — always-on split counts */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
        <Cell label="Live trades" value={String(s?.live_trades_count ?? 0)}
              hint="excluded from replay manifest" />
        <Cell label="Recovered replay trades"
              value={String(s?.replay_trades_count ?? 0)}
              hint="not live trading activity" warn />
        <Cell label="Open trades" value={String(s?.open_trades ?? 0)}
              hint="default toggle off" />
        <Cell label="Closed trades" value={String(s?.closed_trades ?? 0)}
              hint="realized_pnl IS NOT NULL" />
      </div>

      {/* Realized panel */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
        <Cell label="Realized P&L (live)"
              value={fmtUsd(s?.realized_pnl_total)} />
        <Cell label="Win rate (live)"
              value={s?.win_rate == null ? '—' : fmtPct(s.win_rate)}
              hint={s?.note ?? ''} />
        <Cell label="Best closed trade"
              value={fmtUsd(s?.best_realized_pnl)} />
        <Cell label="Worst closed trade"
              value={fmtUsd(s?.worst_realized_pnl)} />
      </div>

      {s?.note === 'no_closed_outcomes_yet' && (
        <div
          data-test="perf-no-closed-outcomes"
          className="text-xs text-amber-300 mb-3"
        >
          No closed trade outcomes yet — win-rate and average return
          intentionally left blank. Numbers will populate as
          paper_trade rows close.
        </div>
      )}

      {s?.has_replay_recovered_rows && (
        <div
          data-test="perf-replay-banner"
          className="rounded-md border border-amber-700 bg-amber-900/20 px-3 py-2 text-xs text-zinc-200 mb-3"
        >
          <strong>{s.replay_trades_count}</strong> recovered replay
          trades present — NOT live trading activity. Toggle "Show
          recovered replay data" on the Paper Trading Terminal at{' '}
          <a href="/portfolio" className="underline">/portfolio</a>{' '}
          to inspect them. Excluded from this card by default.
        </div>
      )}

      {/* By-source breakdown */}
      {a?.by_source && a.by_source.length > 0 && (
        <table
          data-test="perf-by-source-table"
          className="w-full text-xs"
        >
          <thead className="text-zinc-500">
            <tr>
              <th className="text-left py-1">Source</th>
              <th className="text-right">Total</th>
              <th className="text-right">Closed</th>
              <th className="text-right">Open pending</th>
              <th className="text-right">Realized P&L</th>
            </tr>
          </thead>
          <tbody>
            {a.by_source.map(row => (
              <tr key={row.source ?? 'unknown'}>
                <td className="py-1">
                  {row.source === 'replay' || row.source === 'test' ? (
                    <span className="text-amber-400">
                      {row.source} — not live
                    </span>
                  ) : (
                    <span>{row.source ?? 'live'}</span>
                  )}
                </td>
                <td className="text-right">{row.total_trades}</td>
                <td className="text-right">{row.closed_trades}</td>
                <td className="text-right">{row.open_pending_trades}</td>
                <td className="text-right">{fmtUsd(row.realized_pnl_usd)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function Cell({
  label, value, hint, warn,
}: {
  label: string; value: string; hint?: string; warn?: boolean;
}) {
  return (
    <div className="rounded border border-zinc-800 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wide text-zinc-500">
        {label}
      </div>
      <div className={
        'text-lg font-semibold mt-0.5 ' +
        (warn ? 'text-amber-300' : 'text-zinc-100')
      }>
        {value}
      </div>
      {hint && (
        <div className="text-[10px] text-zinc-500 mt-0.5">{hint}</div>
      )}
    </div>
  );
}
