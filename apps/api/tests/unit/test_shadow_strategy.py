"""Tests for research.shadow_strategy.

Covers pure-function behavior + invariants. DB upsert is exercised
via integration tests; here we test the decision logic only.
"""

from __future__ import annotations

from datetime import date

from src.research.shadow_strategy import (
    INSTRUMENT_DEFAULT,
    SOURCE_STRATEGY,
    TSMOM_HORIZON,
    _tsmom_60_signal,
    compute_decision,
)


def _trend_up(n: int, base: float = 100.0,
                drift: float = 0.001) -> list[float]:
    p = [base]
    for _ in range(n - 1):
        p.append(p[-1] * (1 + drift))
    return p


def _trend_down(n: int, base: float = 100.0,
                  drift: float = -0.001) -> list[float]:
    return _trend_up(n, base, drift)


def test_constants():
    assert SOURCE_STRATEGY == "tsmom_60_no_stress"
    assert INSTRUMENT_DEFAULT == "ES"
    assert TSMOM_HORIZON == 60


def test_tsmom_signal_short_history_flat():
    sig, mom = _tsmom_60_signal([100.0, 101.0])
    assert sig == "FLAT"
    assert mom is None


def test_tsmom_signal_uptrend_long():
    sig, mom = _tsmom_60_signal(_trend_up(80))
    assert sig == "LONG"
    assert mom is not None and mom > 0


def test_tsmom_signal_downtrend_flat():
    sig, mom = _tsmom_60_signal(_trend_down(80))
    assert sig == "FLAT"
    assert mom is not None and mom <= 0


def test_stress_filter_forces_flat_even_when_momentum_positive():
    closes = _trend_up(80)
    d = compute_decision(
        as_of_date=date(2024, 6, 1),
        closes_thru_today=closes,
        stress_regime=True,
        directional_regime=False,
        engine_a_active=False,
    )
    assert d.signal == "FLAT"
    assert "stress_regime=True" in d.note
    assert d.entry_price is None
    assert d.regime_label == "STRESS"


def test_no_stress_uptrend_long():
    closes = _trend_up(80)
    d = compute_decision(
        as_of_date=date(2024, 6, 1),
        closes_thru_today=closes,
        stress_regime=False,
        directional_regime=True,
        engine_a_active=False,
    )
    assert d.signal == "LONG"
    assert d.regime_label == "DIRECTIONAL"
    assert d.entry_price is not None
    assert d.entry_price > 0


def test_no_stress_downtrend_flat():
    closes = _trend_down(80)
    d = compute_decision(
        as_of_date=date(2024, 6, 1),
        closes_thru_today=closes,
        stress_regime=False,
        directional_regime=False,
        engine_a_active=False,
    )
    assert d.signal == "FLAT"
    assert d.regime_label == "NEUTRAL"


def test_engine_a_active_recorded_but_does_not_force_flat():
    """engine_a_active is RECORDED for analysis but does NOT alter the
    signal. tsmom_60_no_stress is independent of Engine A schedule."""
    closes = _trend_up(80)
    d = compute_decision(
        as_of_date=date(2024, 6, 1),
        closes_thru_today=closes,
        stress_regime=False,
        directional_regime=True,
        engine_a_active=True,
    )
    assert d.signal == "LONG"
    assert d.engine_a_active is True


def test_decision_immutable_dataclass_to_dict():
    closes = _trend_up(80)
    d = compute_decision(
        as_of_date=date(2024, 6, 1),
        closes_thru_today=closes,
        stress_regime=False,
        directional_regime=True,
        engine_a_active=False,
    )
    # dataclass is frozen
    import dataclasses
    assert dataclasses.is_dataclass(d)
    payload = d.to_dict()
    assert payload["signal"] == "LONG"
    assert payload["source_strategy"] == SOURCE_STRATEGY
    assert payload["regime_label"] == "DIRECTIONAL"
    assert "as_of_date" in payload


def test_decision_does_not_mutate_input():
    closes = _trend_up(80)
    snap = list(closes)
    compute_decision(
        as_of_date=date(2024, 6, 1),
        closes_thru_today=closes,
        stress_regime=False, directional_regime=True,
        engine_a_active=False,
    )
    assert closes == snap
