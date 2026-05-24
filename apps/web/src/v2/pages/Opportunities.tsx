// Phase 2C — Opportunities as Decision Desk.
//
// Structure:
//   - Arth opening + trust banner
//   - MY FAVORITE IDEA TODAY        (THE ONE)        ← hero with 6 answers
//   - ALSO CONSIDER                  (alternatives)   ← ranked, compact
//   - WORTH WATCHING                 (waiting list)   ← waiting-on condition
//   - PASS FOR NOW                   (passed-on)      ← collapsed by default
//
// Empty-day variant: "Cash is the call today" when nothing clears the
// risk-free bar with non-low confidence.

import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArthosPage } from '../chrome/ArthosChrome';
import { PageHeader } from '../components/ui/PageHeader';
import { SurfaceCard } from '../components/ui/SurfaceCard';
import { ArthVoice } from '../chrome/ArthVoice';
import { DecisionDeskHero } from '../components/DecisionDeskHero';
import { TrustBanner } from '../components/TrustBanner';
import { TODAYS_DESK, TRACKING_NAMES, PASSED_ON_TODAY,
         type Recommendation } from '../data/arthosData';
import { resolveWhyNotCash, cashIsTheCall,
         RISK_FREE_ANNUAL_PCT } from '../lib/arth/whyNotCash';
import { recordDecision } from '../lib/arth/decisions';
import { dispatch } from '../lib/arth/dispatcher';
import { addMemory } from '../lib/arth/memory';

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

function rankRecs(recs: Recommendation[]): Recommendation[] {
  const rank = (r: Recommendation): number => {
    const isPick = r.is_arth_pick ? 100 : 0;
    const conf = r.confidence_level === 'high' ? 30 :
                 r.confidence_level === 'medium' ? 20 :
                 r.confidence_level === 'low' ? 10 : 0;
    const edge = r.expected_return_per_day_bp ?? 0;
    const inverseHoldFloor =
      r.hold_estimate_days_min ? (100 - Math.min(r.hold_estimate_days_min, 90)) / 100 : 0;
    return isPick + conf + edge / 10 + inverseHoldFloor;
  };
  return [...recs].sort((a, b) => rank(b) - rank(a));
}

export function Opportunities() {
  const placeable = useMemo(
    () => [...TODAYS_DESK.stocks, ...TODAYS_DESK.options].filter((r) => r.placeable),
    [],
  );
  const ranked = useMemo(() => rankRecs(placeable), [placeable]);
  const hero = ranked.find((r) => r.is_arth_pick) ?? ranked[0];
  const alternatives = ranked.filter((r) => r.symbol !== hero?.symbol);
  const cashCalls = cashIsTheCall(placeable);

  return (
    <ArthosPage topBarEyebrow="Opportunities">
      <PageHeader
        eyebrow="Opportunities"
        title={<>What should I do<br />today?</>}
        description="One hero idea, ranked alternatives, names I'm watching, and what I passed on. Every recommendation answers six questions and compares itself to holding cash."
      />

      <div className="mb-6">
        <TrustBanner />
      </div>

      {cashCalls ? (
        <CashIsTheCall recs={placeable} />
      ) : (
        <>
          <Section number="01" title="My favorite idea today">
            {hero && <DecisionDeskHero rec={hero} allRecs={placeable} />}
          </Section>

          {alternatives.length > 0 && (
            <Section number="02" title="Also consider">
              <div className="space-y-3">
                {alternatives.map((r) => <AlternativeCard key={r.symbol} rec={r} />)}
              </div>
            </Section>
          )}
        </>
      )}

      <Section number="03" title="Worth watching">
        {TRACKING_NAMES.length === 0 ? (
          <ArthVoice mode="advisory">Nothing on the waiting list right now.</ArthVoice>
        ) : (
          <SurfaceCard variant="default" className="p-5">
            <ul className="divide-y" style={{ borderColor: 'var(--border)' }}>
              {TRACKING_NAMES.slice(0, 6).map((n) => (
                <li key={n.symbol} className="py-3 grid grid-cols-[80px_1fr_auto] items-baseline gap-3">
                  <span className="font-mono ink-primary" style={{ fontSize: 13 }}>{n.symbol}</span>
                  <span className="ink-primary" style={{ fontSize: 13 }}>{n.oneLineSetup}</span>
                  <span className="ink-muted italic" style={{ fontSize: 12 }}>
                    Waiting for: {n.whatToWatch}
                  </span>
                </li>
              ))}
            </ul>
            {TRACKING_NAMES.length > 6 && (
              <p className="ink-muted mt-3 text-right" style={{ fontSize: 12 }}>
                {TRACKING_NAMES.length - 6} more in the queue.
              </p>
            )}
          </SurfaceCard>
        )}
      </Section>

      <PassForNow />
    </ArthosPage>
  );
}

// ───────────────────────────────────────────────────────────────────

function AlternativeCard({ rec }: { rec: Recommendation }) {
  const why = rec.why_not_others?.[0]?.reason;
  const cash = resolveWhyNotCash(rec);
  return (
    <SurfaceCard variant="default" className="p-5">
      <div className="flex items-baseline gap-3 flex-wrap mb-1">
        <span className="font-mono ink-primary tabular-nums" style={{ fontSize: 16 }}>
          {rec.symbol}
        </span>
        <span className="ink-muted" style={{ fontSize: 13 }}>{rec.actionLabel}</span>
      </div>
      <div className="flex items-center gap-2 mt-1 mb-3 flex-wrap">
        <SmallChip>{rec.confidence_level ?? 'medium'} conf</SmallChip>
        {rec.hold_estimate_days_min && rec.hold_estimate_days_max && (
          <SmallChip>~{rec.hold_estimate_days_min}-{rec.hold_estimate_days_max}d</SmallChip>
        )}
        <SmallChip tone={cash.mode === 'clears_bar' ? 'pos'
                  : cash.mode === 'thin_edge' ? 'muted' : 'neg'}>
          {cash.mode === 'clears_bar' ? 'beats cash'
            : cash.mode === 'thin_edge' ? 'thin edge'
            : "doesn't beat cash"}
        </SmallChip>
      </div>
      {why && (
        <p className="ink-muted italic" style={{ fontSize: 13, lineHeight: 1.5 }}>
          Why I have it lower: {why}
        </p>
      )}
      <p className="ink-primary mt-3" style={{ fontSize: 13.5, lineHeight: 1.6 }}>
        {rec.paragraph}
      </p>
      <p className="ink-muted mt-3" style={{ fontSize: 12 }}>
        Open this for the full 6-question breakdown.
      </p>
    </SurfaceCard>
  );
}

// ───────────────────────────────────────────────────────────────────

function CashIsTheCall({ recs }: { recs: Recommendation[] }) {
  const [held, setHeld] = useState(false);
  function onHoldCash() {
    recordDecision({
      rec_id: 'CASH',
      symbol: 'CASH',
      action: 'held_cash',
      thesis_snapshot: `No setup beat the cash bar today (${RISK_FREE_ANNUAL_PCT}% annualized risk-free).`,
      cohort: 'uncategorized',
    });
    dispatch('decide', 'card_saved', 'CASH', { mode: 'held_cash' },
      { idempotency_key: `cash-${today()}` });
    addMemory({
      category: 'seen',
      text: `You held cash today — Arth couldn't find a setup that beat the risk-free rate.`,
      source: 'decision',
    });
    setHeld(true);
  }
  return (
    <Section number="01" title="My favorite idea today">
      <SurfaceCard variant="highlight" className="p-7">
        <p className="font-semibold uppercase mb-2" style={{
          fontSize: 11, letterSpacing: '0.14em', color: 'var(--brand)',
        }}>★ Cash is the call</p>
        <ArthVoice mode="opening">
          Nothing I'm looking at has enough edge over the T-bill rate to justify the risk. Holding cash earns ~{RISK_FREE_ANNUAL_PCT}% annualized, risk-free. That's the bar today's setups need to clear, and they don't. I'd rather show you nothing than make something up.
        </ArthVoice>
        <div className="mt-6">
          <p className="font-semibold uppercase mb-2" style={{
            fontSize: 11, letterSpacing: '0.14em', color: 'var(--muted-foreground)',
          }}>Why not the alternatives?</p>
          <ul className="space-y-1.5">
            {recs.map((r) => {
              const c = resolveWhyNotCash(r);
              return (
                <li key={r.symbol} className="ink-primary" style={{ fontSize: 13.5 }}>
                  <strong className="font-mono">{r.symbol}</strong>: {c.line.split('. ')[0]}.
                </li>
              );
            })}
          </ul>
        </div>
        <div className="mt-6 flex items-center gap-2 flex-wrap">
          {held ? (
            <ArthVoice mode="responsive">Held. I'll come back tomorrow with a fresh read.</ArthVoice>
          ) : (
            <button onClick={onHoldCash} className="inline-flex items-center gap-2 h-10 px-4 rounded-full" style={{
              fontSize: 13, fontWeight: 600,
              backgroundColor: 'var(--brand)', color: 'var(--brand-foreground)',
            }}>Hold cash today</button>
          )}
        </div>
      </SurfaceCard>
    </Section>
  );
}

// ───────────────────────────────────────────────────────────────────

function PassForNow() {
  const [open, setOpen] = useState(false);
  if (PASSED_ON_TODAY.length === 0) return null;
  return (
    <Section number="04" title="Pass for now">
      <button onClick={() => setOpen((o) => !o)} className="ink-muted mb-3" style={{
        fontSize: 13, textDecoration: 'underline', textUnderlineOffset: 3,
      }}>
        {open ? `Hide ${PASSED_ON_TODAY.length} rejections` : `Show ${PASSED_ON_TODAY.length} rejections`}
      </button>
      {open && (
        <div className="space-y-2">
          {PASSED_ON_TODAY.map((p) => (
            <SurfaceCard key={p.symbol} variant="muted" className="p-4">
              <div className="flex items-baseline gap-3">
                <span className="font-mono ink-primary" style={{ fontSize: 13 }}>{p.symbol}</span>
                <span className="ink-primary" style={{ fontSize: 13 }}>{p.failedCriterion}</span>
              </div>
              <p className="ink-muted mt-1" style={{ fontSize: 12.5 }}>{p.reason}</p>
              {p.lessonSlug && (
                <Link to={`/v2/learn/lesson/${p.lessonSlug}`} className="inline-block mt-2"
                      style={{ fontSize: 12, color: 'var(--brand)', fontWeight: 600 }}>
                  Primer →
                </Link>
              )}
            </SurfaceCard>
          ))}
        </div>
      )}
    </Section>
  );
}

// ───────────────────────────────────────────────────────────────────

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
  const bg = tone === 'pos'
    ? 'color-mix(in oklch, var(--brand) 18%, transparent)'
    : tone === 'neg'
    ? 'color-mix(in oklch, var(--destructive) 14%, transparent)'
    : 'var(--card)';
  const color = tone === 'pos' ? 'var(--brand)'
              : tone === 'neg' ? 'var(--destructive)'
              : 'var(--foreground)';
  return (
    <span className="px-2 py-0.5 rounded-full" style={{
      fontSize: 11, fontWeight: 500,
      backgroundColor: bg, color, border: '1px solid var(--border)',
    }}>{children}</span>
  );
}
