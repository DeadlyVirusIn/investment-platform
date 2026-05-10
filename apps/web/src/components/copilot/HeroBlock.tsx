// UX-13 — HeroBlock (transformation pass).
//
// Replaces the bordered ConvictionTile chrome with typographic
// blocks. No card, no border, no shadow — text + numbers in space.
// Click anywhere → drawer opens.

import { freshnessTimestamp } from "@/lib/copilot/conviction_card_schema";
import type { ConvictionTileData } from "@/lib/copilot/tile_schema";


export interface HeroBlockProps {
  tile: ConvictionTileData;
  onClick: (ticker: string) => void;
}


export default function HeroBlock({ tile, onClick }: HeroBlockProps) {
  return (
    <div
      className="ux13-hero"
      data-test="ux13-hero-block"
      data-ticker={tile.ticker}
      role="button"
      tabIndex={0}
      onClick={() => onClick(tile.ticker)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick(tile.ticker);
        }
      }}
      aria-label={`${tile.verb} ${tile.ticker}: ${tile.thesisName}. Open reasoning.`}
    >
      <div className="ux13-hero-eyebrow">
        <span>{tile.verb.toLowerCase()}</span>
        <span>·</span>
        <span className="ux13-hero-ticker">{tile.ticker}</span>
        <span>·</span>
        <span className="ux13-hero-thesis-name">{tile.thesisName}</span>
        <span>·</span>
        <span>{freshnessTimestamp(tile.lastReviewedAt)}</span>
      </div>

      <p className="ux13-hero-decision">{tile.decisionSentence}</p>

      {tile.bullClause && tile.bearClause && (
        <div className="ux13-hero-bull-bear">
          <div>
            <span className="ux13-hero-bull-bear-label">Bull</span>
            {tile.bullClause}
          </div>
          <div>
            <span className="ux13-hero-bull-bear-label">Bear</span>
            {tile.bearClause}
          </div>
        </div>
      )}

      <div className="ux13-hero-meta">
        <span className="ux13-invalid">{tile.invalidationDistance}</span>
        <span>{tile.horizon}</span>
      </div>
    </div>
  );
}
