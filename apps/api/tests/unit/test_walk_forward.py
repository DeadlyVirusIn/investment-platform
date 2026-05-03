"""Unit tests: walk-forward splitter, aggregation, WFE, classification."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from apps.api.src.domain.backtest.walk_forward import (
    DEFAULT_STEP_DAYS,
    DEFAULT_TEST_DAYS,
    DEFAULT_TRAIN_DAYS,
    OutcomeRow,
    aggregate_window,
    build_splits,
    classify_stability,
    compute_wfe,
    run_walk_forward,
)

BASE = dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc)


def _row(days_offset: int, label: int | None, ret: str | None, sig: str = "default") -> OutcomeRow:
    return OutcomeRow(
        recommendation_id=f"r-{days_offset}",
        asset_id="a-1",
        generated_at=BASE + dt.timedelta(days=days_offset),
        barrier_label=label,
        realized_return=Decimal(ret) if ret is not None else None,
        signal_type=sig,
    )


# ---------------------------------------------------------------------------
# build_splits
# ---------------------------------------------------------------------------


def test_build_splits_single_full_window() -> None:
    first = BASE
    last = BASE + dt.timedelta(days=DEFAULT_TRAIN_DAYS + DEFAULT_TEST_DAYS)
    splits = build_splits(first, last)
    assert len(splits) == 1
    w = splits[0]
    assert w.train_start == first
    assert (w.train_end - w.train_start).days == DEFAULT_TRAIN_DAYS
    assert (w.test_end - w.test_start).days == DEFAULT_TEST_DAYS
    assert w.test_start == w.train_end


def test_build_splits_multiple_rolling() -> None:
    first = BASE
    last = BASE + dt.timedelta(days=DEFAULT_TRAIN_DAYS + 3 * DEFAULT_TEST_DAYS)
    splits = build_splits(first, last)
    assert len(splits) == 3
    # Rolling by step_days
    assert (splits[1].train_start - splits[0].train_start).days == DEFAULT_STEP_DAYS
    assert (splits[2].train_start - splits[1].train_start).days == DEFAULT_STEP_DAYS


def test_build_splits_too_short_returns_empty() -> None:
    splits = build_splits(BASE, BASE + dt.timedelta(days=100))
    assert splits == []


def test_build_splits_equal_bounds_empty() -> None:
    assert build_splits(BASE, BASE) == []


def test_build_splits_zero_or_negative_params() -> None:
    assert build_splits(BASE, BASE + dt.timedelta(days=400), train_days=0) == []
    assert build_splits(BASE, BASE + dt.timedelta(days=400), test_days=-1) == []
    assert build_splits(BASE, BASE + dt.timedelta(days=400), step_days=0) == []


def test_build_splits_custom_params() -> None:
    splits = build_splits(
        BASE, BASE + dt.timedelta(days=200),
        train_days=100, test_days=50, step_days=25,
    )
    # Need 150 days; cursor goes 0, 25, 50 → last start+150=200 OK, 25+150=175 OK, 50+150=200 OK
    assert len(splits) == 3


# ---------------------------------------------------------------------------
# aggregate_window
# ---------------------------------------------------------------------------


def test_aggregate_empty_returns_nulls() -> None:
    m = aggregate_window([])
    assert m.count == 0
    assert m.wins == 0
    assert m.expectancy is None
    assert m.hit_rate is None
    assert m.profit_factor is None
    assert m.sharpe is None
    assert m.total_return_proxy is None


def test_aggregate_counts_wins_losses_breakeven() -> None:
    rows = [
        _row(0, 1, "0.05"),
        _row(1, -1, "-0.03"),
        _row(2, 0, "0"),
        _row(3, 1, "0.02"),
        _row(4, None, None),  # no label → excluded from win/loss counts
    ]
    m = aggregate_window(rows)
    assert m.count == 5
    assert m.wins == 2
    assert m.losses == 1
    assert m.breakeven == 1
    assert m.hit_rate == Decimal("2") / Decimal("3")


def test_aggregate_expectancy_and_total_return() -> None:
    rows = [_row(0, 1, "0.1"), _row(1, -1, "-0.05"), _row(2, 1, "0.03")]
    m = aggregate_window(rows)
    assert m.total_return_proxy == Decimal("0.08")
    assert m.expectancy == Decimal("0.08") / Decimal("3")


def test_aggregate_profit_factor_guards_zero_losses() -> None:
    rows = [_row(0, 1, "0.1"), _row(1, 1, "0.2")]
    m = aggregate_window(rows)
    assert m.profit_factor is None  # no losses → undefined


def test_aggregate_sharpe_needs_two_returns_and_nonzero_std() -> None:
    rows_one = [_row(0, 1, "0.1")]
    assert aggregate_window(rows_one).sharpe is None

    rows_flat = [_row(0, 1, "0.1"), _row(1, 1, "0.1"), _row(2, 1, "0.1")]
    assert aggregate_window(rows_flat).sharpe is None  # zero std

    rows_mixed = [_row(0, 1, "0.02"), _row(1, -1, "-0.01"), _row(2, 1, "0.03")]
    m = aggregate_window(rows_mixed)
    assert m.sharpe is not None
    assert m.sharpe > 0


# ---------------------------------------------------------------------------
# compute_wfe
# ---------------------------------------------------------------------------


def test_wfe_basic_ratio() -> None:
    assert compute_wfe(Decimal("0.02"), Decimal("0.01")) == Decimal("0.5")


def test_wfe_above_one_possible() -> None:
    wfe = compute_wfe(Decimal("0.01"), Decimal("0.015"))
    assert wfe == Decimal("1.5")


def test_wfe_none_when_is_none_or_zero_or_negative() -> None:
    assert compute_wfe(None, Decimal("0.01")) is None
    assert compute_wfe(Decimal("0"), Decimal("0.01")) is None
    assert compute_wfe(Decimal("-0.01"), Decimal("0.01")) is None


def test_wfe_none_when_oos_none() -> None:
    assert compute_wfe(Decimal("0.02"), None) is None


def test_wfe_zero_when_edge_fully_lost() -> None:
    # IS positive, OOS zero or negative → fully-lost edge maps to 0
    assert compute_wfe(Decimal("0.02"), Decimal("0")) == Decimal("0")
    assert compute_wfe(Decimal("0.02"), Decimal("-0.01")) == Decimal("0")


# ---------------------------------------------------------------------------
# classify_stability
# ---------------------------------------------------------------------------


def test_classify_thresholds() -> None:
    assert classify_stability(Decimal("0.9")) == "ROBUST"
    assert classify_stability(Decimal("0.70")) == "ROBUST"
    assert classify_stability(Decimal("0.69")) == "MODERATE"
    assert classify_stability(Decimal("0.50")) == "MODERATE"
    assert classify_stability(Decimal("0.49")) == "WEAK"
    assert classify_stability(Decimal("0")) == "WEAK"
    assert classify_stability(None) == "UNKNOWN"


# ---------------------------------------------------------------------------
# run_walk_forward (integration of the pure pieces)
# ---------------------------------------------------------------------------


def test_run_walk_forward_empty_rows() -> None:
    rep = run_walk_forward([])
    assert rep.splits == []
    assert rep.aggregate_wfe is None
    assert rep.aggregate_stability == "UNKNOWN"
    assert rep.config["train_days"] == DEFAULT_TRAIN_DAYS


def test_run_walk_forward_insufficient_span() -> None:
    rows = [_row(i, 1, "0.01") for i in range(0, 50, 5)]
    rep = run_walk_forward(rows)
    assert rep.splits == []
    assert rep.aggregate_stability == "UNKNOWN"


def test_run_walk_forward_robust_case() -> None:
    # 1-year train, 3-month test; seed identical positive expectancy in both
    # windows → WFE = 1.0 → ROBUST
    rows: list[OutcomeRow] = []
    # IS: day 0..251
    for i in range(0, DEFAULT_TRAIN_DAYS, 7):
        rows.append(_row(i, 1, "0.02"))
    # OOS: day 252..314
    for i in range(DEFAULT_TRAIN_DAYS, DEFAULT_TRAIN_DAYS + DEFAULT_TEST_DAYS, 7):
        rows.append(_row(i, 1, "0.02"))
    rep = run_walk_forward(rows)
    assert len(rep.splits) == 1
    s = rep.splits[0]
    assert s.is_metrics.expectancy == Decimal("0.02")
    assert s.oos_metrics.expectancy == Decimal("0.02")
    assert s.wfe == Decimal("1")
    assert s.stability == "ROBUST"


def test_run_walk_forward_weak_case() -> None:
    # IS big positive; OOS small positive → WFE low → WEAK
    rows: list[OutcomeRow] = []
    for i in range(0, DEFAULT_TRAIN_DAYS, 7):
        rows.append(_row(i, 1, "0.05"))
    for i in range(DEFAULT_TRAIN_DAYS, DEFAULT_TRAIN_DAYS + DEFAULT_TEST_DAYS, 7):
        rows.append(_row(i, 1, "0.01"))
    rep = run_walk_forward(rows)
    assert len(rep.splits) == 1
    s = rep.splits[0]
    assert s.wfe == Decimal("0.01") / Decimal("0.05")
    assert s.stability == "WEAK"


def test_run_walk_forward_stratification_filters() -> None:
    rows = []
    for i in range(0, DEFAULT_TRAIN_DAYS, 7):
        rows.append(_row(i, 1, "0.02", sig="trend"))
        rows.append(_row(i, -1, "-0.02", sig="mean_reversion"))
    for i in range(DEFAULT_TRAIN_DAYS, DEFAULT_TRAIN_DAYS + DEFAULT_TEST_DAYS, 7):
        rows.append(_row(i, 1, "0.02", sig="trend"))
        rows.append(_row(i, -1, "-0.02", sig="mean_reversion"))

    trend = run_walk_forward(rows, signal_type="trend")
    assert trend.stratified_by == "trend"
    assert trend.splits[0].wfe == Decimal("1")

    mean_rev = run_walk_forward(rows, signal_type="mean_reversion")
    # IS expectancy is negative → WFE undefined → UNKNOWN
    assert mean_rev.splits[0].wfe is None
    assert mean_rev.splits[0].stability == "UNKNOWN"


def test_run_walk_forward_empty_splits_noted() -> None:
    # Gap: IS has rows, OOS empty
    rows = [_row(i, 1, "0.02") for i in range(0, DEFAULT_TRAIN_DAYS, 7)]
    rep = run_walk_forward(rows)
    # No OOS rows in the test window → no splits (last rec is before train_end)
    # since last_ts < train_end + test_days, build_splits returns []
    assert rep.splits == []
