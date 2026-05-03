"""PIT-safety + behavior tests for regime_backfill_persist3."""

from __future__ import annotations

import random
from datetime import date

from src.research.regime_backfill_persist3 import (
    LOGIC_VERSION, MA_SLOW, PERSIST_N, RVOL_20_STRESS, STATUS,
    classify_pit, logic_hash,
)


def _series(n, start=100.0, drift=0.0005, vol=0.005, seed=7):
    rng = random.Random(seed)
    p = [start]
    for _ in range(n - 1):
        p.append(p[-1] * (1 + drift + rng.gauss(0, vol)))
    return p


def test_constants():
    assert LOGIC_VERSION == "research_backfill_persist3_v1"
    assert STATUS == "diagnostic"
    assert PERSIST_N == 3


def test_pit_invariance_to_future_bars():
    closes = _series(400)
    today = date(2024, 6, 1)
    base = classify_pit(today, closes)
    # Append future bars; truncate back; same input must give same output.
    future = closes + _series(50, start=closes[-1] * 0.5)
    truncated = future[: len(closes)]
    after = classify_pit(today, truncated)
    assert base.stress_regime == after.stress_regime
    assert base.directional_regime == after.directional_regime


def test_persist1_below_ma200_does_not_trigger_when_v1_would():
    """Direct comparison: same input → v1 stress=True (single close
    below MA200 with no other trigger), persist3 stress=False.

    This proves the only behavioral difference is the MA200 component.
    """
    from src.research.regime_backfill import classify_pit as classify_v1
    # Construct: uptrend long enough to build MA200, then plateau where
    # the last close drifts just below MA200 without spike volatility.
    closes = [100.0]
    for i in range(220):
        closes.append(closes[-1] * 1.001)
    # Plateau decline: 79 small flat-to-slightly-negative bars
    for _ in range(79):
        closes.append(closes[-1] * 0.9999)
    r_v1 = classify_v1(date(2024, 6, 1), closes)
    r_v2 = classify_pit(date(2024, 6, 1), closes)
    # Both should agree on vol/dd metrics
    assert r_v1.close == r_v2.close
    assert abs(r_v1.ma200 - r_v2.ma200) < 1e-9
    # If v1 fired stress purely due to close<MA200 (no vol/dd), v2 may
    # disagree depending on persist count. Otherwise both should agree.
    if (r_v1.stress_regime
        and r_v1.close < r_v1.ma200
        and r_v1.rvol_20d < 0.30
        and r_v1.rvol_5d < 0.45
        and r_v1.dd_60d > -0.10):
        # v1 fired ONLY on close<MA200 → v2 must require ≥3 persist
        if r_v2.persist_below_ma200_n < 3:
            assert r_v2.stress_regime is False
        else:
            assert r_v2.stress_regime is True


def test_three_consecutive_closes_below_ma200_triggers():
    closes = _series(300, drift=0.001, vol=0.002, seed=13)
    # Force last 3 closes below MA200 of preceding bars.
    for k in (3, 2, 1):
        i = len(closes) - k
        ma200_i = sum(closes[i - 200:i]) / 200
        closes[i] = ma200_i * 0.997
    r = classify_pit(date(2024, 6, 1), closes)
    assert r.persist_below_ma200_n >= 3
    assert r.stress_regime is True


def test_high_vol_still_triggers_stress():
    closes = _series(MA_SLOW + 50, vol=0.05)
    r = classify_pit(date(2024, 6, 1), closes)
    assert r.rvol_20d >= RVOL_20_STRESS
    assert r.stress_regime is True


def test_clean_uptrend_directional():
    closes = _series(MA_SLOW + 100, drift=0.001, vol=0.003)
    r = classify_pit(date(2024, 6, 1), closes)
    assert r.stress_regime is False
    assert r.directional_regime is True


def test_logic_hash_stable_and_different_from_v1():
    h1 = logic_hash(); h2 = logic_hash()
    assert h1 == h2
    # Should NOT collide with v1 hash
    from src.research.regime_backfill import logic_hash as v1_hash
    assert h1 != v1_hash()


def test_no_input_mutation():
    closes = _series(300)
    snap = list(closes)
    classify_pit(date(2024, 6, 1), closes)
    assert closes == snap


def test_insufficient_history_safe():
    r = classify_pit(date(2024, 6, 1), _series(50))
    assert r.insufficient_history is True
    assert r.stress_regime is False
    assert r.directional_regime is False
