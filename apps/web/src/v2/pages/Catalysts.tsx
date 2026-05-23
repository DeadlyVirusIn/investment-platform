// V2 Catalysts — forward-looking "why now" surface.
//
// Not a calendar. Each event is an Intelligence Card. Filter chips
// scope the view: All / Your portfolio / Macro / Industry.
// Empty groups still render with a calm note — "nothing this week"
// is information, not absence.

import { useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import { ArthosPage, MetaLabel } from '../chrome/ArthosChrome';
import { CatalystCard } from '../components/CatalystCard';
import { MarketPulse } from '../components/MarketPulse';
import {
  CATALYSTS_AHEAD,
  HORIZON_LABELS,
  PORTFOLIO,
  BRIEFING_AS_OF,
  type CatalystCard as CatalystCardType,
  type CatalystHorizon,
  type CatalystKind,
} from '../data/arthosData';
import { useUserPrefs } from '../state/UserPrefsContext';

type ScopeFilter = 'all' | 'portfolio' | 'watchlist' | 'macro' | 'industry';

const SCOPE_LABEL: Record<ScopeFilter, string> = {
  all: 'All',
  portfolio: 'Your portfolio',
  watchlist: 'Your watchlist',
  macro: 'Macro',
  industry: 'Industry',
};

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

function matchesScope(
  card: CatalystCardType,
  scope: ScopeFilter,
  watchlist: string[]
): boolean {
  if (scope === 'all') return true;
  if (scope === 'portfolio') {
    const portfolioSyms = PORTFOLIO.positions.map((p) => p.symbol);
    return card.affectedPositions.some((s) => portfolioSyms.includes(s));
  }
  if (scope === 'watchlist') {
    if (watchlist.length === 0) return false;
    return (
      (card.symbol && watchlist.includes(card.symbol)) ||
      card.affectedPositions.some((s) => watchlist.includes(s)) ||
      card.affectedOpportunities.some((s) => watchlist.includes(s))
    );
  }
  if (scope === 'macro') return card.kind === 'macro';
  if (scope === 'industry') return card.kind === 'industry';
  return true;
}

function isWatchedCatalyst(
  card: CatalystCardType,
  watchlist: string[]
): boolean {
  if (watchlist.length === 0) return false;
  return (
    (card.symbol !== undefined && watchlist.includes(card.symbol)) ||
    card.affectedPositions.some((s) => watchlist.includes(s)) ||
    card.affectedOpportunities.some((s) => watchlist.includes(s))
  );
}

const HORIZONS: CatalystHorizon[] = [
  'this-week',
  'next-week',
  'two-weeks-out',
  'beyond',
];

export function Catalysts() {
  const { watchlist } = useUserPrefs();
  // Personalization-aware default: if the user has a watchlist, default
  // to "Your watchlist" scope; else "Your portfolio".
  const [scope, setScope] = useState<ScopeFilter>(
    watchlist.length > 0 ? 'watchlist' : 'portfolio'
  );

  const filtered = useMemo(
    () => CATALYSTS_AHEAD.filter((c) => matchesScope(c, scope, watchlist)),
    [scope, watchlist]
  );

  const watchedCount = useMemo(
    () => CATALYSTS_AHEAD.filter((c) => isWatchedCatalyst(c, watchlist)).length,
    [watchlist]
  );

  const byHorizon = useMemo(() => {
    const map: Record<CatalystHorizon, CatalystCardType[]> = {
      'this-week': [],
      'next-week': [],
      'two-weeks-out': [],
      'beyond': [],
    };
    filtered.forEach((c) => map[c.horizon].push(c));
    return map;
  }, [filtered]);

  const kindCounts = useMemo(() => {
    const counts: Record<CatalystKind, number> = {
      earnings: 0,
      macro: 0,
      industry: 0,
      'corp-action': 0,
      'thesis-review': 0,
    };
    filtered.forEach((c) => counts[c.kind]++);
    return counts;
  }, [filtered]);

  return (
    <ArthosPage maxWidth="max-w-6xl">
      <FadeIn>
        <header className="mb-10">
          <MetaLabel>Catalysts</MetaLabel>
          <h1 className="font-serif text-masthead ink-primary mt-3 mb-4 max-w-[20ch]">
            Why now.
          </h1>
          <p className="ink-muted leading-relaxed max-w-narrative text-[15px]">
            The events ahead that could move what we hold or what we're
            considering. Every event carries our disposition — what we're
            doing about it — so the page reads as decisions, not as a calendar.
          </p>
          <div className="flex items-baseline gap-3 mt-5 text-[13px]">
            <span className="text-meta ink-fainter">As of</span>
            <span className="ink-primary tabular-nums">
              {BRIEFING_AS_OF.prettyDate}
            </span>
          </div>
        </header>
      </FadeIn>

      {/* Market Pulse strip — Phase 4. Same band as Opportunities. */}
      <FadeIn delay={0.03}>
        <div className="mb-12">
          <MarketPulse variant="strip" />
        </div>
      </FadeIn>

      {/* Scope filter chips — watchlist chip only shown when populated */}
      <FadeIn delay={0.04}>
        <div className="mb-12 flex items-baseline gap-3 flex-wrap">
          <span className="text-meta ink-fainter mr-2">Scope</span>
          {(
            [
              'portfolio',
              ...(watchlist.length > 0 ? (['watchlist'] as const) : []),
              'macro',
              'industry',
              'all',
            ] as ScopeFilter[]
          ).map((s) => {
            const isActive = scope === s;
            const showStar = s === 'watchlist';
            return (
              <button
                key={s}
                onClick={() => setScope(s)}
                className={`text-[13px] px-3 py-1.5 rounded-full border transition-colors inline-flex items-center gap-1.5 ${
                  isActive
                    ? 'ink-primary border-ink-primary'
                    : 'ink-muted border-hairline hover:ink-primary'
                }`}
                style={
                  isActive
                    ? { backgroundColor: 'var(--surface-drawer)' }
                    : undefined
                }
              >
                {showStar && <span aria-hidden>★</span>}
                {SCOPE_LABEL[s]}
                {s === 'watchlist' && (
                  <span className="ink-fainter tabular-nums ml-1">
                    {watchedCount}
                  </span>
                )}
              </button>
            );
          })}
          <span className="text-meta ink-fainter ml-auto tabular-nums">
            {filtered.length} {filtered.length === 1 ? 'event' : 'events'}
            {filtered.length > 0 && (
              <>
                {' · '}
                {kindCounts.earnings > 0 && (
                  <>{kindCounts.earnings} earnings, </>
                )}
                {kindCounts.macro > 0 && <>{kindCounts.macro} macro, </>}
                {kindCounts['thesis-review'] > 0 && (
                  <>{kindCounts['thesis-review']} reviews, </>
                )}
                {kindCounts.industry > 0 && (
                  <>{kindCounts.industry} industry, </>
                )}
                {kindCounts['corp-action'] > 0 && (
                  <>{kindCounts['corp-action']} corp actions</>
                )}
              </>
            )}
          </span>
        </div>
      </FadeIn>

      {/* Horizon groups */}
      {HORIZONS.map((horizon, hi) => {
        const items = byHorizon[horizon];
        return (
          <FadeIn key={horizon} delay={0.08 + hi * 0.04}>
            <section className="mb-16">
              <div className="flex items-baseline gap-4 mb-2">
                <span className="font-mono ink-fainter text-[13px] tabular-nums">
                  {String(hi + 1).padStart(2, '0')}
                </span>
                <h2 className="font-serif text-headline ink-primary">
                  {HORIZON_LABELS[horizon]}
                </h2>
                <span className="text-meta ink-fainter ml-auto">
                  {items.length} {items.length === 1 ? 'event' : 'events'}
                </span>
              </div>

              {items.length === 0 ? (
                <p className="font-serif italic ink-muted text-[15px] leading-relaxed mt-5 max-w-narrative">
                  {scope === 'portfolio'
                    ? 'Nothing ahead in this window for what you hold.'
                    : 'Nothing in this window.'}
                </p>
              ) : (
                <div className="grid lg:grid-cols-2 gap-6 mt-8">
                  {items.map((c) => (
                    <CatalystCard
                      key={c.id}
                      card={c}
                      isWatched={isWatchedCatalyst(c, watchlist)}
                      watchlist={watchlist}
                    />
                  ))}
                </div>
              )}
            </section>
          </FadeIn>
        );
      })}

      {/* Footer doctrine */}
      <FadeIn delay={0.28}>
        <div className="border-t border-hairline pt-12 mt-8">
          <p className="font-serif italic ink-muted text-[16px] leading-relaxed max-w-narrative">
            A catalyst is not a trade. It is a moment that updates a thesis.
            The work is knowing which one — before the date arrives.
          </p>
        </div>
      </FadeIn>
    </ArthosPage>
  );
}
