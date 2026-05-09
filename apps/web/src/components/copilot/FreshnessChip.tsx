// UX-10 Phase 10A — FreshnessChip primitive.
//
// Source of truth: docs/research/UX_10_CONVICTION_ENGINE.md
//   Section 4.1 (Freshness state — 4 named levels)
//
// Tiny meta line — "Fresh · 14h ago" / "Stale · 3d ago" /
// "Expired". Color encodes state per token sheet (most are
// muted; Stale=amber, Expired=risk-red).

import type { FreshnessState } from "@/lib/copilot/conviction_card_schema";
import { freshnessTimestamp } from "@/lib/copilot/conviction_card_schema";


export interface FreshnessChipProps {
  state: FreshnessState;
  lastReviewedAt: string;       // ISO timestamp
  expiryCondition?: string;     // optional second line text
}


export default function FreshnessChip({ state, lastReviewedAt, expiryCondition }: FreshnessChipProps) {
  return (
    <span
      className="ux10-fresh"
      data-state={state}
      data-test="ux10-fresh-chip"
    >
      <span>{state} · {freshnessTimestamp(lastReviewedAt)}</span>
      {expiryCondition && (
        <span style={{ opacity: 0.7 }}>· valid until {expiryCondition}</span>
      )}
    </span>
  );
}
