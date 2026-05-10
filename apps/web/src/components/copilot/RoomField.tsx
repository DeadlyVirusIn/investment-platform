// UX-13 — Field room (busy ~25% of sessions).
//
// 4-6 Forming theses, no Confirmed. NO hero. Posture sentence
// becomes 22pt focal. NO verb-glyph. Subordinates in staggered
// scan rows (NOT symmetric grid — 71-item anti-pattern lock).

import type { LivingPageData } from "@/lib/copilot/living_compose";

import ConvictionTile from "./ConvictionTile";


export interface RoomFieldProps {
  data: LivingPageData;
  onTileClick: (ticker: string) => void;
  openTicker: string | null;
}


export default function RoomField({ data, onTileClick, openTicker }: RoomFieldProps) {
  return (
    <>
      <div className="ux13-stage-zone">
        <div className="ux13-hero-area" data-test="ux13-field-empty-hero">
          {/* Posture sentence is the focal object in Field — already
              rendered above by AIRead13 with .ux13-posture-field class.
              This zone is intentionally light to honor the void. */}
        </div>
      </div>

      <div className="ux13-shop-zone">
        <div className="ux13-field-grid" data-test="ux13-field-grid">
          {data.subordinateTiles.map(tile => (
            <div
              key={tile.ticker}
              className="ux13-tile-host"
              data-hero="false"
            >
              <ConvictionTile
                tile={tile}
                onClick={onTileClick}
                isActive={openTicker === tile.ticker}
                isDimmed={openTicker !== null && openTicker !== tile.ticker}
              />
            </div>
          ))}
        </div>

        <div className="ux13-market-band" data-test="ux13-market-band">
          {data.marketContextText}
        </div>
      </div>
    </>
  );
}
