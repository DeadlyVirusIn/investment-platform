// GlobalTicker — the running market tape, mounted globally in ArthosChrome so
// it shows near the top on every main page (Discover, Portfolio, Pick, …).
//
// Restores the old Shell-mounted MarketTicker behaviour (a *moving* tape, not a
// static row) but self-contained: the old `u-ticker-track` CSS was removed in
// the V2 migration, so the marquee keyframes are injected inline here. Uses the
// existing live tape (useTape → Polygon delayed quotes). Honest: hides when
// there are no quotes; when markets are closed (all 0.00%) it still scrolls with
// a "Markets closed" lead and muted values. Respects prefers-reduced-motion.

import { useTape } from '@/lib/market/hooks';

const LABELS: Record<string, string> = {
  SPY: 'S&P 500', QQQ: 'Nasdaq 100', DIA: 'Dow Jones',
};

export function GlobalTicker() {
  const { data } = useTape('macro');
  const quotes = (data && !data.stale ? data.quotes : []).filter((q) => q.change_pct != null);
  if (quotes.length === 0) return null;

  const allFlat = quotes.every((q) => (q.change_pct ?? 0) === 0);
  // Triple the run so translateX(-33.333%) loops seamlessly.
  const run = [...quotes, ...quotes, ...quotes];

  return (
    <div className="w-full overflow-hidden" aria-label="Live market ticker"
      style={{
        borderBottom: '1px solid var(--border)',
        backgroundColor: 'color-mix(in oklch, var(--background) 90%, var(--card))',
      }}>
      <style>{`
        @keyframes arthos-ticker { from { transform: translateX(0); } to { transform: translateX(-33.333%); } }
        .arthos-ticker-track { animation: arthos-ticker 36s linear infinite; will-change: transform; }
        @media (prefers-reduced-motion: reduce) { .arthos-ticker-track { animation: none; } }
      `}</style>
      <div className="arthos-ticker-track flex items-center whitespace-nowrap py-1.5">
        {allFlat && (
          <span className="px-4 ink-fainter" style={{ fontSize: 11 }}>Markets closed · delayed</span>
        )}
        {run.map((q, i) => {
          const chg = q.change_pct ?? 0;
          const up = chg >= 0;
          return (
            <span key={`${q.symbol}-${i}`} className="inline-flex items-baseline gap-1.5 px-4" style={{ fontSize: 11.5 }}>
              <span className="ink-primary" style={{ fontWeight: 600 }}>{LABELS[q.symbol] ?? q.symbol}</span>
              {q.price != null && (
                <span className="ink-muted tabular-nums">{q.price.toFixed(2)}</span>
              )}
              <span className="tabular-nums" style={{
                color: allFlat ? 'var(--muted-foreground)' : up ? 'var(--brand)' : 'oklch(0.70 0.14 75)',
              }}>{allFlat ? '' : up ? '▲ ' : '▼ '}{up ? '+' : ''}{chg.toFixed(2)}%</span>
            </span>
          );
        })}
      </div>
    </div>
  );
}
