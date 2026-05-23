// MarketPulse — answers "what kind of market is this?"
//
// Two variants:
//   hero  → Today's hero block. Narrative paragraph + 6-tile grid.
//   strip → Compact tile row for data surfaces (Opportunities,
//           Catalysts). No narrative; 6 tiles only.
//
// No flashing, no red/green, no alert language. Qualitative read
// first, quantitative anchor below.

import { MARKET_PULSE_TODAY, type PulseTile } from '../data/arthosData';

interface Props {
  variant?: 'hero' | 'strip';
}

export function MarketPulse({ variant = 'hero' }: Props) {
  const pulse = MARKET_PULSE_TODAY;

  if (variant === 'strip') {
    return (
      <section
        aria-label="Market pulse"
        className="surface-drawer rounded-2xl px-6 py-5"
      >
        <div className="flex items-baseline justify-between gap-4 mb-4 flex-wrap">
          <div className="flex items-baseline gap-3">
            <span className="text-meta ink-fainter">Market pulse</span>
            <span className="ink-muted text-[12px] italic">
              {pulse.narrative.split('. ')[0]}.
            </span>
          </div>
          <span className="text-meta ink-fainter tabular-nums">
            {pulse.asOf.prettyDate}
          </span>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-px bg-hairline rounded-xl overflow-hidden">
          {pulse.tiles.map((t) => (
            <CompactTile key={t.label} tile={t} />
          ))}
        </div>
      </section>
    );
  }

  // hero variant
  return (
    <section
      aria-label="Market pulse"
      className="card-elevated p-7 sm:p-9 mb-12"
    >
      <div className="flex items-baseline justify-between gap-4 mb-6 flex-wrap">
        <span className="text-meta ink-fainter">Market pulse</span>
        <span className="text-meta ink-fainter tabular-nums">
          {pulse.asOf.prettyDate}
        </span>
      </div>

      <p
        className="font-serif text-[20px] sm:text-[22px] leading-[1.45] ink-primary max-w-copy mb-9"
        style={{ fontVariationSettings: '"opsz" 32' }}
      >
        {pulse.narrative}
      </p>

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-px bg-hairline rounded-2xl overflow-hidden">
        {pulse.tiles.map((t) => (
          <HeroTile key={t.label} tile={t} />
        ))}
      </div>

      <div className="flex items-baseline justify-between mt-5 text-meta ink-fainter">
        <span>{pulse.source}</span>
      </div>
    </section>
  );
}

function HeroTile({ tile }: { tile: PulseTile }) {
  return (
    <div className="surface-drawer p-5">
      <div className="text-meta ink-fainter mb-2.5">{tile.label}</div>
      <div className="font-serif text-[22px] ink-primary leading-none mb-2">
        {tile.value}
      </div>
      <div className="text-[12px] ink-muted leading-snug mb-1.5">
        {tile.context}
      </div>
      {tile.anchor && (
        <div className="text-[11px] ink-fainter tabular-nums">
          {tile.anchor}
        </div>
      )}
    </div>
  );
}

function CompactTile({ tile }: { tile: PulseTile }) {
  return (
    <div className="surface-base p-3.5">
      <div className="text-meta ink-fainter mb-1.5 truncate">{tile.label}</div>
      <div className="font-serif text-[15px] ink-primary leading-none mb-1 truncate">
        {tile.value}
      </div>
      {tile.anchor && (
        <div className="text-[11px] ink-fainter tabular-nums truncate">
          {tile.anchor}
        </div>
      )}
    </div>
  );
}
