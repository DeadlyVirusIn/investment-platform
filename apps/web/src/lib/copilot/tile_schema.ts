// UX-11 Phase 11A — ConvictionTile refuses-to-render schema.
//
// Source of truth: docs/research/UX_11_INTERACTIVE_COPILOT.md
//   Section 3.4 (refuses-to-render conditions)
//
// Validation runs at composer time. Throws TileSchemaError if any
// invariant violated. We do NOT silently fall back; we surface
// the failure so the composer logic gets fixed.

import {
  type Verb, type ConfidenceTier, type FreshnessState,
  VERBS,
} from "./conviction_card_schema";


export interface ConvictionTileData {
  verb: Verb;
  ticker: string;
  thesisName: string;                 // ≤ 5 words
  decisionSentence: string;           // 80-140 chars
  confidenceTier: ConfidenceTier;
  freshnessState: FreshnessState;
  lastReviewedAt: string;             // ISO timestamp
  invalidationDistance: string;       // e.g., "Invalid < $158" or "−4.2% to invalidation"
  horizon: string;                    // e.g., "~6w" / "6-18mo"
  bullClause?: string;                // ≤ 32 chars; REQUIRED on Confirmed+
  bearClause?: string;                // ≤ 32 chars; REQUIRED on Confirmed+
}


export class TileSchemaError extends Error {
  constructor(message: string, public readonly tile: Partial<ConvictionTileData>) {
    super(`[UX-11 ConvictionTile refuses-to-render] ${message}`);
    this.name = "TileSchemaError";
  }
}


/** Returns the tile unchanged on success; throws on failure. */
export function validateConvictionTile(tile: ConvictionTileData): ConvictionTileData {
  // Verb in locked set
  if (!tile.verb || !VERBS.includes(tile.verb)) {
    throw new TileSchemaError(
      `verb '${tile.verb}' not in locked set [${VERBS.join(", ")}]`,
      tile,
    );
  }

  // Ticker present
  if (!tile.ticker) {
    throw new TileSchemaError("ticker missing", tile);
  }

  // thesisName ≤ 5 words (trim splits, ignore double spaces)
  if (!tile.thesisName) {
    throw new TileSchemaError("thesisName missing", tile);
  }
  const wordCount = tile.thesisName.trim().split(/\s+/).length;
  if (wordCount > 5) {
    throw new TileSchemaError(
      `thesisName has ${wordCount} words (max 5)`,
      tile,
    );
  }

  // Decision sentence 80-140 chars (UX-11 master Section 3.4)
  if (!tile.decisionSentence) {
    throw new TileSchemaError("decisionSentence missing", tile);
  }
  if (tile.decisionSentence.length < 80) {
    throw new TileSchemaError(
      `decisionSentence too short (${tile.decisionSentence.length} chars; min 80)`,
      tile,
    );
  }
  if (tile.decisionSentence.length > 140) {
    throw new TileSchemaError(
      `decisionSentence too long (${tile.decisionSentence.length} chars; max 140)`,
      tile,
    );
  }

  // Invalidation distance present + non-stub
  if (!tile.invalidationDistance) {
    throw new TileSchemaError("invalidationDistance missing", tile);
  }
  const stubMarkers = ["TBD", "tbd", "varies", "n/a"];
  if (stubMarkers.some(s => tile.invalidationDistance.toLowerCase().includes(s.toLowerCase()))) {
    throw new TileSchemaError(
      `invalidationDistance contains stub marker (${stubMarkers.join(", ")})`,
      tile,
    );
  }

  // Horizon present
  if (!tile.horizon) {
    throw new TileSchemaError("horizon missing", tile);
  }

  // L4 / S3: bear-case-mandated for Confirmed+ tier
  // UX-11 expression: bullClause + bearClause both required on Confirmed+
  const isHighTier = tile.confidenceTier === "Confirmed" || tile.confidenceTier === "Conviction";
  if (isHighTier) {
    if (!tile.bullClause || tile.bullClause.length < 8) {
      throw new TileSchemaError(
        `${tile.confidenceTier} tier requires bullClause ≥ 8 chars (got ${tile.bullClause?.length ?? 0})`,
        tile,
      );
    }
    if (!tile.bearClause || tile.bearClause.length < 8) {
      throw new TileSchemaError(
        `${tile.confidenceTier} tier requires bearClause ≥ 8 chars (got ${tile.bearClause?.length ?? 0})`,
        tile,
      );
    }
    if (tile.bullClause.length > 32) {
      throw new TileSchemaError(
        `bullClause too long (${tile.bullClause.length} chars; max 32)`,
        tile,
      );
    }
    if (tile.bearClause.length > 32) {
      throw new TileSchemaError(
        `bearClause too long (${tile.bearClause.length} chars; max 32)`,
        tile,
      );
    }
  }

  // Banned content sniffing — explicit ban on numeric upside on tile (D3)
  // Catches the classic "+18% upside" / "+18% modeled upside" patterns.
  const upsidePattern = /[+\-]?\d{1,3}(\.\d+)?%\s*(modeled\s+)?upside/i;
  if (upsidePattern.test(tile.decisionSentence)) {
    throw new TileSchemaError(
      "decisionSentence contains banned numeric upside anchor (UX-11 D3 lock)",
      tile,
    );
  }

  return tile;
}
