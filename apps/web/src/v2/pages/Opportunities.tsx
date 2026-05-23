// V2 Opportunities — daily action surface.
//
// Three setup-state tiers + tracking list + watchlist focus +
// risk flags + expanded "What we passed on" with educational reasons.

import { useState, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArthosPage, MetaLabel } from '../chrome/ArthosChrome';
import { IntelligenceCard } from '../components/IntelligenceCard';
import { SetupStrength } from '../components/SetupStrength';
import { TradeSheet } from '../components/TradeSheet';
import { MarketPulse } from '../components/MarketPulse';
import {
  OPPORTUNITIES_TODAY,
  TRACKING_NAMES,
  PASSED_ON_TODAY,
  PASSED_ON_TOTAL_SCREENED,
  REVIEW_QUEUE,
  BRIEFING_AS_OF,
  getSymbolContext,
  type OpportunityCard,
  type Recommendation,
} from '../data/arthosData';
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
      transition={{ duration: 0.45, delay, ease: [0.32, 0.72, 0, 1] }}
    >
      {children}
    </motion.div>
  );
}

function cardToRec(c: OpportunityCard): Recommendation {
  return {
    symbol: c.symbol,
    kind: c.kind,
    actionLabel: c.actionLabel,
    paragraph: c.paragraph,
    contract: c.contract,
    entry: c.entry,
    target: c.target,
    invalidate: c.invalidate,
    sizing: c.sizing,
    lessonSlug: c.lessonSlug,
    placeable: c.placeable,
    side: c.side,
    entryPrice: c.entryPrice,
    defaultQuantity: c.defaultQuantity,
    maxLossPerContract: c.maxLossPerContract,
  };
}

export function Opportunities() {
  const [openRec, setOpenRec] = useState<Recommendation | null>(null);
  const { toggleWatchlist, inWatchlist, watchlist } = useUserPrefs();

  const tier1Stocks = useMemo(
    () =>
      OPPORTUNITIES_TODAY.filter(
        (c) => c.tier === 'strongest-setups' && c.kind === 'stock'
      ),
    []
  );
  const tier1Options = useMemo(
    () =>
      OPPORTUNITIES_TODAY.filter(
        (c) => c.tier === 'strongest-setups' && c.kind === 'option'
      ),
    []
  );
  const tier2Stocks = useMemo(
    () =>
      OPPORTUNITIES_TODAY.filter(
        (c) => c.tier === 'setups-forming' && c.kind === 'stock'
      ),
    []
  );
  const tier2Options = useMemo(
    () =>
      OPPORTUNITIES_TODAY.filter(
        (c) => c.tier === 'setups-forming' && c.kind === 'option'
      ),
    []
  );

  const tier1Count = tier1Stocks.length + tier1Options.length;
  const tier2Count = tier2Stocks.length + tier2Options.length;
  const trackingCount = TRACKING_NAMES.length;

  // Phase 3 — full watchlist personalization across all three tiers
  // plus the tracking list. Each context row tells the user WHERE
  // their watched name surfaced (Tier 1 / 2 / 3 / passed-on / held).
  const watchedContexts = useMemo(
    () =>
      watchlist
        .map((s) => getSymbolContext(s))
        .filter(
          (c) =>
            c.opportunityTier !== null ||
            c.held ||
            PASSED_ON_TODAY.some((p) => p.symbol === c.symbol)
        ),
    [watchlist]
  );

  return (
    <ArthosPage maxWidth="max-w-6xl">
      <FadeIn>
        <header className="mb-10">
          <MetaLabel>Opportunities</MetaLabel>
          <h1 className="font-serif text-masthead ink-primary mt-3 mb-4 max-w-[20ch]">
            What's on the desk.
          </h1>
          <p className="ink-muted leading-relaxed max-w-narrative text-[15px]">
            {tier1Count} {tier1Count === 1 ? 'setup is' : 'setups are'} ready to
            place today. {tier2Count} {tier2Count === 1 ? 'is' : 'are'} still
            forming. {trackingCount} more names meet our criteria but we're not
            acting yet.
          </p>
          <div className="flex items-baseline gap-3 mt-5 text-[13px]">
            <span className="text-meta ink-fainter">As of</span>
            <span className="ink-primary tabular-nums">
              {BRIEFING_AS_OF.prettyDate}
            </span>
          </div>
        </header>
      </FadeIn>

      {/* Market Pulse strip — Phase 4. Calm context band. */}
      <FadeIn delay={0.03}>
        <div className="mb-12">
          <MarketPulse variant="strip" />
        </div>
      </FadeIn>

      {/* ─────────── TIER 1 — STRONGEST SETUPS TODAY ─────────── */}
      <FadeIn delay={0.04}>
        <section className="mb-20">
          <div className="flex items-baseline gap-4 mb-2">
            <span className="font-mono ink-fainter text-[13px] tabular-nums">
              01
            </span>
            <h2 className="font-serif text-headline ink-primary">
              Strongest setups today
            </h2>
          </div>
          <p className="ink-muted text-[14px] leading-relaxed max-w-narrative mb-10">
            Most signals firing. Sized for entry. These are the setups where
            our criteria are unambiguous today.
          </p>

          <div className="grid lg:grid-cols-2 gap-6">
            {/* Stocks column */}
            <div>
              <div className="flex items-baseline gap-3 mb-5">
                <MetaLabel>Stocks</MetaLabel>
                <span className="text-meta ink-fainter">
                  {tier1Stocks.length}{' '}
                  {tier1Stocks.length === 1 ? 'placement' : 'placements'}
                </span>
              </div>
              {tier1Stocks.length === 0 ? (
                <EmptyState text="No stock setups at full strength today." />
              ) : (
                <div className="space-y-6">
                  {tier1Stocks.map((c) => (
                    <IntelligenceCard
                      key={c.symbol}
                      card={c}
                      onPlace={() => setOpenRec(cardToRec(c))}
                      onWatch={() => toggleWatchlist(c.symbol)}
                      isWatching={inWatchlist(c.symbol)}
                    />
                  ))}
                </div>
              )}
            </div>

            {/* Options column — EQUAL prominence */}
            <div>
              <div className="flex items-baseline gap-3 mb-5">
                <MetaLabel>Options</MetaLabel>
                <span className="text-meta ink-fainter">
                  {tier1Options.length}{' '}
                  {tier1Options.length === 1 ? 'placement' : 'placements'}
                </span>
              </div>
              {tier1Options.length === 0 ? (
                <EmptyState text="No options setups at full strength today." />
              ) : (
                <div className="space-y-6">
                  {tier1Options.map((c) => (
                    <IntelligenceCard
                      key={c.symbol}
                      card={c}
                      onPlace={() => setOpenRec(cardToRec(c))}
                      onWatch={() => toggleWatchlist(c.symbol)}
                      isWatching={inWatchlist(c.symbol)}
                    />
                  ))}
                </div>
              )}
            </div>
          </div>
          {tier1Options.length > 0 && (
            <p className="text-[12px] ink-fainter italic mt-6 max-w-narrative leading-relaxed">
              Every options structure is defined-risk by construction. The
              maximum loss is known before the position is placed.
            </p>
          )}
        </section>
      </FadeIn>

      {/* ─────────── TIER 2 — SETUPS STILL FORMING ─────────── */}
      <FadeIn delay={0.08}>
        <section className="mb-20">
          <div className="flex items-baseline gap-4 mb-2">
            <span className="font-mono ink-fainter text-[13px] tabular-nums">
              02
            </span>
            <h2 className="font-serif text-headline ink-primary">
              Setups still forming
            </h2>
          </div>
          <p className="ink-muted text-[14px] leading-relaxed max-w-narrative mb-10">
            Mixed signals. Sized lighter. These setups need another two to
            three sessions of confirmation before we'd size them up.
          </p>

          <div className="grid lg:grid-cols-2 gap-6">
            <div>
              <div className="flex items-baseline gap-3 mb-5">
                <MetaLabel>Stocks</MetaLabel>
                <span className="text-meta ink-fainter">
                  {tier2Stocks.length}{' '}
                  {tier2Stocks.length === 1 ? 'placement' : 'placements'}
                </span>
              </div>
              {tier2Stocks.length === 0 ? (
                <EmptyState text="No forming stock setups today." />
              ) : (
                <div className="space-y-6">
                  {tier2Stocks.map((c) => (
                    <IntelligenceCard
                      key={c.symbol}
                      card={c}
                      onPlace={() => setOpenRec(cardToRec(c))}
                      onWatch={() => toggleWatchlist(c.symbol)}
                      isWatching={inWatchlist(c.symbol)}
                    />
                  ))}
                </div>
              )}
            </div>

            <div>
              <div className="flex items-baseline gap-3 mb-5">
                <MetaLabel>Options</MetaLabel>
                <span className="text-meta ink-fainter">
                  {tier2Options.length}{' '}
                  {tier2Options.length === 1 ? 'placement' : 'placements'}
                </span>
              </div>
              {tier2Options.length === 0 ? (
                <EmptyState text="No forming options setups today." />
              ) : (
                <div className="space-y-6">
                  {tier2Options.map((c) => (
                    <IntelligenceCard
                      key={c.symbol}
                      card={c}
                      onPlace={() => setOpenRec(cardToRec(c))}
                      onWatch={() => toggleWatchlist(c.symbol)}
                      isWatching={inWatchlist(c.symbol)}
                    />
                  ))}
                </div>
              )}
            </div>
          </div>
        </section>
      </FadeIn>

      {/* ─────────── TIER 3 — NAMES WE'RE TRACKING ─────────── */}
      <FadeIn delay={0.12}>
        <section className="mb-20">
          <div className="flex items-baseline gap-4 mb-2">
            <span className="font-mono ink-fainter text-[13px] tabular-nums">
              03
            </span>
            <h2 className="font-serif text-headline ink-primary">
              Names we're tracking
            </h2>
          </div>
          <p className="ink-muted text-[14px] leading-relaxed max-w-narrative mb-10">
            Criteria met but we're not acting yet. Each one has a specific
            condition we're waiting on.
          </p>

          <ul className="space-y-px bg-hairline max-w-copy">
            {TRACKING_NAMES.map((n) => (
              <li
                key={n.symbol}
                className="surface-base py-5 px-1 flex items-baseline justify-between gap-4 flex-wrap"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-baseline gap-3 mb-1">
                    <span className="font-mono ink-primary text-[14px]">
                      {n.symbol}
                    </span>
                    {inWatchlist(n.symbol) && (
                      <span aria-hidden className="ink-primary text-[12px]">
                        ★
                      </span>
                    )}
                  </div>
                  <div className="ink-muted text-[14px] leading-snug">
                    {n.oneLineSetup}
                  </div>
                  <div className="text-meta ink-fainter mt-2">
                    Watching: <span className="ink-muted">{n.whatToWatch}</span>
                  </div>
                </div>
                <div className="shrink-0 flex items-center gap-4">
                  <SetupStrength
                    setup={{ score: n.setupScore, criteria: [] }}
                    variant="compact"
                  />
                  <button
                    onClick={() => toggleWatchlist(n.symbol)}
                    className="text-meta ink-fainter hover:ink-muted transition-colors"
                  >
                    {inWatchlist(n.symbol) ? 'Watching' : 'Watch'}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </section>
      </FadeIn>

      {/* ─────────── WATCHLIST IN FOCUS ─────────── */}
      <FadeIn delay={0.16}>
        <section className="mb-20">
          <div className="flex items-baseline gap-4 mb-5">
            <span aria-hidden className="ink-primary text-[16px]">
              ★
            </span>
            <MetaLabel>Watchlist in focus</MetaLabel>
            {watchlist.length > 0 && (
              <span className="text-meta ink-fainter ml-auto tabular-nums">
                {watchedContexts.length} of {watchlist.length} surfacing today
              </span>
            )}
          </div>
          {watchlist.length === 0 ? (
            <p className="ink-muted italic font-serif text-[16px] leading-relaxed max-w-narrative">
              You haven't added anything to your watchlist yet. Star any name
              from a Pick or Opportunity card to track it here.
            </p>
          ) : watchedContexts.length === 0 ? (
            <p className="ink-muted italic font-serif text-[16px] leading-relaxed max-w-narrative">
              {watchlist.length} {watchlist.length === 1 ? 'name' : 'names'} on
              your watchlist, none surfaced in today's opportunities.
            </p>
          ) : (
            <ul className="space-y-px bg-hairline max-w-copy">
              {watchedContexts.map((c) => {
                const passedOn = PASSED_ON_TODAY.find(
                  (p) => p.symbol === c.symbol
                );
                const tierLabel =
                  c.opportunityTier === 'strongest-setups'
                    ? 'Strongest setup today'
                    : c.opportunityTier === 'setups-forming'
                      ? 'Setup forming'
                      : c.opportunityTier === 'tracking'
                        ? 'We\'re tracking'
                        : c.held
                          ? 'Held position'
                          : passedOn
                            ? `Passed — ${passedOn.failedCriterion}`
                            : 'On your list';
                return (
                  <li
                    key={c.symbol}
                    className="surface-base py-5 px-1 flex items-baseline justify-between gap-5 flex-wrap"
                  >
                    <div className="flex items-baseline gap-3 shrink-0 w-32">
                      <span aria-hidden className="ink-primary text-[12px]">★</span>
                      <span className="font-mono ink-primary text-[14px]">
                        {c.symbol}
                      </span>
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="ink-primary text-[14px] leading-snug mb-1">
                        {tierLabel}
                      </div>
                      {c.opportunity && (
                        <div className="ink-muted text-[13px] leading-relaxed">
                          {c.opportunity.actionLabel}
                        </div>
                      )}
                      {!c.opportunity && c.tracking && (
                        <div className="ink-muted text-[13px] leading-relaxed">
                          {c.tracking.oneLineSetup}
                        </div>
                      )}
                      {!c.opportunity && !c.tracking && c.held && (
                        <div className="ink-muted text-[13px] leading-relaxed">
                          Day {c.position?.dayHeld} · {c.position?.thesisShort}
                        </div>
                      )}
                      {!c.opportunity && !c.tracking && passedOn && (
                        <div className="ink-muted text-[13px] leading-relaxed">
                          {passedOn.reason}
                        </div>
                      )}
                      {c.catalystsThisHorizon.length > 0 && (
                        <div className="text-meta ink-fainter mt-1.5">
                          Catalyst this horizon:{' '}
                          {c.catalystsThisHorizon[0].title}
                        </div>
                      )}
                    </div>
                    <Link
                      to={
                        c.held
                          ? `/v2/today/pick/${c.symbol}`
                          : passedOn
                            ? `/v2/learn/lesson/${passedOn.lessonSlug}`
                            : '/v2/opportunities'
                      }
                      className="text-meta ink-muted hover:ink-primary transition-colors shrink-0"
                    >
                      Open →
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      </FadeIn>

      {/* ─────────── RISK FLAGS — FROM REVIEW QUEUE ─────────── */}
      <FadeIn delay={0.2}>
        <section className="mb-20">
          <div className="flex items-baseline gap-4 mb-5">
            <span aria-hidden className="ink-primary text-[14px]">
              ⚠
            </span>
            <MetaLabel>Risk flags — your portfolio</MetaLabel>
          </div>
          {REVIEW_QUEUE.filter((r) => r.daysFromToday <= 0).length === 0 ? (
            <p className="ink-muted italic font-serif text-[16px] leading-relaxed max-w-narrative">
              No positions need attention today.
            </p>
          ) : (
            <ul className="space-y-5 max-w-copy">
              {REVIEW_QUEUE.filter((r) => r.daysFromToday <= 0).map((r) => (
                <li
                  key={r.symbol}
                  className="border-t border-hairline pt-4 flex items-baseline gap-5"
                >
                  <span className="font-mono ink-primary text-[14px] w-14 shrink-0">
                    {r.symbol}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="ink-primary text-[14px] leading-snug mb-1">
                      {r.reason}
                    </div>
                    <div className="text-meta ink-fainter">
                      Thesis last touched {r.thesisLastTouched}
                    </div>
                  </div>
                  <Link
                    to={`/v2/today/pick/${r.symbol}`}
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

      {/* ─────────── WHAT WE PASSED ON — EXPANDED, EDUCATIONAL ─────────── */}
      <FadeIn delay={0.24}>
        <section className="mb-16">
          <div className="flex items-baseline gap-4 mb-3">
            <span className="font-mono ink-fainter text-[13px] tabular-nums">
              04
            </span>
            <h2 className="font-serif text-headline ink-primary">
              What we passed on
            </h2>
          </div>
          <p className="ink-muted leading-relaxed max-w-narrative mb-10 text-[14px]">
            {PASSED_ON_TOTAL_SCREENED} candidates screened today.{' '}
            {PASSED_ON_TODAY.length} are shown below with the specific
            criterion that disqualified them. Reading these is how the screen
            itself becomes a teacher — every rejection teaches what makes a
            setup good.
          </p>

          <div className="space-y-px bg-hairline max-w-copy">
            {PASSED_ON_TODAY.map((p) => (
              <article
                key={p.symbol}
                className="surface-base py-6 px-1 flex items-start gap-5 flex-wrap"
              >
                <div className="flex items-baseline gap-3 shrink-0 w-32">
                  <span className="font-mono ink-primary text-[14px]">
                    {p.symbol}
                  </span>
                  <SetupStrength
                    setup={{ score: p.setupScore, criteria: [] }}
                    variant="compact"
                  />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="ink-primary text-[14px] leading-snug mb-1.5">
                    {p.failedCriterion}
                  </div>
                  <p className="ink-muted text-[13px] leading-relaxed max-w-narrative">
                    {p.reason}
                  </p>
                </div>
                <Link
                  to={`/v2/learn/lesson/${p.lessonSlug}`}
                  className="text-meta ink-fainter hover:ink-muted transition-colors shrink-0"
                >
                  Lesson →
                </Link>
              </article>
            ))}
          </div>
        </section>
      </FadeIn>

      <TradeSheet rec={openRec} onClose={() => setOpenRec(null)} />
    </ArthosPage>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="surface-drawer rounded-2xl p-7 text-center">
      <p className="font-serif italic ink-muted text-[15px] leading-relaxed">
        {text}
      </p>
    </div>
  );
}
