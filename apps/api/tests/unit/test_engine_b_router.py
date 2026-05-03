"""Tests for engine_b_router — pure deterministic routing."""

from __future__ import annotations

from datetime import date

import pytest

from src.research.engine_b_router import (
    EXECUTION_CHANGE_MODES, VALID_MODES, route,
)


def _r(mode, b="LONG", b2="FLAT", d=date(2024, 6, 1)):
    return route(mode=mode, as_of=d,
                  engine_b_signal=b, b2_signal=b2)


def test_valid_modes_constant_complete():
    assert "LEGACY" in VALID_MODES
    assert "FULL_B2" in VALID_MODES
    assert "PARTIAL_B2_25" in VALID_MODES
    assert "PARTIAL_B2_50" in VALID_MODES
    assert "PARTIAL_B2_75" in VALID_MODES
    assert "SHADOW_COMPARE" in VALID_MODES


def test_unknown_mode_raises():
    with pytest.raises(ValueError):
        _r("INVALID")


def test_legacy_routes_engine_b():
    r = _r("LEGACY", b="LONG", b2="FLAT")
    assert r.routed_signal == "LONG"
    assert r.routed_engine == "B"
    assert r.execution_changed is False


def test_shadow_compare_routes_engine_b_logs_b2():
    r = _r("SHADOW_COMPARE", b="LONG", b2="FLAT")
    assert r.routed_signal == "LONG"
    assert r.routed_engine == "B"
    assert r.execution_changed is False
    assert r.b2_signal == "FLAT"


def test_full_b2_routes_b2():
    r = _r("FULL_B2", b="FLAT", b2="LONG")
    assert r.routed_signal == "LONG"
    assert r.routed_engine == "B2"
    assert r.execution_changed is True


def test_divergence_flag():
    assert _r("LEGACY", b="LONG", b2="FLAT").divergence is True
    assert _r("LEGACY", b="LONG", b2="LONG").divergence is False
    assert _r("LEGACY", b="FLAT", b2="FLAT").divergence is False


def test_partial_modes_deterministic_per_date():
    # Same date + mode → same routed_engine across calls
    d = date(2024, 6, 1)
    runs = {route(mode="PARTIAL_B2_50", as_of=d,
                    engine_b_signal="LONG", b2_signal="FLAT").routed_engine
            for _ in range(20)}
    assert len(runs) == 1


def test_partial_50_distribution_close_to_target():
    # Sample 365 dates; ~50% should pick B2
    n_b2 = 0
    n = 365
    for i in range(n):
        d = date(2024, 1, 1).replace(day=1)
        # advance day by 1 each iter (use ordinal arithmetic)
        from datetime import timedelta
        d2 = date(2024, 1, 1) + timedelta(days=i)
        r = route(mode="PARTIAL_B2_50", as_of=d2,
                    engine_b_signal="LONG", b2_signal="FLAT")
        if r.routed_engine == "B2":
            n_b2 += 1
    pct = n_b2 / n
    # Allow ±10% slack on hash-based pseudo-uniform
    assert 0.40 <= pct <= 0.60, f"pct={pct}"


def test_partial_25_lower_than_75():
    from datetime import timedelta
    n_25 = n_75 = 0
    n = 200
    for i in range(n):
        d = date(2024, 1, 1) + timedelta(days=i)
        if route(mode="PARTIAL_B2_25", as_of=d,
                  engine_b_signal="LONG", b2_signal="FLAT").routed_engine == "B2":
            n_25 += 1
        if route(mode="PARTIAL_B2_75", as_of=d,
                  engine_b_signal="LONG", b2_signal="FLAT").routed_engine == "B2":
            n_75 += 1
    assert n_25 < n_75


def test_execution_change_modes_constant():
    for m in EXECUTION_CHANGE_MODES:
        assert m in VALID_MODES
    # LEGACY and SHADOW_COMPARE must NOT be in change modes
    assert "LEGACY" not in EXECUTION_CHANGE_MODES
    assert "SHADOW_COMPARE" not in EXECUTION_CHANGE_MODES


def test_to_dict_payload_complete():
    r = _r("FULL_B2", b="FLAT", b2="LONG")
    d = r.to_dict()
    assert set(d.keys()) >= {
        "mode", "routed_signal", "engine_b_signal", "b2_signal",
        "routed_engine", "divergence", "note", "execution_changed",
    }
