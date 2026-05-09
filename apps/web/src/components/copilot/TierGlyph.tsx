// UX-10 Phase 10A — TierGlyph primitive.
//
// Source of truth: docs/research/UX_10_CONVICTION_ENGINE.md
//   Section 4.1 (Strength tier — 4 named levels)
//
// Dot row ●○○○ → ●●●●. Single color. NO animation on first paint
// of glyph itself (the card reveal handles its own motion).

import type { ConfidenceTier } from "@/lib/copilot/conviction_card_schema";


const TIER_DOTS: Record<ConfidenceTier, number> = {
  Forming: 1,
  Working: 2,
  Confirmed: 3,
  Conviction: 4,
};


export interface TierGlyphProps {
  tier: ConfidenceTier;
}


export default function TierGlyph({ tier }: TierGlyphProps) {
  const filled = TIER_DOTS[tier];
  return (
    <span
      className="ux10-tier"
      data-tier={tier}
      data-test="ux10-tier-glyph"
      aria-label={`${tier} confidence (${filled} of 4)`}
    >
      <span className="ux10-tier-dots" aria-hidden="true">
        {[0, 1, 2, 3].map(i => (
          <span key={i} data-on={i < filled ? "true" : "false"} />
        ))}
      </span>
      <span>{tier}</span>
    </span>
  );
}
