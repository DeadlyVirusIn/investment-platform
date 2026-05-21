"""Phase L envelope generator — orchestrator.

Single pure entry point that composes:
    D4.1 signal_extractor
    D4.2 skeleton_selector
    D4.3 invalidation_populator
    D4.4 marker_assigner
    D3.3 envelope.build_envelope

Inputs:  DecisionContext (engine features + fill context + side + source)
Output:  ReasoningEnvelope | None

None is returned (and MUST be respected by the caller) when:
  * extracted signal set has fewer than 2 canonical signals — too thin
    to make any structured claim; OR
  * skeleton_selector returns None — no rule matched.

Honest absence policy: callers MUST NOT fabricate a substitute envelope.
Trades proceed; Decision Detail surfaces incomplete_lifecycle banner.

Determinism: every step is pure. Same DecisionContext (including
identical generated_at) → identical envelope_hash.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Mapping, Optional

from apps.api.src.reasoning.envelope import (
    EnvelopeSource, ExpectedSignal, ReasoningEnvelope, ThesisHorizon,
    ThesisStatement, build_envelope,
)
from apps.api.src.reasoning.invalidation_populator import (
    EntryContext, populate_invalidation,
)
from apps.api.src.reasoning.marker_assigner import (
    MarkerContext, assign_markers,
)
from apps.api.src.reasoning.signal_extractor import (
    FeatureContext, extract_signals,
)
from apps.api.src.reasoning.skeleton_selector import select_skeleton
from apps.api.src.reasoning.skeletons import CATALOG, SkeletonId


MIN_SIGNALS_FOR_ENVELOPE = 2


# Discrete skip reasons emitted by generate_envelope_detailed.
# Persisted into envelope_generation_run for skip-reason granularity.
SKIP_MIN_SIGNALS = "min_signals_not_met"
SKIP_NO_SKELETON_MATCH = "no_skeleton_match"
SKIP_EMPTY_SLOT_FILLS = "empty_slot_fills"


@dataclass(frozen=True)
class GenerationResult:
    """Detailed generator output — envelope plus discrete skip reason.

    `envelope` is None iff `none_reason` is set. Mutually exclusive.
    """
    envelope: Optional["ReasoningEnvelope"]
    none_reason: Optional[str]


@dataclass(frozen=True)
class DecisionContext:
    side: str                                 # 'buy' | 'sell'
    asset_class: str = "equity"               # 'equity' | 'options'
    factor_breakdown: Optional[Mapping[str, Any]] = None
    regime_snapshot: Optional[Mapping[str, Any]] = None
    fill_price: Optional[Decimal] = None
    suggested_stop_price: Optional[Decimal] = None
    realized_vol_20d: Optional[Decimal] = None
    source: EnvelopeSource = EnvelopeSource.LIVE
    generated_at: Optional[dt.datetime] = None
    catalyst_proximate_macro: bool = False
    catalyst_proximate_earnings: bool = False


# Per-skeleton slot-fill builders: each takes (side, active_signals,
# regime_snapshot) and returns the slot_fills dict for the skeleton.
#
# Each builder picks ONE canonical signal as trigger_signal and the
# rest as confirming_signals (where the slot exists). Determinism:
# canonical signals iterated in sorted order.

_REGIME_SIGNALS = frozenset({"macro_tailwind", "macro_headwind"})
_IV_SIGNALS = frozenset({"iv_compression", "iv_expansion"})
_CATALYST_SIGNALS = frozenset({
    "catalyst_proximate_earnings", "catalyst_proximate_macro",
})


def _pick_first(signals: frozenset[str], preferred: tuple[str, ...]) -> Optional[str]:
    """Return the first signal from `preferred` that's active, deterministically."""
    for p in preferred:
        if p in signals:
            return p
    return None


def _confirming(
    signals: frozenset[str], exclude: set[str], cap: int,
) -> list[str]:
    """Return confirming signals in sorted order, excluding given names."""
    return sorted(s for s in signals if s not in exclude)[:cap]


def _slot_fills_for(
    skeleton_id: SkeletonId, side: str, signals: frozenset[str],
) -> dict[str, str | list[str]]:
    spec = CATALOG[skeleton_id]
    fills: dict[str, str | list[str]] = {}

    if skeleton_id == SkeletonId.MOMENTUM_BREAKOUT:
        trigger = _pick_first(
            signals,
            ("momentum_3w_positive", "momentum_3w_negative"),
        )
        if trigger is None:
            return {}
        fills["trigger_signal"] = trigger
        conf = _confirming(
            signals, exclude={trigger} | _REGIME_SIGNALS | _IV_SIGNALS, cap=3,
        )
        if conf:
            fills["confirming_signals"] = conf

    elif skeleton_id == SkeletonId.MEAN_REVERSION_PULLBACK:
        trigger = _pick_first(signals, ("momentum_3w_negative",))
        regime = _pick_first(signals, ("macro_tailwind", "macro_headwind"))
        if trigger is None or regime is None:
            return {}
        fills["trigger_signal"] = trigger
        fills["regime_context"] = regime

    elif skeleton_id == SkeletonId.BREADTH_THRUST_ENTRY:
        trigger = _pick_first(
            signals, ("breadth_broadening", "breadth_narrowing"),
        )
        if trigger is None:
            return {}
        fills["trigger_signal"] = trigger
        conf = _confirming(
            signals, exclude={trigger} | _REGIME_SIGNALS | _IV_SIGNALS, cap=2,
        )
        if conf:
            fills["confirming_signals"] = conf

    elif skeleton_id == SkeletonId.IV_COMPRESSION_SETUP:
        trigger = _pick_first(signals, ("iv_compression",))
        if trigger is None:
            return {}
        fills["trigger_signal"] = trigger

    elif skeleton_id == SkeletonId.CATALYST_ANTICIPATION:
        trigger = _pick_first(
            signals,
            ("catalyst_proximate_earnings", "catalyst_proximate_macro"),
        )
        if trigger is None:
            return {}
        fills["trigger_signal"] = trigger

    elif skeleton_id == SkeletonId.REGIME_ALIGNED_CONTINUATION:
        trigger = _pick_first(
            signals, ("momentum_3w_positive", "momentum_3w_negative"),
        )
        regime = _pick_first(signals, ("macro_tailwind", "macro_headwind"))
        if trigger is None or regime is None:
            return {}
        fills["trigger_signal"] = trigger
        fills["regime_context"] = regime

    else:  # pragma: no cover — every skeleton handled above
        raise KeyError(f"no slot builder for {skeleton_id}")

    # invalidation_condition is filled by populator; for now record a
    # placeholder linkage so the spec validates. Replaced after populator
    # returns the trigger.
    return fills


_BUY_OUTCOME_BY_SKELETON: dict[SkeletonId, tuple[ThesisHorizon, ExpectedSignal]] = {
    SkeletonId.MOMENTUM_BREAKOUT: (ThesisHorizon.SWING, ExpectedSignal.PRICE_UP),
    SkeletonId.MEAN_REVERSION_PULLBACK: (ThesisHorizon.SHORT_TERM, ExpectedSignal.PRICE_UP),
    SkeletonId.BREADTH_THRUST_ENTRY: (ThesisHorizon.SWING, ExpectedSignal.PRICE_UP),
    SkeletonId.IV_COMPRESSION_SETUP: (ThesisHorizon.SWING, ExpectedSignal.VOLATILITY_EXPANSION),
    SkeletonId.CATALYST_ANTICIPATION: (ThesisHorizon.INTRADAY, ExpectedSignal.PRICE_UP),
    SkeletonId.REGIME_ALIGNED_CONTINUATION: (ThesisHorizon.SWING, ExpectedSignal.PRICE_UP),
}


def _thesis_for(
    skeleton_id: SkeletonId, side: str,
) -> ThesisStatement:
    horizon, buy_outcome = _BUY_OUTCOME_BY_SKELETON[skeleton_id]
    if side == "buy":
        return ThesisStatement(horizon=horizon, expected_signal=buy_outcome)
    # Sell-side mirror: flip PRICE_UP <-> PRICE_DOWN. Volatility outcomes
    # stay as-is (IV setups don't sell-by-symmetry).
    if buy_outcome == ExpectedSignal.PRICE_UP:
        flipped = ExpectedSignal.PRICE_DOWN
    elif buy_outcome == ExpectedSignal.PRICE_DOWN:
        flipped = ExpectedSignal.PRICE_UP
    else:
        flipped = buy_outcome
    return ThesisStatement(horizon=horizon, expected_signal=flipped)


def generate_envelope_detailed(ctx: DecisionContext) -> GenerationResult:
    """Same composition as generate_envelope, but always returns a
    GenerationResult — when envelope is None, a discrete `none_reason`
    is set. Use this when you need to record WHY envelope generation
    was skipped (e.g., observability telemetry).
    """
    feature_ctx = FeatureContext(
        factor_breakdown=ctx.factor_breakdown,
        regime_snapshot=ctx.regime_snapshot,
        catalyst_proximate_macro=ctx.catalyst_proximate_macro,
        catalyst_proximate_earnings=ctx.catalyst_proximate_earnings,
    )
    signals = extract_signals(feature_ctx)
    if len(signals) < MIN_SIGNALS_FOR_ENVELOPE:
        return GenerationResult(envelope=None, none_reason=SKIP_MIN_SIGNALS)

    skeleton = select_skeleton(
        side=ctx.side, signals=signals, asset_class=ctx.asset_class,
    )
    if skeleton is None:
        return GenerationResult(envelope=None, none_reason=SKIP_NO_SKELETON_MATCH)

    slot_fills = _slot_fills_for(skeleton, ctx.side, signals)
    if not slot_fills:
        return GenerationResult(envelope=None, none_reason=SKIP_EMPTY_SLOT_FILLS)

    invalidation = populate_invalidation(
        skeleton,
        EntryContext(
            fill_price=ctx.fill_price,
            suggested_stop_price=ctx.suggested_stop_price,
            realized_vol_20d=ctx.realized_vol_20d,
            side=ctx.side,
        ),
    )
    slot_fills["invalidation_condition"] = invalidation.condition_vocab

    markers = assign_markers(
        MarkerContext(
            side=ctx.side,
            skeleton_id=skeleton,
            active_signals=signals,
            factor_breakdown=ctx.factor_breakdown,
            regime_snapshot=ctx.regime_snapshot,
        )
    )

    thesis = _thesis_for(skeleton, ctx.side)

    envelope = build_envelope(
        skeleton_id=skeleton,
        slot_fills=slot_fills,
        invalidation=invalidation,
        thesis=thesis,
        uncertainty_markers=list(markers),
        generated_at=ctx.generated_at,
        source=ctx.source,
    )
    return GenerationResult(envelope=envelope, none_reason=None)


def generate_envelope(ctx: DecisionContext) -> Optional[ReasoningEnvelope]:
    """Backward-compatible wrapper returning envelope-or-None.

    Use generate_envelope_detailed if you need the none_reason.
    """
    return generate_envelope_detailed(ctx).envelope
