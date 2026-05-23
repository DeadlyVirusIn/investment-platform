// MVP Phase A — Today's 60-second hero.
//
// Three quadrants stacked vertically inside one card:
//   01 · SINCE YESTERDAY        (continuity bridge — load-bearing)
//   02 · STRONGEST SETUP TODAY  (only forward action; Place embedded)
//   03 · NEAREST CATALYST       (one thing nearby)
//
// Cold-start: when firstVisitedDate equals today (i.e. first visit ever),
// SINCE YESTERDAY shows a calm Day-1 fallback instead of yesterday's
// data — we have nothing to bridge from yet.
//
// PromiseLine renders at the bottom of the card (variant="signature").

import { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  SINCE_YESTERDAY,
  OPPORTUNITIES_TODAY,
  CATALYSTS_AHEAD,
  BRIEFING_AS_OF,
  type OpportunityCard,
  type Recommendation,
} from '../data/arthosData';
import { useUserPrefs } from '../state/UserPrefsContext';
import { SetupStrength } from './SetupStrength';
import { TradeSheet } from './TradeSheet';
import { PromiseLine } from './PromiseLine';

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

export function TodayHero60s() {
  const { firstVisitedDate } = useUserPrefs();
  const today = new Date().toISOString().slice(0, 10);
  const isFirstVisit = !firstVisitedDate || firstVisitedDate === today;

  const [openRec, setOpenRec] = useState<Recommendation | null>(null);

  // Strongest setup — first Tier-1 opportunity, if any.
  const strongest = OPPORTUNITIES_TODAY.find(
    (o) => o.tier === 'strongest-setups'
  );

  // Nearest catalyst — first this-week catalyst, if any.
  const nearestCatalyst = CATALYSTS_AHEAD.find(
    (c) => c.horizon === 'this-week'
  );

  return (
    <section
      aria-label="Today in 60 seconds"
      className="card-elevated p-7 sm:p-9 mb-12"
    >
      <header className="flex items-baseline justify-between gap-4 mb-7 flex-wrap">
        <span className="text-meta ink-fainter">Today in 60 seconds</span>
        <span className="text-meta ink-fainter tabular-nums">
          As of {BRIEFING_AS_OF.prettyDate}
        </span>
      </header>

      {/* ───── 01 SINCE YESTERDAY ───── */}
      <section className="mb-9">
        <div className="flex items-baseline gap-3 mb-4">
          <span className="font-mono ink-fainter text-[12px] tabular-nums">
            01
          </span>
          <span className="text-meta ink-fainter">Since yesterday</span>
        </div>
        {isFirstVisit ? (
          <p className="font-serif italic ink-muted text-[15px] leading-relaxed max-w-copy">
            Today is Day 1. The AI's portfolio is below — we'll start
            tracking what continues from here tomorrow.
          </p>
        ) : (
          <div className="space-y-3 max-w-copy">
            {SINCE_YESTERDAY.map((item, i) => (
              <p
                key={i}
                className="ink-primary text-[15px] leading-relaxed"
              >
                {item.text}
                {item.link && (
                  <>
                    {' '}
                    <Link
                      to={item.link.to}
                      className="text-meta ink-muted hover:ink-primary transition-colors"
                    >
                      {item.link.label} →
                    </Link>
                  </>
                )}
              </p>
            ))}
          </div>
        )}
      </section>

      <div className="h-px bg-hairline mb-9" />

      {/* ───── 02 STRONGEST SETUP TODAY ───── */}
      <section className="mb-9">
        <div className="flex items-baseline justify-between mb-4 flex-wrap gap-2">
          <div className="flex items-baseline gap-3">
            <span className="font-mono ink-fainter text-[12px] tabular-nums">
              02
            </span>
            <span className="text-meta ink-fainter">
              Strongest setup today
            </span>
          </div>
          {strongest && (
            <SetupStrength setup={strongest.setup} variant="compact" />
          )}
        </div>

        {!strongest ? (
          <p className="font-serif italic ink-muted text-[15px] leading-relaxed max-w-narrative">
            No setup at full strength today. The work today is in holding.{' '}
            <Link
              to="/v2/opportunities"
              className="ink-muted hover:ink-primary transition-colors not-italic"
            >
              See what we passed on →
            </Link>
          </p>
        ) : (
          <div className="max-w-copy">
            <div className="flex items-baseline gap-3 mb-2">
              <span className="font-mono ink-primary text-[13px]">
                {strongest.symbol}
              </span>
              <span className="text-meta ink-fainter">
                {strongest.kind === 'option' ? 'Options' : 'Stock'}
              </span>
            </div>
            <h3 className="font-serif text-subhead ink-primary leading-snug mb-3">
              {strongest.actionLabel}
            </h3>
            <p className="ink-muted text-[14px] leading-relaxed mb-4">
              {strongest.intelligence.whyItMatters}
            </p>
            <dl className="grid grid-cols-2 sm:grid-cols-4 gap-x-5 gap-y-2 mb-5 text-[12px]">
              <div>
                <dt className="text-meta ink-fainter mb-0.5">Entry</dt>
                <dd className="ink-primary tabular-nums">{strongest.entry}</dd>
              </div>
              <div>
                <dt className="text-meta ink-fainter mb-0.5">Target</dt>
                <dd className="ink-primary tabular-nums">
                  {strongest.target}
                </dd>
              </div>
              <div>
                <dt className="text-meta ink-fainter mb-0.5">Invalidate</dt>
                <dd className="ink-primary tabular-nums">
                  {strongest.invalidate}
                </dd>
              </div>
              <div>
                <dt className="text-meta ink-fainter mb-0.5">Sizing</dt>
                <dd className="ink-primary">{strongest.sizing}</dd>
              </div>
            </dl>
            <div className="flex items-center gap-5 flex-wrap">
              {strongest.placeable && (
                <button
                  onClick={() => setOpenRec(cardToRec(strongest))}
                  className="font-serif transition-opacity hover:opacity-80 inline-flex items-center gap-2"
                  style={{
                    backgroundColor: 'var(--ink-primary)',
                    color: 'var(--surface-base)',
                    fontSize: '15px',
                    padding: '10px 22px',
                    borderRadius: '999px',
                    letterSpacing: '0.01em',
                  }}
                >
                  Place in paper book <span aria-hidden>→</span>
                </button>
              )}
              <Link
                to="/v2/opportunities"
                className="text-meta ink-muted hover:ink-primary transition-colors"
              >
                Read the setup →
              </Link>
            </div>
          </div>
        )}
      </section>

      <div className="h-px bg-hairline mb-9" />

      {/* ───── 03 NEAREST CATALYST ───── */}
      <section className="mb-9">
        <div className="flex items-baseline gap-3 mb-4">
          <span className="font-mono ink-fainter text-[12px] tabular-nums">
            03
          </span>
          <span className="text-meta ink-fainter">Nearest catalyst</span>
        </div>

        {!nearestCatalyst ? (
          <p className="font-serif italic ink-muted text-[15px] leading-relaxed max-w-narrative">
            No catalyst this week.{' '}
            <Link
              to="/v2/catalysts"
              className="ink-muted hover:ink-primary transition-colors not-italic"
            >
              See ahead →
            </Link>
          </p>
        ) : (
          <div className="max-w-copy">
            <div className="flex items-baseline gap-3 mb-2 flex-wrap">
              <span className="font-mono ink-primary text-[13px] tabular-nums">
                {nearestCatalyst.prettyDate}
              </span>
              {nearestCatalyst.symbol && (
                <span className="font-mono ink-fainter text-[12px]">
                  {nearestCatalyst.symbol}
                </span>
              )}
              <span className="text-meta ink-fainter">
                {nearestCatalyst.kindLabel}
              </span>
            </div>
            <h3 className="font-serif text-subhead ink-primary leading-snug mb-2">
              {nearestCatalyst.title}
            </h3>
            <p className="ink-muted text-[14px] leading-relaxed mb-3">
              {nearestCatalyst.dispositionDetail}
            </p>
            <Link
              to="/v2/catalysts"
              className="text-meta ink-muted hover:ink-primary transition-colors inline-flex items-center gap-1.5"
            >
              Open the catalyst <span aria-hidden>→</span>
            </Link>
          </div>
        )}
      </section>

      {/* Promise — signature variant */}
      <div className="border-t border-hairline pt-6">
        <PromiseLine variant="signature" />
      </div>

      {/* TradeSheet — opens inline from STRONGEST SETUP Place button */}
      <TradeSheet rec={openRec} onClose={() => setOpenRec(null)} />
    </section>
  );
}
