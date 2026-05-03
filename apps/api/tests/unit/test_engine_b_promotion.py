"""Tests for engine_b_promotion — gates + kill switch."""

from __future__ import annotations

import math

from src.research.engine_b_promotion import (
    STATE_ORDER, evaluate, evaluate_advance_gates, evaluate_kill_switch,
)


def _series(n: int, mu: float, sd: float = 0.005,
              seed: int = 0) -> list[float]:
    import random
    rng = random.Random(seed)
    return [rng.gauss(mu, sd) for _ in range(n)]


def test_state_order_complete():
    assert STATE_ORDER[0] == "LEGACY"
    assert STATE_ORDER[-1] == "FULL_B2"
    assert "SHADOW_COMPARE" in STATE_ORDER


def test_kill_switch_insufficient_data():
    k = evaluate_kill_switch(routed_returns=[0.01] * 5)
    assert k.triggered is False
    assert "insufficient" in k.reason.lower()


def test_kill_switch_sharpe_floor_triggered():
    rets = _series(60, mu=-0.005, sd=0.003, seed=1)
    k = evaluate_kill_switch(routed_returns=rets,
                                sharpe_floor=-1.0, dd_floor_pct=-99.0)
    assert k.triggered is True
    assert "Sharpe" in k.reason


def test_kill_switch_dd_breach_triggered():
    rets = [-0.01] * 60
    k = evaluate_kill_switch(routed_returns=rets,
                                sharpe_floor=-99.0, dd_floor_pct=-15.0)
    assert k.triggered is True
    assert "DD" in k.reason


def test_kill_switch_within_bounds_silent():
    rets = _series(80, mu=0.001, sd=0.005, seed=2)
    k = evaluate_kill_switch(routed_returns=rets,
                                sharpe_floor=-3.0, dd_floor_pct=-50.0)
    assert k.triggered is False


def test_advance_gates_pass_when_b2_dominates():
    b  = _series(120, mu=0.0, sd=0.005, seed=3)
    b2 = _series(120, mu=0.005, sd=0.005, seed=4)
    routed = list(b)   # routed=engine B (LEGACY)
    div = [-0.001] * 30   # B2 advantage on divergent days (negative=B beats B2 → flip in promotion code)
    # Note: divergence_outcome is "B - B2"; positive = B beats B2;
    # for B2 to win, divergence_outcome must be negative → mean negative.
    div = [-0.002] * 30
    gates = evaluate_advance_gates(
        n_observations=120,
        b_returns=b, b2_returns=b2,
        routed_returns=routed, divergence_outcomes=div,
        min_shadow_days=60, operator_approval=True,
    )
    failed = [g.name for g in gates if not g.passed]
    assert failed == [], f"unexpected failures: {failed}"


def test_advance_gates_fail_without_operator_approval():
    b  = _series(120, mu=0.0, sd=0.005, seed=3)
    b2 = _series(120, mu=0.005, sd=0.005, seed=4)
    div = [-0.002] * 30
    gates = evaluate_advance_gates(
        n_observations=120,
        b_returns=b, b2_returns=b2,
        routed_returns=list(b), divergence_outcomes=div,
        operator_approval=False,
    )
    failed = [g.name for g in gates if not g.passed]
    assert "operator_approval" in failed


def test_advance_gates_fail_when_b2_loses_divergence():
    b  = _series(120, mu=0.005, sd=0.005, seed=10)
    b2 = _series(120, mu=0.001, sd=0.005, seed=11)
    div = [+0.003] * 30   # B beat B2 on divergent days
    gates = evaluate_advance_gates(
        n_observations=120,
        b_returns=b, b2_returns=b2,
        routed_returns=list(b), divergence_outcomes=div,
        operator_approval=True,
    )
    failed = [g.name for g in gates if not g.passed]
    assert "divergence_quality" in failed


def test_evaluate_kill_switch_recommends_revert():
    bad_routed = [-0.01] * 60
    v = evaluate(
        current_state="SHADOW_COMPARE",
        n_observations=200,
        b_returns=[0.0]*200, b2_returns=[0.0]*200,
        routed_returns=bad_routed, divergence_outcomes=[],
        sharpe_floor=-99.0, dd_floor_pct=-15.0,
        operator_approval=True,
    )
    assert v.action == "REVERT"
    assert v.recommended_state == "LEGACY"
    assert v.kill_switch is not None and v.kill_switch.triggered


def test_evaluate_legacy_advance_to_shadow_when_clean():
    b  = _series(120, mu=0.0, sd=0.005, seed=21)
    b2 = _series(120, mu=0.005, sd=0.005, seed=22)
    div = [-0.002] * 30
    v = evaluate(
        current_state="LEGACY",
        n_observations=120,
        b_returns=b, b2_returns=b2,
        routed_returns=list(b), divergence_outcomes=div,
        operator_approval=True,
    )
    assert v.action == "ADVANCE"
    assert v.recommended_state == "SHADOW_COMPARE"


def test_evaluate_holds_at_terminal_full_b2():
    b  = _series(120, mu=0.0, sd=0.005, seed=31)
    b2 = _series(120, mu=0.005, sd=0.005, seed=32)
    div = [-0.002] * 30
    v = evaluate(
        current_state="FULL_B2",
        n_observations=120,
        b_returns=b, b2_returns=b2,
        routed_returns=list(b2), divergence_outcomes=div,
        operator_approval=True,
    )
    # Either HOLD with note about terminal state, or all gates pass
    # but no next state available
    assert v.action == "HOLD"
    assert "terminal" in v.note.lower() or v.recommended_state == "FULL_B2"


def test_advisory_invariants():
    v = evaluate(
        current_state="LEGACY",
        n_observations=10,
        b_returns=[], b2_returns=[],
        routed_returns=[], divergence_outcomes=[],
        operator_approval=False,
    )
    d = v.to_dict()
    assert d["advisory_only"] is True
    assert d["auto_promote"] is False
