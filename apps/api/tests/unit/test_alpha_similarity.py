"""SYSTEM-ALPHA-8 — similarity engine unit tests.

Deterministic: pure functions on vectors + synthetic HistoricalPoint lists.
No DB, no network.
"""

from __future__ import annotations

from apps.api.src.alpha.similarity import (
    FEATURE_KEYS, MIN_MULTIPLIER, MIN_NEIGHBORS, TOP_K,
    HistoricalPoint, _l2, _multiplier_from, build_current_vector,
    evaluate_similarity,
)


# ---------------------------------------------------------------------------
# Vector building — determinism + bounds
# ---------------------------------------------------------------------------

def test_vector_has_all_features():
    v = build_current_vector(
        regime="neutral", engine="B", exploratory=False,
        gates_passed=2, context_values={},
    )
    assert len(v) == len(FEATURE_KEYS)
    for x in v:
        assert 0.0 <= x <= 1.0


def test_vector_is_deterministic():
    kwargs = dict(
        regime="stress", engine="A", exploratory=True,
        gates_passed=3,
        context_values={"credit_stable": True, "vol_elevated": True},
        catalyst={"event_risk_score": 0.6},
        data_quality={"confidence": 0.8},
    )
    v1 = build_current_vector(**kwargs)
    v2 = build_current_vector(**kwargs)
    assert v1 == v2


def test_vector_normalizes_gates_passed():
    # gates_passed max = 4 → 4/4 = 1.0
    v_max = build_current_vector(
        regime="neutral", engine="B", exploratory=False,
        gates_passed=4, context_values={},
    )
    # 7 should clamp to 4 → 1.0
    v_over = build_current_vector(
        regime="neutral", engine="B", exploratory=False,
        gates_passed=7, context_values={},
    )
    assert v_max == v_over


def test_regime_is_one_hot():
    v = build_current_vector(
        regime="stress", engine="A", exploratory=False,
        gates_passed=0, context_values={},
    )
    keys = list(FEATURE_KEYS)
    rs = v[keys.index("regime_stress")]
    rd = v[keys.index("regime_directional")]
    rn = v[keys.index("regime_neutral")]
    assert rs == 1.0 and rd == 0.0 and rn == 0.0


# ---------------------------------------------------------------------------
# _l2
# ---------------------------------------------------------------------------

def test_l2_zero_for_identical():
    v = [0.1, 0.2, 0.3]
    assert _l2(v, v) == 0.0


def test_l2_triangle():
    a = [0.0, 0.0]
    b = [3.0, 4.0]
    assert abs(_l2(a, b) - 5.0) < 1e-9


# ---------------------------------------------------------------------------
# _multiplier_from — never increases, floor
# ---------------------------------------------------------------------------

def test_multiplier_no_reduction_when_positive():
    assert _multiplier_from(0.5, 0.6) == 1.0


def test_multiplier_mild_reduction():
    m = _multiplier_from(-0.1, 0.5)
    assert m == 0.85
    assert m < 1.0


def test_multiplier_moderate_reduction():
    m = _multiplier_from(-0.3, 0.4)
    assert m == 0.7


def test_multiplier_floor_on_strong_loss():
    m = _multiplier_from(-1.0, 0.2)
    assert m == MIN_MULTIPLIER
    assert m >= 0.5


def test_multiplier_floor_enforced_even_on_extreme():
    # Contract: never below MIN_MULTIPLIER
    for w in (-5.0, -100.0, -0.6):
        assert _multiplier_from(w, 0.1) >= MIN_MULTIPLIER


def test_multiplier_never_exceeds_one():
    for w in (-2.0, -0.1, 0.0, 0.5, 5.0):
        for wr in (0.0, 0.3, 0.5, 0.8, 1.0):
            assert _multiplier_from(w, wr) <= 1.0


# ---------------------------------------------------------------------------
# evaluate_similarity — fallback + neighbor math
# ---------------------------------------------------------------------------

def _mk_hist(n: int, outcome: float, vec: list[float] | None = None
             ) -> list[HistoricalPoint]:
    base = vec or [0.5] * len(FEATURE_KEYS)
    return [
        HistoricalPoint(vector=list(base), outcome_pct=outcome,
                         engine="B", exploratory=False)
        for _ in range(n)
    ]


def test_fallback_when_below_min_neighbors():
    cur = [0.5] * len(FEATURE_KEYS)
    hist = _mk_hist(n=MIN_NEIGHBORS - 1, outcome=-1.0)
    r = evaluate_similarity(cur, hist)
    assert r.matched is False
    assert r.multiplier == 1.0
    assert r.n_neighbors == 0


def test_fallback_when_empty():
    r = evaluate_similarity([0.5] * len(FEATURE_KEYS), [])
    assert r.matched is False
    assert r.multiplier == 1.0


def test_reduces_when_peers_lost_money():
    cur = [0.5] * len(FEATURE_KEYS)
    hist = _mk_hist(n=25, outcome=-2.0)
    r = evaluate_similarity(cur, hist)
    assert r.matched is True
    assert r.multiplier < 1.0
    assert r.multiplier >= MIN_MULTIPLIER
    assert r.n_neighbors >= MIN_NEIGHBORS
    assert r.avg_return_pct < 0


def test_no_reduction_when_peers_profitable():
    cur = [0.5] * len(FEATURE_KEYS)
    hist = _mk_hist(n=30, outcome=+1.5)
    r = evaluate_similarity(cur, hist)
    assert r.matched is False
    assert r.multiplier == 1.0
    assert r.win_rate == 1.0


def test_drops_far_neighbors_beyond_max_distance():
    cur = [0.0] * len(FEATURE_KEYS)
    far_vec = [1.0] * len(FEATURE_KEYS)
    hist = _mk_hist(n=25, outcome=-2.0, vec=far_vec)
    # Far distance > MAX_DISTANCE (sqrt(12) ≈ 3.46) → should fallback
    r = evaluate_similarity(cur, hist)
    assert r.matched is False
    assert r.multiplier == 1.0


def test_top_k_cap():
    cur = [0.5] * len(FEATURE_KEYS)
    hist = _mk_hist(n=TOP_K * 3, outcome=-1.0)
    r = evaluate_similarity(cur, hist)
    assert r.n_neighbors == TOP_K


def test_avg_distance_reported():
    cur = [0.5] * len(FEATURE_KEYS)
    hist = _mk_hist(n=25, outcome=-1.0)
    r = evaluate_similarity(cur, hist)
    assert r.avg_distance == 0.0
    assert r.top_similarity == 1.0


def test_multiplier_never_exceeds_one_via_evaluate():
    cur = [0.5] * len(FEATURE_KEYS)
    # Even very positive outcomes must not raise size
    hist = _mk_hist(n=40, outcome=+50.0)
    r = evaluate_similarity(cur, hist)
    assert r.multiplier <= 1.0
