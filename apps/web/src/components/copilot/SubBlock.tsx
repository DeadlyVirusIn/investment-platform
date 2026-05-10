// UX-13 — SubBlock (cinematic + heat pass).
//
// Adds inline mini sparkline + pressure glyph. Smaller than hero
// but communicates direction at scan speed.

import { freshnessTimestamp } from "@/lib/copilot/conviction_card_schema";
import type { ConvictionTileData } from "@/lib/copilot/tile_schema";
import type {
  ConvictionSeries, PressureDirection,
} from "@/lib/copilot/living_compose";

import ConvictionSparkline from "./ConvictionSparkline";
import PressureGlyph from "./PressureGlyph";


export interface SubBlockProps {
  tile: ConvictionTileData;
  onClick: (ticker: string) => void;
  conviction?: ConvictionSeries;
  pressure?: PressureDirection;
}


export default function SubBlock({
  tile, onClick,
  conviction, pressure = "stable",
}: SubBlockProps) {
  return (
    <div
      className="ux13-sub"
      data-test="ux13-sub-block"
      data-ticker={tile.ticker}
      data-pressure={pressure}
      role="button"
      tabIndex={0}
      onClick={() => onClick(tile.ticker)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick(tile.ticker);
        }
      }}
      aria-label={`${tile.verb} ${tile.ticker}. Conviction ${pressure}. Open reasoning.`}
    >
      <div className="ux13-sub-eyebrow">
        <span>{tile.verb.toLowerCase()}</span>
        <span>·</span>
        <span className="ux13-sub-ticker">{tile.ticker}</span>
        <PressureGlyph pressure={pressure} />
        {conviction && conviction.length > 1 && (
          <ConvictionSparkline series={conviction} pressure={pressure} width={48} height={12} />
        )}
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
