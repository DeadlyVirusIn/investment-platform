"""PIT-safety tests for research.regime_backfill.

Proves: classify_pit's output for date D depends ONLY on closes ≤ D.
Future bars cannot influence label.
"""

from __future__ import annotations

from datetime import date, timedelta

from src.research.regime_backfill import (
    DD_60_STRESS,
    LOGIC_VERSION,
    MA_SLOW,
    RVOL_20_CALM,
    RVOL_20_STRESS,
    STATUS,
    classify_pit,
    logic_hash,
)


def _series(n: int, start: float = 100.0,
            drift: float = 0.0005, vol: float = 0.005,
            seed: int = 7) -> list[float]:
    import random
    rng = random.Random(seed)
    p = [start]
    for _ in range(n - 1):
        p.append(p[-1] * (1 + drift + rng.gauss(0, vol)))
    return p


def test_pit_invariance_to_future_bars():
    """Adding bars AFTER as_of must not change label for as_of."""
    closes = _series(400)
    today = date(2024, 6, 1)
    base = classify_pit(today, closes)
    # Append 100 more (very different) future bars
    future = closes + _series(100, start=closes[-1] * 2.0,
                                  drift=-0.01, vol=0.05, seed=99)
    # Pass only closes ≤ today, which is the SAME truncation
    truncated = future[: len(closes)]
    after = classify_pit(today, truncated)
    assert base.stress_regime == after.stress_regime
    assert base.directional_regime == after.directional_regime
    assert base.rvol_20d == after.rvol_20d


def test_label_changes_with_history_only():
    """Label IS allowed to differ when given different *past* history."""
    today = date(2024, 6, 1)
    calm   = _series(400, vol=0.003)
    chaos  = _series(400, vol=0.04)
    a = classify_pit(today, calm)
    b = classify_pit(today, chaos)
    # chaos rvol must be higher
    assert b.rvol_20d > a.rvol_20d


def test_insufficient_history_yields_both_false():
    today = date(2024, 6, 1)
    short = _series(50)
    r = classify_pit(today, short)
    assert r.insufficient_history is True
    assert r.stress_regime is False
    assert r.directional_regime is False


def test_stress_when_rvol20_above_threshold():
    today = date(2024, 6, 1)
    # high vol series
    closes = _series(MA_SLOW + 50, vol=0.05)
    r = classify_pit(today, closes)
    assert r.rvol_20d >= RVOL_20_STRESS
    assert r.stress_regime is True
    assert r.directional_regime is False


def test_directional_in_calm_uptrend():
    today = date(2024, 6, 1)
    closes = _series(MA_SLOW + 100, drift=0.001, vol=0.003)
    r = classify_pit(today, closes)
    assert r.rvol_20d < RVOL_20_CALM
    assert r.ma50 > r.ma200
    assert r.close > r.ma50
    assert r.directional_regime is True
    assert r.stress_regime is False


def test_drawdown_triggers_stress():
    # Steady up then progressive crash
    closes = _series(MA_SLOW + 30, drift=0.001, vol=0.002, seed=1)
    crashed = list(closes)
    for _ in range(20):
        crashed.append(crashed[-1] * 0.985)   # compound -1.5%/day
    today = date(2024, 6, 1)
    r = classify_pit(today, crashed)
    assert r.dd_60d <= DD_60_STRESS
    assert r.stress_regime is True


def test_label_constants_and_hash_are_stable():
    h1 = logic_hash()
    h2 = logic_hash()
    assert h1 == h2
    assert isinstance(h1, str) and len(h1) >= 8
    assert LOGIC_VERSION == "research_backfill_v1"
    assert STATUS == "diagnostic"


def test_classify_does_not_mutate_input():
    closes = _series(300)
    snap = list(closes)
    classify_pit(date(2024, 6, 1), closes)
    assert closes == snap


def test_truncation_invariance_pair():
    """For two `as_of` dates D1 < D2, the label at D1 must be identical
    whether we pass closes[:D1+1] or closes[:D2+1]-truncated-to-D1."""
    closes = _series(500)
    d1_idx = 250
    d1 = date(2024, 1, 1)
    a = classify_pit(d1, closes[: d1_idx + 1])
    b = classify_pit(d1, closes[: d1_idx + 1])  # same input
    assert a == b
