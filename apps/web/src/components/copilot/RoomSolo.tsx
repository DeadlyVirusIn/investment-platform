// UX-13 — Solo room (transformation pass).
//
// 1 hero typographic block. No subordinates. Single watchlist
// prose line. Market context as inline italic prose.

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
      <HeroBlock tile={data.heroTile} onClick={onTileClick} />

      <p className="ux13-watchlist-prose" data-test="ux13-solo-watchlist">
        Four watch items unchanged. Last reviewed 11 hours ago.
      </p>

      <p className="ux13-market" data-test="ux13-market">
        {data.marketContextText}
      </p>
    </>
  );
}
