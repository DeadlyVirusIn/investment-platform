// Opportunities — P0 LIVE rewire. The full desk, ranked from the LIVE
// recommendation engine (useTodaysRecommendations → GET /recommendations).
// NO TODAYS_DESK / TRACKING_NAMES / PASSED_ON_TODAY static literals.
//
//   01 Top opportunity     — effective-Buy, confidence-ranked
//   02 Also consider       — remaining actionable Buys
//   03 Passed for now      — Trim (engine said reduce/avoid)
// Empty-day variant derives from /recommendations/diagnostics.

import { Link, useSearchParams } from 'react-router-dom';
import { ArthosPage } from '../chrome/ArthosChrome';
import { OpportunitiesOptionsSection } from '../components/OpportunitiesOptionsSection';
import { useOptionsAvailability } from '../lib/optionsAvailability';
import { PageHeader } from '../components/ui/PageHeader';
import { SurfaceCard } from '../components/ui/SurfaceCard';
import { ArthVoice } from '../chrome/ArthVoice';
import { TrustBanner } from '../components/TrustBanner';
import { CONFIDENCE_DOCTRINE } from '../lib/copy';
import {
  useTodaysRecommendations,
  useRecommendationDiagnostics,
  effectiveAction,
  confidenceNum,
  type RecApi,
} from '@/lib/operator/hooks';

export function Opportunities() {
  const { data, isLoading, isError } = useTodaysRecommendations();
  const { data: diag } = useRecommendationDiagnostics();
  const recs: RecApi[] = data?.recommendations ?? [];
  const avail = useOptionsAvailability();
  // Tab is URL-driven so the Today CTA (/v2/opportunities?tab=options) lands
  // directly on the options tab, and the view is shareable.
  const [sp, setSp] = useSearchParams();
  const tabParam = sp.get('tab');
  const tab: 'all' | 'stocks' | 'options' =
    tabParam === 'stocks' || tabParam === 'options' ? tabParam : 'all';
  const setTab = (t: 'all' | 'stocks' | 'options') => {
    const next = new URLSearchParams(sp);
    if (t === 'all') next.delete('tab');
    else next.set('tab', t);
    setSp(next, { replace: true });
  };

  const byConf = (a: RecApi, b: RecApi) => confidenceNum(b) - confidenceNum(a);
  const buys = recs.filter((r) => effectiveAction(r) === 'Buy').sort(byConf);
  const trims = recs.filter((r) => effectiveAction(r) === 'Trim').sort(byConf);
  const hero = buys[0];
  const alsoConsider = buys.slice(1);
  const dist = diag?.action_distribution ?? {};
  const evaluated = diag?.total ?? null;

  return (
    <ArthosPage topBarEyebrow="Discover">
      <PageHeader
        eyebrow="Today's Ideas"
        title={<>Ideas you can<br />follow and prove.</>}
        description="What the engine sees today — ranked, sourced live, each one explained. Add any idea to your paper portfolio and watch it become your track record."
      />

      <div className="mb-6"><TrustBanner /></div>

      {/* P1.3 — confidence doctrine (shared SSOT) */}
      <p className="ink-fainter text-[12px] leading-relaxed mb-6 max-w-narrative">
        {CONFIDENCE_DOCTRINE}
      </p>

      <OppSegment
        tab={tab}
        setTab={setTab}
        stockCount={buys.length}
        optionsCount={avail.compatible}
      />

      {tab !== 'options' && (
      <>
      {isLoading && (
        <SurfaceCard variant="muted" className="p-6">
          <p className="ink-muted" style={{ fontSize: 14 }}>Loading the desk…</p>
        </SurfaceCard>
      )}
      {isError && (
        <SurfaceCard variant="default" className="p-6">
          <p style={{ fontSize: 14, color: 'var(--destructive)', fontWeight: 600 }}>
            Couldn't load recommendations right now.
          </p>
        </SurfaceCard>
      )}

      {data && (
        <>
          {buys.length === 0 ? (
            <Section number="01" title="Cash is the call today">
              <SurfaceCard variant="highlight" className="p-7">
                <ArthVoice mode="opening">
                  {evaluated != null
                    ? `${evaluated} recommendations evaluated today; none cleared the Buy threshold (${dist['Hold'] ?? 0} Hold, ${dist['Trim'] ?? 0} Trim). I'd rather show you nothing than manufacture a trade.`
                    : 'No actionable Buy recommendations right now.'}
                </ArthVoice>
              </SurfaceCard>
            </Section>
          ) : (
            <>
              <Section number="01" title="Top opportunity">
                {hero && <RecCard rec={hero} featured />}
              </Section>
              {alsoConsider.length > 0 && (
                <Section number="02" title="Also consider">
                  <div className="space-y-3">
                    {alsoConsider.map((r) => <RecCard key={r.id} rec={r} />)}
                  </div>
                </Section>
              )}
            </>
          )}

          <Section number="03" title="Passed for now">
            {trims.length === 0 ? (
              <ArthVoice mode="advisory">Nothing flagged to trim today.</ArthVoice>
            ) : (
              <SurfaceCard variant="default" className="p-5">
                <ul className="divide-y" style={{ borderColor: 'var(--border)' }}>
                  {trims.slice(0, 8).map((r) => (
                    <li key={r.id} className="py-3 grid grid-cols-[90px_1fr_auto] items-baseline gap-3">
                      <Link to={`/v2/today/pick/${r.symbol}`} className="font-mono ink-primary" style={{ fontSize: 13 }}>
                        {r.symbol}
                      </Link>
                      <span className="ink-muted truncate" style={{ fontSize: 12.5 }}>{r.thesis ?? 'Reduce / avoid.'}</span>
                      <span className="ink-muted italic" style={{ fontSize: 12 }}>
                        {r.confidence_label} {confidenceNum(r).toFixed(0)}
                      </span>
                    </li>
                  ))}
                </ul>
                {trims.length > 8 && (
                  <p className="ink-muted mt-3 text-right" style={{ fontSize: 12 }}>
                    {trims.length - 8} more flagged to trim.
                  </p>
                )}
              </SurfaceCard>
            )}
          </Section>
        </>
      )}
      </>
      )}

      {tab !== 'stocks' && (
        <Section number={tab === 'all' ? '04' : '01'} title="Options">
          <OpportunitiesOptionsSection />
        </Section>
      )}
    </ArthosPage>
  );
}

function fresh(rec: RecApi): boolean {
  if (rec.stale_data) return false;
  if (!rec.generated_at) return true;
  const h = (Date.now() - new Date(rec.generated_at).getTime()) / 3600_000;
  return !(Number.isFinite(h) && h > 30);
}

// "What $1,000 would've done" — honest: only renders a figure when the
// rec payload carries a since-recommended return; otherwise says so plainly.
function whatThousandDid(rec: RecApi): { text: string; tone: 'pos' | 'neg' | 'muted' } {
  const r = rec as unknown as Record<string, unknown>;
  const pctRaw = r.return_since_pct ?? r.perf_since_pct ?? r.since_return_pct ?? r.return_since;
  const pct = typeof pctRaw === 'number' ? pctRaw : Number(pctRaw);
  if (Number.isFinite(pct)) {
    const value = 1000 * (1 + pct / 100);
    const tone = pct >= 0 ? 'pos' : 'neg';
    return { text: `$1,000 → $${value.toFixed(0)} (${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%) since flagged`, tone };
  }
  return { text: 'Tracking from today — follow it to build the record', tone: 'muted' };
}

function RecCard({ rec, featured }: { rec: RecApi; featured?: boolean }) {
  const action = effectiveAction(rec) ?? 'Hold';
  const perf = whatThousandDid(rec);
  return (
    <SurfaceCard variant={featured ? 'highlight' : 'default'} className="p-5">
      <div className="flex items-baseline gap-3 flex-wrap mb-1">
        <span className="font-mono ink-primary tabular-nums" style={{ fontSize: 16 }}>{rec.symbol}</span>
        <span className="ink-muted" style={{ fontSize: 13 }}>{action}</span>
      </div>
      <div className="flex items-center gap-2 mt-1 mb-3 flex-wrap">
        <SmallChip>{rec.confidence_label ?? 'Medium'} · {confidenceNum(rec).toFixed(0)}</SmallChip>
        <SmallChip tone={fresh(rec) ? 'pos' : 'neg'}>{fresh(rec) ? 'fresh' : 'stale'}</SmallChip>
      </div>
      {rec.thesis && (
        <p className="ink-primary" style={{ fontSize: 13.5, lineHeight: 1.6 }}>{rec.thesis}</p>
      )}
      {/* what $1,000 would've done */}
      <p className="mt-3 mb-1 tabular-nums" style={{
        fontSize: 12.5, fontWeight: 600,
        color: perf.tone === 'pos' ? 'var(--brand)'
          : perf.tone === 'neg' ? 'oklch(0.70 0.14 75)' : 'var(--muted-foreground)',
      }}>{perf.text}</p>
      <div className="flex items-center gap-4 mt-3">
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

// All | Stocks | Options segment. View toggle only — NOT a trade control.
// Lets ArthOS rank across both asset classes (All) once options is ready;
// today Options shows honest read-only readiness.
function OppSegment({ tab, setTab, stockCount, optionsCount }: {
  tab: 'all' | 'stocks' | 'options';
  setTab: (t: 'all' | 'stocks' | 'options') => void;
  stockCount: number;
  optionsCount: number;
}) {
  const items: Array<{ k: 'all' | 'stocks' | 'options'; label: string; badge?: number }> = [
    { k: 'all', label: 'All' },
    { k: 'stocks', label: 'Stocks', badge: stockCount },
    { k: 'options', label: 'Options', badge: optionsCount },
  ];
  return (
    <div
      className="inline-flex rounded-full p-1 mb-6"
      role="tablist"
      aria-label="Asset class"
      style={{ backgroundColor: 'var(--card)', border: '1px solid var(--border)' }}
    >
      {items.map((it) => {
        const active = tab === it.k;
        return (
          <button
            key={it.k}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => setTab(it.k)}
            className="px-3.5 py-1.5 rounded-full transition-colors"
            style={{
              fontSize: 12.5,
              fontWeight: 600,
              color: active ? 'var(--background)' : 'var(--muted-foreground)',
              backgroundColor: active ? 'var(--brand)' : 'transparent',
            }}
          >
            {it.label}
            {it.badge != null && (
              <span style={{ marginLeft: 6, fontSize: 11, opacity: 0.85 }}>{it.badge}</span>
            )}
          </button>
        );
      })}
    </div>
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
