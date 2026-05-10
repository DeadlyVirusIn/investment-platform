// UX-13 — SubBlock (transformation pass).
//
// Subordinate text block. Same pattern as HeroBlock but smaller +
// more recessive. No border, no card — just typography in space.

import { freshnessTimestamp } from "@/lib/copilot/conviction_card_schema";
import type { ConvictionTileData } from "@/lib/copilot/tile_schema";


export interface SubBlockProps {
  tile: ConvictionTileData;
  onClick: (ticker: string) => void;
}


export default function SubBlock({ tile, onClick }: SubBlockProps) {
  return (
    <div
      className="ux13-sub"
      data-test="ux13-sub-block"
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
      aria-label={`${tile.verb} ${tile.ticker}. Open reasoning.`}
    >
      <div className="ux13-sub-eyebrow">
        <span>{tile.verb.toLowerCase()}</span>
        <span>·</span>
        <span className="ux13-sub-ticker">{tile.ticker}</span>
        <span>·</span>
        <span>{freshnessTimestamp(tile.lastReviewedAt)}</span>
      </div>

      <p className="ux13-sub-decision">{tile.decisionSentence}</p>

      <div className="ux13-sub-meta">
        {tile.invalidationDistance} · {tile.horizon}
      </div>
    </div>
  );
}
