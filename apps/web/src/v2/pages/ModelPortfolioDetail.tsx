// MVP — model-portfolio detail: thesis, track record (equity curve + stats),
// holdings, Follow CTA. Reuses ArthosPage + SurfaceCard + useModelPortfolio.

import { useParams, Link } from 'react-router-dom';
import { ArthosPage } from '../chrome/ArthosChrome';
import { PageHeader } from '../components/ui/PageHeader';
import { SurfaceCard } from '../components/ui/SurfaceCard';
import { CompanyTitle } from '../components/CompanyTitle';
import { riskLevel, riskWho, riskWhy, HOLD_PERIOD } from '../lib/portfolioMeta';
import { useModelPortfolio, useFollowModelPortfolio } from '@/lib/operator/modelPortfolios';

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
  const follow = useFollowModelPortfolio();

  const onFollow = () => {
    if (!slug) return;
    follow.mutate({ slug, startingCash: 10000 });   // result surfaced below
  };

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
            <Curve navs={(pf.curve ?? []).map((c) => c.nav)} />
            <p className="ink-muted mt-2" style={{ fontSize: 12.5, lineHeight: 1.5 }}>
              Total-return track record (dividends reinvested) from past prices.
              It only includes companies that still exist today, which flatters
              the past — <strong>past performance is not a promise.</strong>
            </p>
          </SurfaceCard>

          {/* Holdings */}
          <SurfaceCard variant="default" className="p-5 mb-6">
            <h3 className="ink-primary mb-3" style={{ fontSize: 14, fontWeight: 600 }}>
              Holdings
            </h3>
            <ul className="divide-y" style={{ borderColor: 'var(--border)' }}>
              {(pf.holdings ?? []).map((h) => (
                <li key={h.symbol} className="py-2 flex items-center justify-between">
                  <CompanyTitle symbol={h.symbol} className="ink-primary" style={{ fontSize: 13 }} />
                  <span className="ink-muted tabular-nums" style={{ fontSize: 13 }}>
                    {h.weight_pct.toFixed(0)}%
                  </span>
                </li>
              ))}
            </ul>
          </SurfaceCard>

          {/* Build stage — Identity: who/why/how-long, plain language. */}
          <SurfaceCard variant="default" className="p-5 mb-6">
            <h3 className="ink-primary mb-3" style={{ fontSize: 14, fontWeight: 600 }}>Is this for me?</h3>
            <IdRow label="Who it's for" value={riskWho(pf.risk_label)} />
            <IdRow label="Why it exists" value={riskWhy(pf.risk_label)} />
            <IdRow label="How long to hold" value={HOLD_PERIOD} />
            <IdRow label="Risk level" value={riskLevel(pf.risk_label)} />
          </SurfaceCard>

          {/* Education — plain explanations of the concepts at play. */}
          <SurfaceCard variant="default" className="p-5 mb-6">
            <h3 className="ink-primary mb-3" style={{ fontSize: 14, fontWeight: 600 }}>Good to know</h3>
            <IdRow label="Diversification" value="Holding several companies spreads your risk — one bad name hurts less than if you owned just one." />
            <IdRow label="Concentration" value="This basket holds only a handful of names, so each one matters more — more punch, less cushion." />
            <IdRow label="Volatility" value="Prices swing. 'Worst drop' shows how far it fell before recovering — expect bumps on the way up." />
            <IdRow label="Rebalancing" value="The basket is occasionally trimmed back to its target shape. You don't have to do anything — it's handled." />
          </SurfaceCard>

          {/* Trust — how it's run + honest risks. */}
          <SurfaceCard variant="default" className="p-5 mb-6">
            <h3 className="ink-primary mb-3" style={{ fontSize: 14, fontWeight: 600 }}>How it works &amp; what could go wrong</h3>
            <IdRow label="How holdings are picked" value="Chosen to fit the theme above and weighted across the basket — not stock-picked week to week." />
            <IdRow label="How often they change" value="Rarely. These are long-hold baskets, not active trading." />
            <IdRow label="What success looks like" value="Growing steadily over years and recovering from drops — not winning every single week." />
            <IdRow label="What could go wrong" value="A market-wide downturn drags everything down together, and a concentrated basket falls harder. Practice it first." />
          </SurfaceCard>

          {/* Follow — one-tap: seeds a paper portfolio mirroring the weights
              ($10,000 of practice money). Result (incl. any skipped holdings)
              is surfaced so a partial fill is never silent. */}
          {follow.isSuccess ? (
            <SurfaceCard variant="highlight" className="p-5">
              <p className="ink-primary" style={{ fontSize: 15, fontWeight: 600 }}>
                ✓ You're now practising {pf.name}.
              </p>
              <p className="ink-muted leading-relaxed mt-1.5" style={{ fontSize: 13 }}>
                Added {follow.data?.opened.length ?? 0} holdings to your practice book.
                They move together now — watch how a diversified set behaves
                differently from a single idea.
              </p>
              {follow.data && Object.keys(follow.data.skipped).length > 0 && (
                <p className="ink-muted mt-1.5" style={{ fontSize: 12.5 }}>
                  {Object.keys(follow.data.skipped).length} couldn't be added today
                  ({Object.keys(follow.data.skipped).join(', ')}) — usually missing
                  recent price data.
                </p>
              )}
              <Link to="/v2/portfolio" className="inline-flex items-center mt-3 px-4 h-9 rounded-full"
                style={{ fontSize: 13, fontWeight: 600, backgroundColor: 'var(--brand)', color: 'var(--brand-foreground)' }}>
                Watch it in My Portfolio →
              </Link>
            </SurfaceCard>
          ) : (
            <div>
              {/* P1 — beginner explainer for what a model portfolio is. */}
              <p className="ink-muted leading-relaxed max-w-narrative mb-3" style={{ fontSize: 13 }}>
                A model portfolio is a collection of investments designed to work
                together. Follow it to practice all of them at once with practice
                money — no real money is used.
              </p>
              <button type="button" onClick={onFollow} disabled={follow.isPending}
                className="px-5 py-2.5 rounded-full"
                style={{
                  fontSize: 14, fontWeight: 600, color: 'var(--brand-foreground)',
                  backgroundColor: 'var(--brand)', opacity: follow.isPending ? 0.6 : 1,
                  cursor: follow.isPending ? 'default' : 'pointer', border: 'none',
                }}>
                {follow.isPending ? 'Following…' : 'Follow Portfolio'}
              </button>
              <p className="ink-fainter mt-1.5" style={{ fontSize: 11.5 }}>
                Adds the holdings to your practice account ($10,000 practice money).
              </p>
            </div>
          )}
          {follow.isError && (
            <p className="mt-2" style={{ fontSize: 12, color: 'var(--destructive)' }}>
              Couldn't create the practice portfolio. Try again.
            </p>
          )}
        </>
      )}
    </ArthosPage>
  );
}

function IdRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid gap-2 py-2 max-w-narrative"
      style={{ gridTemplateColumns: '128px 1fr', borderTop: '1px solid var(--border)' }}>
      <span className="font-semibold uppercase" style={{
        fontSize: 10, letterSpacing: '0.06em', color: 'var(--muted-foreground)',
      }}>{label}</span>
      <span className="ink-primary leading-snug" style={{ fontSize: 13 }}>{value}</span>
    </div>
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
