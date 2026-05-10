// UX-13 — Field room (transformation pass).
//
// No hero. Posture sentence is the focal object. Subordinates as
// staggered typographic blocks (NOT grid). Market context as
// inline prose.

import type { LivingPageData } from "@/lib/copilot/living_compose";

import SubBlock from "./SubBlock";


export interface RoomFieldProps {
  data: LivingPageData;
  onTileClick: (ticker: string) => void;
}


export default function RoomField({ data, onTileClick }: RoomFieldProps) {
  return (
    <>
      <div className="ux13-field-list" data-test="ux13-field-list">
        {data.subordinateTiles.map(tile => (
          <SubBlock key={tile.ticker} tile={tile} onClick={onTileClick} />
        ))}
      </div>

      <p className="ux13-market" data-test="ux13-market">
        {data.marketContextText}
      </p>
    </>
  );
}
