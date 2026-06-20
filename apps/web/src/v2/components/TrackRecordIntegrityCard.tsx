// Track Record Integrity Card (P0-3, investor-demo).
//
// One canonical trust card proving honesty + consistency. Every figure is
// computed from REAL paper trades and live snapshots (canonical portfolio +
// executed trades/positions + equity curve) — nothing hand-entered. Honesty
// rules: win-rate stays hidden until >= MIN_CLOSES resolve; calibration is
// disclosed as internal-until-enough-data rather than faked.

import { useMemo } from 'react';
import { MetaLabel } from '../chrome/ArthosChrome';
import {
  useCanonicalStockPortfolio,
  useExecutedTrades,
  useExecutedPositions,
  usePaperEquity,
} from '@/lib/operator/hooks';

const MIN_CLOSES = 10;

function fmtUsd(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return '—';
  const s = n < 0 ? '-' : '';
  return `${s}$${Math.abs(n).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}
function fmtPct(n: number | null | undefined, dp = 2): string {
  if (n == null || !Number.isFinite(n)) return '—';
  return `${n >= 0 ? '+' : ''}${n.toFixed(dp)}%`;
}

function Tile({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: 'pos' | 'neg' }) {
  const color = tone === 'pos' ? 'var(--brand)' : tone === 'neg' ? 'oklch(0.70 0.14 75)' : undefined;
  return (
    <div className="border-t border-hairline pt-3">
      <div className="text-meta ink-fainter mb-1">{label}</div>
      <div className="font-serif text-[22px] leading-none tabular-nums" style={color ? { color } : undefined}>{value}</div>
      {sub && <div className="ink-fainter text-[12px] mt-1">{sub}</div>}
    </div>
  );
}

export function TrackRecordIntegrityCard() {
  const { data: book } = useCanonicalStockPortfolio();
  const pid = book?.portfolio_id;
  const { data: tradesData } = useExecutedTrades(false, pid);
  const { data: closedPos } = useExecutedPositions(false, false, pid);
  const { data: equity } = usePaperEquity(undefined, undefined, pid);

  const closedSells = useMemo(
    () => (tradesData?.trades ?? []).filter((t) => t.side === 'sell' && t.realized_pnl != null),
    [tradesData],
  );
  const wins = closedSells.filter((t) => (t.realized_pnl as number) > 0).length;
  const enoughCloses = closedSells.length >= MIN_CLOSES;
  const winRate = enoughCloses ? (wins / closedSells.length) * 100 : null;

  const avgHoldDays = useMemo(() => {
    const ds: number[] = [];
    for (const p of closedPos?.positions ?? []) {
      if (p.is_open || !p.opened_at || !p.closed_at) continue;
      const a = new Date(p.opened_at).getTime();
      const b = new Date(p.closed_at).getTime();
      if (Number.isFinite(a) && Number.isFinite(b) && b >= a) ds.push((b - a) / 86_400_000);
    }
    if (ds.length === 0) return null;
    return ds.reduce((s, d) => s + d, 0) / ds.length;
  }, [closedPos]);

  const maxDrawdown = useMemo(() => {
    const pts = (equity ?? []) as Array<{ equity?: number; total_equity?: number }>;
    let peak = -Infinity, mdd = 0;
    for (const p of pts) {
      const v = p.equity ?? p.total_equity;
      if (v == null || !Number.isFinite(v)) continue;
      if (v > peak) peak = v;
      if (peak > 0) mdd = Math.min(mdd, (v - peak) / peak);
    }
    return mdd < 0 ? mdd * 100 : null;
  }, [equity]);

  const realizedTone = (book?.realized_pnl ?? 0) > 0 ? 'pos' : (book?.realized_pnl ?? 0) < 0 ? 'neg' : undefined;
  const freshness = book?.freshness ?? 'unknown';
  const closedCount = (closedPos?.positions ?? []).filter((p) => !p.is_open).length;

  return (
    <section className="mb-12">
      <div className="flex items-baseline justify-between">
        <MetaLabel>Track record integrity</MetaLabel>
        <span className="ink-fainter text-[12px] capitalize">{freshness} · {book?.source ?? 'live'}</span>
      </div>
      <p className="ink-muted text-[14px] leading-relaxed mt-2 mb-5 max-w-narrative">
        Every number below is computed from real paper trades and live snapshots — nothing is hand-entered.
      </p>

      <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-5">
        <Tile label="Realized return" value={fmtPct(book?.total_return_pct)} sub={`NAV ${fmtUsd(book?.nav)}`} tone={realizedTone} />
        <Tile label="Realized P/L" value={fmtUsd(book?.realized_pnl)} tone={realizedTone} />
        <Tile label="Open positions" value={String(book?.open_positions_count ?? '—')} />
        <Tile label="Closed (paper)" value={String(closedCount || closedSells.length || '—')} sub={`${closedSells.length} resolved trades`} />
        <Tile
          label="Win rate"
          value={enoughCloses ? fmtPct(winRate, 0).replace('+', '') : 'Hidden'}
          sub={enoughCloses ? `${wins}/${closedSells.length} resolved` : `needs ${MIN_CLOSES}, have ${closedSells.length}`}
        />
        <Tile label="Avg hold time" value={avgHoldDays == null ? '—' : `${Math.round(avgHoldDays)}d`} />
        <Tile label="Max drawdown" value={maxDrawdown == null ? '—' : `${maxDrawdown.toFixed(1)}%`} tone={maxDrawdown == null ? undefined : 'neg'} />
        <Tile label="Data freshness" value={freshness === 'fresh' ? 'Fresh' : freshness.charAt(0).toUpperCase() + freshness.slice(1)} sub={`source: ${book?.source ?? 'live'}`} />
      </div>

      <p className="ink-fainter text-[12px] leading-relaxed mt-5 max-w-narrative">
        Win-rate stays hidden until at least {MIN_CLOSES} ideas resolve — we won't publish a rate we can't back.
        Confidence calibration is tracked internally and surfaces here as more ideas close.
      </p>
    </section>
  );
}
