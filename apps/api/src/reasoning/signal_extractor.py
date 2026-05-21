"""Phase L canonical signal extractor — deterministic.

Maps engine feature vectors (CandidateIdea.factor_breakdown +
regime_snapshot, or equivalent for live Recommendations) onto the
locked canonical signal set (vocabulary_type='signal', 12 entries).

Pure function. Same inputs → same set. No DB calls, no time-of-day
dependence, no randomness.

Coverage policy (honest absence):
  The extractor derives only what the data supports. Of the 12 canonical
  signals, MVP reliably maps 6:
    momentum_3w_positive, momentum_3w_negative,
    iv_compression,       iv_expansion,
    macro_tailwind,        macro_headwind
  The remaining 6 require substrate we don't yet have plumbed
  (breadth_regime, market_event_calendar, volume baselines per asset).
  When those substrates land, this module is the single integration
  point — the rest of the reasoning pipeline does not change.

Threshold rationale: see docs/research/SIGNAL_EXTRACTION_THRESHOLDS.md
(to be written in a later day). For now thresholds are conservative —
they reject borderline activations rather than over-claim.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Optional


# Locked canonical signal names — must match vocabulary_entry rows for
# vocabulary_type='signal'. Keep in alphabetical order for easy diff.
CANONICAL_SIGNALS: frozenset[str] = frozenset({
    "breadth_broadening",
    "breadth_narrowing",
    "catalyst_proximate_earnings",
    "catalyst_proximate_macro",
    "iv_compression",
    "iv_expansion",
    "macro_headwind",
    "macro_tailwind",
    "momentum_3w_negative",
    "momentum_3w_positive",
    "volume_confirmation",
    "volume_divergence",
})


# Thresholds (frozen — see header).
MOMENTUM_TREND_POS = Decimal("0.10")
MOMENTUM_TREND_NEG = Decimal("-0.10")
MOMENTUM_RESIDUAL_POS = Decimal("0.05")
MOMENTUM_RESIDUAL_NEG = Decimal("-0.05")


@dataclass(frozen=True)
class FeatureContext:
    """Inputs the extractor needs from the engine.

    All fields optional — missing fields just mean signals that depend
    on them won't fire. Strict typing on the way in keeps the rest of
    the pipeline pure.

    Catalyst flags are populated externally (typically by a DB lookup
    against market_event_calendar / earnings_event done at the
    integration layer). The extractor itself stays pure.
    """
    factor_breakdown: Mapping[str, Any] | None = None
    regime_snapshot: Mapping[str, Any] | None = None
    catalyst_proximate_macro: bool = False
    catalyst_proximate_earnings: bool = False


def _to_decimal(v: Any) -> Optional[Decimal]:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return v
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _get_values(ctx: FeatureContext) -> dict[str, Any]:
    fb = ctx.factor_breakdown or {}
    # factor_breakdown.values holds the actual numeric features
    values = fb.get("values") if isinstance(fb, dict) else None
    return values if isinstance(values, dict) else {}


def extract_signals(ctx: FeatureContext) -> frozenset[str]:
    """Return the set of canonical signals firing for this context.

    Pure. Deterministic. Empty set on insufficient/unsupported data.
    """
    active: set[str] = set()

    values = _get_values(ctx)
    trend_20d = _to_decimal(values.get("trend_strength_20d"))
    residual_20d = _to_decimal(values.get("residual_momentum_20d"))

    # Momentum: positive if EITHER trend OR residual clears its threshold,
    # but never both directions simultaneously (logical guard).
    pos_hits = (
        (trend_20d is not None and trend_20d >= MOMENTUM_TREND_POS)
        or (residual_20d is not None and residual_20d >= MOMENTUM_RESIDUAL_POS)
    )
    neg_hits = (
        (trend_20d is not None and trend_20d <= MOMENTUM_TREND_NEG)
        or (residual_20d is not None and residual_20d <= MOMENTUM_RESIDUAL_NEG)
    )
    if pos_hits and not neg_hits:
        active.add("momentum_3w_positive")
    elif neg_hits and not pos_hits:
        active.add("momentum_3w_negative")

    # Regime-derived signals
    regime = ctx.regime_snapshot or {}
    vol_regime = regime.get("vol_regime") if isinstance(regime, dict) else None
    if vol_regime == "low":
        active.add("iv_compression")
    elif vol_regime == "high":
        active.add("iv_expansion")

    market_trend = regime.get("market_trend") if isinstance(regime, dict) else None
    sma50_over_sma200 = regime.get("sma50_over_sma200") if isinstance(regime, dict) else None
    if market_trend == "uptrend" and sma50_over_sma200 is True:
        active.add("macro_tailwind")
    elif market_trend == "downtrend" or (
        market_trend != "uptrend" and sma50_over_sma200 is False
    ):
        active.add("macro_headwind")

    # Catalyst signals — driven by explicit flags from a DB lookup.
    # Never inferred from price action or other signals.
    if ctx.catalyst_proximate_macro:
        active.add("catalyst_proximate_macro")
    if ctx.catalyst_proximate_earnings:
        active.add("catalyst_proximate_earnings")

    # Validate every derived signal is canonical — fail loud if drift.
    unknown = active - CANONICAL_SIGNALS
    if unknown:
        raise ValueError(
            f"extractor produced non-canonical signals: {sorted(unknown)}"
        )
    return frozenset(active)
