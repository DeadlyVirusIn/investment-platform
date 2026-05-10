// UX-13 — Solo room (cinematic + heat pass).

import type { LivingPageData } from "@/lib/copilot/living_compose";

import HeroBlock from "./HeroBlock";


export interface RoomSoloProps {
  data: LivingPageData;
  onTileClick: (ticker: string) => void;
}


export default function RoomSolo({ data, onTileClick }: RoomSoloProps) {
  if (!data.heroTile) return null;

  return (
    <>
      <HeroBlock
        tile={data.heroTile}
        onClick={onTileClick}
        conviction={data.conviction[data.heroTile.ticker]}
        pressure={data.pressure[data.heroTile.ticker] ?? "stable"}
      />

      <p className="ux13-watchlist-prose" data-test="ux13-solo-watchlist">
        Four watch items unchanged. Last reviewed 11 hours ago.
      </p>

      <p className="ux13-market" data-test="ux13-market">
        {data.marketContextText}
      </p>
    </>
  );
}
