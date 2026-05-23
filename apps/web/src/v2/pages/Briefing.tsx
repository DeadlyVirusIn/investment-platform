// V2 Today's Briefing — masthead + lede + WORKING narrative cards +
// On the desk today (stocks + options) + portfolio snapshot rail.

import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  ArthosPage,
  MetaLabel,
  ParagraphWithTerms,
} from '../chrome/ArthosChrome';
import {
  PORTFOLIO,
  BRIEFING_AS_OF,
  WHAT_CHANGED_SINCE_YESTERDAY,
  REVIEW_QUEUE,
  FIELD_NOTES_TODAY,
  FIELD_NOTES_CURATED_FROM,
  getSymbolContext,
} from '../data/arthosData';
import { MarketPulse } from '../components/MarketPulse';
import { Salutation } from '../components/Salutation';
import { TodayHero60s } from '../components/TodayHero60s';
import { FirstPositionPanel } from '../components/FirstPositionPanel';
import { CollapsibleOnMobile } from '../components/CollapsibleOnMobile';
import { useUserPrefs } from '../state/UserPrefsContext';

function FadeIn({
  delay = 0,
  children,
}: {
  delay?: number;
  children: React.ReactNode;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay, ease: [0.32, 0.72, 0, 1] }}
    >
      {children}
    </motion.div>
  );
}

interface WorkingItem {
  headline: string;
  body: string;
  lessonSlug: string;
  lessonTitle: string;
  // Evidence chips appended at the bottom of each card so the
  // narrative carries the *why* alongside the prose. Plain strings,
  // no icons, no color coding — they read as captions.
  evidence: {
    signal: string;     // 'Six-week semicap momentum'
    source: string;     // 'Sector relative-strength · Tiingo daily bars'
    confidence: string; // 'we are reducing' / 'we are watching' / 'we would hold'
  };
}

const WORKING: WorkingItem[] = [
  {
    headline: 'We trimmed AMAT.',
    body: "AMAT has run +4.1% over the last six sessions. The thesis hasn't changed — semicap momentum remains broad — but position size had drifted above the band we set when we opened it on Day 1. We sold a quarter of the position and parked the cash overnight.",
    lessonSlug: 'why-great-investors-do-nothing-most-days',
    lessonTitle: 'Why we trim winners, even when we still like them',
    evidence: {
      signal: 'Position weight at 5.2% vs sized 4.0% at entry',
      source: 'Internal portfolio accounting + Tiingo daily bars',
      confidence: 'we are reducing',
    },
  },
  {
    headline: 'We added to CME.',
    body: 'CME was opened Tuesday as a half-position. Three sessions later, the original signal — exchange-operator momentum — has held without giving back. We used the AMAT cash to bring CME to a full position rather than open a new name. Concentration matters more than count.',
    lessonSlug: 'what-is-a-signal',
    lessonTitle: 'What is a signal?',
    evidence: {
      signal: 'Exchange-operator cohort momentum, 3 sessions held',
      source: 'Sub-industry relative-strength · Tiingo daily bars',
      confidence: 'we would hold',
    },
  },
  {
    headline: 'Twelve positions held through a quiet Friday.',
    body: "The S&P moved less than half a percent. None of the ten other names triggered any rule we'd written for them. On days like this, the work is in resisting the urge to do anything — not because doing nothing is a strategy, but because doing something would be a strategy without a reason.",
    lessonSlug: 'why-great-investors-do-nothing-most-days',
    lessonTitle: 'Why great investors do nothing most days',
    evidence: {
      signal: 'Zero rules triggered across 12 open positions',
      source: 'Position-level rule monitor · post-close evaluation',
      confidence: 'we would hold',
    },
  },
  {
    headline: 'Momentum stayed broad.',
    body: "Across the eleven sectors we track, momentum readings closed the week roughly where they began. There is no rotation visible in the data yet. We're watching the financials cohort, where the readings have been quietly compressing for two weeks — the kind of compression that often resolves into a move, but rarely tells us in advance which direction.",
    lessonSlug: 'what-is-a-signal',
    lessonTitle: 'How momentum signals compress before they resolve',
    evidence: {
      signal: 'Financials cohort 14-day momentum range tightened 38%',
      source: 'GICS sector cohort scan · 21-day window',
      confidence: 'we are watching',
    },
  },
];

export function Briefing() {
  const { watchlist } = useUserPrefs();

  // Personalization spine — intersect watchlist with today's surfaces.
  // Empty watchlist hides the whole panel; we don't upsell.
  const watchedContexts = watchlist
    .map((s) => getSymbolContext(s))
    .filter(
      (c) =>
        c.mentionedInChangedToday ||
        c.opportunityTier !== null ||
        c.catalystsThisHorizon.length > 0 ||
        c.held
    );

  return (
    <ArthosPage maxWidth="max-w-6xl">
      <div className="grid lg:grid-cols-[1fr_280px] gap-16 lg:gap-20">
        <div className="min-w-0">
          <FadeIn>
            <header className="mb-8">
              <h1 className="font-serif text-masthead ink-primary mb-3">
                Today's Briefing
              </h1>
              <div className="text-meta ink-muted">
                {PORTFOLIO.dateLong} · Edition #{PORTFOLIO.edition}
              </div>
            </header>
          </FadeIn>

          {/* MVP Phase A — Salutation + 60-second hero replace the
              previous Pulse hero. Pulse moves below as a secondary panel. */}
          <FadeIn delay={0.02}>
            <Salutation />
          </FadeIn>

          <FadeIn delay={0.03}>
            <TodayHero60s />
          </FadeIn>

          {/* MVP Phase A — First-position panel. Gated by paper-book state;
              auto-dismisses after 7 days OR first close. */}
          <FirstPositionPanel />

          {/* Market Pulse — demoted from hero to secondary panel. */}
          <FadeIn delay={0.035}>
            <div className="mb-12">
              <MarketPulse variant="strip" />
            </div>
          </FadeIn>

          {/* Evidence: as-of stamp — what window the briefing reflects */}
          <FadeIn delay={0.04}>
            <div className="mb-16 sm:mb-20 max-w-copy">
              <div className="flex items-baseline gap-3 mb-2">
                <MetaLabel>As of</MetaLabel>
                <span className="ink-primary text-[14px] tabular-nums">
                  {BRIEFING_AS_OF.prettyDate}
                </span>
              </div>
              <p className="ink-fainter text-[13px] leading-relaxed italic max-w-narrative">
                {BRIEFING_AS_OF.windowDescription}
              </p>
            </div>
          </FadeIn>

          <FadeIn delay={0.06}>
            <p
              className="font-serif text-[22px] leading-[1.4] ink-primary max-w-copy mb-20 sm:mb-24"
              style={{ fontVariationSettings: '"opsz" 32' }}
            >
              We held twelve positions through a quiet Friday. The portfolio is
              up {PORTFOLIO.dayMovePct >= 0 ? '+' : ''}
              {PORTFOLIO.dayMovePct}% on the day; momentum stayed broad. We
              trimmed one name — AMAT — because position sizing had drifted,
              and we used the freed cash to add to a half-position in CME we
              opened Tuesday.
            </p>
          </FadeIn>

          {/* Polish pass — collapse downstream sections on mobile behind
              a single "Show full briefing" expand. Desktop renders all
              children unchanged. */}
          <CollapsibleOnMobile
            label="Show full briefing"
            hint="Watched · field notes · review · working"
          >

          {/* Watched names panel — Phase 3 personalization. Hidden if
              watchlist is empty (we don't upsell). */}
          {watchlist.length > 0 && (
            <FadeIn delay={0.065}>
              <section className="mb-16 sm:mb-20 max-w-copy">
                <div className="flex items-baseline gap-3 mb-5">
                  <span aria-hidden className="ink-primary text-[14px]">★</span>
                  <MetaLabel>Your watched names today</MetaLabel>
                  <span className="text-meta ink-fainter ml-auto tabular-nums">
                    {watchedContexts.length} of {watchlist.length}
                  </span>
                </div>
                {watchedContexts.length === 0 ? (
                  <p className="font-serif italic ink-muted text-[16px] leading-relaxed">
                    {watchlist.length}{' '}
                    {watchlist.length === 1 ? 'name' : 'names'} on your list,
                    nothing triggered today.
                  </p>
                ) : (
                  <ul className="space-y-px bg-hairline">
                    {watchedContexts.map((c) => (
                      <li
                        key={c.symbol}
                        className="surface-base py-5 flex items-baseline justify-between gap-5 flex-wrap"
                      >
                        <div className="flex items-baseline gap-3 shrink-0 w-32">
                          <span aria-hidden className="ink-primary text-[12px]">★</span>
                          <span className="font-mono ink-primary text-[14px]">
                            {c.symbol}
                          </span>
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="ink-primary text-[14px] leading-snug mb-1.5">
                            {c.mentionedInChangedToday
                              ? c.changedToday?.headline
                              : c.opportunityTier === 'strongest-setups'
                                ? `Strongest setup today — ${c.opportunity?.actionLabel}`
                                : c.opportunityTier === 'setups-forming'
                                  ? `Forming setup — ${c.opportunity?.actionLabel}`
                                  : c.opportunityTier === 'tracking'
                                    ? `We're tracking — ${c.tracking?.oneLineSetup}`
                                    : c.held
                                      ? `Held · Day ${c.position?.dayHeld}`
                                      : 'Mentioned in today\'s briefing'}
                          </div>
                          {c.catalystsThisHorizon.length > 0 && (
                            <div className="text-meta ink-fainter">
                              Catalyst:{' '}
                              <Link
                                to="/v2/catalysts"
                                className="ink-muted hover:ink-primary transition-colors"
                              >
                                {c.catalystsThisHorizon[0].title} ·{' '}
                                {c.catalystsThisHorizon[0].prettyDate}
                              </Link>
                            </div>
                          )}
                        </div>
                        <Link
                          to={
                            c.held
                              ? `/v2/today/pick/${c.symbol}`
                              : c.opportunityTier
                                ? '/v2/opportunities'
                                : '/v2/watchlist'
                          }
                          className="text-meta ink-muted hover:ink-primary transition-colors shrink-0"
                        >
                          Open →
                        </Link>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            </FadeIn>
          )}

          {/* Field Notes today — Phase 5. Top 3 + see-all link. */}
          <FadeIn delay={0.062}>
            <section className="mb-16 sm:mb-20 max-w-copy">
              <div className="flex items-baseline gap-3 mb-3 flex-wrap">
                <span aria-hidden className="ink-primary text-[14px]">✦</span>
                <MetaLabel>Field notes today</MetaLabel>
                <span className="text-meta ink-fainter ml-auto tabular-nums">
                  {FIELD_NOTES_TODAY.length} of{' '}
                  {FIELD_NOTES_CURATED_FROM} candidates
                </span>
              </div>
              {(() => {
                const portfolio = FIELD_NOTES_TODAY.filter(
                  (n) => n.impact === 'portfolio'
                ).length;
                const considering = FIELD_NOTES_TODAY.filter(
                  (n) => n.impact === 'considering'
                ).length;
                const regime = FIELD_NOTES_TODAY.filter(
                  (n) => n.impact === 'regime'
                ).length;
                const summary = [
                  portfolio > 0 ? `${portfolio} affect what you hold` : null,
                  considering > 0
                    ? `${considering} affect what you're considering`
                    : null,
                  regime > 0 ? `${regime} regime` : null,
                ]
                  .filter(Boolean)
                  .join(' · ');
                return (
                  <p className="ink-muted text-[14px] leading-relaxed mb-5">
                    {summary || 'Nothing material today.'}
                  </p>
                );
              })()}

              <ul className="space-y-px bg-hairline">
                {FIELD_NOTES_TODAY.slice(0, 4).map((n) => (
                  <li
                    key={n.id}
                    className="surface-base py-5 flex items-baseline gap-5 flex-wrap"
                  >
                    <span className="font-mono ink-fainter text-[12px] tabular-nums w-20 shrink-0">
                      {n.prettyTime}
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-baseline gap-3 mb-1 flex-wrap">
                        {n.symbol && (
                          <span className="font-mono ink-primary text-[13px]">
                            {n.symbol}
                          </span>
                        )}
                        <span className="text-meta ink-fainter">
                          {n.kindLabel}
                        </span>
                      </div>
                      <div className="ink-primary text-[14px] leading-snug">
                        {n.headline}
                      </div>
                    </div>
                    <Link
                      to="/v2/field-notes"
                      className="text-meta ink-muted hover:ink-primary transition-colors shrink-0 ml-auto"
                    >
                      Read →
                    </Link>
                  </li>
                ))}
              </ul>

              {FIELD_NOTES_TODAY.length > 4 && (
                <div className="mt-5">
                  <Link
                    to="/v2/field-notes"
                    className="text-meta ink-muted hover:ink-primary transition-colors inline-flex items-center gap-1.5"
                  >
                    See all {FIELD_NOTES_TODAY.length} field notes{' '}
                    <span aria-hidden>→</span>
                  </Link>
                </div>
              )}
            </section>
          </FadeIn>

          {/* Review Queue panel — Phase 1: theses due for re-read */}
          <FadeIn delay={0.07}>
            <section className="mb-16 sm:mb-20 max-w-copy">
              <div className="flex items-baseline gap-3 mb-5">
                <span aria-hidden className="ink-primary text-[14px]">✦</span>
                <MetaLabel>Review queue — this week</MetaLabel>
              </div>
              {(() => {
                const due = REVIEW_QUEUE.filter((r) => r.daysFromToday <= 7);
                if (due.length === 0) {
                  return (
                    <p className="font-serif italic ink-muted text-[16px] leading-relaxed">
                      No theses up for re-read this week.
                    </p>
                  );
                }
                return (
                  <ul className="space-y-px bg-hairline">
                    {due.map((r) => (
                      <li
                        key={r.symbol}
                        className="surface-base py-5 flex items-baseline gap-5 flex-wrap"
                      >
                        <div className="flex items-baseline gap-3 shrink-0 w-44">
                          <span className="font-mono text-[12px] ink-fainter tabular-nums">
                            {r.dueDate}
                          </span>
                          {r.daysFromToday <= 0 && (
                            <span className="text-[10px] ink-primary border border-hairline rounded-full px-2 py-0.5 tabular-nums uppercase tracking-wider">
                              due
                            </span>
                          )}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-baseline gap-3 mb-1.5">
                            <span className="font-mono ink-primary text-[14px]">
                              {r.symbol}
                            </span>
                            <span className="ink-muted text-[13px] truncate">
                              {r.company}
                            </span>
                          </div>
                          <p className="ink-muted text-[13px] leading-relaxed">
                            {r.reason}
                          </p>
                        </div>
                        <Link
                          to={`/v2/today/pick/${r.symbol}`}
                          className="text-meta ink-muted hover:ink-primary transition-colors shrink-0 ml-auto"
                        >
                          Open →
                        </Link>
                      </li>
                    ))}
                  </ul>
                );
              })()}
            </section>
          </FadeIn>

          {/* Evidence: What changed since yesterday — habit-forming hook */}
          <FadeIn delay={0.08}>
            <section className="mb-20 sm:mb-24 max-w-copy">
              <MetaLabel>What changed since yesterday</MetaLabel>
              <ul className="mt-6 space-y-6">
                {WHAT_CHANGED_SINCE_YESTERDAY.map((c, i) => (
                  <li key={i} className="flex items-baseline gap-5">
                    <span
                      aria-hidden
                      className="ink-fainter text-[13px] tabular-nums font-mono w-6 shrink-0 mt-1"
                    >
                      {String(i + 1).padStart(2, '0')}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-baseline gap-3 mb-1.5 flex-wrap">
                        <span className="ink-primary text-[15px] leading-snug">
                          {c.headline}
                        </span>
                        {c.symbol && (
                          <span className="font-mono ink-fainter text-[12px]">
                            {c.symbol}
                          </span>
                        )}
                      </div>
                      <p className="ink-muted text-[14px] leading-relaxed max-w-narrative">
                        {c.body}
                      </p>
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          </FadeIn>

          <div className="space-y-16 sm:space-y-20 mb-20">
            {WORKING.map((item, i) => (
              <FadeIn key={i} delay={0.1 + i * 0.04}>
                <article className="max-w-copy">
                  <h2 className="font-serif text-subhead ink-primary mb-4">
                    {item.headline}
                  </h2>
                  <p className="ink-muted leading-relaxed mb-5">
                    <ParagraphWithTerms text={item.body} />
                  </p>

                  {/* Evidence chips — signal · source · confidence */}
                  <dl className="grid sm:grid-cols-3 gap-x-6 gap-y-3 pt-5 mb-5 border-t border-hairline text-[12px]">
                    <div>
                      <dt className="text-meta ink-fainter mb-1">Signal</dt>
                      <dd className="ink-primary leading-snug">
                        {item.evidence.signal}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-meta ink-fainter mb-1">Source</dt>
                      <dd className="ink-muted leading-snug">
                        {item.evidence.source}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-meta ink-fainter mb-1">Stance</dt>
                      <dd className="ink-primary italic leading-snug">
                        {item.evidence.confidence}
                      </dd>
                    </div>
                  </dl>

                  <Link
                    to={`/v2/learn/lesson/${item.lessonSlug}`}
                    className="text-meta ink-muted hover:ink-primary inline-flex items-center gap-2 transition-colors"
                  >
                    Read the lesson behind this <span aria-hidden>→</span>
                  </Link>
                </article>
              </FadeIn>
            ))}
          </div>

          {/* MVP Phase A — `On the desk today` removed. Setups now live
              canonically on Opportunities; the 60-second hero surfaces the
              strongest one with Place inline. Brief link below carries
              users to Opps without competing with the hero. */}
          <FadeIn delay={0.24}>
            <section className="mb-24 max-w-copy">
              <div className="border-t border-hairline pt-8">
                <Link
                  to="/v2/opportunities"
                  className="text-meta ink-muted hover:ink-primary inline-flex items-center gap-2 transition-colors"
                >
                  See all of today's setups on Opportunities →
                </Link>
              </div>
            </section>
          </FadeIn>

          <FadeIn delay={0.3}>
            <div className="border-t border-hairline pt-12">
              <p className="font-serif italic ink-muted text-[18px] leading-relaxed max-w-narrative">
                The next briefing is Monday morning. Until then, the portfolio
                is held.
              </p>
            </div>
          </FadeIn>

          </CollapsibleOnMobile>
        </div>

        <aside className="hidden lg:block sticky top-24 self-start">
          <div className="surface-drawer p-7">
            <MetaLabel>Portfolio snapshot</MetaLabel>
            <div className="mt-5 mb-6">
              <div className="font-serif text-[28px] ink-primary tabular-nums leading-none mb-2">
                $
                {PORTFOLIO.equity.toLocaleString(undefined, {
                  minimumFractionDigits: 2,
                  maximumFractionDigits: 2,
                })}
              </div>
              <div className="text-[13px] ink-muted tabular-nums">
                <span className="ink-primary">
                  {PORTFOLIO.dayMovePct >= 0 ? '▲' : '▼'}
                </span>{' '}
                {PORTFOLIO.dayMovePct >= 0 ? '+' : ''}
                {PORTFOLIO.dayMovePct.toFixed(2)}% on the day
              </div>
              <div className="text-[13px] ink-fainter tabular-nums mt-1">
                {PORTFOLIO.lifetimeMovePct >= 0 ? '+' : ''}
                {PORTFOLIO.lifetimeMovePct.toFixed(2)}% since Day 1
              </div>
            </div>

            <div className="text-meta ink-fainter mb-3">12 positions</div>
            <ul className="space-y-2.5">
              {PORTFOLIO.positions.map((p) => {
                const move = ((p.current - p.costBasis) / p.costBasis) * 100;
                return (
                  <li key={p.symbol}>
                    <Link
                      to={`/v2/today/pick/${p.symbol}`}
                      className="flex items-baseline justify-between gap-3 text-[13px] hover:ink-primary transition-colors"
                    >
                      <span className="font-mono ink-primary tabular-nums w-12 shrink-0">
                        {p.symbol}
                      </span>
                      <span className="ink-fainter text-[11px] flex-1 truncate">
                        Day {p.dayHeld}
                      </span>
                      <span className="ink-muted tabular-nums">
                        {move >= 0 ? '+' : ''}
                        {move.toFixed(1)}%
                      </span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        </aside>
      </div>

    </ArthosPage>
  );
}
