"""Tests for b2_v2_comparison pure analytics."""

from __future__ import annotations

import math
from datetime import date, timedelta

import pytest

from src.research.b2_v2_comparison import (
    REGIMES,
    TAIL_GUARD_EDGE_MIN_BPS,
    compute_all,
    divergence_metrics,
    extract_divergence,
    metrics_by_regime,
    stability_check,
    tail_comparison,
    verdict,
)


def _row(
    *,
    d: date,
    b2: str = "FLAT",
    v2: str = "FLAT",
    fwd: float | None = None,
    fwd5: float | None = None,
    b2_regime: str | None = "DIRECTIONAL",
    v2_regime: str | None = None,
) -> dict:
    return {
        "as_of_date": d,
        "instrument": "SPY",
        "b2_signal": b2,
        "v2_signal": v2,
        "b2_regime": b2_regime,
        "v2_regime": v2_regime if v2_regime is not None else b2_regime,
        "fwd_return_1d": fwd,
        "fwd_return_5d": fwd5,
        "b2_trend": 0.0,
        "v2_trend": 0.0,
    }


def _seq(n: int, start: date | None = None) -> list[date]:
    base = start or date(2025, 1, 1)
    return [base + timedelta(days=i) for i in range(n)]


# ---------------------------------------------------------------------------
# Part 1 — extract_divergence
# ---------------------------------------------------------------------------

def test_extract_divergence_classifies_directions():
    days = _seq(2)
    rows = [
        _row(d=days[0], b2="FLAT", v2="LONG", fwd=0.01),
        _row(d=days[1], b2="LONG", v2="FLAT", fwd=-0.005),
    ]
    out = extract_divergence(rows)
    assert len(out) == 2
    assert out[0]["divergence_class"] == "B2_FLAT_V2_LONG"
    assert out[0]["b2_return"] == 0.0
    assert out[0]["v2_return"] == pytest.approx(0.01)
    assert out[0]["delta"] == pytest.approx(0.01)
    assert out[1]["divergence_class"] == "B2_LONG_V2_FLAT"
    assert out[1]["b2_return"] == pytest.approx(-0.005)
    assert out[1]["v2_return"] == 0.0
    assert out[1]["delta"] == pytest.approx(0.005)


def test_extract_divergence_skips_unrealized():
    days = _seq(2)
    rows = [
        _row(d=days[0], b2="FLAT", v2="LONG", fwd=None),
        _row(d=days[1], b2="LONG", v2="FLAT", fwd=0.01),
    ]
    out = extract_divergence(rows)
    assert len(out) == 1
    assert out[0]["as_of_date"] == days[1]


def test_extract_divergence_skips_agreement():
    days = _seq(3)
    rows = [
        _row(d=days[0], b2="LONG", v2="LONG", fwd=0.01),
        _row(d=days[1], b2="FLAT", v2="FLAT", fwd=-0.01),
        _row(d=days[2], b2="FLAT", v2="LONG", fwd=0.01),
    ]
    out = extract_divergence(rows)
    assert len(out) == 1
    assert out[0]["divergence_class"] == "B2_FLAT_V2_LONG"


def test_extract_divergence_skips_invalid_signals():
    days = _seq(2)
    rows = [
        _row(d=days[0], b2="LONG", v2="WAT", fwd=0.01),
        _row(d=days[1], b2=None, v2="LONG", fwd=0.01),
    ]
    out = extract_divergence(rows)
    assert out == []


# ---------------------------------------------------------------------------
# Part 2 — divergence_metrics + impact_weighted_edge
# ---------------------------------------------------------------------------

def test_divergence_metrics_known_inputs():
    days = _seq(4)
    rows = [
        _row(d=days[0], b2="FLAT", v2="LONG", fwd=0.02, fwd5=0.05),
        _row(d=days[1], b2="LONG", v2="FLAT", fwd=-0.01, fwd5=-0.02),
        _row(d=days[2], b2="FLAT", v2="LONG", fwd=-0.015, fwd5=0.0),
        _row(d=days[3], b2="LONG", v2="FLAT", fwd=0.01, fwd5=0.0),
    ]
    div = extract_divergence(rows)
    m = divergence_metrics(div)
    assert m["n_divergent_days"] == 4
    assert m["n_b2_flat_v2_long"] == 2
    assert m["n_b2_long_v2_flat"] == 2
    # Wins: day0 delta=+0.02, day1 delta=+0.01, day2 delta=-0.015, day3 delta=-0.01
    assert m["win_rate_v2_vs_b2_pct"] == pytest.approx(50.0)
    expected_avg_bps = ((0.02 + 0.01 - 0.015 - 0.01) / 4) * 1e4
    assert m["avg_return_diff_1d_bps"] == pytest.approx(expected_avg_bps, rel=1e-3)
    # Avoided: day1 (B2 LONG lost 0.01) → 100 bps
    assert m["avoided_losses_count"] == 1
    assert m["avoided_losses_avg_bps"] == pytest.approx(100.0, rel=1e-3)
    # New losses: day2 (V2 LONG lost 0.015) → 150 bps
    assert m["new_losses_count"] == 1
    assert m["new_losses_avg_bps"] == pytest.approx(150.0, rel=1e-3)


def test_divergence_metrics_empty():
    m = divergence_metrics([])
    assert m["n_divergent_days"] == 0
    assert m["win_rate_v2_vs_b2_pct"] is None
    assert m["impact_weighted_edge"] is None
    assert m["avoided_losses_count"] == 0


def test_impact_weighted_edge_known_inputs():
    days = _seq(2)
    rows = [
        _row(d=days[0], b2="FLAT", v2="LONG", fwd=0.02),    # delta +0.02, |b2|+|v2|=0.02
        _row(d=days[1], b2="LONG", v2="FLAT", fwd=-0.01),   # delta +0.01, |b2|+|v2|=0.01
    ]
    div = extract_divergence(rows)
    m = divergence_metrics(div)
    # sum_delta = 0.03 ; sum_abs = 0.03 → impact-weighted = 1.0
    assert m["impact_weighted_edge"] == pytest.approx(1.0, abs=1e-6)


def test_impact_weighted_edge_zero_denominator():
    # Both engines FLAT cannot diverge → no rows. Construct a divergent row
    # with fwd=0 so abs sums are zero, impact-weighted must be None.
    days = _seq(1)
    rows = [_row(d=days[0], b2="FLAT", v2="LONG", fwd=0.0)]
    div = extract_divergence(rows)
    m = divergence_metrics(div)
    assert m["n_divergent_days"] == 1
    assert m["impact_weighted_edge"] is None


# ---------------------------------------------------------------------------
# Part 2b — metrics_by_regime
# ---------------------------------------------------------------------------

def test_metrics_by_regime_partitions_correctly():
    days = _seq(6)
    rows = [
        _row(d=days[0], b2="FLAT", v2="LONG", fwd=0.01, b2_regime="STRESS"),
        _row(d=days[1], b2="FLAT", v2="LONG", fwd=0.02, b2_regime="STRESS"),
        _row(d=days[2], b2="LONG", v2="FLAT", fwd=-0.01, b2_regime="DIRECTIONAL"),
        _row(d=days[3], b2="FLAT", v2="LONG", fwd=0.03, b2_regime="DIRECTIONAL"),
        _row(d=days[4], b2="LONG", v2="FLAT", fwd=0.005, b2_regime="NEUTRAL"),
        # agreement, should be excluded entirely
        _row(d=days[5], b2="LONG", v2="LONG", fwd=0.01, b2_regime="DIRECTIONAL"),
    ]
    div = extract_divergence(rows)
    top = divergence_metrics(div)
    by_regime = metrics_by_regime(div)

    bucket_total = sum(
        by_regime[r.lower()]["n_divergent_days"] for r in REGIMES
    )
    assert bucket_total == top["n_divergent_days"] == 5
    assert by_regime["stress"]["n_divergent_days"] == 2
    assert by_regime["directional"]["n_divergent_days"] == 2
    assert by_regime["neutral"]["n_divergent_days"] == 1


def test_metrics_by_regime_empty_bucket():
    days = _seq(2)
    rows = [
        _row(d=days[0], b2="FLAT", v2="LONG", fwd=0.01, b2_regime="STRESS"),
        _row(d=days[1], b2="LONG", v2="FLAT", fwd=-0.005, b2_regime="STRESS"),
    ]
    div = extract_divergence(rows)
    by_regime = metrics_by_regime(div)
    assert by_regime["neutral"]["n_divergent_days"] == 0
    assert by_regime["neutral"]["impact_weighted_edge"] is None
    assert by_regime["directional"]["n_divergent_days"] == 0


# ---------------------------------------------------------------------------
# Part 3 — tail_comparison
# ---------------------------------------------------------------------------

def test_tail_comparison_known_inputs():
    days = _seq(10)
    # Both LONG every day — same returns → tail deltas all zero
    rets = [-0.05, -0.04, -0.03, -0.02, -0.01, 0.01, 0.02, 0.03, 0.04, 0.05]
    rows = [
        _row(d=days[i], b2="LONG", v2="LONG", fwd=rets[i])
        for i in range(10)
    ]
    out = tail_comparison(rows)
    assert out["b2"]["n"] == 10
    assert out["v2"]["n"] == 10
    assert out["b2"]["worst_5_losses_bps"] == out["v2"]["worst_5_losses_bps"]
    assert out["b2"]["p95_loss_bps"] == out["v2"]["p95_loss_bps"]
    assert out["tail_delta_p95_bps"] == 0.0


def test_tail_comparison_empty():
    out = tail_comparison([])
    assert out["b2"]["n"] == 0
    assert out["tail_delta_p95_bps"] is None


# ---------------------------------------------------------------------------
# Part 4 — stability_check
# ---------------------------------------------------------------------------

def test_stability_check_first_vs_second():
    # Construct 80 divergent days. First 40: V2 wins by ~0 bps. Last 40: V2 wins by ~+50 bps.
    days = _seq(80)
    rows: list[dict] = []
    for i in range(40):
        # neutral: alternate so deltas average ~0
        rows.append(_row(d=days[i], b2="FLAT", v2="LONG", fwd=0.0001 if i % 2 else -0.0001))
    for i in range(40, 80):
        rows.append(_row(d=days[i], b2="FLAT", v2="LONG", fwd=0.005))
    div = extract_divergence(rows)
    s = stability_check(div)
    assert s["first_half_vs_second_half"]["trend"] == "IMPROVING"
    assert s["last_30_vs_prior_30"]["n_last"] == 30
    assert s["last_30_vs_prior_30"]["n_prior"] == 30


def test_stability_check_insufficient():
    days = _seq(3)
    rows = [
        _row(d=days[i], b2="FLAT", v2="LONG", fwd=0.001)
        for i in range(3)
    ]
    div = extract_divergence(rows)
    s = stability_check(div)
    assert s["last_30_vs_prior_30"]["trend"] == "INSUFFICIENT"


# ---------------------------------------------------------------------------
# Part 5 — verdict pipeline
# ---------------------------------------------------------------------------

def _v2_better_inputs():
    """Build inputs that pass V2_BETTER conditions cleanly."""
    days = _seq(40)
    rows: list[dict] = []
    for i in range(40):
        # Big positive deltas, V2 LONG and wins
        rows.append(_row(d=days[i], b2="FLAT", v2="LONG", fwd=0.003))
    div = extract_divergence(rows)
    metrics = divergence_metrics(div)
    tail = tail_comparison(rows)
    stab = stability_check(div)
    return metrics, tail, stab


def test_verdict_v2_better():
    metrics, tail, stab = _v2_better_inputs()
    v = verdict(metrics, tail, stab)
    assert v["verdict"] == "V2_BETTER"
    assert v["readiness"] in ("REVIEW", "STRONG_CANDIDATE")
    assert 0.0 <= v["confidence"] <= 1.0
    assert v["tail_guard_triggered"] is False


def test_verdict_b2_better():
    days = _seq(40)
    # B2 LONG winning every day, V2 FLAT → delta negative
    rows = [
        _row(d=days[i], b2="LONG", v2="FLAT", fwd=0.003)
        for i in range(40)
    ]
    div = extract_divergence(rows)
    metrics = divergence_metrics(div)
    tail = tail_comparison(rows)
    stab = stability_check(div)
    v = verdict(metrics, tail, stab)
    assert v["verdict"] == "B2_BETTER"
    assert v["readiness"] == "NOT_READY"


def test_verdict_inconclusive_small_n():
    days = _seq(5)
    rows = [
        _row(d=days[i], b2="FLAT", v2="LONG", fwd=0.05)
        for i in range(5)
    ]
    div = extract_divergence(rows)
    metrics = divergence_metrics(div)
    tail = tail_comparison(rows)
    stab = stability_check(div)
    v = verdict(metrics, tail, stab)
    assert v["verdict"] == "INCONCLUSIVE"
    assert v["readiness"] == "NOT_READY"


def test_verdict_confidence_bounds():
    metrics, tail, stab = _v2_better_inputs()
    v = verdict(metrics, tail, stab)
    assert 0.0 <= v["confidence"] <= 1.0


# ---------------------------------------------------------------------------
# Part 4b — tail-sensitivity guard
# ---------------------------------------------------------------------------

def _build_metrics_tail_stab(
    *,
    edge_bps: float,
    cum_pct: float,
    n: int,
    tail_p99_delta: float | None,
    second_half_edge_bps: float | None = None,
):
    """Synthesize the inputs verdict() needs without going through extract_divergence."""
    metrics = {
        "n_divergent_days": n,
        "n_b2_flat_v2_long": n,
        "n_b2_long_v2_flat": 0,
        "win_rate_v2_vs_b2_pct": 60.0,
        "avg_return_diff_1d_bps": edge_bps,
        "avg_return_diff_5d_bps": edge_bps,
        "cumulative_return_diff_pct": cum_pct,
        "avoided_losses_count": 0,
        "avoided_losses_avg_bps": None,
        "new_losses_count": 0,
        "new_losses_avg_bps": None,
        "impact_weighted_edge": 0.1,
    }
    tail = {
        "b2": {"n": n, "p95_loss_bps": -50.0, "p99_loss_bps": -100.0,
               "worst_5_losses_bps": []},
        "v2": {"n": n, "p95_loss_bps": -50.0,
               "p99_loss_bps": (-100.0 - (tail_p99_delta or 0))
               if tail_p99_delta is not None else None,
               "worst_5_losses_bps": []},
        "tail_delta_p95_bps": 0.0,
        "tail_delta_p99_bps": tail_p99_delta,
    }
    sh_edge = second_half_edge_bps if second_half_edge_bps is not None else edge_bps
    stab = {
        "first_half_vs_second_half": {
            "first_half_edge_bps": edge_bps,
            "second_half_edge_bps": sh_edge,
            "n_first": n // 2, "n_second": n // 2,
            "trend": "STABLE",
        },
        "last_30_vs_prior_30": {
            "last_30_edge_bps": edge_bps,
            "prior_30_edge_bps": edge_bps,
            "n_last": 30, "n_prior": 30,
            "trend": "STABLE",
        },
    }
    return metrics, tail, stab


def test_tail_guard_downgrades_v2_better_to_inconclusive():
    # Edge passes V2_BETTER (≥5 bps) but is below 10 bps guard threshold;
    # p99 worsens.
    metrics, tail, stab = _build_metrics_tail_stab(
        edge_bps=6.0, cum_pct=1.0, n=40, tail_p99_delta=-5.0,
    )
    v = verdict(metrics, tail, stab)
    assert v["base_verdict_before_guard"] == "V2_BETTER"
    assert v["tail_guard_triggered"] is True
    assert v["verdict"] == "INCONCLUSIVE"
    assert v["confidence"] <= 0.5
    assert v["readiness"] == "NOT_READY"
    assert v["tail_guard_reason"] is not None


def test_tail_guard_does_not_upgrade():
    # B2_BETTER with V2 p99 better — guard must not trigger (p99 not worse).
    metrics, tail, stab = _build_metrics_tail_stab(
        edge_bps=-10.0, cum_pct=-2.0, n=40, tail_p99_delta=+5.0,
    )
    v = verdict(metrics, tail, stab)
    assert v["base_verdict_before_guard"] == "B2_BETTER"
    assert v["verdict"] == "B2_BETTER"
    assert v["tail_guard_triggered"] is False


def test_tail_guard_no_trigger_when_edge_large():
    # Edge ≥ guard threshold → guard skips even if p99 worsens.
    metrics, tail, stab = _build_metrics_tail_stab(
        edge_bps=TAIL_GUARD_EDGE_MIN_BPS + 0.1,
        cum_pct=1.0, n=40, tail_p99_delta=-20.0,
    )
    v = verdict(metrics, tail, stab)
    assert v["tail_guard_triggered"] is False


def test_tail_guard_no_trigger_when_p99_better():
    # p99 better → guard skips even if edge tiny.
    metrics, tail, stab = _build_metrics_tail_stab(
        edge_bps=1.0, cum_pct=0.1, n=40, tail_p99_delta=+5.0,
    )
    v = verdict(metrics, tail, stab)
    assert v["tail_guard_triggered"] is False


def test_tail_guard_downgrades_inconclusive_to_b2_better():
    # Edge below V2_BETTER threshold, so base = INCONCLUSIVE; p99 worsens
    # and edge below guard threshold → guard fires → B2_BETTER.
    metrics, tail, stab = _build_metrics_tail_stab(
        edge_bps=2.0, cum_pct=0.1, n=40, tail_p99_delta=-5.0,
    )
    v = verdict(metrics, tail, stab)
    assert v["base_verdict_before_guard"] == "INCONCLUSIVE"
    assert v["tail_guard_triggered"] is True
    assert v["verdict"] == "B2_BETTER"


def test_verdict_pipeline_order():
    """Guard runs after base verdict and tightens readiness."""
    metrics, tail, stab = _build_metrics_tail_stab(
        edge_bps=6.0, cum_pct=1.0, n=40, tail_p99_delta=-5.0,
    )
    v = verdict(metrics, tail, stab)
    assert v["base_verdict_before_guard"] == "V2_BETTER"
    assert v["verdict"] == "INCONCLUSIVE"
    # Readiness must reflect post-guard verdict, not base
    assert v["readiness"] == "NOT_READY"


# ---------------------------------------------------------------------------
# compute_all bundle
# ---------------------------------------------------------------------------

def test_compute_all_returns_full_bundle():
    days = _seq(40)
    rows = [
        _row(d=days[i], b2="FLAT", v2="LONG", fwd=0.002)
        for i in range(40)
    ]
    bundle = compute_all(rows)
    assert bundle["n_input_rows"] == 40
    assert bundle["n_divergent_rows"] == 40
    assert "metrics" in bundle
    assert "metrics_by_regime" in bundle
    assert "tail" in bundle
    assert "stability" in bundle
    assert "verdict" in bundle
    assert "thresholds" in bundle
    # Thresholds frozen — bundle exposes them for UI display
    assert bundle["thresholds"]["tail_guard_edge_min_bps"] == TAIL_GUARD_EDGE_MIN_BPS


def test_compute_all_empty_input():
    bundle = compute_all([])
    assert bundle["n_input_rows"] == 0
    assert bundle["n_divergent_rows"] == 0
    assert bundle["verdict"]["verdict"] == "INCONCLUSIVE"
    assert bundle["verdict"]["readiness"] == "NOT_READY"
