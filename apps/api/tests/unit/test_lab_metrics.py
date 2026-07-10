"""Unit tests — apps.ml.lab metrics, benchmarks, and cost model.

Edge cases pinned: single-class AUC/precision/recall return None (never
NaN), ECE/MCE bin math by hand, drawdown on a known series, and exact
cost-adjustment arithmetic (flat haircut + half-spread slippage).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from apps.ml.lab.benchmarks import (
    base_rate_brier,
    buy_and_hold_return,
    momentum_12_1_portfolio_returns,
    momentum_12_1_signal,
)
from apps.ml.lab.costs import (
    apply_trade_costs,
    cost_sweep,
    half_spread_slippage_bps,
)
from apps.ml.lab.metrics import (
    auc,
    brier,
    cost_adjusted_return,
    ece,
    max_drawdown,
    mce,
    precision_recall,
    turnover,
)

# ---------------------------------------------------------------------------
# classification / calibration
# ---------------------------------------------------------------------------


def test_auc_single_class_returns_none():
    assert auc([1, 1, 1], [0.2, 0.5, 0.9]) is None
    assert auc([0, 0], [0.1, 0.9]) is None


def test_auc_perfect_separation():
    assert auc([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9]) == 1.0


def test_brier_known_values():
    assert brier([1, 0], [1.0, 0.0]) == 0.0
    assert brier([1], [0.5]) == pytest.approx(0.25)


def test_ece_single_bin_hand_computed():
    # all 4 predictions in bin [0.1, 0.2): gap = |0.15 - 0.75| = 0.6, weight 1
    p = [0.15, 0.15, 0.15, 0.15]
    y = [0, 1, 1, 1]
    assert ece(y, p) == pytest.approx(0.6)
    assert mce(y, p) == pytest.approx(0.6)


def test_ece_two_bins_weighted():
    # bin [0.0,0.1): gap |0.05-0| = 0.05, weight 0.5
    # bin [0.9,1.0]: gap |0.95-1| = 0.05, weight 0.5  → ece = 0.05
    p = [0.05, 0.05, 0.95, 0.95]
    y = [0, 0, 1, 1]
    assert ece(y, p) == pytest.approx(0.05)
    assert mce(y, p) == pytest.approx(0.05)


def test_ece_rejects_shape_mismatch_and_empty():
    with pytest.raises(ValueError):
        ece([1, 0], [0.5])
    with pytest.raises(ValueError):
        brier([], [])


def test_precision_recall_guards_single_class():
    # no predicted positives → precision None; recall 0.0 (positives exist)
    prec, rec = precision_recall([1, 0, 1], [0, 0, 0])
    assert prec is None
    assert rec == 0.0
    # no actual positives → recall None
    prec, rec = precision_recall([0, 0, 0], [1, 0, 0])
    assert prec == 0.0
    assert rec is None
    # known mixed case: tp=1, fp=1, fn=1
    prec, rec = precision_recall([1, 1, 0], [1, 0, 1])
    assert prec == pytest.approx(0.5)
    assert rec == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# trading metrics
# ---------------------------------------------------------------------------


def test_max_drawdown_known_series():
    # equity: 1.10 → 0.55 → 0.66; peak 1.10 → dd = 0.55/1.10 − 1 = −0.5
    assert max_drawdown([0.1, -0.5, 0.2]) == pytest.approx(-0.5)


def test_max_drawdown_monotonic_up_is_zero():
    assert max_drawdown([0.01, 0.02, 0.03]) == 0.0
    assert max_drawdown([]) == 0.0


def test_turnover_full_rotation_and_static():
    w = pd.DataFrame([[1.0, 0.0], [0.0, 1.0]])
    assert turnover(w) == pytest.approx(1.0)  # 0.5 * (1 + 1)
    static = pd.DataFrame([[0.5, 0.5], [0.5, 0.5]])
    assert turnover(static) == 0.0
    assert turnover(pd.DataFrame([[1.0, 0.0]])) == 0.0  # single period


def test_cost_adjusted_return_math():
    res = cost_adjusted_return([0.01, 0.02], cost_bps=10.0)
    assert res["net_returns"] == pytest.approx([0.009, 0.019])
    assert res["gross_total_return"] == pytest.approx(1.01 * 1.02 - 1.0)
    assert res["net_total_return"] == pytest.approx(1.009 * 1.019 - 1.0)
    with pytest.raises(ValueError):
        cost_adjusted_return([], cost_bps=10.0)


# ---------------------------------------------------------------------------
# benchmarks
# ---------------------------------------------------------------------------


def test_buy_and_hold_return():
    assert buy_and_hold_return([100.0, 110.0, 120.0]) == pytest.approx(0.2)
    with pytest.raises(ValueError):
        buy_and_hold_return([100.0])
    with pytest.raises(ValueError):
        buy_and_hold_return([0.0, 1.0])


def test_momentum_12_1_signal_formula():
    idx = pd.period_range("2023-01", periods=14, freq="M").to_timestamp()
    prices = pd.DataFrame({"A": np.linspace(100, 230, 14)}, index=idx)
    sig = momentum_12_1_signal(prices)
    # signal_t = P_{t-1} / P_{t-12} − 1
    t = idx[-1]
    expected = prices["A"].iloc[-2] / prices["A"].iloc[-13] - 1.0
    assert sig.loc[t, "A"] == pytest.approx(expected)
    # first 12 rows lack history
    assert sig["A"].iloc[:12].isna().all()
    with pytest.raises(ValueError):
        momentum_12_1_signal(prices, lookback=1, skip=1)


def test_momentum_12_1_portfolio_picks_winner():
    idx = pd.period_range("2022-01", periods=15, freq="M").to_timestamp()
    up = 100 * (1.02 ** np.arange(15))     # strong momentum
    down = 100 * (0.99 ** np.arange(15))   # weak momentum
    prices = pd.DataFrame({"UP": up, "DOWN": down}, index=idx)
    rets = momentum_12_1_portfolio_returns(prices, top_frac=0.5)
    assert len(rets) >= 1
    # top-half (1 of 2) portfolio must hold UP → next-month return ≈ +2%
    assert np.allclose(rets.values, 0.02)
    with pytest.raises(ValueError):
        momentum_12_1_portfolio_returns(prices, top_frac=0.0)


def test_base_rate_brier():
    y = [1, 0, 0, 1]
    assert base_rate_brier(y, base_rate=0.5) == pytest.approx(0.25)
    # None → in-sample mean (reference floor only)
    assert base_rate_brier(y) == pytest.approx(0.25)
    assert base_rate_brier([0, 0, 0, 1], base_rate=0.25) == pytest.approx(
        (3 * 0.25**2 + 0.75**2) / 4
    )
    with pytest.raises(ValueError):
        base_rate_brier(y, base_rate=1.5)


# ---------------------------------------------------------------------------
# cost model
# ---------------------------------------------------------------------------


def test_slippage_floor_cap_and_curve():
    # huge liquidity → floor
    assert half_spread_slippage_bps(1e12) == pytest.approx(1.0)
    # unknown/zero liquidity → cap (never a free fill)
    assert half_spread_slippage_bps(0.0) == pytest.approx(50.0)
    assert half_spread_slippage_bps(-5.0) == pytest.approx(50.0)
    # k/sqrt: $1M ADV with k=5000 → 5 bps
    assert half_spread_slippage_bps(1e6) == pytest.approx(5.0)
    # deterministic: same input, same output
    assert half_spread_slippage_bps(3.7e7) == half_spread_slippage_bps(3.7e7)


def test_apply_trade_costs_exact_math():
    trades = [{"gross_return": 0.01, "dollar_volume": 1e6}]
    res = apply_trade_costs(trades, commission_bps=2.0, round_trip=True)
    # per side: 2 commission + 5 slippage = 7 bps; round trip = 14 bps
    assert res["mean_cost_bps"] == pytest.approx(14.0)
    assert res["net_mean_return"] == pytest.approx(0.01 - 0.0014)
    assert res["gross_mean_return"] == pytest.approx(0.01)
    one_side = apply_trade_costs(trades, commission_bps=2.0, round_trip=False)
    assert one_side["mean_cost_bps"] == pytest.approx(7.0)
    with pytest.raises(ValueError):
        apply_trade_costs([])


def test_cost_sweep_net_monotonically_decreasing():
    trades = [
        {"gross_return": 0.02, "dollar_volume": 1e6},
        {"gross_return": -0.01, "dollar_volume": 4e6},
    ]
    sweep = cost_sweep(trades, [0.0, 5.0, 10.0, 20.0])
    nets = [pt["net_mean_return"] for pt in sweep]
    assert nets == sorted(nets, reverse=True)
    assert all("trades" not in pt for pt in sweep)
    # zero-commission point still pays slippage: net < gross
    assert sweep[0]["net_mean_return"] < sweep[0]["gross_mean_return"]
