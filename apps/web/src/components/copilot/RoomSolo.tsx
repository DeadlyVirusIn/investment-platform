// UX-13 — Solo room (rare ~15% of sessions).
//
// 1 Confirmed+ thesis. Hero 1.5×. Halo 4% amber (Solo-only lock).
// 48pt verb-glyph. Watchlist single line. No subordinates.

import type { LivingPageData } from "@/lib/copilot/living_compose";

import ConvictionTile from "./ConvictionTile";


export interface RoomSoloProps {
  data: LivingPageData;
  onTileClick: (ticker: string) => void;
  openTicker: string | null;
}


export default function RoomSolo({ data, onTileClick, openTicker }: RoomSoloProps) {
  if (!data.heroTile) return null;

  return (
    <>
      <div className="ux13-stage-zone">
        <div className="ux13-hero-area">
          <div
            className="ux13-tile-host"
            data-hero="true"
            data-test="ux13-solo-hero"
          >
            <ConvictionTile
              tile={data.heroTile}
              onClick={onTileClick}
              isActive={openTicker === data.heroTile.ticker}
              isDimmed={false}
            />
          </div>
        </div>
      </div>

      <div className="ux13-shop-zone">
        <div className="ux13-watchlist-line" data-test="ux13-solo-watchlist-line">
          4 watch items unchanged · last reviewed 11h ago
        </div>

        <div className="ux13-market-band" data-test="ux13-market-band">
          {data.marketContextText}
        </div>
      </div>
    </>
  );
}
