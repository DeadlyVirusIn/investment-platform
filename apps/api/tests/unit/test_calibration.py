"""MP2B.1 — unit tests for pure calibration math. DB-free."""

from __future__ import annotations

from apps.api.src.analytics.calibration import (
    MIN_CALIBRATION_SAMPLES,
    brier_score,
    expected_calibration_error,
    reliability_bins,
)


def _calibrated(per: int = 20):
    """Perfectly calibrated: for each predicted p, exactly p fraction win."""
    pairs = []
    for p in (0.1, 0.3, 0.5, 0.7, 0.9):
        wins = round(p * per)
        pairs += [(p, True)] * wins + [(p, False)] * (per - wins)
    return pairs  # 100 items, 5 distinct bins


def test_perfectly_calibrated_ece_near_zero():
    pairs = _calibrated()
    r = expected_calibration_error(pairs)
    assert r["note"] is None
    assert r["n"] == 100
    assert r["ece"] < 0.02  # essentially perfect


def test_overconfident_positive_gap():
    # predict 0.9, observe 0.5 -> overconfident, gap +0.4
    pairs = [(0.9, True)] * 25 + [(0.9, False)] * 25
    rel = reliability_bins(pairs)
    b9 = next(b for b in rel["bins"] if b["count"] > 0)
    assert b9["mean_predicted"] == 0.9
    assert b9["observed_rate"] == 0.5
    assert b9["gap"] == 0.4  # positive => overconfident
    assert expected_calibration_error(pairs)["ece"] == 0.4


def test_underconfident_negative_gap():
    # predict 0.2, observe 0.6 -> underconfident, gap -0.4
    pairs = [(0.2, True)] * 30 + [(0.2, False)] * 20
    rel = reliability_bins(pairs)
    b = next(b for b in rel["bins"] if b["count"] > 0)
    assert b["mean_predicted"] == 0.2
    assert b["observed_rate"] == 0.6
    assert b["gap"] == -0.4  # negative => underconfident
    assert expected_calibration_error(pairs)["ece"] == 0.4


def test_brier_known_value():
    # 50 @ p=0.5, half win -> each term (0.5)^2 = 0.25 -> brier 0.25
    pairs = [(0.5, i % 2 == 0) for i in range(50)]
    r = brier_score(pairs)
    assert r["note"] is None
    assert r["n"] == 50
    assert r["brier_score"] == 0.25


def test_brier_perfect_is_zero():
    pairs = [(1.0, True)] * 30 + [(0.0, False)] * 30
    assert brier_score(pairs)["brier_score"] == 0.0


def test_insufficient_data_gate():
    pairs = [(0.5, True)] * 10  # 10 < 50
    b = brier_score(pairs)
    rel = reliability_bins(pairs)
    ece = expected_calibration_error(pairs)
    assert b == {"brier_score": None, "n": 10, "note": "insufficient_for_calibration"}
    assert rel["bins"] is None and rel["note"] == "insufficient_for_calibration"
    assert ece["ece"] is None and ece["note"] == "insufficient_for_calibration"


def test_threshold_boundary():
    # exactly MIN-1 gated; exactly MIN computes.
    below = [(0.5, True)] * (MIN_CALIBRATION_SAMPLES - 1)
    at = [(0.5, True)] * MIN_CALIBRATION_SAMPLES
    assert brier_score(below)["note"] == "insufficient_for_calibration"
    assert brier_score(at)["note"] is None


def test_bin_boundary_assignment():
    # 50 @ p=0.2 -> bin index int(0.2*10)=2 -> [0.20,0.30)
    pairs = [(0.2, True)] * 50
    rel = reliability_bins(pairs, n_bins=10)
    populated = [b for b in rel["bins"] if b["count"] > 0]
    assert len(populated) == 1
    assert populated[0]["lo"] == 0.2
    assert populated[0]["hi"] == 0.3
    assert len(rel["bins"]) == 10


def test_p_equals_one_lands_in_last_bin():
    pairs = [(1.0, True)] * 50
    rel = reliability_bins(pairs, n_bins=10)
    populated = [b for b in rel["bins"] if b["count"] > 0]
    assert len(populated) == 1
    assert populated[0]["lo"] == 0.9
    assert populated[0]["hi"] == 1.0


def test_invalid_pairs_dropped():
    # out-of-range / None predicted prob are dropped before counting.
    pairs = [(1.5, True), (-0.1, False), (None, True)] + [(0.5, True)] * 50
    r = brier_score(pairs)
    assert r["n"] == 50  # only the valid 50 counted
