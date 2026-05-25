"""Phase L skeleton selector — signal-set to SkeletonId resolver.

Priority-ordered deterministic rule list. The first rule whose
preconditions are all satisfied wins. If no rule matches, returns
None — Decision Detail surfaces incomplete_lifecycle, never falls
back to a generic skeleton.

Rules are intentionally restrictive: a single canonical signal set
can fire at most one skeleton. The selector is a pure function of
(side, active_signals).

Rule design:
  * Rules tied to options-specific signals (iv_*) require options
    context to make sense. Equity-only callers will not see them.
  * Counter-trend setups (mean_reversion_pullback) require a regime
    signal to be present so the thesis has a backdrop.
  * The breadth_thrust_entry rule exists in the catalog but cannot
    fire today (breadth signals unimplemented in extractor). When
    breadth substrate ships, no selector code changes are needed —
    the rule activates automatically.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from apps.api.src.reasoning.skeletons import SkeletonId


@dataclass(frozen=True)
class SkeletonRule:
    skeleton_id: SkeletonId
    predicate: Callable[[str, frozenset[str], str], bool]
    description: str  # short, internal — for logging only


# Helper predicates — keep small and named so rules read declaratively.
def _has(s: frozenset[str], *names: str) -> bool:
    return all(n in s for n in names)


def _any(s: frozenset[str], *names: str) -> bool:
    return any(n in s for n in names)


# Side semantics: "buy" or "sell". A sell decision uses skeletons that
# describe exit reasoning differently from entry reasoning — for MVP
# we share skeletons across sides since the slot vocabulary describes
# the same shape. Future days may diverge.
RULES: tuple[SkeletonRule, ...] = (
    # Catalyst skeleton — highest priority because catalyst-proximate
    # framing dominates the trade narrative when a known event is near.
    SkeletonRule(
        skeleton_id=SkeletonId.CATALYST_ANTICIPATION,
        predicate=lambda side, sigs, ac: _any(
            sigs, "catalyst_proximate_earnings", "catalyst_proximate_macro",
        ),
        description="catalyst-near setup",
    ),
    # IV compression — distinct options structural setup. ONLY fires
    # for options-class trades. For equity trades the iv_compression
    # signal is informational; it does not drive skeleton selection.
    SkeletonRule(
        skeleton_id=SkeletonId.IV_COMPRESSION_SETUP,
        predicate=lambda side, sigs, ac: (
            ac == "options"
            and "iv_compression" in sigs
            and "iv_expansion" not in sigs
        ),
        description="IV-compressed options setup",
    ),
    # Counter-trend mean-reversion — only valid when there's a
    # supportive macro backdrop justifying buying weakness.
    SkeletonRule(
        skeleton_id=SkeletonId.MEAN_REVERSION_PULLBACK,
        predicate=lambda side, sigs, ac: (
            side == "buy"
            and "momentum_3w_negative" in sigs
            and "macro_tailwind" in sigs
        ),
        description="pullback inside supportive regime",
    ),
    # Regime-aligned continuation — both regime and momentum agree.
    SkeletonRule(
        skeleton_id=SkeletonId.REGIME_ALIGNED_CONTINUATION,
        predicate=lambda side, sigs, ac: (
            (side == "buy" and _has(sigs, "macro_tailwind", "momentum_3w_positive"))
            or
            (side == "sell" and _has(sigs, "macro_headwind", "momentum_3w_negative"))
        ),
        description="regime + momentum alignment",
    ),
    # Breadth thrust — needs breadth signal. Reserved; cannot fire until
    # breadth substrate lands. Kept here so the rule order is stable
    # when breadth comes online.
    SkeletonRule(
        skeleton_id=SkeletonId.BREADTH_THRUST_ENTRY,
        predicate=lambda side, sigs, ac: (
            side == "buy"
            and "breadth_broadening" in sigs
            and "volume_confirmation" in sigs
        ),
        description="breadth thrust w/ volume",
    ),
    # Plain momentum breakout — buy when momentum-positive, sell when
    # momentum-negative, regime not required.
    SkeletonRule(
        skeleton_id=SkeletonId.MOMENTUM_BREAKOUT,
        predicate=lambda side, sigs, ac: (
            (side == "buy" and "momentum_3w_positive" in sigs)
            or
            (side == "sell" and "momentum_3w_negative" in sigs)
        ),
        description="momentum breakout (default)",
    ),
)


_ALLOWED_ASSET_CLASSES = frozenset({"equity", "options"})


def select_skeleton(
    *, side: str, signals: frozenset[str], asset_class: str = "equity",
) -> Optional[SkeletonId]:
    """Return the highest-priority skeleton whose predicate fires.

    None ⇒ no skeleton matches; the caller must NOT fall back to a
    generic envelope.
    """
    if side not in {"buy", "sell"}:
        raise ValueError(f"side must be 'buy' or 'sell', got {side!r}")
    if asset_class not in _ALLOWED_ASSET_CLASSES:
        raise ValueError(
            f"asset_class must be one of {sorted(_ALLOWED_ASSET_CLASSES)}, "
            f"got {asset_class!r}"
        )
    for rule in RULES:
        if rule.predicate(side, signals, asset_class):
            return rule.skeleton_id
    return None
