// CatalystCard — Intelligence Card for forward-looking events.
// Same surface treatment as Opportunity IntelligenceCard, different
// content shape.
//
// Anatomy:
//   Date strip + Kind chip
//   Title + Symbol
//   ─────
//   Our disposition (chip + sentence)
//   Why it matters now
//   What could change our view
//   ─────
//   Affected positions (chips)
//   Affected opportunities (chips)
//   Lesson link

import { Link } from 'react-router-dom';
import {
  getFieldNoteForCatalyst,
  type CatalystCard as CatalystCardType,
} from '../data/arthosData';

interface Props {
  card: CatalystCardType;
  /** Phase 3 — true when symbol or an affected ticker is in user's watchlist. */
  isWatched?: boolean;
  /** Phase 3 — used to star individual affected chips. */
  watchlist?: string[];
}

const DISPOSITION_LABEL: Record<string, string> = {
  holding: 'Holding',
  watching: 'Watching',
  'reducing pre-event': 'Reducing pre-event',
  'no action': 'No action',
  'reviewing thesis': 'Reviewing thesis',
};

export function CatalystCard({
  card,
  isWatched = false,
  watchlist = [],
}: Props) {
  const daysLabel =
    card.daysFromToday === 0
      ? 'today'
      : card.daysFromToday === 1
        ? 'tomorrow'
        : `${card.daysFromToday} days away`;

  return (
    <article className="surface-drawer rounded-2xl p-7 sm:p-8 flex flex-col gap-6">
      {/* Date + kind strip + watched marker */}
      <header className="flex items-baseline justify-between gap-4 flex-wrap">
        <div className="flex items-baseline gap-3">
          <span className="font-mono ink-primary text-[13px] tabular-nums">
            {card.prettyDate}
          </span>
          <span className="text-meta ink-fainter">{daysLabel}</span>
        </div>
        <div className="flex items-baseline gap-3">
          {isWatched && (
            <span
              className="ink-primary text-meta inline-flex items-center gap-1"
              title="On your watchlist"
            >
              <span aria-hidden>★</span>
              Watching
            </span>
          )}
          <span className="text-meta ink-fainter">{card.kindLabel}</span>
        </div>
      </header>

      {/* Title */}
      <div>
        {card.symbol && (
          <div className="font-mono ink-fainter text-meta mb-2">
            {card.symbol}
          </div>
        )}
        <h3 className="font-serif text-subhead ink-primary leading-snug">
          {card.title}
        </h3>
      </div>

      {/* Disposition — the headline answer to "what are we doing about it" */}
      <section className="pt-5 border-t border-hairline">
        <div className="text-meta ink-fainter mb-2">Our disposition</div>
        <div className="flex items-baseline gap-3 mb-2 flex-wrap">
          <span
            className="ink-primary text-[14px]"
            style={{
              borderBottom: '1px solid var(--ink-primary)',
              paddingBottom: '1px',
            }}
          >
            {DISPOSITION_LABEL[card.disposition] ?? card.disposition}
          </span>
        </div>
        <p className="ink-muted text-[14px] leading-relaxed">
          {card.dispositionDetail}
        </p>
      </section>

      {/* Why it matters now — the load-bearing answer to "why now" */}
      <section>
        <div className="text-meta ink-fainter mb-2">Why it matters now</div>
        <p className="ink-primary text-[14px] leading-relaxed">
          {card.whyItMatters}
        </p>
      </section>

      {/* What could change our view */}
      <section>
        <div className="text-meta ink-fainter mb-2">
          What could change our view
        </div>
        <p className="ink-muted text-[14px] leading-relaxed">
          {card.whatCouldChangeView}
        </p>
      </section>

      {/* Affected — chips, click through to detail */}
      {(card.affectedPositions.length > 0 ||
        card.affectedOpportunities.length > 0) && (
        <section className="pt-5 border-t border-hairline space-y-4">
          {card.affectedPositions.length > 0 && (
            <div>
              <div className="text-meta ink-fainter mb-2">
                Affected positions
              </div>
              <div className="flex flex-wrap gap-2">
                {card.affectedPositions.map((sym) => {
                  const watched = watchlist.includes(sym);
                  return (
                    <Link
                      key={sym}
                      to={`/v2/today/pick/${sym}`}
                      className="font-mono text-[12px] ink-primary px-3 py-1 border border-hairline rounded-full hover:opacity-70 transition-opacity inline-flex items-center gap-1.5"
                    >
                      {watched && <span aria-hidden>★</span>}
                      {sym}
                    </Link>
                  );
                })}
              </div>
            </div>
          )}
          {card.affectedOpportunities.length > 0 && (
            <div>
              <div className="text-meta ink-fainter mb-2">
                Affected opportunities
              </div>
              <div className="flex flex-wrap gap-2">
                {card.affectedOpportunities.map((sym) => {
                  const watched = watchlist.includes(sym);
                  return (
                    <Link
                      key={sym}
                      to="/v2/opportunities"
                      className="font-mono text-[12px] ink-muted px-3 py-1 border border-hairline rounded-full hover:ink-primary transition-colors inline-flex items-center gap-1.5"
                    >
                      {watched && <span aria-hidden>★</span>}
                      {sym}
                    </Link>
                  );
                })}
              </div>
            </div>
          )}
        </section>
      )}

      {/* Lesson link + Field-note retirement link */}
      <div className="flex items-baseline justify-between gap-4 flex-wrap">
        <Link
          to={`/v2/learn/lesson/${card.lessonSlug}`}
          className="text-meta ink-muted hover:ink-primary inline-flex items-center gap-2 transition-colors"
        >
          Read the lesson behind this <span aria-hidden>→</span>
        </Link>
        {getFieldNoteForCatalyst(card.id) && (
          <Link
            to="/v2/field-notes"
            className="text-meta ink-primary hover:opacity-70 inline-flex items-center gap-2 transition-opacity"
            style={{
              borderBottom: '1px solid var(--ink-primary)',
              paddingBottom: '1px',
            }}
          >
            After the event <span aria-hidden>→</span>
          </Link>
        )}
      </div>
    </article>
  );
}
