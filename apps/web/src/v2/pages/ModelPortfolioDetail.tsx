// MVP — model-portfolio detail: thesis, track record (equity curve + stats),
// holdings, Follow CTA. Reuses ArthosPage + SurfaceCard + useModelPortfolio.

import { useParams, Link } from 'react-router-dom';
import { ArthosPage } from '../chrome/ArthosChrome';
import { PageHeader } from '../components/ui/PageHeader';
import { SurfaceCard } from '../components/ui/SurfaceCard';
import { useModelPortfolio } from '@/lib/operator/modelPortfolios';

function Curve({ navs }: { navs: number[] }) {
  if (navs.length < 2) return null;
  const w = 640, h = 160;
  const min = Math.min(...navs), max = Math.max(...navs);
  const span = max - min || 1;
  const d = navs.map((p, i) => {
    const x = (i / (navs.length - 1)) * w;
    const y = h - ((p - min) / span) * h;
    return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  const up = navs[navs.length - 1] >= navs[0];
  return (
    <svg viewBox={`0 0 ${w} ${h}`} width="100%" height={h} preserveAspectRatio="none" aria-hidden>
      <path d={d} fill="none" strokeWidth={2}
        stroke={up ? 'var(--brand)' : 'oklch(0.70 0.14 75)'} />
    </svg>
  );
}

function fmtPct(n: number | null): string {
  return n == null ? '—' : `${n >= 0 ? '+' : ''}${n.toFixed(1)}%`;
}

export function ModelPortfolioDetail() {
  const { slug } = useParams();
  const { data: pf, isLoading, isError } = useModelPortfolio(slug);

  return (
    <ArthosPage topBarEyebrow="Discover">
      <PageHeader
        eyebrow="Model Portfolio"
        title={pf?.name ?? 'Portfolio'}
        description={pf?.thesis ?? undefined}
      />

      {isLoading && (
        <SurfaceCard variant="muted" className="p-6">
          <p className="ink-muted" style={{ fontSize: 14 }}>Loading…</p>
        </SurfaceCard>
      )}
      {isError && (
        <SurfaceCard variant="default" className="p-6">
          <p style={{ fontSize: 14, color: 'var(--destructive)', fontWeight: 600 }}>
            Couldn't load this portfolio.
          </p>
        </SurfaceCard>
      )}

      {pf && (
        <>
          {/* Track record */}
          <SurfaceCard variant="highlight" className="p-6 mb-6">
            <div className="flex flex-wrap gap-6 mb-4">
              <Stat label="Total return" value={fmtPct(pf.return_pct)}
                tone={(pf.return_pct ?? 0) >= 0 ? 'pos' : 'neg'} />
              <Stat label="Max drawdown" value={fmtPct(pf.max_drawdown_pct)} tone="neg" />
              <Stat label="Since" value={pf.since ?? '—'} />
            </div>
            <Curve navs={pf.curve.map((c) => c.nav)} />
            <p className="ink-fainter mt-2" style={{ fontSize: 11 }}>
              Total-return track record (dividends reinvested), computed from
              history. Survivorship-biased — past performance is not a promise.
            </p>
          </SurfaceCard>

          {/* Holdings */}
          <SurfaceCard variant="default" className="p-5 mb-6">
            <h3 className="ink-primary mb-3" style={{ fontSize: 14, fontWeight: 600 }}>
              Holdings
            </h3>
            <ul className="divide-y" style={{ borderColor: 'var(--border)' }}>
              {pf.holdings.map((h) => (
                <li key={h.symbol} className="py-2 flex items-center justify-between">
                  <span className="font-mono ink-primary" style={{ fontSize: 13 }}>{h.symbol}</span>
                  <span className="ink-muted tabular-nums" style={{ fontSize: 13 }}>
                    {h.weight_pct.toFixed(0)}%
                  </span>
                </li>
              ))}
            </ul>
          </SurfaceCard>

          {/* Follow — Phase 4 wires the one-tap submit_trade seed. */}
          <Link to={`/v2/portfolios/${pf.slug}?follow=1`}
            className="inline-block px-5 py-2.5 rounded-full"
            style={{
              fontSize: 14, fontWeight: 600, color: 'var(--background)',
              backgroundColor: 'var(--brand)',
            }}>
            Follow → paper portfolio
          </Link>
        </>
      )}
    </ArthosPage>
  );
}

function Stat({ label, value, tone = 'muted' }: {
  label: string; value: string; tone?: 'pos' | 'neg' | 'muted';
}) {
  const color = tone === 'pos' ? 'var(--brand)'
    : tone === 'neg' ? 'oklch(0.70 0.14 75)' : 'var(--foreground)';
  return (
    <div>
      <div className="ink-fainter" style={{ fontSize: 11 }}>{label}</div>
      <div className="tabular-nums" style={{ fontSize: 20, fontWeight: 700, color }}>{value}</div>
    </div>
  );
}
