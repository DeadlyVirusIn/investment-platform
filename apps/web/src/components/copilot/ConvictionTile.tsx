// UX-11 Phase 11B — ConvictionTile component.
//
// Source of truth: docs/research/UX_11_INTERACTIVE_COPILOT.md
//   Section 3 (ConvictionTile spec)
//
// 304×184 px, 5 required rows on Confirmed+ tier (4 on lower
// tiers). Refuses-to-render schema. Click anywhere → drawer.

import { useMemo } from "react";

import {
  type ConvictionTileData, validateConvictionTile, TileSchemaError,
} from "@/lib/copilot/tile_schema";
import { freshnessTimestamp } from "@/lib/copilot/conviction_card_schema";

import VerbPill from "./VerbPill";
import TierGlyph from "./TierGlyph";


export interface ConvictionTileProps {
  tile: ConvictionTileData;
  onClick: (ticker: string) => void;
  isActive?: boolean;       // currently open in drawer
  isDimmed?: boolean;       // another tile is open
}


export default function ConvictionTile({
  tile, onClick, isActive = false, isDimmed = false,
}: ConvictionTileProps) {
  const validated = useMemo(() => {
    try {
      return validateConvictionTile(tile);
    } catch (e) {
      if (e instanceof TileSchemaError) return null;
      throw e;
    }
  }, [tile]);

  if (!validated) {
    return (
      <button
        className="ux11-tile"
        style={{ borderColor: "var(--ux10-risk)" }}
        data-test="ux11-tile-error"
      >
        <div className="ux11-tile-row1">
          <span style={{ color: "var(--ux10-risk)" }}>SCHEMA ERROR</span>
        </div>
        <div className="ux11-tile-row2">
          {tile.ticker || "(unknown)"} — composer rejected
        </div>
      </button>
    );
  }

  const isStale = validated.freshnessState === "Stale" || validated.freshnessState === "Expired";

  return (
    <button
      type="button"
      className="ux11-tile"
      data-test="ux11-conviction-tile"
      data-ticker={validated.ticker}
      data-tier={validated.confidenceTier}
      data-stale={isStale ? "true" : "false"}
      data-active={isActive ? "true" : "false"}
      data-dim={isDimmed ? "true" : "false"}
      onClick={() => onClick(validated.ticker)}
      aria-haspopup="dialog"
      aria-label={`${validated.verb} ${validated.ticker}: ${validated.thesisName}. Open reasoning drawer.`}
    >
      {/* Row 1: verb pill + tier glyph + freshness chip */}
      <div className="ux11-tile-row1">
        <VerbPill verb={validated.verb} />
        <span style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <TierGlyph tier={validated.confidenceTier} />
          <span aria-hidden="true">·</span>
          <span data-state={validated.freshnessState}>
            {freshnessTimestamp(validated.lastReviewedAt)}
          </span>
        </span>
      </div>

      {/* Row 2: ticker + thesis name */}
      <div className="ux11-tile-row2">
        <strong>{validated.ticker}</strong>
        <span aria-hidden="true">·</span>
        <span>{validated.thesisName}</span>
      </div>

      {/* Row 3: decision sentence — the largest visual element */}
      <div className="ux11-tile-row3">{validated.decisionSentence}</div>

      {/* Row 4: Bull/Bear inline (Confirmed+ only) */}
      {validated.bullClause && validated.bearClause ? (
        <div className="ux11-tile-row4">
          <span className="ux11-bullbear-label">Bull · </span>
          <span>{validated.bullClause}</span>
          <span aria-hidden="true">  ·  </span>
          <span className="ux11-bullbear-label">Bear · </span>
          <span>{validated.bearClause}</span>
        </div>
      ) : (
        <div className="ux11-tile-row4" aria-hidden="true" />
      )}

      {/* Row 5: invalidation distance + horizon */}
      <div className="ux11-tile-row5">
        <span className="ux11-invalidation-distance">
          {validated.invalidationDistance}
        </span>
        <span>{validated.horizon}</span>
      </div>
    </button>
  );
}
