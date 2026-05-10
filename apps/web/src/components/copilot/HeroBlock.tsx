// UX-13 — HeroBlock (operational pass).
//
// Tile schema unchanged. Adds inline operational chips above
// decision sentence: "Day 7", "+12% since OPEN", "−4% to invalid".
// Tonal layering applied via CSS (raised plane).

import { freshnessTimestamp } from "@/lib/copilot/conviction_card_schema";
import type { ConvictionTileData } from "@/lib/copilot/tile_schema";


export interface HeroBlockProps {
  tile: ConvictionTileData;
  onClick: (ticker: string) => void;
  /** Operational stats (fixture for now; Phase 13G+ from real data). */
  daysHeld?: number;
  pctSinceOpen?: number;
  pctToInvalidation?: number;
}


function fmtPct(n: number): string {
  const sign = n >= 0 ? "+" : "−";
  return `${sign}${Math.abs(n).toFixed(1)}%`;
}


export default function HeroBlock({
  tile, onClick,
  daysHeld = 7,
  pctSinceOpen = 12.3,
  pctToInvalidation = -4.1,
}: HeroBlockProps) {
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

      {/* Operational chips — restore action density */}
      <div>
        <span className="ux13-hero-chip" data-test="ux13-chip-day">Day {daysHeld}</span>
        <span className="ux13-hero-chip" data-test="ux13-chip-since-open">
          {fmtPct(pctSinceOpen)} since OPEN
        </span>
        <span className="ux13-hero-chip" data-test="ux13-chip-invalid">
          {fmtPct(pctToInvalidation)} to invalid
        </span>
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
