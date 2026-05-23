// V2 Watchlist — minimal Phase-1 entry point.
// Lists starred symbols, when added, with remove. Full personalization
// across other surfaces ships in Phase 3.

import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArthosPage, MetaLabel } from '../chrome/ArthosChrome';
import { useUserPrefs } from '../state/UserPrefsContext';
import { getSymbolContext } from '../data/arthosData';

export function Watchlist() {
  const { watchlist, toggleWatchlist } = useUserPrefs();

  return (
    <ArthosPage maxWidth="max-w-copy">
      <header className="mb-14">
        <MetaLabel>Watchlist</MetaLabel>
        <h1 className="font-serif text-masthead ink-primary mt-3 mb-5 max-w-[18ch]">
          Names you're watching.
        </h1>
        <p className="ink-muted leading-relaxed max-w-narrative">
          Star any name from a Pick page or an Opportunity card. We'll
          surface them when they trigger or get mentioned in a briefing.
        </p>
      </header>

      {watchlist.length === 0 ? (
        <div className="border-t border-hairline pt-12">
          <p className="font-serif italic ink-muted text-[18px] leading-relaxed max-w-narrative mb-6">
            No symbols on your list yet.
          </p>
          <p className="ink-muted leading-relaxed max-w-narrative mb-7 text-[15px]">
            Open any Pick or Opportunity card and tap the small ★ to add it
            here. We'll let you know when it shows up in our work.
          </p>
          <Link
            to="/v2/opportunities"
            className="text-meta ink-primary hover:opacity-70 transition-opacity inline-flex items-center gap-1.5"
          >
            Open today's opportunities <span aria-hidden>→</span>
          </Link>
        </div>
      ) : (
        <ul className="space-y-px bg-hairline">
          {watchlist.map((symbol, i) => {
            const ctx = getSymbolContext(symbol);
            const tierLabel =
              ctx.opportunityTier === 'strongest-setups'
                ? 'Strongest setup today'
                : ctx.opportunityTier === 'setups-forming'
                  ? 'Setup forming'
                  : ctx.opportunityTier === 'tracking'
                    ? "We're tracking"
                    : null;
            return (
              <motion.li
                key={symbol}
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4, delay: i * 0.04 }}
                className="surface-base py-6 flex items-baseline justify-between gap-5 flex-wrap"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-baseline gap-3 mb-1.5 flex-wrap">
                    <span aria-hidden className="ink-primary">★</span>
                    <span className="font-mono ink-primary text-[15px]">
                      {symbol}
                    </span>
                    {ctx.held && (
                      <span className="text-meta ink-muted">
                        Held · Day {ctx.position?.dayHeld}
                      </span>
                    )}
                    {tierLabel && !ctx.held && (
                      <span className="text-meta ink-primary">
                        {tierLabel}
                      </span>
                    )}
                  </div>
                  <div className="text-[13px] ink-muted leading-relaxed">
                    {ctx.held
                      ? ctx.position?.thesisShort
                      : ctx.opportunity
                        ? ctx.opportunity.actionLabel
                        : ctx.tracking
                          ? ctx.tracking.oneLineSetup
                          : 'On the radar. Not held; not currently in opportunities.'}
                  </div>
                  {ctx.mentionedInChangedToday && (
                    <div className="text-meta ink-fainter mt-2">
                      Mentioned today: {ctx.changedToday?.headline}
                    </div>
                  )}
                  {ctx.catalystsThisHorizon.length > 0 && (
                    <div className="text-meta ink-fainter mt-1.5">
                      Catalyst:{' '}
                      <Link
                        to="/v2/catalysts"
                        className="ink-muted hover:ink-primary transition-colors"
                      >
                        {ctx.catalystsThisHorizon[0].title} ·{' '}
                        {ctx.catalystsThisHorizon[0].prettyDate}
                      </Link>
                    </div>
                  )}
                </div>
                <div className="flex items-baseline gap-4 shrink-0">
                  {ctx.held && (
                    <Link
                      to={`/v2/today/pick/${symbol}`}
                      className="text-meta ink-muted hover:ink-primary transition-colors"
                    >
                      Open
                    </Link>
                  )}
                  {!ctx.held && ctx.opportunityTier && (
                    <Link
                      to="/v2/opportunities"
                      className="text-meta ink-muted hover:ink-primary transition-colors"
                    >
                      Open
                    </Link>
                  )}
                  <button
                    onClick={() => toggleWatchlist(symbol)}
                    className="text-meta ink-fainter hover:ink-muted transition-colors"
                  >
                    Remove
                  </button>
                </div>
              </motion.li>
            );
          })}
        </ul>
      )}
    </ArthosPage>
  );
}
