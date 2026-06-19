// Opportunities — P0 LIVE rewire. The full desk, ranked from the LIVE
// recommendation engine (useTodaysRecommendations → GET /recommendations).
// NO TODAYS_DESK / TRACKING_NAMES / PASSED_ON_TODAY static literals.
//
//   01 Top opportunity     — effective-Buy, confidence-ranked
//   02 Also consider       — remaining actionable Buys
//   03 Passed for now      — Trim (engine said reduce/avoid)
// Empty-day variant derives from /recommendations/diagnostics.

import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArthosPage } from '../chrome/ArthosChrome';
import {
  ModelPortfoliosSection,
  SocialProofStrip,
  TrendingThemes,
  WhatsMovingStrip,
} from '../components/ModelPortfolioCards';
import { PageHeader } from '../components/ui/PageHeader';
import { SurfaceCard } from '../components/ui/SurfaceCard';
import { ArthVoice } from '../chrome/ArthVoice';
import { TrustBanner } from '../components/TrustBanner';
import { plainThesis } from '../lib/plainText';
import { sectorLabel } from '../lib/companyMeta';
import { CompanyTitle } from '../components/CompanyTitle';
import { PlanRows } from '../components/PlanRows';
import { ContinuePathCard } from '../components/ContinuePathCard';
import { OptionsAdvancedSection } from '../components/OptionsAdvancedSection';
import {
  useTodaysRecommendations,
  useRecommendationDiagnostics,
  useCanonicalStockPortfolio,
  effectiveAction,
  confidenceNum,
  type RecApi,
} from '@/lib/operator/hooks';

export function Opportunities() {
  const { data, isLoading, isError } = useTodaysRecommendations();
  const { data: diag } = useRecommendationDiagnostics();
  const { data: book } = useCanonicalStockPortfolio();
  const paperCount = book?.open_positions_count ?? 0;
  const recs: RecApi[] = data?.recommendations ?? [];

  const byConf = (a: RecApi, b: RecApi) => confidenceNum(b) - confidenceNum(a);
  const buys = recs.filter((r) => effectiveAction(r) === 'Buy').sort(byConf);
  const trims = recs.filter((r) => effectiveAction(r) === 'Trim').sort(byConf);
  const hero = buys[0];
  const alsoConsider = buys.slice(1);
  const dist = diag?.action_distribution ?? {};
  const evaluated = diag?.total ?? null;
  const [tab, setTab] = useState<DiscoverTab>('stocks');

  return (
    <ArthosPage topBarEyebrow="Discover">
      <PageHeader
        eyebrow="Discover"
        title={<>Ideas you can<br />follow and prove.</>}
        description="Follow a ready-made portfolio, explore a theme, or add a single idea — each one explained in plain English and tracked in your free practice account."
      />

      <DiscoverTabs tab={tab} onChange={setTab} />

      {tab === 'stocks' && (
        <>
      {/* P1 — persistent "what next?" path card (resume Day 1, then next action). */}
      <ContinuePathCard paperCount={paperCount} />
      {/* P0 onboarding — bridge single ideas → diversified portfolio once the
          user has practiced 2+ individual positions. */}
      {paperCount >= 2 && <PortfolioBridge />}
      {/* P1 progression — 5+ practice positions unlock an Options Readiness
          nudge (NOT options prominence; just an honest "you're ready to learn"). */}
      {paperCount >= 5 && <OptionsReadinessCard onExplore={() => setTab('options')} />}
      {/* Sprint D order: portfolios under the hero, then themes, what's
          moving, social proof, then today's individual ideas. */}
      <div id="model-portfolios"><ModelPortfoliosSection /></div>
      <TrendingThemes />
      <WhatsMovingStrip />
      <SocialProofStrip />

      <div className="mb-8"><TrustBanner /></div>

      {isLoading && (
        <SurfaceCard variant="muted" className="p-6">
          <p className="ink-muted" style={{ fontSize: 14 }}>Loading today's ideas…</p>
        </SurfaceCard>
      )}
      {isError && (
        <SurfaceCard variant="default" className="p-6">
          <p style={{ fontSize: 14, color: 'var(--destructive)', fontWeight: 600 }}>
            Couldn't load ideas right now.
          </p>
        </SurfaceCard>
      )}

      {data && (
        <>
          {buys.length === 0 ? (
            <Section number="01" title="No new ideas today">
              <SurfaceCard variant="highlight" className="p-7">
                <ArthVoice mode="opening">
                  {evaluated != null
                    ? `ArthOS looked at ${evaluated} companies today and none stand out as a clear buy right now (${dist['Hold'] ?? 0} to hold, ${dist['Trim'] ?? 0} to trim). We'd rather show you nothing than push a weak idea.`
                    : 'No standout ideas right now — check back tomorrow.'}
                </ArthVoice>
              </SurfaceCard>
            </Section>
          ) : (
            <>
              <Section number="01" title="Today's top idea">
                {hero && <RecCard rec={hero} featured />}
              </Section>
              {alsoConsider.length > 0 && (
                <Section number="02" title="Also worth a look">
                  <div className="space-y-3">
                    {alsoConsider.map((r) => <RecCard key={r.id} rec={r} />)}
                  </div>
                </Section>
              )}
            </>
          )}

          {trims.length > 0 && (
            <Section number="03" title="Names ArthOS is cautious on">
              <SurfaceCard variant="default" className="p-5">
                <ul className="divide-y" style={{ borderColor: 'var(--border)' }}>
                  {trims.slice(0, 8).map((r) => (
                    <li key={r.id} className="py-3 grid grid-cols-[90px_1fr] items-baseline gap-3">
                      <Link to={`/v2/today/pick/${r.symbol}`} className="ink-primary" style={{ fontSize: 13 }}>
                        <CompanyTitle symbol={r.symbol} name={r.name} />
                      </Link>
                      <span className="ink-muted truncate" style={{ fontSize: 12.5 }}>{plainThesis(r.thesis) ?? 'Cautious for now.'}</span>
                    </li>
                  ))}
                </ul>
              </SurfaceCard>
            </Section>
          )}
        </>
      )}
        </>
      )}

      {/* Options Practice tab — separate from stock ideas, never mixed into
          Today's Top Idea / Also Worth a Look. alwaysOpen renders the warning
          + cards directly (the tab is the disclosure). Beginner language. */}
      {tab === 'options' && <OptionsAdvancedSection alwaysOpen />}
    </ArthosPage>
  );
}

// P0 onboarding — nudge from single ideas to a diversified portfolio once the
// user has 2+ practice positions. Scrolls to the model-portfolios section.
function PortfolioBridge() {
  return (
    <SurfaceCard variant="highlight" className="p-5 mb-8">
      <p className="font-display ink-primary" style={{
        fontSize: 18, fontFamily: "'Instrument Serif', ui-serif, Georgia, serif",
      }}>Ready to diversify?</p>
      <p className="ink-muted leading-relaxed mt-1" style={{ fontSize: 13.5 }}>
        You've practiced individual ideas. Try a model portfolio built from
        multiple investments.
      </p>
      <a href="#model-portfolios"
        className="inline-flex items-center gap-1.5 mt-3 px-4 h-9 rounded-full"
        style={{ fontSize: 12.5, fontWeight: 600, backgroundColor: 'var(--brand)', color: 'var(--brand-foreground)' }}>
        Explore model portfolios →
      </a>
    </SurfaceCard>
  );
}

// P1 progression — shown once the user has 5+ practice positions. Acknowledges
// readiness and points to Options Practice WITHOUT making options prominent.
function OptionsReadinessCard({ onExplore }: { onExplore: () => void }) {
  return (
    <SurfaceCard variant="default" className="p-5 mb-8">
      <p className="font-semibold uppercase" style={{
        fontSize: 10.5, letterSpacing: '0.12em', color: 'var(--muted-foreground)',
      }}>You're building real practice</p>
      <p className="font-display ink-primary mt-1" style={{
        fontSize: 18, fontFamily: "'Instrument Serif', ui-serif, Georgia, serif",
      }}>Curious about options?</p>
      <p className="ink-muted leading-relaxed mt-1" style={{ fontSize: 13 }}>
        You've practiced 5+ ideas. Options are an advanced, capped-risk next step —
        still practice-only, no rush. Take a look when you're ready.
      </p>
      <button type="button" onClick={onExplore}
        className="inline-flex items-center mt-3 px-4 h-9 rounded-full"
        style={{ fontSize: 12.5, fontWeight: 600, border: '1px solid var(--border)', color: 'var(--brand)' }}>
        Open Options Practice
      </button>
    </SurfaceCard>
  );
}

type DiscoverTab = 'stocks' | 'options';

function DiscoverTabs({
  tab, onChange,
}: {
  tab: DiscoverTab;
  onChange: (t: DiscoverTab) => void;
}) {
  const items: { id: DiscoverTab; label: string; sub: string }[] = [
    { id: 'stocks', label: 'Stock Ideas', sub: 'Plain-English ideas to follow' },
    { id: 'options', label: 'Options Practice', sub: 'Advanced, paper-only ideas' },
  ];
  return (
    <div
      className="sticky top-14 lg:top-16 z-20 -mx-5 lg:-mx-10 px-5 lg:px-10 py-2.5 mb-6 backdrop-blur-md"
      style={{ backgroundColor: 'color-mix(in oklch, var(--background) 86%, transparent)', borderBottom: '1px solid var(--border)' }}
    >
      <div role="tablist" aria-label="Discover sections"
        className="grid grid-cols-2 gap-1.5 p-1 rounded-full"
        style={{ backgroundColor: 'var(--card)', border: '1px solid var(--border)' }}>
        {items.map((it) => {
          const active = tab === it.id;
          return (
            <button
              key={it.id}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => onChange(it.id)}
              className="rounded-full px-4 py-2 text-center transition-colors"
              style={{
                backgroundColor: active ? 'var(--brand)' : 'transparent',
                color: active ? 'var(--brand-foreground)' : 'var(--muted-foreground)',
              }}
            >
              <span className="block font-semibold" style={{ fontSize: 13.5 }}>{it.label}</span>
              <span className="block" style={{ fontSize: 10.5, opacity: 0.85 }}>{it.sub}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function fresh(rec: RecApi): boolean {
  if (rec.stale_data) return false;
  if (!rec.generated_at) return true;
  const h = (Date.now() - new Date(rec.generated_at).getTime()) / 3600_000;
  return !(Number.isFinite(h) && h > 30);
}

function RecCard({ rec, featured }: { rec: RecApi; featured?: boolean }) {
  const action = effectiveAction(rec) ?? 'Hold';
  return (
    <SurfaceCard variant={featured ? 'highlight' : 'default'} className="p-5">
      <div className="flex items-baseline gap-3 flex-wrap mb-1">
        <CompanyTitle symbol={rec.symbol} name={rec.name}
          className="ink-primary" style={{ fontSize: 15 }} />
        <span className="ink-muted" style={{ fontSize: 13 }}>{action}</span>
      </div>
      <div className="flex items-center gap-2 mt-1 mb-3 flex-wrap">
        {sectorLabel(rec.sector) && <SmallChip>{sectorLabel(rec.sector)}</SmallChip>}
        <SmallChip>{(rec.confidence_label ?? 'Medium').toLowerCase()} confidence</SmallChip>
        <SmallChip tone={fresh(rec) ? 'pos' : 'neg'}>{fresh(rec) ? 'updated today' : 'older'}</SmallChip>
      </div>
      {plainThesis(rec.thesis) && (
        <p className="ink-primary" style={{ fontSize: 13.5, lineHeight: 1.6 }}>{plainThesis(rec.thesis)}</p>
      )}
      {/* Plan — Entry / Target / Exit if wrong / Timeframe (Sprint K) */}
      <div className="mt-3"><PlanRows rec={rec} compact /></div>
      <div className="flex items-center gap-4 mt-4">
        <Link to={`/v2/today/pick/${rec.symbol}`}
          style={{ fontSize: 12, color: 'var(--brand)', fontWeight: 600 }}>
          See why →
        </Link>
        {/* Add to paper — Phase 4 wires the one-tap submit_trade; routes to
            the idea detail where the action lives until then. */}
        <Link to={`/v2/today/pick/${rec.symbol}?add=1`}
          className="px-3 py-1.5 rounded-full"
          style={{
            fontSize: 12, fontWeight: 600, color: 'var(--background)',
            backgroundColor: 'var(--brand)',
          }}>
          Add to paper
        </Link>
      </div>
    </SurfaceCard>
  );
}

function Section({ number, title, children }: {
  number: string; title: string; children: React.ReactNode;
}) {
  return (
    <section className="mb-10">
      <div className="flex items-baseline gap-3 mb-4">
        <span className="font-mono ink-muted" style={{ fontSize: 12 }}>{number}</span>
        <h2 className="font-display ink-primary" style={{
          fontSize: 22, lineHeight: 1.2,
          fontFamily: "'Instrument Serif', ui-serif, Georgia, serif",
        }}>{title}</h2>
      </div>
      {children}
    </section>
  );
}

function SmallChip({ tone = 'muted', children }: {
  tone?: 'pos' | 'neg' | 'muted'; children: React.ReactNode;
}) {
  const color = tone === 'pos' ? 'var(--brand)'
    : tone === 'neg' ? 'oklch(0.70 0.14 75)' : 'var(--foreground)';
  return (
    <span className="px-2 py-0.5 rounded-full" style={{
      fontSize: 11, fontWeight: 500,
      backgroundColor: `color-mix(in oklch, ${color} 12%, transparent)`,
      color, border: `1px solid color-mix(in oklch, ${color} 24%, transparent)`,
    }}>{children}</span>
  );
}
