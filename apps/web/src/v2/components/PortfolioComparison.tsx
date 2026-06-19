// PortfolioComparison — compare model portfolios side by side (Build stage).
// Mobile-first: a compact, aligned grid (portfolio · return · worst drop ·
// risk) sorted by return so the growth↔conservative spread is obvious. Each
// row taps through to the detail. Real fields only; no fabrication.

import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ChevronDown } from 'lucide-react';
import { SurfaceCard } from './ui/SurfaceCard';
import { useModelPortfolios } from '@/lib/operator/modelPortfolios';
import { riskLevel } from '../lib/portfolioMeta';

// The list endpoint returns holdings_count (the shared summary type is stale).
type Row = {
  slug: string; name: string;
  return_pct: number | null; max_drawdown_pct: number | null;
  risk_label: string | null; holdings_count?: number;
};

function pct(v: number | string | null | undefined, sign = true): string {
  const n = typeof v === 'number' ? v : parseFloat(String(v ?? ''));
  if (!Number.isFinite(n)) return '—';
  return `${sign && n >= 0 ? '+' : ''}${Math.round(n).toLocaleString()}%`;
}

export function PortfolioComparison({ collapsed = false }: { collapsed?: boolean }) {
  const [open, setOpen] = useState(!collapsed);
  const { data, isLoading } = useModelPortfolios();
  const portfolios = ((data?.portfolios ?? []) as unknown as Row[]).slice();
  if (!isLoading && portfolios.length < 2) return null;

  portfolios.sort((a, b) =>
    (Number(b.return_pct) || 0) - (Number(a.return_pct) || 0),
  );

  return (
    <section className="mb-10">
      <button type="button" onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between gap-3 text-left mb-2"
        aria-expanded={open}>
        <span>
          <span className="font-display ink-primary block" style={{
            fontSize: 22, lineHeight: 1.2,
            fontFamily: "'Instrument Serif', ui-serif, Georgia, serif",
          }}>Compare portfolios</span>
          {!open && (
            <span className="ink-muted block mt-0.5" style={{ fontSize: 12.5 }}>
              Return, worst drop &amp; risk, side by side. Tap to open.
            </span>
          )}
        </span>
        <ChevronDown className="size-5 shrink-0 transition-transform"
          style={{ transform: open ? 'rotate(180deg)' : 'none', color: 'var(--muted-foreground)' }} aria-hidden />
      </button>
      {open && (<>
      <p className="ink-muted leading-relaxed max-w-narrative mb-4" style={{ fontSize: 13 }}>
        Same idea, different temperaments — more growth usually means bigger drops
        along the way. Pick the one whose trade-off fits you.
      </p>

      <SurfaceCard variant="default" className="p-0 overflow-hidden">
        <div className="grid items-center gap-2 px-4 py-2.5"
          style={{ gridTemplateColumns: '1fr 58px 56px 64px', borderBottom: '1px solid var(--border)' }}>
          <Head>Portfolio</Head>
          <Head right>Return</Head>
          <Head right>Worst drop</Head>
          <Head right>Risk</Head>
        </div>
        {isLoading ? (
          <p className="ink-muted px-4 py-4" style={{ fontSize: 13 }}>Loading…</p>
        ) : (
          portfolios.map((p) => (
            <Link key={p.slug} to={`/v2/portfolios/${p.slug}`}
              className="grid items-center gap-2 px-4 py-3 hover:opacity-80"
              style={{ gridTemplateColumns: '1fr 58px 56px 64px', borderTop: '1px solid var(--border)' }}>
              <span className="min-w-0">
                <span className="ink-primary block truncate" style={{ fontSize: 13, fontWeight: 600 }}>{p.name}</span>
                {p.holdings_count != null && (
                  <span className="ink-fainter block" style={{ fontSize: 10.5 }}>{p.holdings_count} holdings</span>
                )}
              </span>
              <span className="text-right tabular-nums" style={{ fontSize: 12.5, color: 'var(--brand)', fontWeight: 600 }}>
                {pct(p.return_pct)}
              </span>
              <span className="text-right tabular-nums" style={{ fontSize: 12.5, color: 'oklch(0.70 0.14 75)' }}>
                {pct(p.max_drawdown_pct, false)}
              </span>
              <span className="text-right ink-muted" style={{ fontSize: 11 }}>
                {riskLevel(p.risk_label).replace(' risk', '')}
              </span>
            </Link>
          ))
        )}
      </SurfaceCard>
      <p className="ink-fainter leading-relaxed mt-2" style={{ fontSize: 11 }}>
        All are long-hold baskets of 5–6 companies. Return is total-return since
        inception — <strong>past performance isn't a promise</strong>; "worst drop"
        is the deepest fall along the way.
      </p>
      </>)}
    </section>
  );
}

function Head({ children, right }: { children: React.ReactNode; right?: boolean }) {
  return (
    <span className={`font-semibold uppercase ${right ? 'text-right' : ''}`}
      style={{ fontSize: 9.5, letterSpacing: '0.08em', color: 'var(--muted-foreground)' }}>
      {children}
    </span>
  );
}
