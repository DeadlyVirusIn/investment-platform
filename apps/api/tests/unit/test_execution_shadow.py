"""Unit tests — shadow execution framework."""

from __future__ import annotations

import datetime as dt

import pytest

from apps.api.src.domain.execution.integrator import PrimarySignal
from apps.api.src.domain.execution.shadow import (
    STRATEGIES,
    ComparisonReport,
    PrimaryWithReturn,
    ShadowDay,
    StrategyMetrics,
    aggregate_all,
    aggregate_metrics,
    compare_strategies,
    format_day_log,
    run_shadow_day,
)


# ---------------------------------------------------------------------------
# Synthetic inputs
# ---------------------------------------------------------------------------


def _trend_prices(n: int = 80) -> list[float]:
    out = [100.0]
    for _ in range(n - 1):
        out.append(out[-1] * 1.005)
    return out


def _primary(symbol: str, composite: float = 0.8, vol: float = 0.25) -> PrimarySignal:
    # Note: confidence+vol already normalized (from_raw invariant)
    return PrimarySignal(
        symbol=symbol, composite_score=composite, confidence=0.8,
        realized_vol_20d=vol,
    )


def _pwr(
    symbol: str,
    composite: float = 0.8,
    vol: float = 0.25,
    forward_ret_pct: float = 2.0,
    n_bars: int = 20,
) -> PrimaryWithReturn:
    return PrimaryWithReturn(
        primary=_primary(symbol, composite, vol),
        forward_return_pct=forward_ret_pct,
        barrier_n_bars=n_bars,
    )


def _day_batch(
    n_trades: int = 5,
    forward_rets: list[float] | None = None,
) -> list[PrimaryWithReturn]:
    rets = forward_rets if forward_rets else [2.0] * n_trades
    return [
        _pwr(f"S{i}", composite=0.7, vol=0.25, forward_ret_pct=rets[i])
        for i in range(n_trades)
    ]


# ---------------------------------------------------------------------------
# run_shadow_day
# ---------------------------------------------------------------------------


class TestRunShadowDay:
    def test_three_strategies_populated(self):
        day = run_shadow_day(
            dt.date(2026, 1, 5), _day_batch(5), _trend_prices(),
        )
        assert isinstance(day, ShadowDay)
        for s in STRATEGIES:
            assert s in day.sizes
            assert s in day.daily_return
            assert s in day.avg_position_size
            assert s in day.total_exposure

    def test_baseline_size_is_always_one(self):
        day = run_shadow_day(
            dt.date(2026, 1, 5), _day_batch(4), _trend_prices(),
        )
        assert all(s == 1.0 for s in day.sizes["baseline"])

    def test_baseline_larger_exposure_than_normalized(self):
        day = run_shadow_day(
            dt.date(2026, 1, 5), _day_batch(5), _trend_prices(),
        )
        assert day.total_exposure["baseline"] > day.total_exposure["normalized"]

    def test_kelly_below_neutral_composite_yields_zero(self):
        batch = [
            _pwr("A", composite=0.3, forward_ret_pct=2.0),
            _pwr("B", composite=0.4, forward_ret_pct=-1.0),
        ]
        day = run_shadow_day(dt.date(2026, 1, 5), batch, _trend_prices())
        # Kelly demands composite > 0.5 neutral
        assert all(s == 0.0 for s in day.sizes["kelly"])

    def test_empty_batch_no_crash(self):
        day = run_shadow_day(
            dt.date(2026, 1, 5), [], _trend_prices(),
        )
        assert day.n_trades == 0
        for s in STRATEGIES:
            assert day.daily_return[s] == 0.0

    def test_daily_return_baseline_equal_weighted(self):
        """Baseline daily return ≈ mean of per-bar returns, divided by n."""
        rets = [10.0, 20.0, -5.0]   # pct over holding
        n_bars = 20
        batch = [
            _pwr(f"S{i}", composite=0.7, forward_ret_pct=r, n_bars=n_bars)
            for i, r in enumerate(rets)
        ]
        day = run_shadow_day(dt.date(2026, 1, 5), batch, _trend_prices())
        # Expected: mean(r/100/n_bars)
        per_bar = [(r / 100.0) / n_bars for r in rets]
        expected = sum(per_bar) / len(per_bar)   # equal-weight avg
        assert day.daily_return["baseline"] == pytest.approx(expected)

    def test_regime_classified_once_per_day(self):
        day = run_shadow_day(
            dt.date(2026, 1, 5), _day_batch(5), _trend_prices(),
        )
        assert day.regime.regime in ("trend_up", "low_vol", "sideways", "high_vol")


# ---------------------------------------------------------------------------
# aggregate_metrics
# ---------------------------------------------------------------------------


def _run_series(
    n_days: int = 20, forward_ret_pct: float = 2.0,
) -> list[ShadowDay]:
    days: list[ShadowDay] = []
    for i in range(n_days):
        d = dt.date(2026, 1, 1) + dt.timedelta(days=i)
        batch = _day_batch(5, forward_rets=[forward_ret_pct] * 5)
        days.append(run_shadow_day(d, batch, _trend_prices()))
    return days


class TestAggregateMetrics:
    def test_returns_strategy_metrics(self):
        days = _run_series(10)
        m = aggregate_metrics(days, "baseline")
        assert isinstance(m, StrategyMetrics)
        assert m.strategy_name == "baseline"
        assert m.n_days == 10
        assert len(m.daily_returns) == 10

    def test_n_trades_total_summed(self):
        days = _run_series(10)
        m = aggregate_metrics(days, "baseline")
        assert m.n_trades_total == 10 * 5

    def test_sharpe_with_constant_returns_is_zero(self):
        """Zero stdev → sharpe falls to 0 (degenerate)."""
        days = _run_series(10, forward_ret_pct=5.0)
        m = aggregate_metrics(days, "baseline")
        assert m.sharpe == 0.0

    def test_cumulative_return_compounds(self):
        days = _run_series(10, forward_ret_pct=5.0)
        m = aggregate_metrics(days, "baseline")
        # positive 5% terminal return, should compound to positive cumulative
        assert m.cumulative_return > 0.0

    def test_max_drawdown_zero_for_monotonic_up(self):
        days = _run_series(10, forward_ret_pct=2.0)   # always positive
        m = aggregate_metrics(days, "baseline")
        assert m.max_drawdown_pct == 0.0

    def test_turnover_zero_when_exposure_constant(self):
        days = _run_series(10)
        m = aggregate_metrics(days, "baseline")
        # Baseline exposure is constant → turnover 0
        assert m.turnover == 0.0

    def test_aggregate_all_returns_three(self):
        days = _run_series(5)
        all_m = aggregate_all(days)
        assert set(all_m.keys()) == set(STRATEGIES)
        for s in STRATEGIES:
            assert isinstance(all_m[s], StrategyMetrics)


# ---------------------------------------------------------------------------
# compare_strategies
# ---------------------------------------------------------------------------


class TestCompareStrategies:
    def test_returns_comparison_report(self):
        days = _run_series(10)
        all_m = aggregate_all(days)
        rep = compare_strategies(
            all_m["baseline"], all_m["normalized"], all_m["kelly"],
        )
        assert isinstance(rep, ComparisonReport)
        assert "baseline" in rep.metrics

    def test_table_contains_all_strategies(self):
        days = _run_series(10)
        all_m = aggregate_all(days)
        rep = compare_strategies(
            all_m["baseline"], all_m["normalized"], all_m["kelly"],
        )
        for s in STRATEGIES:
            assert s in rep.table

    def test_table_contains_key_metrics(self):
        days = _run_series(10)
        all_m = aggregate_all(days)
        rep = compare_strategies(
            all_m["baseline"], all_m["normalized"], all_m["kelly"],
        )
        for key in ("sharpe", "max_drawdown", "cumulative_return", "turnover"):
            assert key in rep.table


# ---------------------------------------------------------------------------
# Day logging
# ---------------------------------------------------------------------------


class TestDayLog:
    def test_log_line_contains_key_fields(self):
        day = run_shadow_day(
            dt.date(2026, 1, 5), _day_batch(5), _trend_prices(),
        )
        line = format_day_log(day)
        assert "date=2026-01-05" in line
        assert "regime=" in line
        assert "n_trades=5" in line
        for s in STRATEGIES:
            assert f"{s}_avg_size=" in line
            assert f"{s}_daily_return=" in line

    def test_empty_day_still_logs(self):
        day = run_shadow_day(
            dt.date(2026, 1, 5), [], _trend_prices(),
        )
        line = format_day_log(day)
        assert "n_trades=0" in line


# ---------------------------------------------------------------------------
# Integrator factory (PrimarySignal.from_raw) — scale invariants
# ---------------------------------------------------------------------------


class TestPrimarySignalFromRaw:
    def test_confidence_percent_normalized(self):
        p = PrimarySignal.from_raw("X", 0.8, confidence_raw=71.2, vol_raw=0.30)
        assert p.confidence == pytest.approx(0.712)

    def test_confidence_fraction_unchanged(self):
        p = PrimarySignal.from_raw("X", 0.8, confidence_raw=0.712, vol_raw=0.30)
        assert p.confidence == pytest.approx(0.712)

    def test_daily_vol_annualized(self):
        import math
        p = PrimarySignal.from_raw(
            "X", 0.8, confidence_raw=0.8, vol_raw=0.02, vol_is_daily=True,
        )
        assert p.realized_vol_20d == pytest.approx(0.02 * math.sqrt(252))

    def test_annualized_vol_unchanged(self):
        p = PrimarySignal.from_raw(
            "X", 0.8, confidence_raw=0.8, vol_raw=0.30, vol_is_daily=False,
        )
        assert p.realized_vol_20d == 0.30

    def test_none_inputs_degrade_to_zero(self):
        p = PrimarySignal.from_raw("X", None, None, None)
        assert p.composite_score == 0.0
        assert p.confidence == 0.0
        assert p.realized_vol_20d == 0.0

    def test_out_of_range_composite_clipped(self):
        p = PrimarySignal.from_raw("X", 1.5, 0.8, 0.30)
        assert p.composite_score == 1.0
        p2 = PrimarySignal.from_raw("X", -0.3, 0.8, 0.30)
        assert p2.composite_score == 0.0
