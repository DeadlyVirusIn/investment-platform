// UX-13 — Duet room (transformation pass).
//
// 1 hero typographic block + 2 subordinate blocks below in a wide
// 2-col row separated by hairline. Watchlist becomes inline prose
// (NOT a column). Market context as italic continuation.

import type { LivingPageData } from "@/lib/copilot/living_compose";

import HeroBlock from "./HeroBlock";
import SubBlock from "./SubBlock";


export interface RoomDuetProps {
  data: LivingPageData;
  onTileClick: (ticker: string) => void;
}


export default function RoomDuet({ data, onTileClick }: RoomDuetProps) {
  if (!data.heroTile) return null;

  // Build watchlist as natural prose continuation
  const watchlistProse = data.watchlistRows.length > 0 ? (
    <p className="ux13-watchlist-prose" data-test="ux13-duet-watchlist">
      Watching{" "}
      {data.watchlistRows.map((row, i) => (
        <span key={row.ticker}>
          <strong>{row.ticker}</strong> ({row.status})
          {i < data.watchlistRows.length - 1 ? (i === data.watchlistRows.length - 2 ? ", and " : ", ") : "."}
        </span>
      ))}
    </p>
  ) : null;

  return (
    <>
      <HeroBlock tile={data.heroTile} onClick={onTileClick} />

      {watchlistProse}

      {data.subordinateTiles.length > 0 && (
        <div className="ux13-sub-row" data-test="ux13-duet-subs">
          {data.subordinateTiles.map(tile => (
            <SubBlock key={tile.ticker} tile={tile} onClick={onTileClick} />
          ))}
        </div>
      )}

      <p className="ux13-market" data-test="ux13-market">
        {data.marketContextText}
      </p>
    </>
  );
}
