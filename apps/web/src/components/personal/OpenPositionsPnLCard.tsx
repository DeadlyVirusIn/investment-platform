// Personal-Analytics — read-only Open Positions PnL aggregate.
//
// Reads /api/performance/paper/unrealized and renders headline
// unrealized stats with live vs replay split. Always shows the
// "all positions are replay" note when applicable. No buttons.

import { useQuery } from '@tanstack/react-query';
import { apiGet } from '@/lib/api';

interface Bucket {
  n_positions: number;
  n_with_price: number;
  n_unavailable: number;
  total_unrealized_pnl_usd: number | null;
  avg_unrealized_return_pct: number | null;
  best: { symbol: string; unrealized_pnl_usd: number;
          unrealized_return_pct: number | null } | null;
  worst: { symbol: string; unrealized_pnl_usd: number;
           unrealized_return_pct: number | null } | null;
}

interface UnrealizedResponse {
  include_replay: boolean;
  stale_threshold_days: number;
  as_of: string;
  all_positions_are_replay: boolean;
  headline: Bucket;
  live: Bucket;
  replay: Bucket;
}

const fmtUsd = (n: number | null | undefined) =>
  n == null ? '—' : `$${n.toFixed(2)}`;
const fmtPct = (n: number | null | undefined) =>
  n == null ? '—' : `${(n * 100).toFixed(2)}%`;

export default function OpenPositionsPnLCard() {
  const q = useQuery<UnrealizedResponse>({
    queryKey: ['perf-paper', 'unrealized'],
    queryFn: () => apiGet<UnrealizedResponse>(
      '/performance/paper/unrealized',
    ),
    staleTime: 60_000,
  });
  const r = q.data;
  const live = r?.live;
  const replay = r?.replay;

  return (
    <section
      data-test="open-positions-pnl-card"
      className="rounded-md border border-zinc-700 bg-zinc-900/40 p-4 mb-4"
    >
      <header className="flex items-baseline justify-between mb-3">
        <h3 className="text-sm font-semibold text-zinc-100">
          Open Positions — unrealized P&L
        </h3>
        <span className="text-[10px] uppercase tracking-wide text-zinc-500">
          GET-only · derived from latest price_bar
        </span>
      </header>

      {r?.all_positions_are_replay && (
        <div
          data-test="all-replay-note"
          className="rounded border border-amber-700 bg-amber-900/20 px-3 py-2 text-xs text-zinc-200 mb-3"
        >
          All open positions are <strong>recovered replay</strong> rows
          — NOT live trading activity. Live unrealized headline below
          will read zero until live trades open.
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
        <Cell label="Live total unrealized P&L"
              value={fmtUsd(live?.total_unrealized_pnl_usd)}
              hint={`${live?.n_positions ?? 0} positions`} />
        <Cell label="Live avg return"
              value={fmtPct(live?.avg_unrealized_return_pct)}
              hint={`${live?.n_with_price ?? 0} priced`} />
        <Cell label="Live best"
              value={live?.best
                ? `${live.best.symbol} ${fmtUsd(live.best.unrealized_pnl_usd)}`
                : '—'} />
        <Cell label="Live worst"
              value={live?.worst
                ? `${live.worst.symbol} ${fmtUsd(live.worst.unrealized_pnl_usd)}`
                : '—'} />
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Cell label="Replay positions"
              value={String(replay?.n_positions ?? 0)}
              hint="not live" warn />
        <Cell label="Replay total unrealized"
              value={fmtUsd(replay?.total_unrealized_pnl_usd)}
              hint="not live" warn />
        <Cell label="Replay avg return"
              value={fmtPct(replay?.avg_unrealized_return_pct)}
              hint="not live" warn />
        <Cell label="Stale-price threshold"
              value={`${r?.stale_threshold_days ?? '—'}d`}
              hint="position-level data quality" />
      </div>
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
