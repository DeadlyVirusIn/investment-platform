"""Action priority scoring — deterministic, reuses existing engine fields.

No new scoring system. Priority is a weighted combination of:
  0.35 * confidence (0..1)
  0.25 * urgency weight
  0.20 * regime alignment (0 or 1)
  0.10 * dependencies resolved fraction
  0.10 * economic impact (0..1, normalized)

Output is 0..100 Decimal. Tier bucketing:
  CRT  >= 75
  HIGH >= 50
  NRM  <  50
"""

from __future__ import annotations

from decimal import Decimal
from typing import Final

URGENCY_WEIGHTS: Final[dict[str, float]] = {
    "now": 1.0,
    "today": 0.8,
    "this_week": 0.4,
    "passive": 0.2,
}

# Tier thresholds
TIER_CRT_THRESHOLD = Decimal("75")
TIER_HIGH_THRESHOLD = Decimal("50")


def compute_priority(
    *,
    confidence: Decimal | float | int | None,
    regime_aligned: bool,
    urgency: str,
    dependencies_resolved_frac: float,
    economic_impact_pct: float,
) -> Decimal:
    """Return priority in [0, 100] as Decimal with 2dp.

    confidence: 0..100 scale (matches candidate_idea.confidence). None -> 0.
    regime_aligned: bool, from regime.market_trend vs kind.
    urgency: one of URGENCY_WEIGHTS keys. Unknown -> 0.4 (treated as 'this_week').
    dependencies_resolved_frac: 0..1. Fraction of dependency preconditions met.
    economic_impact_pct: 0..1. Normalized |position_delta_pct|, clipped.
    """
    if confidence is None:
        conf = 0.0
    else:
        conf = float(confidence) / 100.0
        conf = max(0.0, min(1.0, conf))

    urgency_w = URGENCY_WEIGHTS.get(urgency, 0.4)
    regime_w = 1.0 if regime_aligned else 0.0
    deps_w = max(0.0, min(1.0, float(dependencies_resolved_frac)))
    impact_w = max(0.0, min(1.0, float(economic_impact_pct)))

    raw = (
        0.35 * conf
        + 0.25 * urgency_w
        + 0.20 * regime_w
        + 0.10 * deps_w
        + 0.10 * impact_w
    )
    score = round(raw * 100.0, 2)
    return Decimal(str(score))


def priority_tier(priority: Decimal | float | int) -> str:
    p = priority if isinstance(priority, Decimal) else Decimal(str(priority))
    if p >= TIER_CRT_THRESHOLD:
        return "CRT"
    if p >= TIER_HIGH_THRESHOLD:
        return "HIGH"
    return "NRM"
