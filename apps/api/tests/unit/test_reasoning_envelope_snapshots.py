"""Phase L D4.8 — pinned-hash snapshot tests for envelope determinism.

Each fixture is a frozen DecisionContext + the envelope_hash we expect
it to produce. If the hash changes for ANY reason (skeleton template,
slot mapping, marker calibration, vocabulary labels) this test fails
and forces a deliberate update — protecting Phase L's determinism
guarantee from accidental drift.

If you change a skeleton template / mapping intentionally, regenerate
the expected hashes by running this test, capturing the new hash from
the failure, and updating EXPECTED_HASHES below in the same PR.
"""

from __future__ import annotations

import datetime as dt
import sys
from decimal import Decimal

from apps.api.src.reasoning.envelope import EnvelopeSource
from apps.api.src.reasoning.generator import DecisionContext, generate_envelope
from apps.api.src.reasoning.skeletons import SkeletonId


# Frozen timestamp shared by all fixtures so envelope_hash is invariant
# across CI runs.
GEN = dt.datetime(2026, 1, 1, 12, 0, tzinfo=dt.timezone.utc)


# Fixtures cover every skeleton REACHABLE from today's substrate:
#   * REGIME_ALIGNED_CONTINUATION (buy + sell sides)
#   * MEAN_REVERSION_PULLBACK
#   * IV_COMPRESSION_SETUP (options class only)
#   * CATALYST_ANTICIPATION (after D5.2 catalyst substrate wiring)
#   * MOMENTUM_BREAKOUT (after D5.2: momentum + iv_compression on equity)
#
# Skeleton STILL NOT reachable today:
#   * BREADTH_THRUST_ENTRY — no breadth substrate exists. Pinned hash
#     will be added when D5.1 unblocks (currently refused — no
#     real breadth data anywhere).
FIXTURES: dict[str, tuple[DecisionContext, str | None]] = {
    "regime_aligned_continuation_equity_buy": (
        DecisionContext(
            side="buy", asset_class="equity",
            factor_breakdown={
                "values": {"trend_strength_20d": "0.45"},
                "missing_components": [],
                "confidence_label": "Medium",
            },
            regime_snapshot={
                "vol_regime": "medium",
                "market_trend": "uptrend",
                "sma50_over_sma200": True,
            },
            fill_price=Decimal("75.00"),
            source=EnvelopeSource.LIVE,
            generated_at=GEN,
        ),
        SkeletonId.REGIME_ALIGNED_CONTINUATION.value,
    ),
    "mean_reversion_pullback_equity_buy": (
        DecisionContext(
            side="buy", asset_class="equity",
            factor_breakdown={
                "values": {"trend_strength_20d": "-0.40"},
                "missing_components": [],
                "confidence_label": "Medium",
            },
            regime_snapshot={
                "vol_regime": "medium",
                "market_trend": "uptrend",
                "sma50_over_sma200": True,
            },
            fill_price=Decimal("60.00"),
            source=EnvelopeSource.LIVE,
            generated_at=GEN,
        ),
        SkeletonId.MEAN_REVERSION_PULLBACK.value,
    ),
    "iv_compression_options_buy": (
        DecisionContext(
            side="buy", asset_class="options",
            factor_breakdown={
                "values": {"trend_strength_20d": "0.30"},
                "missing_components": [],
                "confidence_label": "Medium",
            },
            regime_snapshot={
                "vol_regime": "low",
                "market_trend": "uptrend",
                "sma50_over_sma200": True,
            },
            realized_vol_20d=Decimal("0.095"),
            source=EnvelopeSource.LIVE,
            generated_at=GEN,
        ),
        SkeletonId.IV_COMPRESSION_SETUP.value,
    ),
    "regime_aligned_equity_sell": (
        DecisionContext(
            side="sell", asset_class="equity",
            factor_breakdown={
                "values": {"trend_strength_20d": "-0.35"},
                "missing_components": [],
                "confidence_label": "High",
            },
            regime_snapshot={
                "vol_regime": "medium",
                "market_trend": "downtrend",
                "sma50_over_sma200": False,
            },
            source=EnvelopeSource.LIVE,
            generated_at=GEN,
        ),
        SkeletonId.REGIME_ALIGNED_CONTINUATION.value,
    ),
    "catalyst_anticipation_macro_equity_buy": (
        DecisionContext(
            side="buy", asset_class="equity",
            factor_breakdown={
                "values": {"trend_strength_20d": "0.30"},
                "missing_components": [],
                "confidence_label": "Medium",
            },
            regime_snapshot={
                "market_trend": "uptrend",
                "sma50_over_sma200": True,
            },
            catalyst_proximate_macro=True,
            source=EnvelopeSource.LIVE,
            generated_at=GEN,
        ),
        SkeletonId.CATALYST_ANTICIPATION.value,
    ),
    "catalyst_anticipation_earnings_equity_buy": (
        DecisionContext(
            side="buy", asset_class="equity",
            factor_breakdown={
                "values": {"trend_strength_20d": "0.30"},
                "missing_components": [],
                "confidence_label": "Medium",
            },
            regime_snapshot={
                "market_trend": "uptrend",
                "sma50_over_sma200": True,
            },
            catalyst_proximate_earnings=True,
            source=EnvelopeSource.LIVE,
            generated_at=GEN,
        ),
        SkeletonId.CATALYST_ANTICIPATION.value,
    ),
    "momentum_breakout_equity_with_iv_compression": (
        DecisionContext(
            side="buy", asset_class="equity",
            factor_breakdown={
                "values": {"trend_strength_20d": "0.30"},
                "missing_components": [],
                "confidence_label": "Medium",
            },
            regime_snapshot={
                "vol_regime": "low",
                "market_trend": "sideways",
            },
            source=EnvelopeSource.LIVE,
            generated_at=GEN,
        ),
        SkeletonId.MOMENTUM_BREAKOUT.value,
    ),
    "honest_absence_empty_context": (
        DecisionContext(
            side="buy", asset_class="equity",
            source=EnvelopeSource.LIVE,
            generated_at=GEN,
        ),
        None,  # expect None envelope
    ),
    "honest_absence_single_signal": (
        DecisionContext(
            side="buy", asset_class="equity",
            factor_breakdown={
                "values": {"trend_strength_20d": "0.50"},
            },
            source=EnvelopeSource.LIVE,
            generated_at=GEN,
        ),
        None,  # only momentum fires, < MIN_SIGNALS_FOR_ENVELOPE
    ),
}


# Pinned envelope_hash values for each non-None fixture. Update
# deliberately when the generator output legitimately changes.
EXPECTED_HASHES: dict[str, str] = {
    "regime_aligned_continuation_equity_buy":
        "22121ef8c7b9e8345d2aef6e4ed041062cc8eecbb502175c29dc16f5ef145c8a",
    "mean_reversion_pullback_equity_buy":
        "bf2dacffcf37f7e1f2b5da1b02ed105e098f72315a9579a862f173678c933485",
    "iv_compression_options_buy":
        "418def596c80c36c9bb2e4a6ba4a12c42d039ba85f0bf4e105fbe1843c1c8860",
    "regime_aligned_equity_sell":
        "655b6dd9a7470db473be7e84210cdce76f8d2fe647285813ade694e757292923",
    "catalyst_anticipation_macro_equity_buy":
        "f54ab60935e4e392879e65365141ac27485857764c15fdf3ebbb070727e387f1",
    "catalyst_anticipation_earnings_equity_buy":
        "7c3bc7826f9baa65ace6ff0d3ed0733d70b6f5fce6530d0cdf81e1f0b50fd750",
    "momentum_breakout_equity_with_iv_compression":
        "97dfb0216608b7ad1df2038c116813f55ca4b8cccd98bbbbfe57d435789c11fc",
}


def check_fixture(name: str) -> tuple[bool, str]:
    """Returns (passed, message). Used by both __main__ runner and any
    future pytest harness."""
    ctx, expected_skeleton = FIXTURES[name]
    env = generate_envelope(ctx)
    if expected_skeleton is None:
        if env is not None:
            return False, (
                f"expected honest-absence None, got skeleton="
                f"{env.skeleton_id.value}"
            )
        return True, "honest absence (None)"

    if env is None:
        return False, "expected envelope, got None"
    if env.skeleton_id.value != expected_skeleton:
        return False, (
            f"expected skeleton {expected_skeleton}, "
            f"got {env.skeleton_id.value}"
        )

    expected_hash = EXPECTED_HASHES.get(name)
    if expected_hash is None:
        return False, (
            f"no pinned hash in EXPECTED_HASHES — actual hash is "
            f"{env.envelope_hash()!r}; pin it deliberately."
        )
    actual_hash = env.envelope_hash()
    if actual_hash != expected_hash:
        return False, (
            f"DETERMINISM DRIFT: expected {expected_hash}, "
            f"got {actual_hash}"
        )
    return True, f"hash={actual_hash[:16]}..."


def main() -> int:
    n_pass = 0
    n_fail = 0
    for name in FIXTURES:
        ok, msg = check_fixture(name)
        prefix = "PASS" if ok else "FAIL"
        print(f"  [{prefix}] {name}: {msg}")
        if ok:
            n_pass += 1
        else:
            n_fail += 1
    print()
    print(f"D4.8 snapshot tests: {n_pass} pass / {n_fail} fail "
          f"({len(FIXTURES)} total)")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
