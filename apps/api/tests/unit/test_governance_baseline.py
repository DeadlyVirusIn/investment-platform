"""Tests for governance.baseline_enforcement."""

from __future__ import annotations

import math
import random

from src.governance.baseline_enforcement import (
    buy_and_hold,
    compute_baselines,
    evaluate_vs_baseline,
    ma_crossover,
    tsmom_long_flat,
)


def _trend(n: int, drift: float = 0.001, start: float = 100.0,
            noise: float = 0.005, seed: int = 7) -> list[float]:
    rng = random.Random(seed)
    p = [start]
    for _ in range(n - 1):
        p.append(p[-1] * (1 + drift + rng.gauss(0, noise)))
    return p


def _flat(n: int, v: float = 100.0) -> list[float]:
    return [v] * n


def test_buy_and_hold_trend_positive_sharpe():
    r = buy_and_hold(_trend(300, drift=0.001))
    assert r.name == "buy_hold"
    assert math.isfinite(r.sharpe)
    assert r.sharpe > 0
    assert r.n == 299


def test_buy_and_hold_flat_sharpe_undefined_or_zero():
    r = buy_and_hold(_flat(50))
    # zero stdev → sharpe nan
    assert not math.isfinite(r.sharpe) or r.sharpe == 0


def test_tsmom_long_flat_trend_positive():
    r = tsmom_long_flat(_trend(400, drift=0.001), horizon=60)
    assert r.name == "tsmom_60d"
    assert r.n > 0
    assert math.isfinite(r.sharpe)


def test_tsmom_short_series_safe():
    r = tsmom_long_flat([100.0, 101.0], horizon=60)
    assert r.n == 0
    assert not math.isfinite(r.sharpe)


def test_ma_crossover_trend():
    r = ma_crossover(_trend(400, drift=0.001), fast=50, slow=200)
    assert r.name == "ma_50_200"
    assert r.n > 0


def test_ma_crossover_short_series_safe():
    r = ma_crossover(_flat(50), fast=50, slow=200)
    assert r.n == 0


def test_compute_baselines_returns_four():
    bs = compute_baselines(_trend(400, drift=0.0005))
    names = [b.name for b in bs]
    assert names == ["buy_hold", "tsmom_20d", "tsmom_60d", "ma_50_200"]


def test_evaluate_vs_baseline_underperform_flag_true():
    snap = evaluate_vs_baseline(_trend(400, drift=0.001),
                                  system_sharpe=-1.0)
    assert snap.system_underperforming_baseline is True
    d = snap.to_dict()
    assert d["system_underperforming_baseline"] is True
    assert "delta_sharpe_vs_baseline" in d


def test_evaluate_vs_baseline_outperform_flag_false():
    snap = evaluate_vs_baseline(_trend(400, drift=0.0005),
                                  system_sharpe=10.0)
    assert snap.system_underperforming_baseline is False


def test_evaluate_vs_baseline_with_no_finite_baselines():
    # All flat → no finite baseline sharpe → snapshot still safe
    snap = evaluate_vs_baseline(_flat(400), system_sharpe=1.0)
    assert isinstance(snap.system_underperforming_baseline, bool)
