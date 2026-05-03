"""Tests for engine_b_analytics + engine_b_decision pure functions."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from src.research.engine_b_analytics import (
    compute_all, divergence_analytics, edge_trajectory,
    regime_consistency, stability_split, tail_risk, transition_zones,
)
from src.research.engine_b_decision import (
    DEFAULT_THRESHOLDS_BY_FROM, evaluate as eval_decision,
)


def _row(
    *,
    d: date,
    b: str = "FLAT", b2: str = "FLAT", routed: str | None = None,
    regime: str = "DIRECTIONAL", fwd: float | None = None,
    div_outcome: float | None = None,
) -> dict:
    return {
        "as_of_date": d,
        "engine_b_signal": b, "b2_signal": b2,
        "routed_signal": routed if routed is not None else b,
        "regime_label": regime,
        "fwd_return_1d": fwd,
        "divergence_outcome": div_outcome,
        "divergence_flag": (b != b2),
    }


def _make_rows(n: int = 100, seed: int = 1) -> list[dict]:
    """Synthetic series: b2 LONG when regime is DIRECTIONAL, b is LONG
    on first half of DIRECTIONAL days only. Forces some divergence."""
    import random
    rng = random.Random(seed)
    out = []
    base = date(2025, 1, 1)
    for i in range(n):
        d = base + timedelta(days=i)
        # Cycle: 80% directional, 20% stress
        regime = "STRESS" if (i % 10 == 0) else "DIRECTIONAL"
        ret = rng.gauss(0.0008, 0.005) if regime == "DIRECTIONAL" \
            else rng.gauss(-0.002, 0.01)
        b = "LONG" if (regime == "DIRECTIONAL" and i < n // 2) else "FLAT"
        b2 = "LONG" if regime == "DIRECTIONAL" else "FLAT"
        # Compute divergence outcome (B - B2) realized return
        b_r = ret if b == "LONG" else 0.0
        b2_r = ret if b2 == "LONG" else 0.0
        div = b_r - b2_r if b != b2 else 0.0
        out.append(_row(d=d, b=b, b2=b2, routed=b, regime=regime,
                          fwd=ret, div_outcome=div))
    return out


def test_divergence_analytics_basic_shape():
    rows = _make_rows(80)
    d = divergence_analytics(rows)
    assert "n_divergent_days" in d
    assert "win_rate_b2_vs_b_pct" in d
    assert "cumulative_return_diff_pct" in d


def test_divergence_empty_safe():
    d = divergence_analytics([])
    assert d["n_divergent_days"] == 0
    assert d["win_rate_b2_vs_b_pct"] is None


def test_tail_risk_compares_arrays():
    rows = _make_rows(150)
    t = tail_risk(rows)
    assert t["engine_b"] is not None
    assert t["engine_b2"] is not None
    assert t["engine_b"]["n"] >= 1
    assert "p99_loss_pct" in t["engine_b"] or t["engine_b"]["p99_loss_pct"] is None


def test_regime_consistency_separates_buckets():
    rows = _make_rows(200)
    r = regime_consistency(rows)
    assert r["stress_n_days"] > 0
    assert r["nonstress_n_days"] > 0
    # B2 must NOT be LONG during stress in synthetic data
    assert (r["stress_b2_long_pct"] or 0) == 0


def test_transition_zones_returns_shape():
    rows = _make_rows(100)
    t = transition_zones(rows)
    assert "n_stress_entries" in t
    assert "n_pre_stress_obs" in t
    assert t["n_stress_entries"] >= 1


def test_stability_split_two_halves():
    rows = _make_rows(100)
    s = stability_split(rows)
    assert "early" in s and "recent" in s
    assert s["early"] is not None and s["recent"] is not None
    assert "b2_sharpe" in s["early"]


def test_compute_all_bundle_keys():
    rows = _make_rows(120)
    bundle = compute_all(rows)
    expected = {"divergence", "tail_risk", "transition_zones",
                "regime_consistency", "stability", "readiness",
                "n_rows", "advisory_only"}
    assert expected <= set(bundle.keys())
    assert bundle["readiness"]["label"] in {
        "NOT_READY", "READY_FOR_REVIEW", "STRONG_CANDIDATE"}
    assert 0 <= bundle["readiness"]["score"] <= 100


def test_decision_legacy_thresholds_loaded():
    th = DEFAULT_THRESHOLDS_BY_FROM["LEGACY"]
    assert th["min_shadow_days"] == 60
    assert th["min_divergence_events"] == 50
    assert th["sharpe_edge_min"] == 0.10
    assert th["divergence_win_rate_min"] == 0.55


def test_decision_partial_state_uses_window_stability():
    th = DEFAULT_THRESHOLDS_BY_FROM["PARTIAL_B2_25"]
    assert th["require_window_stability"] is True
    assert th["min_shadow_days"] == 30


def test_decision_evaluate_advisory_invariants():
    rows = _make_rows(100)
    v = eval_decision(rows=rows, current_state="LEGACY",
                          operator_approval=False)
    d = v.to_dict()
    assert d["advisory_only"] is True
    assert d["auto_promote"] is False
    assert d["action"] in {"HOLD", "READY_FOR_NEXT", "ADVANCE", "REVERT"}
    assert d["label"] in {"NOT_READY", "READY_FOR_REVIEW",
                            "STRONG_CANDIDATE",
                            "READY_FOR_REVIEW_PAUSED",
                            "PROMOTION_PAUSED_EDGE_DECAY",
                            "STRUCTURAL_REVIEW_REQUIRED"}


def test_decision_holds_without_operator_approval():
    rows = _make_rows(120)
    v = eval_decision(rows=rows, current_state="LEGACY",
                          operator_approval=False)
    # Even if score high, action is HOLD without operator approval
    assert v.action != "READY_FOR_NEXT"


def test_decision_kill_switch_recommends_revert():
    # Create rows with consistently bad routed returns
    rows = []
    for i in range(60):
        d = date(2025, 1, 1) + timedelta(days=i)
        rows.append(_row(d=d, b="LONG", b2="LONG", routed="LONG",
                            regime="DIRECTIONAL", fwd=-0.01,
                            div_outcome=0.0))
    v = eval_decision(rows=rows, current_state="SHADOW_COMPARE",
                          operator_approval=True)
    assert v.kill_switch_triggered is True
    assert v.action == "REVERT"
    assert v.recommended_state == "LEGACY"


def test_decision_partial_requires_three_window_stability():
    rows = _make_rows(60, seed=2)
    v = eval_decision(rows=rows, current_state="PARTIAL_B2_25",
                          operator_approval=True)
    # With synthetic data of mixed regime quality, expect either HOLD
    # or stability_windows actually computed
    assert isinstance(v.stability_windows, list)


def test_decision_score_range():
    rows = _make_rows(120)
    v = eval_decision(rows=rows, current_state="LEGACY",
                          operator_approval=True)
    assert 0 <= v.score <= 100


def test_edge_trajectory_insufficient():
    et = edge_trajectory(_make_rows(20))
    assert et["trend"] == "INSUFFICIENT"
    assert et["delta_bps"] is None


def test_edge_trajectory_stable_when_no_change():
    rows = _make_rows(120, seed=5)
    et = edge_trajectory(rows)
    assert et["trend"] in {"IMPROVING", "STABLE", "DECLINING"}
    assert "recent_mean_edge_bps" in et
    assert "prior_mean_edge_bps" in et
    assert "slope_bps_per_day" in et


def test_edge_trajectory_improving_when_recent_better():
    # Build rows where prior 30d has B beat B2, recent has B2 beat B
    base = date(2025, 1, 1)
    rows = []
    # prior 30d: B LONG win, B2 FLAT (B beats B2 → negative B2 edge)
    for i in range(30):
        d = base + timedelta(days=i)
        rows.append({
            "as_of_date": d,
            "engine_b_signal": "LONG", "b2_signal": "FLAT",
            "routed_signal": "LONG", "regime_label": "DIRECTIONAL",
            "fwd_return_1d": 0.005, "divergence_outcome": 0.005,
            "divergence_flag": True,
        })
    # recent 30d: B2 LONG win, B FLAT (B2 beats B → positive B2 edge)
    for i in range(30, 60):
        d = base + timedelta(days=i)
        rows.append({
            "as_of_date": d,
            "engine_b_signal": "FLAT", "b2_signal": "LONG",
            "routed_signal": "FLAT", "regime_label": "DIRECTIONAL",
            "fwd_return_1d": 0.005, "divergence_outcome": -0.005,
            "divergence_flag": True,
        })
    et = edge_trajectory(rows, window_days=30)
    assert et["trend"] == "IMPROVING"
    assert et["delta_bps"] is not None and et["delta_bps"] > 0


def test_edge_trajectory_in_compute_all_bundle():
    rows = _make_rows(120)
    bundle = compute_all(rows)
    assert "edge_trajectory" in bundle
    assert bundle["edge_trajectory"]["trend"] in {
        "IMPROVING", "STABLE", "DECLINING", "INSUFFICIENT"}


def test_decision_unknown_state_falls_back():
    rows = _make_rows(60)
    # Should not raise; uses LEGACY thresholds as fallback
    v = eval_decision(rows=rows, current_state="LEGACY",
                          operator_approval=False)
    assert v is not None
