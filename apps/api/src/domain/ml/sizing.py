"""ML sizing multiplier (V1) — SHADOW MODE helper.

Reference: AFML §10.3 (Lopez de Prado) — bet sizing.

Formula (LOCKED, do not tune):

    multiplier = clip(0.5 + 1.4 * (ml_proba - 0.10), 0.5, 1.2)

Characteristics:
  - proba 0.10 → 0.5x (minimum)
  - proba 0.60 → 1.2x (maximum)
  - no filter; every trade gets a multiplier
  - applied AFTER deterministic engine selection
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

ML_MULTIPLIER_MIN     = Decimal("0.5")
ML_MULTIPLIER_MAX     = Decimal("1.2")
ML_MULTIPLIER_OFFSET  = Decimal("0.10")   # proba pivot
ML_MULTIPLIER_SLOPE   = Decimal("1.4")
ML_MULTIPLIER_BASE    = Decimal("0.5")


def compute_ml_multiplier(ml_proba: Decimal | float | None) -> Decimal:
    """Return the sizing multiplier for a given ML probability.

    Returns 1.0 when proba is None (neutral — no ML adjustment).
    """
    if ml_proba is None:
        return Decimal("1.0")
    p = ml_proba if isinstance(ml_proba, Decimal) else Decimal(str(ml_proba))
    raw = ML_MULTIPLIER_BASE + ML_MULTIPLIER_SLOPE * (p - ML_MULTIPLIER_OFFSET)
    if raw < ML_MULTIPLIER_MIN:
        return ML_MULTIPLIER_MIN
    if raw > ML_MULTIPLIER_MAX:
        return ML_MULTIPLIER_MAX
    return raw


@dataclass
class TradeSizingLog:
    """Per-trade shadow-sizing log row (AFML §10.3 observability)."""
    as_of_date: str
    symbol: str
    asset_id: str
    base_weight: str            # Decimal pre-ML, post-clamp
    ml_proba: str | None
    multiplier: str
    adjusted_weight: str        # base * multiplier (pre-cap)
    final_weight: str           # post-MAX_POSITION_PCT + sector-cap (pre-normalization)
    was_clipped: bool
    cap_reason: str | None      # "position_cap" | "sector_cap" | None
    normalized_weight: str = "" # post book-level normalization to production sum
