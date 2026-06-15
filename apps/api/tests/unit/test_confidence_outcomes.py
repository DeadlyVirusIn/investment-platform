"""MP2A — unit tests for the pure confidence→outcome aggregator.

DB-free: exercises bucketize() math + the honesty gate directly.
"""

from __future__ import annotations

from apps.api.src.analytics.confidence_outcomes import (
    BUCKETS_CONVICTION,
    MIN_CLOSES,
    PER_BUCKET_MIN,
    bucketize,
)


def _by_label(result):
    return {b["bucket"]: b for b in result["buckets"]}


def test_insufficient_data_returns_no_rates():
    # Fewer than MIN_CLOSES closed outcomes -> counts only, no percentages.
    rows = [(85.0, 10.0), (30.0, -5.0), (70.0, 3.0)]  # 3 < 10
    r = bucketize(rows, buckets=BUCKETS_CONVICTION)
    assert r["sufficient"] is False
    assert r["note"] == "insufficient_data"
    assert r["total_closed"] == 3
    for b in r["buckets"]:
        assert b["win_rate"] is None
        assert b["avg_realized_pnl"] is None
        assert b["expectancy"] is None
    # counts still surfaced honestly
    assert sum(b["trade_count"] for b in r["buckets"]) == 3


def test_sufficient_directional_signal():
    # 12 closed: very_high bucket all wins, low bucket all losses.
    rows = (
        [(85.0, 20.0)] * 4          # very_high: 4 wins
        + [(30.0, -10.0)] * 4       # low: 4 losses
        + [(70.0, 5.0)] * 4         # high: 4 wins
    )
    r = bucketize(rows, buckets=BUCKETS_CONVICTION)
    assert r["sufficient"] is True
    assert r["note"] is None
    assert r["total_closed"] == 12
    b = _by_label(r)
    assert b["very_high (80+)"]["win_rate"] == 1.0
    assert b["very_high (80+)"]["avg_realized_pnl"] == 20.0
    assert b["very_high (80+)"]["expectancy"] == 20.0
    assert b["very_high (80+)"]["total_realized_pnl"] == 80.0
    assert b["low (<40)"]["win_rate"] == 0.0
    assert b["low (<40)"]["avg_realized_pnl"] == -10.0
    assert b["high (60–80)"]["win_rate"] == 1.0
    # medium bucket empty -> 0 count, null rates
    assert b["medium (40–60)"]["trade_count"] == 0
    assert b["medium (40–60)"]["win_rate"] is None


def test_per_bucket_min_gate():
    # Total sufficient (10) but very_high has only 2 (< PER_BUCKET_MIN=3).
    rows = [(30.0, -1.0)] * 8 + [(90.0, 50.0)] * 2
    assert len(rows) == MIN_CLOSES
    r = bucketize(rows, buckets=BUCKETS_CONVICTION)
    assert r["sufficient"] is True
    b = _by_label(r)
    vh = b["very_high (80+)"]
    assert vh["trade_count"] == 2
    assert vh["win_rate"] is None            # below per-bucket min
    assert vh["total_realized_pnl"] == 100.0  # count/total still honest
    low = b["low (<40)"]
    assert low["trade_count"] == 8
    assert low["win_rate"] == 0.0            # 8 >= 3 -> computed


def test_none_scores_and_pnls_excluded():
    rows = [
        (None, 10.0),     # no score -> excluded
        (50.0, None),     # no pnl -> excluded
        (50.0, 1.0),      # kept
    ]
    r = bucketize(rows, buckets=BUCKETS_CONVICTION)
    assert r["total_closed"] == 1


def test_win_rate_mixed_bucket():
    # 10 closed all in 'high' bucket: 6 wins / 4 losses.
    rows = [(70.0, 2.0)] * 6 + [(70.0, -1.0)] * 4
    r = bucketize(rows, buckets=BUCKETS_CONVICTION)
    b = _by_label(r)
    high = b["high (60–80)"]
    assert high["trade_count"] == 10
    assert high["win_rate"] == 0.6
    # mean = (6*2 + 4*-1)/10 = (12-4)/10 = 0.8
    assert high["avg_realized_pnl"] == 0.8
    assert high["expectancy"] == 0.8
    assert high["total_realized_pnl"] == 8.0


def test_constants_match_trackrecord_threshold():
    assert MIN_CLOSES == 10
    assert PER_BUCKET_MIN == 3


# --- MP2B.2A: calibration pair mapping + result shaping (pure) ---

def test_mp2b2a_stock_pairs_mapping():
    from apps.api.src.analytics.confidence_outcomes import _stock_pairs
    pairs = _stock_pairs(
        [(66.67, 12.0), (40.0, -3.0), (80.0, 0.0), (None, 5.0), (50.0, None)]
    )
    assert len(pairs) == 3  # None score/pnl rows dropped
    assert round(pairs[0][0], 4) == 0.6667 and pairs[0][1] is True  # 66.67->0.6667, win
    assert pairs[1] == (0.4, False)   # realized -3 not a win
    assert pairs[2][1] is False       # realized 0.0 not > 0


def test_mp2b2a_options_pairs_mapping():
    from apps.api.src.analytics.confidence_outcomes import _options_pairs
    pairs = _options_pairs([(0.71, 5.0), (0.3, -1.0), (0.9, 0.0)])
    assert pairs[0] == (0.71, True)   # confidence_v2 kept as-is; win
    assert pairs[1] == (0.3, False)
    assert pairs[2][1] is False       # 0.0 not > 0


def test_mp2b2a_calibration_result_insufficient():
    from apps.api.src.analytics.confidence_outcomes import _calibration_result
    res = _calibration_result("stock", [(0.6, True)] * 3)  # 3 < 50
    assert res["asset_class"] == "stock"
    assert res["sample_count"] == 3
    assert res["status"] == "insufficient_for_calibration"
    assert res["note"] == "insufficient_for_calibration"
    assert res["brier_score"] is None
    assert res["expected_calibration_error"] is None
    assert res["reliability_bins"] is None
