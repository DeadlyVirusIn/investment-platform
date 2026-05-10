// UX-13 — Duet room (default ~60% of sessions).
//
// 1 hero + 1-2 challengers. Hero cols 1-7, watchlist column cols
// 10-12 with "since you left" delta. Subordinates below 40vh
// staggered.

import type { LivingPageData } from "@/lib/copilot/living_compose";

import ConvictionTile from "./ConvictionTile";


export interface RoomDuetProps {
  data: LivingPageData;
  onTileClick: (ticker: string) => void;
  openTicker: string | null;
}


export default function RoomDuet({ data, onTileClick, openTicker }: RoomDuetProps) {
  if (!data.heroTile) return null;

  return (
    <>
      <div className="ux13-stage-zone">
        <div className="ux13-hero-area">
          <div
            className="ux13-tile-host"
            data-hero="true"
            data-test="ux13-duet-hero"
          >
            <ConvictionTile
              tile={data.heroTile}
              onClick={onTileClick}
              isActive={openTicker === data.heroTile.ticker}
              isDimmed={openTicker !== null && openTicker !== data.heroTile.ticker}
            />
          </div>

          {data.watchlistRows.length > 0 && (
            <aside className="ux13-watchlist-column" data-test="ux13-duet-watchlist">
              <h4>Watchlist</h4>
              {data.watchlistRows.map(row => (
                <div key={row.ticker} className="ux13-watchlist-row">
                  <span>{row.ticker}</span>
                  <span>{row.status}</span>
                </div>
              ))}
            </aside>
          )}
        </div>
      </div>

      <div className="ux13-shop-zone">
        {data.subordinateTiles.length > 0 && (
          <div className="ux13-subs-row" data-test="ux13-duet-subs">
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
        )}

        <div className="ux13-market-band" data-test="ux13-market-band">
          {data.marketContextText}
        </div>
      </div>
    </>
  );
}
