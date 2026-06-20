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
const POS = 'var(--brand)';
const NEG = 'oklch(0.70 0.14 75)';

function fmtUsd(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return '—';
  const s = n < 0 ? '-' : '';
  return `${s}$${Math.abs(n).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}
function fmtPct(n: number | null | undefined, dp = 2): string {
  if (n == null || !Number.isFinite(n)) return '—';
  return `${n >= 0 ? '+' : ''}${n.toFixed(dp)}%`;
}

function Tile({ label, value, sub, tone, big }: { label: string; value: string; sub?: string; tone?: 'pos' | 'neg'; big?: boolean }) {
  const color = tone === 'pos' ? POS : tone === 'neg' ? NEG : undefined;
  return (
    <div className="border-t border-hairline pt-3">
      <div className="text-meta ink-fainter mb-1">{label}</div>
      <div className={`font-serif leading-none tabular-nums ${big ? 'text-[28px]' : 'text-[20px]'}`} style={color ? { color } : undefined}>{value}</div>
      {sub && <div className="ink-fainter text-[12px] mt-1">{sub}</div>}
    </div>
  );
}

export function TrackRecordIntegrityCard() {
  const { data: book } = useCanonicalStockPortfolio();
  const pid = book?.portfolio_id;
  const { data: tradesData } = useExecutedTrades(false, pid, { enabled: !!pid });
  const { data: closedPos } = useExecutedPositions(false, false, pid, { enabled: !!pid });
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
  const fresh = freshness === 'fresh';
  const closedCount = (closedPos?.positions ?? []).filter((p) => !p.is_open).length;

  return (
    <section className="mb-12">
      <MetaLabel>Track record integrity</MetaLabel>
      <p className="ink-muted text-[14px] leading-relaxed mt-2 mb-4 max-w-narrative">
        Every number is computed from real paper trades and live snapshots — nothing hand-entered.
      </p>

      <div className="rounded-xl border border-hairline overflow-hidden">
        <div className="flex items-center justify-between px-5 sm:px-6 py-3 border-b border-hairline">
          <span className="text-[12px] font-semibold uppercase tracking-wide ink-muted">Live performance</span>
          <span className="flex items-center gap-1.5 text-[12px] ink-muted capitalize">
            <span className="rounded-full" style={{ width: 7, height: 7, background: fresh ? POS : NEG }} />
            {freshness} · {book?.source ?? 'live'}
          </span>
        </div>

        <div className="p-5 sm:p-6 grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-5">
          <Tile label="Realized return" value={fmtPct(book?.total_return_pct)} sub={`NAV ${fmtUsd(book?.nav)}`} tone={realizedTone} big />
          <Tile label="Realized P/L" value={fmtUsd(book?.realized_pnl)} tone={realizedTone} big />
          <Tile label="Max drawdown" value={maxDrawdown == null ? '—' : `${maxDrawdown.toFixed(1)}%`} tone={maxDrawdown == null ? undefined : 'neg'} big />
          <Tile label="Open positions" value={String(book?.open_positions_count ?? '—')} />
          <Tile label="Closed ideas" value={String(closedCount || closedSells.length || '—')} sub={`${closedSells.length} resolved trades`} />
          <Tile
            label="Win rate"
            value={enoughCloses ? fmtPct(winRate, 0).replace('+', '') : 'Hidden'}
            sub={enoughCloses ? `${wins}/${closedSells.length} resolved` : `needs ${MIN_CLOSES}, have ${closedSells.length}`}
          />
          <Tile label="Avg hold time" value={avgHoldDays == null ? '—' : `${Math.round(avgHoldDays)} days`} />
        </div>

        <p className="ink-fainter text-[12px] leading-relaxed px-5 sm:px-6 py-3 border-t border-hairline">
          Win-rate stays hidden until at least {MIN_CLOSES} ideas resolve — we won't publish a rate we can't back.
          Confidence calibration is tracked internally and surfaces here as more ideas close.
        </p>
      </div>
    </section>
  );
}
