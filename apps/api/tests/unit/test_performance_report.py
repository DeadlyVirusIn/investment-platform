"""Unit tests for tiered performance report (confidence calibration, per-asset)."""

from __future__ import annotations

from decimal import Decimal

from apps.api.src.domain.performance.report import (
    EXPERIMENTAL_WARNING,
    OutcomeRecord,
    _bucket_for_confidence,
    compute_confidence_buckets,
    compute_core_metrics,
    compute_experimental_metrics,
    compute_per_asset,
    compute_per_month,
    compute_report,
)


def _rec(
    symbol: str = "X",
    asset_id: str = "x1",
    conf: str | None = "50",
    ret: str | None = "0.01",
    label: int | None = 1,
    iso: str = "2026-01-01T00:00:00+00:00",
) -> OutcomeRecord:
    return OutcomeRecord(
        generated_at_iso=iso,
        symbol=symbol,
        asset_id=asset_id,
        confidence=Decimal(conf) if conf is not None else None,
        return_value=Decimal(ret) if ret is not None else None,
        label=label,
    )


# ---------------------------------------------------------------------------
# Core (Tier 1)
# ---------------------------------------------------------------------------


def test_hit_rate_vs_win_rate() -> None:
    recs = [
        _rec(label=1, ret="0.05"),
        _rec(label=1, ret="0.03"),
        _rec(label=-1, ret="-0.02"),
        _rec(label=0, ret="0"),
    ]
    core = compute_core_metrics(recs)
    # hit_rate = 2 / (2+1) = 0.667 (decisive trades only)
    assert core["hit_rate"] == Decimal("2") / Decimal("3")
    # win_rate = 2 / 4 = 0.5 (includes neutral)
    assert core["win_rate"] == Decimal("0.5")


def test_median_return() -> None:
    recs = [
        _rec(label=1, ret="0.10"),
        _rec(label=1, ret="0.05"),
        _rec(label=-1, ret="-0.02"),
    ]
    core = compute_core_metrics(recs)
    assert core["median_return"] == Decimal("0.05")


def test_core_unlabeled_records_excluded() -> None:
    recs = [
        _rec(label=1, ret="0.05"),
        _rec(label=None, ret="0.10"),  # excluded
        _rec(label=1, ret=None),        # excluded
    ]
    core = compute_core_metrics(recs)
    assert core["total_trades"] == 1


def test_core_empty_returns_safe_zeros() -> None:
    core = compute_core_metrics([])
    assert core["total_trades"] == 0
    assert core["hit_rate"] is None
    assert core["win_rate"] is None
    assert core["expectancy"] is None
    assert core["avg_return"] is None
    assert core["median_return"] is None
    assert core["profit_factor"] is None


# ---------------------------------------------------------------------------
# Confidence buckets
# ---------------------------------------------------------------------------


def test_bucket_for_confidence_boundaries() -> None:
    assert _bucket_for_confidence(None) == "Unknown"
    assert _bucket_for_confidence(Decimal("0")) == "Low (0-30)"
    assert _bucket_for_confidence(Decimal("29.99")) == "Low (0-30)"
    assert _bucket_for_confidence(Decimal("30")) == "Medium (30-60)"
    assert _bucket_for_confidence(Decimal("59.99")) == "Medium (30-60)"
    assert _bucket_for_confidence(Decimal("60")) == "High (60-100)"
    assert _bucket_for_confidence(Decimal("100")) == "High (60-100)"


def test_confidence_calibration_all_four_buckets_present() -> None:
    recs = [
        _rec(conf="10", label=1, ret="0.05"),     # Low
        _rec(conf="45", label=1, ret="0.03"),     # Medium
        _rec(conf="45", label=-1, ret="-0.02"),   # Medium
        _rec(conf="80", label=1, ret="0.08"),     # High
        _rec(conf=None, label=1, ret="0.01"),     # Unknown
    ]
    buckets = compute_confidence_buckets(recs)
    by_name = {b["bucket"]: b for b in buckets}
    # Always emits all 4 buckets
    assert set(by_name.keys()) == {"Low (0-30)", "Medium (30-60)", "High (60-100)", "Unknown"}
    assert by_name["Low (0-30)"]["count"] == 1
    assert by_name["Medium (30-60)"]["count"] == 2
    assert by_name["High (60-100)"]["count"] == 1
    assert by_name["Unknown"]["count"] == 1
    # Medium: 1 win, 1 loss → hit_rate=0.5
    assert by_name["Medium (30-60)"]["hit_rate"] == Decimal("0.5")
    # High: 1 win, 0 loss → hit_rate=1.0
    assert by_name["High (60-100)"]["hit_rate"] == Decimal("1")


def test_confidence_bucket_empty_has_none_metrics() -> None:
    recs = [_rec(conf="80", label=1, ret="0.05")]
    buckets = compute_confidence_buckets(recs)
    low = next(b for b in buckets if b["bucket"] == "Low (0-30)")
    assert low["count"] == 0
    assert low["hit_rate"] is None
    assert low["expectancy"] is None
    assert low["median_return"] is None


# ---------------------------------------------------------------------------
# Per-asset
# ---------------------------------------------------------------------------


def test_per_asset_groups_by_symbol() -> None:
    recs = [
        _rec(symbol="AAA", asset_id="a1", label=1, ret="0.05"),
        _rec(symbol="AAA", asset_id="a1", label=-1, ret="-0.03"),
        _rec(symbol="BBB", asset_id="b1", label=1, ret="0.08"),
    ]
    per = compute_per_asset(recs)
    by_sym = {p["symbol"]: p for p in per}
    assert by_sym["AAA"]["count"] == 2
    assert by_sym["AAA"]["wins"] == 1
    assert by_sym["AAA"]["losses"] == 1
    assert by_sym["AAA"]["hit_rate"] == Decimal("0.5")
    assert by_sym["BBB"]["count"] == 1
    assert by_sym["BBB"]["hit_rate"] == Decimal("1")
    # Deterministic alphabetical order
    assert [p["symbol"] for p in per] == ["AAA", "BBB"]


def test_per_asset_empty() -> None:
    assert compute_per_asset([]) == []


# ---------------------------------------------------------------------------
# Per-month
# ---------------------------------------------------------------------------


def test_per_month_groups_by_year_month() -> None:
    recs = [
        _rec(label=1, ret="0.05", iso="2026-01-05T00:00:00+00:00"),
        _rec(label=-1, ret="-0.02", iso="2026-01-20T00:00:00+00:00"),
        _rec(label=1, ret="0.03", iso="2026-02-10T00:00:00+00:00"),
    ]
    per = compute_per_month(recs)
    months = [p["month"] for p in per]
    assert months == ["2026-01", "2026-02"]
    jan = next(p for p in per if p["month"] == "2026-01")
    assert jan["count"] == 2
    assert jan["hit_rate"] == Decimal("0.5")


# ---------------------------------------------------------------------------
# Experimental warning
# ---------------------------------------------------------------------------


def test_experimental_metrics_has_warning_and_keys() -> None:
    recs = [
        _rec(label=1, ret="0.05"),
        _rec(label=-1, ret="-0.03"),
        _rec(label=1, ret="0.04"),
    ]
    exp = compute_experimental_metrics(recs, annualization=12)
    assert exp["__warning__"] == EXPERIMENTAL_WARNING
    assert exp["annualization"] == 12
    assert "sharpe_ratio" in exp
    assert "sortino_ratio" in exp
    assert "calmar_ratio" in exp
    assert "max_drawdown" in exp
    assert "max_drawdown_duration" in exp


# ---------------------------------------------------------------------------
# Full report shape
# ---------------------------------------------------------------------------


def test_report_shape_has_three_tiers() -> None:
    recs = [_rec(label=1, ret="0.05"), _rec(label=-1, ret="-0.02")]
    r = compute_report(recs, annualization=12)
    assert "recommendation_metrics" in r
    assert "experimental_metrics" in r
    rec_m = r["recommendation_metrics"]
    assert "tier_1_core" in rec_m
    assert "tier_2_conditional" in rec_m
    t2 = rec_m["tier_2_conditional"]
    assert "confidence_buckets" in t2
    assert "per_asset" in t2
    assert "per_month" in t2
