// V2 Track Record — P1 LIVE rewire. Real backend portfolio performance:
// canonical stock portfolio (NAV / returns / realized+unrealized / as_of /
// freshness) + scoped live equity curve + REAL closed trades. NO static
// TRACK_RECORD_CLOSED / EQUITY_TIMELINE / QUARTERLY_RETROS, NO fabricated
// win-rate/expectancy. Hit-rate/expectancy are computed ONLY from resolved
// (closed, realized-pnl) trades, with an honest "not enough closed history"
// state below threshold.

import { useMemo } from 'react';
import { motion } from 'framer-motion';
import { ArthosPage, MetaLabel } from '../chrome/ArthosChrome';
import {
  useCanonicalStockPortfolio,
  usePaperEquity,
  useExecutedTrades,
  type ExecutedTrade,
} from '@/lib/operator/hooks';

const MIN_CLOSES_FOR_STATS = 10;

function FadeIn({ delay = 0, children, className }: {
  delay?: number; children: React.ReactNode; className?: string;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.55, delay, ease: [0.32, 0.72, 0, 1] }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

function absTime(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

export function TrackRecord() {
  const { data: book } = useCanonicalStockPortfolio();
  const pid = book?.portfolio_id;
  const { data: equity } = usePaperEquity(undefined, undefined, pid);
  const { data: tradesData } = useExecutedTrades(false, pid);

  const points = equity ?? [];
  // Real closed trades = sells with a realized P&L.
  const closed: ExecutedTrade[] = useMemo(
    () => (tradesData?.trades ?? []).filter(
      (t) => t.side === 'sell' && t.realized_pnl != null,
    ),
    [tradesData],
  );

  const stats = useMemo(() => {
    if (closed.length === 0) return null;
    const pnls = closed.map((t) => t.realized_pnl as number);
    const wins = pnls.filter((p) => p > 0);
    const losses = pnls.filter((p) => p < 0);
    const hitRate = wins.length / closed.length;
    const avgWin = wins.length ? wins.reduce((s, p) => s + p, 0) / wins.length : 0;
    const avgLoss = losses.length ? losses.reduce((s, p) => s + p, 0) / losses.length : 0;
    const expectancy = pnls.reduce((s, p) => s + p, 0) / pnls.length;
    return { total: closed.length, wins: wins.length, losses: losses.length, hitRate, avgWin, avgLoss, expectancy };
  }, [closed]);

  const dd = useMemo(() => {
    if (points.length === 0) return null;
    let peak = points[0].equity, depth = 0;
    for (const p of points) { peak = Math.max(peak, p.equity); depth = Math.min(depth, ((p.equity - peak) / peak) * 100); }
    return depth;
  }, [points]);

  return (
    <ArthosPage maxWidth="max-w-copy">
      <header className="mb-12 sm:mb-14">
        <MetaLabel>Track Record</MetaLabel>
        <h1 className="font-serif text-masthead ink-primary mt-3 mb-6 max-w-[20ch]">The honest math.</h1>
        <p className="ink-muted leading-relaxed max-w-narrative mb-2">
          Real performance of the tracked practice portfolio — sourced live from
          the backend. Nothing here is hand-written.
        </p>
        {book?.as_of && (
          <p className="ink-fainter text-[12px] tabular-nums">
            As of {absTime(book.as_of)} · source: live ·{' '}
            <span style={{ color: book.freshness === 'fresh' ? 'var(--brand)' : 'oklch(0.70 0.14 75)' }}>
              {book.freshness}
            </span>
          </p>
        )}
      </header>

      <FadeIn delay={0.04}>
        <section className="mb-14">
          <MetaLabel>Lifetime</MetaLabel>
          {book?.total_return_pct == null ? (
            <p className="ink-muted text-[15px] mt-3">Practice account performance is unavailable right now.</p>
          ) : (
            <>
              <div className="font-serif text-headline ink-primary mt-3 tabular-nums mb-2">
                {book.total_return_pct >= 0 ? '+' : '−'}{Math.abs(book.total_return_pct).toFixed(2)}%
              </div>
              <p className="ink-muted text-[15px] leading-relaxed">
                NAV{' '}
                <span className="ink-primary tabular-nums">
                  ${(book.nav ?? 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                </span>
                {' '}from ${(book.starting_capital ?? 0).toLocaleString(undefined, { maximumFractionDigits: 0 })} ·
                realized <span className="ink-primary tabular-nums">{(book.realized_pnl ?? 0) >= 0 ? '+' : '−'}${Math.abs(book.realized_pnl ?? 0).toFixed(0)}</span> ·
                unrealized <span className="ink-primary tabular-nums">{(book.unrealized_pnl ?? 0) >= 0 ? '+' : '−'}${Math.abs(book.unrealized_pnl ?? 0).toFixed(0)}</span>.
              </p>
            </>
          )}
        </section>
      </FadeIn>

      <FadeIn delay={0.08}>
        <section className="mb-16">
          <div className="flex items-baseline justify-between mb-5 flex-wrap gap-3">
            <MetaLabel>Equity curve · live snapshots</MetaLabel>
            {dd != null && <span className="text-meta ink-fainter">Worst drawdown {dd.toFixed(1)}%</span>}
          </div>
          {points.length < 2 ? (
            <p className="ink-muted italic text-[14px]">Not enough live snapshots yet to plot a curve.</p>
          ) : (
            <EquityChart points={points} />
          )}
        </section>
      </FadeIn>

      <FadeIn delay={0.14}>
        <section className="mb-16">
          <MetaLabel>The numbers</MetaLabel>
          {stats == null || stats.total < MIN_CLOSES_FOR_STATS ? (
            <p className="ink-muted italic leading-relaxed mt-4 max-w-narrative text-[14px]">
              {stats == null
                ? 'No closed trades resolved yet. Hit-rate and expectancy appear here once trades close — I won’t show a win rate I can’t back with resolved trades.'
                : `Only ${stats.total} closed trade${stats.total === 1 ? '' : 's'} so far — I won’t publish a hit rate or expectancy until at least ${MIN_CLOSES_FOR_STATS} have resolved.`}
            </p>
          ) : (
            <>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-px bg-hairline mt-5 rounded-2xl overflow-hidden">
                <StatCell label="Hit rate" value={`${(stats.hitRate * 100).toFixed(0)}%`} sub={`${stats.wins} of ${stats.total}`} />
                <StatCell label="Avg win" value={`+$${stats.avgWin.toFixed(0)}`} />
                <StatCell label="Avg loss" value={`-$${Math.abs(stats.avgLoss).toFixed(0)}`} />
                <StatCell label="Expectancy" value={`${stats.expectancy >= 0 ? '+' : '−'}$${Math.abs(stats.expectancy).toFixed(0)}`} sub="realized/trade" />
              </div>
              <p className="text-[13px] ink-fainter italic leading-relaxed mt-5 max-w-narrative">
                Computed from {stats.total} resolved (closed) trades' realized P&L. Past results do not promise the next trade.
              </p>
            </>
          )}
        </section>
      </FadeIn>

      <FadeIn delay={0.2}>
        <section className="mb-16">
          <MetaLabel>All closed positions</MetaLabel>
          {closed.length === 0 ? (
            <p className="ink-muted italic text-[14px] mt-4">No closed positions yet.</p>
          ) : (
            <ul className="mt-7 space-y-px bg-hairline">
              {closed.slice().sort((a, b) => (b.fill_ts ?? '').localeCompare(a.fill_ts ?? '')).map((t) => (
                <li key={t.trade_id} className="surface-base py-5 flex items-baseline justify-between gap-4 flex-wrap">
                  <div className="min-w-0 flex-1">
                    <span className="font-mono ink-primary text-[14px]">{t.symbol}</span>
                    <span className="text-meta ink-fainter tabular-nums ml-3">
                      {t.fill_ts ? absTime(t.fill_ts) : '—'}{t.source !== 'live' && ` · ${t.source}`}
                    </span>
                  </div>
                  <div className="text-right tabular-nums shrink-0 ink-primary text-[14px]">
                    <span className="mr-1">{(t.realized_pnl ?? 0) >= 0 ? '▲' : '▼'}</span>
                    {(t.realized_pnl ?? 0) >= 0 ? '+' : '−'}${Math.abs(t.realized_pnl ?? 0).toFixed(2)}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </FadeIn>

      <div className="border-t border-hairline pt-12">
        <p className="font-serif italic ink-muted text-[18px] leading-[1.6] max-w-narrative">
          A track record only means something if the losses carry the same weight as the wins — and the numbers come from real, resolved trades.
        </p>
      </div>
    </ArthosPage>
  );
}

function StatCell({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="surface-drawer p-5 sm:p-6">
      <div className="text-meta ink-fainter mb-2.5">{label}</div>
      <div className="font-serif text-[24px] sm:text-[28px] ink-primary leading-none tabular-nums">{value}</div>
      {sub && <div className="text-[11px] ink-fainter mt-1.5">{sub}</div>}
    </div>
  );
}

interface EqPoint { date: string; equity: number }
function EquityChart({ points }: { points: EqPoint[] }) {
  const width = 800, height = 240, pad = { top: 20, right: 20, bottom: 30, left: 50 };
  const innerW = width - pad.left - pad.right, innerH = height - pad.top - pad.bottom;
  const eqs = points.map((p) => p.equity);
  const min = Math.min(...eqs), max = Math.max(...eqs), range = max - min || 1;
  const x = (i: number) => pad.left + (i / (points.length - 1)) * innerW;
  const y = (eq: number) => pad.top + innerH - ((eq - min) / range) * innerH;
  const line = points.map((p, i) => `${x(i).toFixed(1)},${y(p.equity).toFixed(1)}`).join(' ');
  const area = `${pad.left},${pad.top + innerH} ${line} ${pad.left + innerW},${pad.top + innerH}`;
  return (
    <div className="overflow-x-auto -mx-2 sm:mx-0">
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full min-w-[600px] ink-primary" style={{ height: 'auto' }}>
        <polygon points={area} fill="currentColor" opacity={0.06} />
        <polyline points={line} fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" opacity={0.9} />
        {[0, Math.floor(points.length / 2), points.length - 1].map((i) => (
          <text key={i} x={x(i)} y={height - 8} textAnchor="middle" fill="currentColor" fillOpacity={0.5} fontSize="10" fontFamily="Inter">
            {points[i].date.slice(5)}
          </text>
        ))}
      </svg>
    </div>
  );
}
