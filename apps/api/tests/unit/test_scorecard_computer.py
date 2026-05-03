"""Unit tests for Phase 2 scorecard aggregation."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from apps.api.src.domain.model_scorecard.computer import (
    CALIBRATION_BUCKETS,
    compute_scorecard,
)

D = Decimal


def _row(
    *,
    confidence: float | None = 0.5,
    label: str = "win",
    realized: float = 0.05,
    dd: float | None = -0.01,
    as_of: dt.date = dt.date(2026, 1, 1),
    eval_ts: dt.datetime | None = None,
    holding: int = 5,
    factor_top: list | None = None,
) -> dict:
    if eval_ts is None:
        eval_ts = dt.datetime.combine(
            as_of + dt.timedelta(days=holding),
            dt.time(22, 0), tzinfo=dt.timezone.utc,
        )
    return {
        "outcome_label": label,
        "realized_return": realized,
        "max_drawdown": dd,
        "confidence": confidence,
        "signal_as_of_date": as_of,
        "evaluation_timestamp": eval_ts,
        "holding_period_bars": holding,
        "factor_top": factor_top,
    }


class TestEmptyInput:
    def test_empty_returns_zero_totals(self):
        m = compute_scorecard([])
        assert m.total_signals == 0
        assert m.win_rate is None
        assert m.avg_return is None
        assert m.avg_days_to_evaluation is None
        assert m.calibration == []
        assert m.factor_effectiveness == []


class TestBucketAssignment:
    def test_confidence_0_1_goes_to_first_bucket(self):
        m = compute_scorecard([_row(confidence=0.1, label="win")])
        first = next(b for b in m.calibration if b["bucket"] == "0.0-0.2")
        assert first["count"] == 1
        assert first["win_rate"] == 1.0

    def test_confidence_0_5_goes_to_third(self):
        m = compute_scorecard([_row(confidence=0.5, label="loss", realized=-0.03)])
        b = next(b for b in m.calibration if b["bucket"] == "0.4-0.6")
        assert b["count"] == 1
        assert b["win_rate"] == 0.0

    def test_boundary_exact_0_2_is_second_bucket(self):
        # Left-inclusive: 0.2 belongs to 0.2-0.4
        m = compute_scorecard([_row(confidence=0.2)])
        b = next(b for b in m.calibration if b["bucket"] == "0.2-0.4")
        assert b["count"] == 1
        first = next(b for b in m.calibration if b["bucket"] == "0.0-0.2")
        assert first["count"] == 0

    def test_confidence_1_0_goes_to_last_bucket(self):
        m = compute_scorecard([_row(confidence=1.0)])
        last = next(b for b in m.calibration if b["bucket"] == "0.8-1.0")
        assert last["count"] == 1

    def test_none_confidence_is_not_bucketed(self):
        m = compute_scorecard([_row(confidence=None)])
        for b in m.calibration:
            assert b["count"] == 0
        assert m.total_signals == 1


class TestWinRate:
    def test_all_wins(self):
        rows = [_row(label="win") for _ in range(3)]
        m = compute_scorecard(rows)
        assert m.win_rate == 1.0
        assert m.total_signals == 3

    def test_mixed(self):
        rows = [
            _row(label="win"), _row(label="win"),
            _row(label="loss"), _row(label="breakeven"),
        ]
        m = compute_scorecard(rows)
        # 2/4 wins
        assert m.win_rate == 0.5
        assert m.total_signals == 4

    def test_no_wins(self):
        rows = [_row(label="loss") for _ in range(5)]
        m = compute_scorecard(rows)
        assert m.win_rate == 0.0


class TestEvaluationLag:
    def test_avg_days_simple(self):
        rows = [
            _row(  # 3 days lag
                as_of=dt.date(2026, 1, 1),
                eval_ts=dt.datetime(2026, 1, 4, 22, 0, tzinfo=dt.timezone.utc),
                holding=2, label="win",
            ),
            _row(  # 5 days lag
                as_of=dt.date(2026, 1, 1),
                eval_ts=dt.datetime(2026, 1, 6, 22, 0, tzinfo=dt.timezone.utc),
                holding=2, label="win",
            ),
        ]
        m = compute_scorecard(rows)
        assert m.avg_days_to_evaluation == 4.0
        assert m.max_days_to_evaluation == 5

    def test_pct_within_horizon(self):
        # 2 within horizon (lag <= holding), 1 outside, 1 timeout (excluded)
        rows = [
            _row(as_of=dt.date(2026, 1, 1),
                 eval_ts=dt.datetime(2026, 1, 3, 22, 0, tzinfo=dt.timezone.utc),
                 holding=5, label="win"),             # lag 2 ≤ 5 ✓
            _row(as_of=dt.date(2026, 1, 1),
                 eval_ts=dt.datetime(2026, 1, 5, 22, 0, tzinfo=dt.timezone.utc),
                 holding=5, label="loss"),            # lag 4 ≤ 5 ✓
            _row(as_of=dt.date(2026, 1, 1),
                 eval_ts=dt.datetime(2026, 1, 10, 22, 0, tzinfo=dt.timezone.utc),
                 holding=5, label="loss"),            # lag 9 > 5 ✗
            _row(as_of=dt.date(2026, 1, 1),
                 eval_ts=dt.datetime(2026, 1, 20, 22, 0, tzinfo=dt.timezone.utc),
                 holding=5, label="timeout"),         # excluded
        ]
        m = compute_scorecard(rows)
        # 2 / 3 non-timeout within horizon
        assert m.pct_within_horizon == round(2 / 3, 4)

    def test_no_dates_leaves_lag_none(self):
        rows = [{
            "outcome_label": "win", "realized_return": 0.05,
            "max_drawdown": -0.01, "confidence": 0.5,
            "signal_as_of_date": None, "evaluation_timestamp": None,
            "holding_period_bars": 5, "factor_top": None,
        }]
        m = compute_scorecard(rows)
        assert m.avg_days_to_evaluation is None
        assert m.max_days_to_evaluation is None


class TestDeterminism:
    def test_same_input_same_output(self):
        rows = [_row(confidence=0.3, label="win"), _row(confidence=0.7, label="loss", realized=-0.02)]
        a = compute_scorecard(rows)
        b = compute_scorecard(rows)
        assert a == b

    def test_input_order_doesnt_matter_for_metrics(self):
        a = compute_scorecard([
            _row(confidence=0.3, label="win", realized=0.05),
            _row(confidence=0.7, label="loss", realized=-0.02),
        ])
        b = compute_scorecard([
            _row(confidence=0.7, label="loss", realized=-0.02),
            _row(confidence=0.3, label="win", realized=0.05),
        ])
        assert a.total_signals == b.total_signals
        assert a.win_rate == b.win_rate
        assert a.avg_return == b.avg_return
        assert a.avg_drawdown == b.avg_drawdown


class TestFactorEffectiveness:
    def test_picks_top_by_abs_contribution(self):
        # Row 1 has rm60 strong positive, Row 2 has sector strong positive
        rows = [
            _row(label="win", factor_top=[
                {"key": "rm60", "contribution": 0.30},
                {"key": "trend", "contribution": 0.05},
            ]),
            _row(label="loss", realized=-0.03, factor_top=[
                {"key": "sector", "contribution": -0.40},
                {"key": "trend", "contribution": 0.02},
            ]),
            _row(label="win", factor_top=[
                {"key": "rm60", "contribution": 0.25},
            ]),
        ]
        m = compute_scorecard(rows)
        keys = {f["factor"]: f for f in m.factor_effectiveness}
        assert "rm60" in keys and "sector" in keys
        assert keys["rm60"]["count"] == 2
        assert keys["rm60"]["win_rate"] == 1.0
        assert keys["sector"]["count"] == 1
        assert keys["sector"]["win_rate"] == 0.0

    def test_missing_factor_top_skipped(self):
        rows = [_row(label="win", factor_top=None)]
        m = compute_scorecard(rows)
        assert m.factor_effectiveness == []
