"""Unit tests for paper-performance metric functions."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from apps.api.src.domain.performance.paper_performance import (
    EquityPoint,
    daily_returns,
    expectancy,
    hit_rate,
    max_drawdown,
    profit_factor,
    sharpe,
    total_return,
)


BASE = dt.date(2026, 1, 1)


def _curve(vals: list[str]) -> list[EquityPoint]:
    return [
        EquityPoint(BASE + dt.timedelta(days=i), Decimal(v))
        for i, v in enumerate(vals)
    ]


# ---------------------------------------------------------------------------
# total_return
# ---------------------------------------------------------------------------


def test_total_return_basic() -> None:
    assert total_return(Decimal("1000"), Decimal("1100")) == Decimal("0.1")


def test_total_return_zero_starting_is_none() -> None:
    assert total_return(Decimal("0"), Decimal("100")) is None


def test_total_return_null_inputs() -> None:
    assert total_return(None, Decimal("100")) is None
    assert total_return(Decimal("1000"), None) is None


# ---------------------------------------------------------------------------
# max_drawdown
# ---------------------------------------------------------------------------


def test_max_drawdown_basic() -> None:
    # peak 1200 → trough 960 → -20%
    curve = _curve(["1000", "1200", "960", "1300"])
    dd = max_drawdown(curve)
    assert dd == Decimal("-0.2")


def test_max_drawdown_monotonic_up_is_none() -> None:
    curve = _curve(["1000", "1050", "1100"])
    assert max_drawdown(curve) is None


def test_max_drawdown_empty_is_none() -> None:
    assert max_drawdown([]) is None


def test_max_drawdown_single_point_is_none() -> None:
    assert max_drawdown(_curve(["1000"])) is None


# ---------------------------------------------------------------------------
# hit_rate
# ---------------------------------------------------------------------------


def test_hit_rate_basic() -> None:
    assert hit_rate(3, 2) == Decimal("3") / Decimal("5")


def test_hit_rate_no_trades_is_none() -> None:
    assert hit_rate(0, 0) is None


# ---------------------------------------------------------------------------
# expectancy
# ---------------------------------------------------------------------------


def test_expectancy_mean_pnl() -> None:
    result = expectancy([Decimal("10"), Decimal("-5"), Decimal("3")])
    assert result == Decimal("8") / Decimal("3")


def test_expectancy_empty_is_none() -> None:
    assert expectancy([]) is None


# ---------------------------------------------------------------------------
# profit_factor
# ---------------------------------------------------------------------------


def test_profit_factor_basic() -> None:
    pnls = [Decimal("10"), Decimal("3"), Decimal("-5")]
    assert profit_factor(pnls) == Decimal("13") / Decimal("5")


def test_profit_factor_all_wins_is_none() -> None:
    assert profit_factor([Decimal("5"), Decimal("10")]) is None


def test_profit_factor_empty_is_none() -> None:
    assert profit_factor([]) is None


# ---------------------------------------------------------------------------
# daily_returns
# ---------------------------------------------------------------------------


def test_daily_returns_sequence() -> None:
    curve = _curve(["1000", "1100", "1210"])
    rs = daily_returns(curve)
    assert len(rs) == 2
    assert rs[0] == Decimal("0.1")
    assert rs[1] == Decimal("0.1")


def test_daily_returns_skips_nonpositive() -> None:
    curve = _curve(["0", "100"])
    assert daily_returns(curve) == []


# ---------------------------------------------------------------------------
# sharpe
# ---------------------------------------------------------------------------


def test_sharpe_single_return_is_none() -> None:
    assert sharpe([Decimal("0.01")]) is None


def test_sharpe_zero_std_is_none() -> None:
    assert sharpe([Decimal("0.01"), Decimal("0.01"), Decimal("0.01")]) is None


def test_sharpe_positive_on_positive_mean() -> None:
    out = sharpe([Decimal("0.01"), Decimal("-0.005"), Decimal("0.02"), Decimal("0.015")])
    assert out is not None
    assert out > 0


def test_sharpe_negative_on_negative_mean() -> None:
    out = sharpe([Decimal("-0.01"), Decimal("-0.02"), Decimal("-0.005"), Decimal("-0.015")])
    assert out is not None
    assert out < 0


def test_sharpe_empty_is_none() -> None:
    assert sharpe([]) is None
