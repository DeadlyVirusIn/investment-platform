"""Unit tests for confidence × regime cross-tab + insight flags."""

from __future__ import annotations

from decimal import Decimal

from apps.api.src.domain.features.regime_classifier import (
    DD_REGIMES,
    TREND_REGIMES,
    VOL_REGIMES,
)
from apps.api.src.domain.performance.report import (
    CONFIDENCE_BUCKETS,
    OutcomeRecord,
    compute_confidence_buckets,
    compute_confidence_regime_matrix,
    compute_insights,
    compute_per_drawdown_regime,
    compute_per_trend_regime,
    compute_per_volatility_regime,
    compute_report,
)


def _rec(
    conf: str | None = "50",
    ret: str | None = "0.01",
    label: int | None = 1,
    trend: str | None = None,
    vol: str | None = None,
    dd: str | None = None,
) -> OutcomeRecord:
    return OutcomeRecord(
        generated_at_iso="2026-01-01T00:00:00+00:00",
        symbol="X", asset_id="x1",
        confidence=Decimal(conf) if conf is not None else None,
        return_value=Decimal(ret) if ret is not None else None,
        label=label,
        trend_regime=trend, volatility_regime=vol, drawdown_regime=dd,
    )


# ---------------------------------------------------------------------------
# Cross-tab shape
# ---------------------------------------------------------------------------


def test_matrix_emits_all_cells_deterministic_order() -> None:
    matrix = compute_confidence_regime_matrix([], "trend_regime", TREND_REGIMES)
    # 4 confidence buckets × (3 trend states + "unknown") = 16 rows
    assert len(matrix) == 16
    # Confidence outer, regime inner; first 4 rows are all "Low (0-30)"
    assert all(row["confidence_bucket"] == "Low (0-30)" for row in matrix[:4])
    # Within each confidence bucket: regime order = tuple + "unknown"
    assert matrix[0]["regime"] == "uptrend"
    assert matrix[1]["regime"] == "downtrend"
    assert matrix[2]["regime"] == "sideways"
    assert matrix[3]["regime"] == "unknown"
    # Full confidence ordering preserved
    confs = [row["confidence_bucket"] for row in matrix]
    assert confs[:4] == ["Low (0-30)"] * 4
    assert confs[4:8] == ["Medium (30-60)"] * 4
    assert confs[8:12] == ["High (60-100)"] * 4
    assert confs[12:] == ["Unknown"] * 4


def test_matrix_empty_cells_null_metrics() -> None:
    matrix = compute_confidence_regime_matrix([], "trend_regime", TREND_REGIMES)
    for row in matrix:
        assert row["count"] == 0
        assert row["hit_rate"] is None
        assert row["expectancy"] is None
        assert row["median_return"] is None


def test_matrix_correctly_groups_records() -> None:
    recs = [
        _rec(conf="75", label=1, ret="0.10", trend="uptrend"),
        _rec(conf="70", label=1, ret="0.05", trend="uptrend"),
        _rec(conf="75", label=-1, ret="-0.03", trend="downtrend"),
        _rec(conf="20", label=-1, ret="-0.05", trend="downtrend"),
    ]
    matrix = compute_confidence_regime_matrix(recs, "trend_regime", TREND_REGIMES)
    by_key = {(r["confidence_bucket"], r["regime"]): r for r in matrix}
    high_up = by_key[("High (60-100)", "uptrend")]
    assert high_up["count"] == 2
    assert Decimal(high_up["hit_rate"]) == Decimal("1")
    high_down = by_key[("High (60-100)", "downtrend")]
    assert high_down["count"] == 1
    assert Decimal(high_down["hit_rate"]) == Decimal("0")
    low_down = by_key[("Low (0-30)", "downtrend")]
    assert low_down["count"] == 1
    # Empty cells remain empty
    low_up = by_key[("Low (0-30)", "uptrend")]
    assert low_up["count"] == 0


def test_matrix_counts_all_three_regime_attrs() -> None:
    recs = [_rec(trend="sideways", vol="medium", dd="mild")]
    mt = compute_confidence_regime_matrix(recs, "trend_regime", TREND_REGIMES)
    mv = compute_confidence_regime_matrix(recs, "volatility_regime", VOL_REGIMES)
    md = compute_confidence_regime_matrix(recs, "drawdown_regime", DD_REGIMES)
    # 1 record counted once per dimension
    assert sum(row["count"] for row in mt) == 1
    assert sum(row["count"] for row in mv) == 1
    assert sum(row["count"] for row in md) == 1


def test_matrix_missing_regime_fall_to_unknown() -> None:
    recs = [_rec(conf="80", trend=None), _rec(conf="80", trend=None)]
    matrix = compute_confidence_regime_matrix(recs, "trend_regime", TREND_REGIMES)
    by_key = {(r["confidence_bucket"], r["regime"]): r for r in matrix}
    cell = by_key[("High (60-100)", "unknown")]
    assert cell["count"] == 2


# ---------------------------------------------------------------------------
# Insights — confidence inversion
# ---------------------------------------------------------------------------


def _build_conf_buckets(low_n: int, low_hr: str, high_n: int, high_hr: str) -> list:
    return [
        {"bucket": "Low (0-30)", "count": low_n, "hit_rate": Decimal(low_hr)},
        {"bucket": "Medium (30-60)", "count": 0, "hit_rate": None},
        {"bucket": "High (60-100)", "count": high_n, "hit_rate": Decimal(high_hr)},
        {"bucket": "Unknown", "count": 0, "hit_rate": None},
    ]


def test_confidence_inversion_detected_when_high_below_low() -> None:
    buckets = _build_conf_buckets(low_n=10, low_hr="0.7", high_n=10, high_hr="0.4")
    insights = compute_insights(buckets, {})
    inv = insights["confidence_inversion"]
    assert len(inv) == 1
    assert inv[0]["higher_bucket"] == "High (60-100)"
    assert inv[0]["lower_bucket"] == "Low (0-30)"
    assert inv[0]["spread"] == Decimal("0.3")


def test_confidence_inversion_not_detected_on_low_samples() -> None:
    buckets = _build_conf_buckets(low_n=3, low_hr="0.7", high_n=3, high_hr="0.4")
    insights = compute_insights(buckets, {})
    assert insights["confidence_inversion"] == []


def test_confidence_inversion_not_triggered_when_high_above_low() -> None:
    buckets = _build_conf_buckets(low_n=10, low_hr="0.3", high_n=10, high_hr="0.7")
    insights = compute_insights(buckets, {})
    assert insights["confidence_inversion"] == []


# ---------------------------------------------------------------------------
# Insights — regime sensitivity
# ---------------------------------------------------------------------------


def test_regime_sensitivity_detected_when_spread_over_20pct() -> None:
    breakdowns = {
        "trend": [
            {"regime": "uptrend", "count": 10, "hit_rate": Decimal("0.8")},
            {"regime": "downtrend", "count": 10, "hit_rate": Decimal("0.2")},
            {"regime": "sideways", "count": 10, "hit_rate": Decimal("0.5")},
            {"regime": "unknown", "count": 0, "hit_rate": None},
        ],
        "volatility": [],
        "drawdown": [],
    }
    insights = compute_insights([], breakdowns)
    sens = insights["regime_sensitivity"]
    assert len(sens) == 1
    assert sens[0]["dimension"] == "trend"
    assert sens[0]["best_regime"] == "uptrend"
    assert sens[0]["worst_regime"] == "downtrend"
    assert sens[0]["spread"] == Decimal("0.6")


def test_regime_sensitivity_none_when_spread_below_threshold() -> None:
    breakdowns = {
        "trend": [
            {"regime": "uptrend", "count": 10, "hit_rate": Decimal("0.55")},
            {"regime": "downtrend", "count": 10, "hit_rate": Decimal("0.50")},
            {"regime": "sideways", "count": 10, "hit_rate": Decimal("0.45")},
        ],
        "volatility": [],
        "drawdown": [],
    }
    insights = compute_insights([], breakdowns)
    assert insights["regime_sensitivity"] == []


def test_regime_sensitivity_ignores_low_sample_buckets() -> None:
    # Only one eligible regime → no sensitivity computed
    breakdowns = {
        "trend": [
            {"regime": "uptrend", "count": 10, "hit_rate": Decimal("0.8")},
            {"regime": "downtrend", "count": 2, "hit_rate": Decimal("0.0")},
            {"regime": "sideways", "count": 0, "hit_rate": None},
        ],
        "volatility": [],
        "drawdown": [],
    }
    insights = compute_insights([], breakdowns)
    assert insights["regime_sensitivity"] == []


# ---------------------------------------------------------------------------
# Insights — low-sample warnings
# ---------------------------------------------------------------------------


def test_low_sample_warnings_emitted_for_small_buckets() -> None:
    conf_buckets = [
        {"bucket": "Low (0-30)", "count": 3, "hit_rate": Decimal("0")},
        {"bucket": "Medium (30-60)", "count": 10, "hit_rate": Decimal("0.5")},
        {"bucket": "High (60-100)", "count": 0, "hit_rate": None},
        {"bucket": "Unknown", "count": 0, "hit_rate": None},
    ]
    breakdowns = {
        "trend": [
            {"regime": "uptrend", "count": 2, "hit_rate": Decimal("0.5")},
            {"regime": "downtrend", "count": 10, "hit_rate": Decimal("0.5")},
            {"regime": "sideways", "count": 0, "hit_rate": None},
        ],
        "volatility": [],
        "drawdown": [],
    }
    insights = compute_insights(conf_buckets, breakdowns)
    warnings = insights["low_sample_warnings"]
    labels = {(w["dimension"], w["label"], w["count"]) for w in warnings}
    assert ("confidence", "Low (0-30)", 3) in labels
    assert ("regime.trend", "uptrend", 2) in labels
    # Zero-count buckets are NOT warnings (reported via count=0 already)
    assert not any(w["count"] == 0 for w in warnings)


# ---------------------------------------------------------------------------
# Full report includes matrix + insights
# ---------------------------------------------------------------------------


def test_report_includes_matrix_and_insights() -> None:
    recs = [_rec(trend="uptrend"), _rec(trend="downtrend")]
    r = compute_report(recs, annualization=12)
    t2 = r["recommendation_metrics"]["tier_2_conditional"]
    assert "confidence_regime_matrix" in t2
    assert set(t2["confidence_regime_matrix"].keys()) == {"trend", "volatility", "drawdown"}
    assert "insights" in t2
    assert set(t2["insights"].keys()) == {
        "confidence_inversion", "regime_sensitivity", "low_sample_warnings"
    }


def test_report_matrix_16_rows_per_dimension() -> None:
    r = compute_report([], annualization=12)
    matrix = r["recommendation_metrics"]["tier_2_conditional"]["confidence_regime_matrix"]
    for dim in ("trend", "volatility", "drawdown"):
        assert len(matrix[dim]) == 16
