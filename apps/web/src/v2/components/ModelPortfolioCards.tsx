// MVP — model-portfolio cards + the Discover "Model Portfolios" section.
// Reuses SurfaceCard + the shared useModelPortfolios hook. Sparkline is a
// dependency-free inline SVG.

import { Link } from 'react-router-dom';
import { SurfaceCard } from './ui/SurfaceCard';
import { useTape } from '@/lib/market/hooks';
import {
  useModelPortfolios,
  useSocialProof,
  type ModelPortfolioSummary,
} from '@/lib/operator/modelPortfolios';

// Sprint D — Trending Themes: plain-English ways into the curated portfolios.
// Only themes whose portfolio actually exists are shown (honest, no dead links).
const THEMES: { label: string; slug: string }[] = [
  { label: 'Dividend growth', slug: 'dividend-growers' },
  { label: 'Big American companies', slug: 'american-megacaps' },
  { label: 'Brands you use daily', slug: 'everyday-brands' },
  { label: 'Steady compounders', slug: 'steady-compounders' },
];

export function TrendingThemes() {
  const { data } = useModelPortfolios();
  const slugs = new Set((data?.portfolios ?? []).map((p) => p.slug));
  const themes = THEMES.filter((t) => slugs.has(t.slug));
  if (themes.length === 0) return null;
  return (
    <section className="mb-10">
      <div className="flex items-baseline gap-3 mb-4">
        <span className="font-mono ink-muted" style={{ fontSize: 12 }}>#</span>
        <h2 className="font-display ink-primary" style={{
          fontSize: 22, lineHeight: 1.2,
          fontFamily: "'Instrument Serif', ui-serif, Georgia, serif",
        }}>Trending Themes</h2>
      </div>
      <div className="flex flex-wrap gap-2">
        {themes.map((t) => (
          <Link key={t.slug} to={`/v2/portfolios/${t.slug}`}
            className="px-3.5 py-1.5 rounded-full ink-primary"
            style={{ fontSize: 13, fontWeight: 600, backgroundColor: 'var(--card)', border: '1px solid var(--border)' }}>
            {t.label}
          </Link>
        ))}
      </div>
    </section>
  );
}

const INDEX_LABELS: Record<string, string> = {
  SPY: 'S&P 500', QQQ: 'Nasdaq 100', DIA: 'Dow Jones',
};

export function WhatsMovingStrip() {
  const { data } = useTape('macro');
  const quotes = (data && !data.stale ? data.quotes : []).filter((q) => q.change_pct != null);
  if (quotes.length === 0) return null;   // hide when market data unavailable
  return (
    <section className="mb-10">
      <div className="flex items-baseline gap-3 mb-4">
        <span className="font-mono ink-muted" style={{ fontSize: 12 }}>~</span>
        <h2 className="font-display ink-primary" style={{
          fontSize: 22, lineHeight: 1.2,
          fontFamily: "'Instrument Serif', ui-serif, Georgia, serif",
        }}>What's Moving Today</h2>
      </div>
      <div className="flex flex-wrap gap-3">
        {quotes.map((q) => {
          const up = (q.change_pct ?? 0) >= 0;
          return (
            <div key={q.symbol} className="px-3.5 py-2 rounded-xl"
              style={{ backgroundColor: 'var(--card)', border: '1px solid var(--border)' }}>
              <div className="ink-primary" style={{ fontSize: 13, fontWeight: 600 }}>
                {INDEX_LABELS[q.symbol] ?? q.symbol}
              </div>
              <div className="tabular-nums" style={{
                fontSize: 14, fontWeight: 700,
                color: up ? 'var(--brand)' : 'oklch(0.70 0.14 75)',
              }}>{up ? '+' : ''}{(q.change_pct ?? 0).toFixed(2)}%</div>
            </div>
          );
        })}
      </div>
      <p className="ink-fainter mt-2" style={{ fontSize: 11 }}>
        Major US market indexes, about 15 minutes delayed.
      </p>
    </section>
  );
}

// MVP Phase 7 — social proof strip: most-followed portfolio, trending,
// most-added idea. Hidden entirely when there's no activity yet (honest).
export function SocialProofStrip() {
  const { data } = useSocialProof();
  const topFollow = data?.most_followed?.[0];
  const trending = data?.trending?.[0];
  const topAdd = data?.most_added?.[0];
  if (!topFollow && !trending && !topAdd) return null;
  return (
    <div className="flex flex-wrap gap-2 mb-6">
      {topFollow && (
        <Pill to={`/v2/portfolios/${topFollow.slug}`}
          label="Most followed" value={`${topFollow.name} · ${topFollow.follows}★`} />
      )}
      {trending && trending.slug !== topFollow?.slug && (
        <Pill to={`/v2/portfolios/${trending.slug}`}
          label="Trending" value={trending.name} />
      )}
      {topAdd && (
        <Pill to={`/v2/today/pick/${topAdd.symbol}`}
          label="Most added" value={`${topAdd.symbol} · ${topAdd.adds}×`} />
      )}
    </div>
  );
}

function Pill({ to, label, value }: { to: string; label: string; value: string }) {
  return (
    <Link to={to} className="px-3 py-1.5 rounded-full inline-flex items-center gap-1.5"
      style={{ fontSize: 12, backgroundColor: 'var(--card)', border: '1px solid var(--border)' }}>
      <span className="ink-fainter" style={{ fontSize: 10.5, textTransform: 'uppercase', letterSpacing: 0.4 }}>{label}</span>
      <span className="ink-primary" style={{ fontWeight: 600 }}>{value}</span>
    </Link>
  );
}

function Spark({ points }: { points: number[] }) {
  if (!points || points.length < 2) return null;
  const w = 120, h = 32;
  const min = Math.min(...points), max = Math.max(...points);
  const span = max - min || 1;
  const d = points
    .map((p, i) => {
      const x = (i / (points.length - 1)) * w;
      const y = h - ((p - min) / span) * h;
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');
  const up = points[points.length - 1] >= points[0];
  return (
    <svg width={w} height={h} aria-hidden style={{ display: 'block' }}>
      <path d={d} fill="none" strokeWidth={1.5}
        stroke={up ? 'var(--brand)' : 'oklch(0.70 0.14 75)'} />
    </svg>
  );
}

function pct(n: number | null): string {
  return n == null ? '—' : `${n >= 0 ? '+' : ''}${n.toFixed(1)}%`;
}

export function ModelPortfolioCard({ pf }: { pf: ModelPortfolioSummary }) {
  const up = (pf.return_pct ?? 0) >= 0;
  return (
    <SurfaceCard variant="default" className="p-5">
      <div className="flex items-baseline justify-between gap-2 mb-1">
        <span className="font-display ink-primary" style={{ fontSize: 17 }}>{pf.name}</span>
        {pf.risk_label && (
          <span className="px-2 py-0.5 rounded-full" style={{
            fontSize: 10.5, fontWeight: 600, textTransform: 'capitalize',
            color: 'var(--muted-foreground)',
            border: '1px solid var(--border)',
          }}>{pf.risk_label}</span>
        )}
      </div>
      {pf.thesis && (
        <p className="ink-muted" style={{ fontSize: 12.5, lineHeight: 1.55 }}>{pf.thesis}</p>
      )}
      <div className="flex items-end justify-between mt-3">
        <div>
          <div className="tabular-nums" style={{
            fontSize: 20, fontWeight: 700,
            color: up ? 'var(--brand)' : 'oklch(0.70 0.14 75)',
          }}>{pct(pf.return_pct)}</div>
          <div className="ink-fainter" style={{ fontSize: 11 }}>
            {pf.since ? `since ${pf.since}` : 'track record'} · {pf.holdings_count} holdings
          </div>
        </div>
        <Spark points={pf.spark} />
      </div>
      <Link to={`/v2/portfolios/${pf.slug}`}
        className="inline-block mt-4 px-3.5 py-1.5 rounded-full"
        style={{
          fontSize: 12.5, fontWeight: 600, color: 'var(--background)',
          backgroundColor: 'var(--brand)',
        }}>
        Follow →
      </Link>
    </SurfaceCard>
  );
}

export function ModelPortfoliosSection() {
  const { data, isLoading } = useModelPortfolios();
  const pfs = data?.portfolios ?? [];
  if (!isLoading && pfs.length === 0) return null;   // honest: hide if none
  return (
    <section className="mb-10">
      <div className="flex items-baseline gap-3 mb-4">
        <span className="font-mono ink-muted" style={{ fontSize: 12 }}>★</span>
        <h2 className="font-display ink-primary" style={{
          fontSize: 22, lineHeight: 1.2,
          fontFamily: "'Instrument Serif', ui-serif, Georgia, serif",
        }}>Model Portfolios</h2>
      </div>
      {isLoading ? (
        <SurfaceCard variant="muted" className="p-6">
          <p className="ink-muted" style={{ fontSize: 14 }}>Loading portfolios…</p>
        </SurfaceCard>
      ) : (
        <div className="grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(min(100%, 240px), 1fr))' }}>
          {pfs.map((pf) => <ModelPortfolioCard key={pf.slug} pf={pf} />)}
        </div>
      )}
    </section>
  );
}
