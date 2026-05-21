"""Phase L invalidation populator.

Per-skeleton deterministic mapping:
    (SkeletonId, entry_context) -> InvalidationTrigger

Pure. No prose. No discretion.

The invalidation vocabulary is locked (seeded by D3.2 invalidations_v1):
    stop_below_anchor       — price closes below an anchor level
    thesis_signal_flips     — original trigger signal now opposite
    volatility_collapse     — IV mean-reverts (options-only)
    regime_break            — regime backdrop flips away from trade

Mapping rationale:
  * MOMENTUM_BREAKOUT  → stop_below_anchor  (chartist exit)
  * MEAN_REVERSION_PULLBACK → thesis_signal_flips (the momentum that
    justified buying weakness re-confirms downside)
  * BREADTH_THRUST_ENTRY → thesis_signal_flips (breadth narrows again)
  * IV_COMPRESSION_SETUP → volatility_collapse (IV re-expands too late)
  * CATALYST_ANTICIPATION → thesis_signal_flips (catalyst reads opposite)
  * REGIME_ALIGNED_CONTINUATION → regime_break (regime classification flips)

Threshold population (where applicable): the populator is allowed to
pass through structured numeric thresholds from the entry context.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping, Optional

from apps.api.src.reasoning.envelope import InvalidationTrigger
from apps.api.src.reasoning.skeletons import SkeletonId


# Default stop distance for momentum/breakout setups, as a fraction
# of entry price. Conservative; engine config may override per-portfolio
# later.
DEFAULT_STOP_PCT = Decimal("0.07")


@dataclass(frozen=True)
class EntryContext:
    """Information available at decision time that informs invalidation."""
    fill_price: Optional[Decimal] = None
    suggested_stop_price: Optional[Decimal] = None  # if engine emitted one
    realized_vol_20d: Optional[Decimal] = None      # for IV setups
    side: str = "buy"


_SKELETON_TO_TRIGGER: dict[SkeletonId, str] = {
    SkeletonId.MOMENTUM_BREAKOUT: "stop_below_anchor",
    SkeletonId.MEAN_REVERSION_PULLBACK: "thesis_signal_flips",
    SkeletonId.BREADTH_THRUST_ENTRY: "thesis_signal_flips",
    SkeletonId.IV_COMPRESSION_SETUP: "volatility_collapse",
    SkeletonId.CATALYST_ANTICIPATION: "thesis_signal_flips",
    SkeletonId.REGIME_ALIGNED_CONTINUATION: "regime_break",
}


def populate_invalidation(
    skeleton_id: SkeletonId, ctx: EntryContext,
) -> InvalidationTrigger:
    """Deterministically populate the InvalidationTrigger for a given skeleton."""
    trigger = _SKELETON_TO_TRIGGER.get(skeleton_id)
    if trigger is None:
        raise ValueError(f"no invalidation mapping for {skeleton_id}")

    threshold: Optional[Mapping[str, Any]] = None
    if trigger == "stop_below_anchor":
        if ctx.suggested_stop_price is not None and ctx.fill_price is not None:
            stop = Decimal(ctx.suggested_stop_price)
            entry = Decimal(ctx.fill_price)
            if entry > 0:
                pct = ((stop - entry) / entry).quantize(Decimal("0.0001"))
                threshold = {
                    "anchor_price": str(stop),
                    "entry_price": str(entry),
                    "drawdown_pct": str(pct),
                }
        elif ctx.fill_price is not None:
            entry = Decimal(ctx.fill_price)
            implied_stop = (entry * (Decimal("1") - DEFAULT_STOP_PCT)).quantize(
                Decimal("0.01")
            )
            threshold = {
                "anchor_price": str(implied_stop),
                "entry_price": str(entry),
                "drawdown_pct": str(-DEFAULT_STOP_PCT),
            }
    elif trigger == "volatility_collapse":
        if ctx.realized_vol_20d is not None:
            threshold = {
                "realized_vol_20d_entry": str(ctx.realized_vol_20d),
            }
    # thesis_signal_flips and regime_break: threshold is qualitative
    # (i.e. the signal/regime state itself), not numeric. Leave None.

    return InvalidationTrigger(
        condition_vocab=trigger,
        threshold=threshold,
    )
