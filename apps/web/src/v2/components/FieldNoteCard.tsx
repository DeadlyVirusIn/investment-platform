// FieldNoteCard — past-tense Intelligence Card.
// Sibling of CatalystCard (forward-looking) and IntelligenceCard
// (opportunity setup). Same visual atom; different content shape.
//
// Anatomy:
//   Time strip + Kind chip + ★ if watched
//   Headline (ArthOS-lens phrasing)
//   What happened
//   Why it matters (ArthOS lens)
//   What we observed
//   ─────
//   What It Means For Us — disposition + elaboration
//   What could change our reading
//   ─────
//   Affected positions / Affected opportunities
//   Fired catalyst (link back if applicable)
//   Lesson link

import { Link } from 'react-router-dom';
import type {
  FieldNote,
  FieldNoteReading,
} from '../data/arthosData';

interface Props {
  note: FieldNote;
  isWatched?: boolean;
  watchlist?: string[];
}

const READING_LABEL: Record<FieldNoteReading, string> = {
  'confirming thesis': 'Confirming thesis',
  'breaking thesis': 'Breaking thesis',
  'no change': 'No change',
  watching: 'Watching',
  reducing: 'Reducing',
};

export function FieldNoteCard({
  note,
  isWatched = false,
  watchlist = [],
}: Props) {
  return (
    <article className="surface-drawer rounded-2xl p-7 sm:p-8 flex flex-col gap-6">
      {/* Time + kind + watched marker */}
      <header className="flex items-baseline justify-between gap-4 flex-wrap">
        <div className="flex items-baseline gap-3">
          <span className="font-mono ink-primary text-[13px] tabular-nums">
            {note.prettyTime}
          </span>
          {note.symbol && (
            <span className="font-mono ink-fainter text-meta">
              {note.symbol}
            </span>
          )}
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
          <span className="text-meta ink-fainter">{note.kindLabel}</span>
        </div>
      </header>

      {/* Headline — ArthOS-lens phrasing, not the factual headline */}
      <h3 className="font-serif text-subhead ink-primary leading-snug">
        {note.headline}
      </h3>

      {/* What happened */}
      <section className="pt-5 border-t border-hairline">
        <div className="text-meta ink-fainter mb-2">What happened</div>
        <p className="ink-primary text-[14px] leading-relaxed">
          {note.whatHappened}
        </p>
      </section>

      {/* Why it matters — ArthOS lens */}
      <section>
        <div className="text-meta ink-fainter mb-2">Why it matters</div>
        <p className="ink-primary text-[14px] leading-relaxed">
          {note.whyItMatters}
        </p>
      </section>

      {/* What we observed */}
      <section>
        <div className="text-meta ink-fainter mb-2">What we observed</div>
        <p className="ink-muted text-[14px] leading-relaxed">
          {note.whatWeObserved}
        </p>
      </section>

      {/* What It Means For Us — disposition + elaboration */}
      <section className="pt-5 border-t border-hairline">
        <div className="text-meta ink-fainter mb-2">What it means for us</div>
        <div className="flex items-baseline gap-3 mb-2 flex-wrap">
          <span
            className="ink-primary text-[14px]"
            style={{
              borderBottom: '1px solid var(--ink-primary)',
              paddingBottom: '1px',
            }}
          >
            {READING_LABEL[note.reading]}
          </span>
        </div>
        <p className="ink-muted text-[14px] leading-relaxed">
          {note.readingNote}
        </p>
      </section>

      {/* What could change our reading */}
      <section>
        <div className="text-meta ink-fainter mb-2">
          What could change our reading
        </div>
        <p className="ink-muted text-[14px] leading-relaxed">
          {note.whatCouldChange}
        </p>
      </section>

      {/* Affected lists + fired catalyst */}
      {(note.affectedPositions.length > 0 ||
        note.affectedOpportunities.length > 0 ||
        note.firedCatalystId) && (
        <section className="pt-5 border-t border-hairline space-y-4">
          {note.affectedPositions.length > 0 && (
            <div>
              <div className="text-meta ink-fainter mb-2">
                Affected positions
              </div>
              <div className="flex flex-wrap gap-2">
                {note.affectedPositions.map((sym) => {
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
          {note.affectedOpportunities.length > 0 && (
            <div>
              <div className="text-meta ink-fainter mb-2">
                Affected opportunities
              </div>
              <div className="flex flex-wrap gap-2">
                {note.affectedOpportunities.map((sym) => {
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
          {note.firedCatalystId && (
            <div className="text-meta ink-fainter">
              Catalyst retired:{' '}
              <Link
                to="/v2/catalysts"
                className="ink-muted hover:ink-primary transition-colors"
              >
                see the original catalyst →
              </Link>
            </div>
          )}
        </section>
      )}

      {/* Sources + lesson */}
      <div className="pt-5 border-t border-hairline flex items-baseline justify-between gap-4 flex-wrap text-meta">
        <span className="ink-fainter">
          Sources: <span className="ink-muted">{note.sources.join(' · ')}</span>
        </span>
        <Link
          to={`/v2/learn/lesson/${note.lessonSlug}`}
          className="ink-muted hover:ink-primary transition-colors inline-flex items-center gap-2"
        >
          Read the lesson behind this <span aria-hidden>→</span>
        </Link>
      </div>
    </article>
  );
}
