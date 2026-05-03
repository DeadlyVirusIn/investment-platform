"""Regime-based signal router (Phase B3).

Pure function. Takes a regime label and two signal lists, returns the
subset of each that should be executed plus an exposure multiplier.

Caller is responsible for applying the multiplier to position sizing.
Signal list contents are opaque — router does not inspect individual
signals, just routes streams.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

# Generic — router is agnostic to concrete signal types.
M = TypeVar("M")
B = TypeVar("B")


# ---------------------------------------------------------------------------
# Routing rules (from Phase B2 evidence)
# ---------------------------------------------------------------------------

REGIME_LOW_VOL: str = "low_vol"
REGIME_TREND_UP: str = "trend_up"
REGIME_SIDEWAYS: str = "sideways"
REGIME_HIGH_VOL: str = "high_vol"

SIDEWAYS_EXPOSURE_MULTIPLIER: float = 0.5
DEFAULT_EXPOSURE_MULTIPLIER: float = 1.0

RULE_LOW_VOL_BOTH: str = "low_vol_both"
RULE_TREND_UP_MODEL_ONLY: str = "trend_up_model_only"
RULE_SIDEWAYS_REDUCE: str = "sideways_reduce_exposure"
RULE_FALLBACK_MODEL_ONLY: str = "fallback_model_only"


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RoutedOutput(Generic[M, B]):
    """Output of route_signals.

    - `model_signals`: model-family signals to execute (subset of input).
    - `behavioral_signals`: behavioral signals to execute (subset of input).
    - `exposure_multiplier`: extra scale to apply on top of existing sizing
      (e.g. regime-gating multiplier). Always in (0, 1].
    - `rule_applied`: which rule fired (for logging + audit).
    """

    model_signals: list[M]
    behavioral_signals: list[B]
    exposure_multiplier: float
    rule_applied: str


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------


def route_signals(
    regime: str,
    model_signals: list[M],
    behavioral_signals: list[B],
) -> RoutedOutput[M, B]:
    """Route model + behavioral signal streams per regime.

    Rules (Phase B3 spec, 2026-04-21):

        regime == "low_vol"   -> both model + behavioral, full exposure
        regime == "trend_up"  -> model only, full exposure
        regime == "sideways"  -> both, 0.5x exposure
        else                  -> model only, full exposure (fallback)
    """
    if regime == REGIME_LOW_VOL:
        return RoutedOutput(
            model_signals=list(model_signals),
            behavioral_signals=list(behavioral_signals),
            exposure_multiplier=DEFAULT_EXPOSURE_MULTIPLIER,
            rule_applied=RULE_LOW_VOL_BOTH,
        )
    if regime == REGIME_TREND_UP:
        return RoutedOutput(
            model_signals=list(model_signals),
            behavioral_signals=[],
            exposure_multiplier=DEFAULT_EXPOSURE_MULTIPLIER,
            rule_applied=RULE_TREND_UP_MODEL_ONLY,
        )
    if regime == REGIME_SIDEWAYS:
        return RoutedOutput(
            model_signals=list(model_signals),
            behavioral_signals=list(behavioral_signals),
            exposure_multiplier=SIDEWAYS_EXPOSURE_MULTIPLIER,
            rule_applied=RULE_SIDEWAYS_REDUCE,
        )
    # Fallback: high_vol, unknown, or any unanticipated label
    return RoutedOutput(
        model_signals=list(model_signals),
        behavioral_signals=[],
        exposure_multiplier=DEFAULT_EXPOSURE_MULTIPLIER,
        rule_applied=RULE_FALLBACK_MODEL_ONLY,
    )
