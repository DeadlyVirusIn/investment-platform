// UX-13 — Duet room (cinematic + heat pass).

import type { LivingPageData } from "@/lib/copilot/living_compose";

import HeroBlock from "./HeroBlock";
import SubBlock from "./SubBlock";


export interface RoomDuetProps {
  data: LivingPageData;
  onTileClick: (ticker: string) => void;
}


export default function RoomDuet({ data, onTileClick }: RoomDuetProps) {
  if (!data.heroTile) return null;

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
      <HeroBlock
        tile={data.heroTile}
        onClick={onTileClick}
        conviction={data.conviction[data.heroTile.ticker]}
        pressure={data.pressure[data.heroTile.ticker] ?? "stable"}
      />

      {watchlistProse}

      {data.subordinateTiles.length > 0 && (
        <div className="ux13-sub-row" data-test="ux13-duet-subs">
          {data.subordinateTiles.map(tile => (
            <SubBlock
              key={tile.ticker}
              tile={tile}
              onClick={onTileClick}
              conviction={data.conviction[tile.ticker]}
              pressure={data.pressure[tile.ticker] ?? "stable"}
            />
          ))}
        </div>
      )}

      <p className="ux13-market" data-test="ux13-market">
        {data.marketContextText}
      </p>
    </>
  );
}
