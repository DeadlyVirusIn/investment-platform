"""Phase L uncertainty marker assigner.

Deterministically maps decision context onto the locked
UncertaintyMarker set (7 members from D3.5).

Calibration rules (intentionally restrictive — markers exist to
surface honest uncertainty, not to hedge defensively on every trade):

  LIMITED_HISTORY        ← confidence_label == 'Low'
  LOW_SIGNAL_STRENGTH    ← composite within ±10% of the BUY threshold
                           (i.e. signal barely cleared its bar)
  REGIME_TRANSITION      ← market_trend == 'sideways'
                           OR (regime sma50/sma200 conflict with trend)
  PARTIAL_DATA           ← factor_breakdown.missing_components non-empty
  CROWDED_TRADE          ← sector_relative_rank >= 0.95
  COUNTER_TREND          ← skeleton == MEAN_REVERSION_PULLBACK
                           OR (side='buy' AND macro_headwind in signals)
  UNUSUAL_VOLATILITY     ← atr_pctile_1y >= 0.85 OR <= 0.15
                           (i.e. realized vol far from typical envelope)

Marker cap: max 3 per envelope. If >3 fire, we keep the highest-
priority three by the order defined in PRIORITY below.

Priority (most informative first):
  PARTIAL_DATA, LIMITED_HISTORY, REGIME_TRANSITION,
  UNUSUAL_VOLATILITY, COUNTER_TREND, LOW_SIGNAL_STRENGTH, CROWDED_TRADE

Pure. Same context -> same markers in same order.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Optional

from apps.api.src.reasoning.skeletons import SkeletonId
from apps.api.src.reasoning.uncertainty_markers import UncertaintyMarker


MAX_MARKERS_PER_ENVELOPE = 3

# Priority order — lowest index wins under the cap.
PRIORITY: list[UncertaintyMarker] = [
    UncertaintyMarker.PARTIAL_DATA,
    UncertaintyMarker.LIMITED_HISTORY,
    UncertaintyMarker.REGIME_TRANSITION,
    UncertaintyMarker.UNUSUAL_VOLATILITY,
    UncertaintyMarker.COUNTER_TREND,
    UncertaintyMarker.LOW_SIGNAL_STRENGTH,
    UncertaintyMarker.CROWDED_TRADE,
]


@dataclass(frozen=True)
class MarkerContext:
    """Inputs the assigner draws from."""
    side: str = "buy"
    skeleton_id: Optional[SkeletonId] = None
    active_signals: frozenset[str] = frozenset()
    factor_breakdown: Optional[Mapping[str, Any]] = None
    regime_snapshot: Optional[Mapping[str, Any]] = None


def _dec(v: Any) -> Optional[Decimal]:
    if v is None:
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError):
        return None


def assign_markers(ctx: MarkerContext) -> list[UncertaintyMarker]:
    """Return calibrated markers for this context, capped at MAX."""
    fb = ctx.factor_breakdown or {}
    regime = ctx.regime_snapshot or {}
    values = fb.get("values") if isinstance(fb, dict) else None
    values = values if isinstance(values, dict) else {}
    missing = fb.get("missing_components") if isinstance(fb, dict) else None
    composite = _dec(fb.get("composite") if isinstance(fb, dict) else None)
    confidence_label = (
        fb.get("confidence_label") if isinstance(fb, dict) else None
    )
    thresholds = fb.get("thresholds") if isinstance(fb, dict) else None
    buy_thresh = _dec(thresholds.get("BUY")) if isinstance(thresholds, dict) else None

    candidates: set[UncertaintyMarker] = set()

    # PARTIAL_DATA
    if isinstance(missing, list) and len(missing) > 0:
        candidates.add(UncertaintyMarker.PARTIAL_DATA)

    # LIMITED_HISTORY
    if confidence_label == "Low":
        candidates.add(UncertaintyMarker.LIMITED_HISTORY)

    # REGIME_TRANSITION
    market_trend = regime.get("market_trend") if isinstance(regime, dict) else None
    sma50_over_sma200 = regime.get("sma50_over_sma200") if isinstance(regime, dict) else None
    if market_trend == "sideways":
        candidates.add(UncertaintyMarker.REGIME_TRANSITION)
    elif (
        market_trend == "uptrend" and sma50_over_sma200 is False
    ) or (
        market_trend == "downtrend" and sma50_over_sma200 is True
    ):
        candidates.add(UncertaintyMarker.REGIME_TRANSITION)

    # UNUSUAL_VOLATILITY
    atr_pctile = _dec(regime.get("atr_pctile_1y") if isinstance(regime, dict) else None)
    if atr_pctile is not None and (
        atr_pctile >= Decimal("0.85") or atr_pctile <= Decimal("0.15")
    ):
        candidates.add(UncertaintyMarker.UNUSUAL_VOLATILITY)

    # COUNTER_TREND
    if ctx.skeleton_id == SkeletonId.MEAN_REVERSION_PULLBACK:
        candidates.add(UncertaintyMarker.COUNTER_TREND)
    elif ctx.side == "buy" and "macro_headwind" in ctx.active_signals:
        candidates.add(UncertaintyMarker.COUNTER_TREND)
    elif ctx.side == "sell" and "macro_tailwind" in ctx.active_signals:
        candidates.add(UncertaintyMarker.COUNTER_TREND)

    # LOW_SIGNAL_STRENGTH
    if composite is not None and buy_thresh is not None and buy_thresh > 0:
        band = buy_thresh * Decimal("0.10")
        if buy_thresh - band <= composite <= buy_thresh + band:
            candidates.add(UncertaintyMarker.LOW_SIGNAL_STRENGTH)

    # CROWDED_TRADE
    sector_rank = _dec(values.get("sector_relative_rank"))
    if sector_rank is not None and sector_rank >= Decimal("0.95"):
        candidates.add(UncertaintyMarker.CROWDED_TRADE)

    # Apply priority + cap
    ordered = [m for m in PRIORITY if m in candidates]
    return ordered[:MAX_MARKERS_PER_ENVELOPE]
