"""Unit tests: recommendation diagnostics pure functions."""

from __future__ import annotations

import json
from decimal import Decimal

from apps.api.src.domain.recommendations.diagnostics import (
    DEFAULT_BUY_THRESHOLD,
    analyze_recommendation,
    order_by_closest_to_buy,
    summarize_batch,
)


def _ev(factor: str, family: str, score: str, weight: str = "0.3",
        direction: str = "bullish", narrative: str = "") -> dict:
    return {
        "factor_key": factor,
        "family": family,
        "weight": weight,
        "score": score,
        "direction": direction,
        "narrative": narrative,
    }


def _rationale(
    composite: str = "0.10",
    adjusted: str | None = None,
    stale: bool = False,
    enough: bool = True,
    dampers: list | None = None,
    confidence_label: str = "Medium",
    family_scores: dict | None = None,
) -> str:
    data: dict = {
        "composite_score": composite,
        "stale_data": stale,
        "enough_data": enough,
        "confidence_label": confidence_label,
        "family_scores": family_scores or {"trend_momentum": "0.05"},
    }
    if adjusted is not None or dampers is not None:
        data["policy"] = {
            "adjusted_composite_score": adjusted if adjusted is not None else composite,
            "adjustments": dampers or [],
        }
    return json.dumps(data)


# ---------------------------------------------------------------------------
# analyze_recommendation — distance calc
# ---------------------------------------------------------------------------


def test_distance_uses_adjusted_composite() -> None:
    d = analyze_recommendation(
        recommendation_id="r1", asset_id="a1", symbol="AAA",
        action="Hold",
        rationale_json=_rationale(composite="0.20", adjusted="0.15"),
        conviction=Decimal("75"),
        generated_at_iso="2026-04-20T00:00:00+00:00",
        evidences=[],
    )
    # distance = 0.25 - 0.15 = 0.10 (not 0.25 - 0.20)
    assert d.distance_to_buy == Decimal("0.10")
    assert d.composite_score == Decimal("0.15")
    assert d.original_composite_score == Decimal("0.20")


def test_distance_zero_for_buy_rec() -> None:
    d = analyze_recommendation(
        recommendation_id="r2", asset_id="a2", symbol="BBB",
        action="Buy",
        rationale_json=_rationale(composite="0.40"),
        conviction=Decimal("85"),
        generated_at_iso=None, evidences=[],
    )
    assert d.distance_to_buy == Decimal("0")


def test_distance_none_when_stale() -> None:
    d = analyze_recommendation(
        recommendation_id="r3", asset_id="a3", symbol="CCC",
        action="Watch",
        rationale_json=_rationale(composite="0.10", stale=True),
        conviction=None, generated_at_iso=None, evidences=[],
    )
    assert d.distance_to_buy is None
    assert d.stale_data is True


def test_distance_none_when_not_enough_data() -> None:
    d = analyze_recommendation(
        recommendation_id="r4", asset_id="a4", symbol="DDD",
        action="Watch",
        rationale_json=_rationale(composite="0.30", enough=False),
        conviction=None, generated_at_iso=None, evidences=[],
    )
    assert d.distance_to_buy is None
    assert d.enough_data is False


def test_distance_none_when_composite_missing() -> None:
    raw = json.dumps({"enough_data": True, "stale_data": False})
    d = analyze_recommendation(
        recommendation_id="r5", asset_id="a5", symbol="EEE",
        action="Watch", rationale_json=raw,
        conviction=None, generated_at_iso=None, evidences=[],
    )
    assert d.distance_to_buy is None
    assert d.composite_score is None


# ---------------------------------------------------------------------------
# Contributor extraction
# ---------------------------------------------------------------------------


def test_top_positive_and_negative_contributors() -> None:
    evs = [
        _ev("trend_strength", "trend_momentum", "0.15"),
        _ev("sma_20_vs_50", "trend_momentum", "-0.08"),
        _ev("rsi_14", "volatility_risk", "-0.22"),
        _ev("price_vs_sma_long", "trend_momentum", "0.05"),
        _ev("max_drawdown", "volatility_risk", "-0.03"),
    ]
    d = analyze_recommendation(
        recommendation_id="r", asset_id="a", symbol="X",
        action="Hold", rationale_json=_rationale(composite="0.05"),
        conviction=Decimal("60"), generated_at_iso=None,
        evidences=evs,
    )
    pos_keys = [c.factor_key for c in d.top_positive]
    neg_keys = [c.factor_key for c in d.top_negative]
    # Positive ranked desc by score
    assert pos_keys == ["trend_strength", "price_vs_sma_long"]
    # Negative ranked asc by score (most negative first)
    assert neg_keys == ["rsi_14", "sma_20_vs_50", "max_drawdown"]


def test_contributor_parses_nested_summary_shape() -> None:
    # ORM-like payload where score is inside summary JSON string.
    evs = [{
        "factor_key": "rsi_14", "family": "volatility_risk",
        "weight": "0.3",
        "summary": json.dumps({"score": "0.11", "direction": "bullish",
                               "narrative": "RSI at 28 (oversold)"}),
    }]
    d = analyze_recommendation(
        recommendation_id="r", asset_id="a", symbol="X",
        action="Hold", rationale_json=_rationale(composite="0.00"),
        conviction=None, generated_at_iso=None,
        evidences=evs,
    )
    assert d.top_positive[0].factor_key == "rsi_14"
    assert d.top_positive[0].score == Decimal("0.11")


def test_contributor_skips_unscored_evidence() -> None:
    evs = [{"factor_key": "x", "family": "y", "weight": "0.1"}]  # no score
    d = analyze_recommendation(
        recommendation_id="r", asset_id="a", symbol="X",
        action="Hold", rationale_json=_rationale(),
        conviction=None, generated_at_iso=None, evidences=evs,
    )
    assert d.top_positive == []
    assert d.top_negative == []


# ---------------------------------------------------------------------------
# Damper flags
# ---------------------------------------------------------------------------


def test_dampers_extracted_from_policy() -> None:
    dampers = [{
        "rule": "high_volatility_damping",
        "factor": "0.7",
        "score_before": "0.30",
        "score_after": "0.21",
        "reason": "High volatility regime",
    }]
    d = analyze_recommendation(
        recommendation_id="r", asset_id="a", symbol="X",
        action="Hold",
        rationale_json=_rationale(composite="0.30", adjusted="0.21", dampers=dampers),
        conviction=None, generated_at_iso=None, evidences=[],
    )
    assert len(d.dampers) == 1
    assert d.dampers[0].rule == "high_volatility_damping"
    assert d.dampers[0].score_before == Decimal("0.30")
    assert d.dampers[0].score_after == Decimal("0.21")


# ---------------------------------------------------------------------------
# Ordering
# ---------------------------------------------------------------------------


def test_order_by_closest_to_buy() -> None:
    d1 = analyze_recommendation(
        recommendation_id="1", asset_id="a", symbol="FAR",
        action="Hold", rationale_json=_rationale(composite="-0.10"),
        conviction=None, generated_at_iso=None, evidences=[])
    d2 = analyze_recommendation(
        recommendation_id="2", asset_id="b", symbol="NEAR",
        action="Hold", rationale_json=_rationale(composite="0.20"),
        conviction=None, generated_at_iso=None, evidences=[])
    d3 = analyze_recommendation(
        recommendation_id="3", asset_id="c", symbol="STALE",
        action="Watch", rationale_json=_rationale(stale=True),
        conviction=None, generated_at_iso=None, evidences=[])
    d4 = analyze_recommendation(
        recommendation_id="4", asset_id="d", symbol="BUY",
        action="Buy", rationale_json=_rationale(composite="0.40"),
        conviction=None, generated_at_iso=None, evidences=[])

    ordered = order_by_closest_to_buy([d1, d2, d3, d4])
    assert [d.symbol for d in ordered] == ["BUY", "NEAR", "FAR", "STALE"]


def test_order_empty_returns_empty() -> None:
    assert order_by_closest_to_buy([]) == []


# ---------------------------------------------------------------------------
# Batch summary
# ---------------------------------------------------------------------------


def test_summary_action_distribution() -> None:
    ds = [
        analyze_recommendation(recommendation_id=str(i), asset_id=f"a{i}", symbol=f"S{i}",
            action=a, rationale_json=_rationale(composite="0.00"),
            conviction=None, generated_at_iso=None, evidences=[])
        for i, a in enumerate(["Buy", "Hold", "Hold", "Trim", "Watch"])
    ]
    s = summarize_batch(ds)
    assert s.action_distribution == {"Buy": 1, "Hold": 2, "Trim": 1, "Watch": 1}
    assert s.buys == 1
    assert s.total == 5


def test_summary_near_buy_counts() -> None:
    # Scores: 0.24 (dist 0.01), 0.20 (0.05), 0.14 (0.11), -0.10 (0.35)
    ds = [
        analyze_recommendation(recommendation_id=str(i), asset_id=f"a{i}", symbol=f"S{i}",
            action="Hold", rationale_json=_rationale(composite=c),
            conviction=None, generated_at_iso=None, evidences=[])
        for i, c in enumerate(["0.24", "0.20", "0.14", "-0.10"])
    ]
    s = summarize_batch(ds)
    # Tight 5%: 0.01, 0.05 → 2
    assert s.near_buy_tight == 2
    # Loose 10%: 0.01, 0.05 → 2 (0.11 is outside 10%)
    assert s.near_buy_loose == 2


def test_summary_damper_and_stale_counts() -> None:
    damper = [{"rule": "high_volatility_damping", "score_before": "0.30", "score_after": "0.21"}]
    ds = [
        analyze_recommendation(recommendation_id="1", asset_id="a", symbol="A",
            action="Hold",
            rationale_json=_rationale(composite="0.30", adjusted="0.21", dampers=damper),
            conviction=None, generated_at_iso=None, evidences=[]),
        analyze_recommendation(recommendation_id="2", asset_id="b", symbol="B",
            action="Watch", rationale_json=_rationale(stale=True),
            conviction=None, generated_at_iso=None, evidences=[]),
        analyze_recommendation(recommendation_id="3", asset_id="c", symbol="C",
            action="Watch", rationale_json=_rationale(enough=False),
            conviction=None, generated_at_iso=None, evidences=[]),
    ]
    s = summarize_batch(ds)
    assert s.dampers_applied == 1
    assert s.stale_count == 1
    assert s.insufficient_data_count == 1


def test_summary_score_distribution_buckets() -> None:
    ds = [
        analyze_recommendation(recommendation_id=str(i), asset_id=f"a{i}", symbol=f"S{i}",
            action="Hold", rationale_json=_rationale(composite=c),
            conviction=None, generated_at_iso=None, evidences=[])
        for i, c in enumerate(["-0.80", "-0.50", "-0.10", "0.10", "0.30", "0.70"])
    ]
    s = summarize_batch(ds)
    buckets = {b.label: b.count for b in s.score_distribution}
    assert buckets["<= -0.65"] == 1
    assert buckets["-0.65..-0.25"] == 1
    assert buckets["-0.25..0"] == 1
    assert buckets["0..0.25"] == 1
    assert buckets["0.25..0.65"] == 1
    assert buckets[">= 0.65"] == 1


def test_summary_empty_returns_zeroed_fields() -> None:
    s = summarize_batch([])
    assert s.total == 0
    assert s.buys == 0
    assert s.near_buy_tight == 0
    assert s.near_buy_loose == 0
    assert s.max_composite is None
    assert s.min_composite is None
    assert s.median_composite is None
    assert all(b.count == 0 for b in s.score_distribution)
    assert s.buy_threshold == DEFAULT_BUY_THRESHOLD


def test_summary_min_max_median() -> None:
    ds = [
        analyze_recommendation(recommendation_id=str(i), asset_id=f"a{i}", symbol=f"S{i}",
            action="Hold", rationale_json=_rationale(composite=c),
            conviction=None, generated_at_iso=None, evidences=[])
        for i, c in enumerate(["-0.20", "0.10", "0.30", "0.40", "0.50"])
    ]
    s = summarize_batch(ds)
    assert s.max_composite == Decimal("0.50")
    assert s.min_composite == Decimal("-0.20")
    assert s.median_composite == Decimal("0.30")


def test_summary_custom_threshold_changes_near_counts() -> None:
    # Composite 0.10 → distance 0.05 vs threshold 0.15
    ds = [
        analyze_recommendation(recommendation_id="1", asset_id="a", symbol="A",
            action="Hold", rationale_json=_rationale(composite="0.10"),
            conviction=None, generated_at_iso=None, evidences=[],
            buy_threshold=Decimal("0.15")),
    ]
    s = summarize_batch(ds, buy_threshold=Decimal("0.15"))
    assert s.near_buy_tight == 1
