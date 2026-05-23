// IntelligenceCard — reusable shape for an opportunity, catalyst, or
// pick. Single component used across Opportunities, Catalysts (later),
// and as a collapsible block on PickPage (later).
//
// Anatomy:
//   Headline · Levels strip · Setup strength · Why · What changes ·
//   What we watch · Lesson link · Actions

import { Link } from 'react-router-dom';
import { SetupStrength } from './SetupStrength';
import type { OpportunityCard } from '../data/arthosData';

interface Props {
  card: OpportunityCard;
  onPlace?: () => void;
  onWatch?: () => void;
  isWatching?: boolean;
}

export function IntelligenceCard({
  card,
  onPlace,
  onWatch,
  isWatching,
}: Props) {
  return (
    <article className="surface-drawer rounded-2xl p-7 sm:p-8 flex flex-col gap-6">
      {/* Headline */}
      <header>
        <div className="flex items-baseline justify-between gap-4 mb-2">
          <span className="font-mono ink-fainter text-meta">{card.symbol}</span>
          <span className="text-meta ink-fainter">
            {card.kind === 'option' ? 'Options' : 'Stock'}
          </span>
        </div>
        <h3 className="font-serif text-subhead ink-primary leading-snug">
          {card.actionLabel}
        </h3>
        {card.contract && (
          <div className="font-mono text-[12px] ink-muted mt-2 tabular-nums">
            {card.contract}
          </div>
        )}
      </header>

      {/* Levels strip */}
      <dl className="grid grid-cols-2 sm:grid-cols-4 gap-x-5 gap-y-3 pt-5 border-t border-hairline">
        <Level label="Entry" value={card.entry} />
        <Level label="Target" value={card.target} />
        <Level label="Invalidate" value={card.invalidate} />
        <Level label="Sizing" value={card.sizing} />
      </dl>

      {/* Setup strength */}
      <div className="pt-2 border-t border-hairline">
        <SetupStrength setup={card.setup} />
      </div>

      {/* Why it matters */}
      <section className="pt-2 border-t border-hairline">
        <div className="text-meta ink-fainter mb-2">Why it matters</div>
        <p className="ink-primary leading-relaxed text-[14px]">
          {card.intelligence.whyItMatters}
        </p>
      </section>

      {/* What could change it */}
      <section>
        <div className="text-meta ink-fainter mb-2">What could change it</div>
        <p className="ink-muted leading-relaxed text-[14px]">
          {card.intelligence.whatCouldChangeIt}
        </p>
      </section>

      {/* What we're watching */}
      <section>
        <div className="text-meta ink-fainter mb-2">What we're watching</div>
        <ul className="space-y-1.5">
          {card.intelligence.whatWeWatch.map((w, i) => (
            <li
              key={i}
              className="ink-muted text-[14px] leading-relaxed flex items-baseline gap-2"
            >
              <span aria-hidden className="ink-fainter">
                →
              </span>
              {w}
            </li>
          ))}
        </ul>
      </section>

      {/* Lesson link */}
      <Link
        to={`/v2/learn/lesson/${card.lessonSlug}`}
        className="text-meta ink-muted hover:ink-primary inline-flex items-center gap-2 transition-colors"
      >
        Read the lesson behind this <span aria-hidden>→</span>
      </Link>

      {/* Actions */}
      <div className="flex items-center gap-4 pt-5 border-t border-hairline">
        {card.placeable && onPlace && (
          <button
            onClick={onPlace}
            className="text-meta ink-primary hover:opacity-70 transition-opacity inline-flex items-center gap-1.5"
            style={{
              borderBottom: '1px solid var(--ink-primary)',
              paddingBottom: '2px',
            }}
          >
            Place in paper book <span aria-hidden>→</span>
          </button>
        )}
        {onWatch && (
          <button
            onClick={onWatch}
            className="text-meta ink-fainter hover:ink-muted transition-colors inline-flex items-center gap-1.5 ml-auto"
            aria-label={isWatching ? 'Remove from watchlist' : 'Add to watchlist'}
          >
            <span aria-hidden>{isWatching ? '★' : '☆'}</span>
            {isWatching ? 'Watching' : 'Watch'}
          </button>
        )}
      </div>
    </article>
  );
}

function Level({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-meta ink-fainter mb-1">{label}</dt>
      <dd className="ink-primary text-[13px] tabular-nums leading-snug">
        {value}
      </dd>
    </div>
  );
}
