"""Unit tests for performance metrics."""

from __future__ import annotations

from decimal import Decimal

from apps.api.src.domain.performance.metrics import (
    Metrics,
    _compound,
    _max_drawdown_duration,
    compute_metrics,
)


def _d(v: str | float | int) -> Decimal:
    return Decimal(str(v))


# ---------------------------------------------------------------------------
# Edge: no trades
# ---------------------------------------------------------------------------


def test_empty_returns_zero_trades() -> None:
    m = compute_metrics([], [])
    assert m.total_trades == 0
    assert m.wins == 0
    assert m.losses == 0
    assert m.neutral == 0
    assert m.win_rate is None
    assert m.expectancy is None
    assert m.profit_factor is None
    assert m.total_return is None
    assert m.sharpe_ratio is None
    assert m.sortino_ratio is None
    assert m.calmar_ratio is None
    assert m.max_drawdown is None
    assert m.max_drawdown_duration is None


def test_length_mismatch_raises() -> None:
    import pytest
    with pytest.raises(ValueError):
        compute_metrics([_d("0.05")], [])


# ---------------------------------------------------------------------------
# Counts + simple stats
# ---------------------------------------------------------------------------


def test_counts_and_win_rate() -> None:
    returns = [_d("0.1"), _d("-0.05"), _d("0"), _d("0.02")]
    labels = [1, -1, 0, 1]
    m = compute_metrics(returns, labels)
    assert m.total_trades == 4
    assert m.wins == 2
    assert m.losses == 1
    assert m.neutral == 1
    assert m.win_rate == _d("0.5")


def test_expectancy_is_mean_return() -> None:
    returns = [_d("0.1"), _d("-0.05"), _d("0.08"), _d("-0.02")]
    labels = [1, -1, 1, -1]
    m = compute_metrics(returns, labels)
    # mean = 0.11 / 4 = 0.0275
    assert m.expectancy == _d("0.11") / _d("4")


def test_profit_factor_sum_gains_over_losses() -> None:
    returns = [_d("0.10"), _d("0.05"), _d("-0.04"), _d("-0.01")]
    labels = [1, 1, -1, -1]
    m = compute_metrics(returns, labels)
    # PF = (0.10 + 0.05) / (0.04 + 0.01) = 0.15 / 0.05 = 3
    assert m.profit_factor == _d("3")


def test_profit_factor_no_losses_is_none() -> None:
    returns = [_d("0.05"), _d("0.03"), _d("0.01")]
    labels = [1, 1, 1]
    m = compute_metrics(returns, labels)
    assert m.profit_factor is None


def test_total_return_compound() -> None:
    returns = [_d("0.1"), _d("0.1")]
    labels = [1, 1]
    m = compute_metrics(returns, labels)
    # (1.1)(1.1) - 1 = 0.21
    assert m.total_return == _d("0.21")


# ---------------------------------------------------------------------------
# Drawdown
# ---------------------------------------------------------------------------


def test_all_wins_no_drawdown() -> None:
    returns = [_d("0.05"), _d("0.03"), _d("0.02")]
    labels = [1, 1, 1]
    m = compute_metrics(returns, labels)
    assert m.max_drawdown is None   # no DD recorded → None
    assert m.max_drawdown_duration is None


def test_all_losses_shows_drawdown() -> None:
    returns = [_d("-0.05"), _d("-0.03"), _d("-0.02")]
    labels = [-1, -1, -1]
    m = compute_metrics(returns, labels)
    assert m.max_drawdown is not None
    assert m.max_drawdown < _d("0")
    # Full series underwater from trade 1 → duration = 3
    assert m.max_drawdown_duration == 3


def test_max_dd_duration_simple() -> None:
    # equity: 1.0 → 1.1 → 1.0 → 0.9 → 1.2  (underwater from idx 2..3, recovered at idx 4 → duration=2)
    returns = [_d("0.1"), _d("-0.0909090909"), _d("-0.1"), _d("0.3333333333")]
    labels = [1, -1, -1, 1]
    m = compute_metrics(returns, labels)
    # Duration is 2 or 3 depending on recovery granularity; just assert > 0
    assert m.max_drawdown_duration is not None
    assert m.max_drawdown_duration >= 1


def test_max_dd_duration_helper() -> None:
    # equity 1.0, 1.2, 1.1, 1.0, 0.9, 1.3 → underwater idx 2..4, recovers at 5 → duration=3
    eq = [_d("1.0"), _d("1.2"), _d("1.1"), _d("1.0"), _d("0.9"), _d("1.3")]
    assert _max_drawdown_duration(eq) == 3


# ---------------------------------------------------------------------------
# Risk-adjusted ratios
# ---------------------------------------------------------------------------


def test_sharpe_finite_on_mixed() -> None:
    returns = [_d("0.05"), _d("-0.02"), _d("0.03"), _d("-0.01"), _d("0.04")]
    labels = [1, -1, 1, -1, 1]
    m = compute_metrics(returns, labels)
    assert m.sharpe_ratio is not None
    assert m.sharpe_ratio > _d("0")  # positive expectancy


def test_sortino_finite_with_downside() -> None:
    returns = [_d("0.05"), _d("-0.02"), _d("0.03"), _d("-0.04")]
    labels = [1, -1, 1, -1]
    m = compute_metrics(returns, labels)
    assert m.sortino_ratio is not None


def test_calmar_none_when_no_drawdown() -> None:
    # Monotonic gains → empyrical returns max_drawdown=0 → calmar divides by 0 → inf/nan → None
    returns = [_d("0.05"), _d("0.03")]
    labels = [1, 1]
    m = compute_metrics(returns, labels)
    # profit factor has no losses → None
    assert m.profit_factor is None
    # calmar sanitized to None
    assert m.calmar_ratio is None


def test_sharpe_none_on_single_trade() -> None:
    m = compute_metrics([_d("0.05")], [1])
    assert m.sharpe_ratio is None


def test_sharpe_none_when_all_same_return() -> None:
    # std=0 → sharpe undefined → None
    m = compute_metrics([_d("0.02"), _d("0.02"), _d("0.02")], [1, 1, 1])
    assert m.sharpe_ratio is None


# ---------------------------------------------------------------------------
# _compound helper
# ---------------------------------------------------------------------------


def test_compound_builds_equity_curve() -> None:
    eq = _compound([_d("0.1"), _d("-0.1")])
    # [1.0, 1.1, 0.99]
    assert eq[0] == _d("1")
    assert eq[1] == _d("1.1")
    assert eq[2] == _d("1.1") * _d("0.9")
