"""Unit tests — Phase 1.6 cutover readiness logic (pure, no DB)."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from apps.api.src.domain.cutover.check import (
    REQUIRED_CONSECUTIVE_DAYS,
    check_cutover_ready,
)


class _FakeRow:
    def __init__(
        self, d: dt.date, *,
        diff_status="ok",
        diff_reason=None,
        signals_count=3, ranked_count=3,
        max_score_delta=None,
        asset_set_match=True, topn_match=True, reorder_count=0,
    ):
        self.as_of_date = d
        self.diff_status = diff_status
        self.diff_reason = diff_reason
        self.signals_count = signals_count
        self.ranked_count = ranked_count
        self.max_score_delta = max_score_delta
        self.asset_set_match = asset_set_match
        self.topn_match = topn_match
        self.reorder_count = reorder_count


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self, _stmt):
        class _Iter:
            def __init__(self, rows):
                self._rows = rows
            def __iter__(self):
                return iter(self._rows)
        return _Iter(self._rows)


def _business_days_back(end: dt.date, n: int) -> list[dt.date]:
    out, d = [], end
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= dt.timedelta(days=1)
    return sorted(out)


TODAY = dt.date(2026, 4, 17)   # Friday


# ---------------------------------------------------------------------------
# Baseline
# ---------------------------------------------------------------------------


class TestBaseline:
    def test_all_7_days_ok_is_ready(self):
        days = _business_days_back(TODAY, 7)
        rows = [_FakeRow(d) for d in days]
        rep = check_cutover_ready(_FakeSession(rows), today=TODAY, required_days=7)
        assert rep.ready is True
        assert rep.reasons == []
        assert rep.consecutive_days_ok == 7
        assert rep.non_consecutive is False

    def test_required_days_default(self):
        assert REQUIRED_CONSECUTIVE_DAYS == 7


# ---------------------------------------------------------------------------
# Task 1 — consecutive business day enforcement
# ---------------------------------------------------------------------------


class TestConsecutive:
    def test_gap_inside_window_blocks(self):
        days = _business_days_back(TODAY, 7)
        rows = [_FakeRow(d) for d in days if d != days[3]]
        rep = check_cutover_ready(_FakeSession(rows), today=TODAY, required_days=7)
        assert rep.ready is False
        assert rep.non_consecutive is True
        assert "non_consecutive_days_detected" in rep.reasons
        assert len(rep.missing_days) == 1

    def test_weekend_gap_does_not_count_as_non_consecutive(self):
        # Mon-Fri is consecutive business; weekends implicit.
        mon = dt.date(2026, 4, 13)   # Monday
        rows = [_FakeRow(mon + dt.timedelta(days=i)) for i in range(5)]
        rep = check_cutover_ready(
            _FakeSession(rows), today=dt.date(2026, 4, 17), required_days=5,
        )
        assert rep.non_consecutive is False

    def test_trailing_streak_counted(self):
        days = _business_days_back(TODAY, 7)
        rows = [_FakeRow(d) for d in days[-3:]]
        rep = check_cutover_ready(_FakeSession(rows), today=TODAY, required_days=7)
        assert rep.consecutive_days_ok == 3
        assert rep.ready is False

    def test_single_day_no_non_consecutive_flag(self):
        rows = [_FakeRow(TODAY)]
        rep = check_cutover_ready(_FakeSession(rows), today=TODAY, required_days=7)
        assert rep.non_consecutive is False
        assert rep.consecutive_days_ok == 1


# ---------------------------------------------------------------------------
# Task 2 — signal count variance (WARN only, non-blocking)
# ---------------------------------------------------------------------------


class TestVarianceWarning:
    def test_stable_counts_no_warning(self):
        days = _business_days_back(TODAY, 7)
        rows = [_FakeRow(d, signals_count=4) for d in days]
        rep = check_cutover_ready(_FakeSession(rows), today=TODAY, required_days=7)
        assert rep.signal_count_variance == "stable"
        assert rep.warnings == []
        assert rep.ready is True

    def test_50pct_deviation_emits_warn(self):
        days = _business_days_back(TODAY, 7)
        rows = [_FakeRow(d, signals_count=4) for d in days[:-1]]
        rows.append(_FakeRow(days[-1], signals_count=7))
        rep = check_cutover_ready(_FakeSession(rows), today=TODAY, required_days=7)
        assert rep.signal_count_variance == "warn"
        assert len(rep.warnings) >= 1
        # 7/4=1.75× < 5× → no hard block
        assert "signals_count_spike_detected" not in rep.reasons

    def test_hard_spike_still_blocks(self):
        days = _business_days_back(TODAY, 7)
        rows = [_FakeRow(d, signals_count=3) for d in days]
        rows[3].signals_count = 100
        rep = check_cutover_ready(_FakeSession(rows), today=TODAY, required_days=7)
        assert rep.ready is False
        assert any("spike" in r for r in rep.reasons)


# ---------------------------------------------------------------------------
# Task 3 — diff stability metrics
# ---------------------------------------------------------------------------


class TestDiffStability:
    def test_max_and_avg_score_delta(self):
        days = _business_days_back(TODAY, 7)
        rows = [
            _FakeRow(d, max_score_delta=Decimal(str(delta)))
            for d, delta in zip(days, [0.0, 1e-5, 2e-5, 5e-5, 0.0, 0.0, 1e-5])
        ]
        rep = check_cutover_ready(_FakeSession(rows), today=TODAY, required_days=7)
        assert rep.max_score_delta == 5e-5
        # avg ≈ (0+1e-5+2e-5+5e-5+0+0+1e-5)/7 ≈ 1.286e-5
        assert 1.2e-5 <= rep.avg_score_delta <= 1.4e-5

    def test_missing_deltas_zero_metrics(self):
        days = _business_days_back(TODAY, 7)
        rows = [_FakeRow(d) for d in days]
        rep = check_cutover_ready(_FakeSession(rows), today=TODAY, required_days=7)
        assert rep.max_score_delta == 0.0
        assert rep.avg_score_delta == 0.0


# ---------------------------------------------------------------------------
# Task 4 — failure day log
# ---------------------------------------------------------------------------


class TestFailureLog:
    def test_diff_fail_adds_to_failing_days(self):
        days = _business_days_back(TODAY, 7)
        rows = [_FakeRow(d) for d in days]
        rows[2].diff_status = "fail"
        rows[2].diff_reason = "asset_set_mismatch"
        rows[2].asset_set_match = False
        rep = check_cutover_ready(_FakeSession(rows), today=TODAY, required_days=7)
        assert rep.ready is False
        assert len(rep.failing_days) == 1
        assert rep.failing_days[0] == days[2].isoformat()
        assert any("diff_failures" in r for r in rep.reasons)


# ---------------------------------------------------------------------------
# Task 5 — structured summary shape
# ---------------------------------------------------------------------------


class TestSummaryShape:
    def test_to_dict_has_all_phase_16_keys(self):
        rep = check_cutover_ready(_FakeSession([]), today=TODAY, required_days=3)
        d = rep.to_dict()
        expected = {
            "ready", "required_days", "reasons", "warnings",
            "rows_examined", "missing_days", "failing_days",
            "non_consecutive", "consecutive_days_ok",
            "max_score_delta", "avg_score_delta",
            "signal_count_variance",
            "signals_counts", "ranked_counts",
        }
        assert expected.issubset(d.keys())

    def test_empty_window_stays_safe(self):
        rep = check_cutover_ready(_FakeSession([]), today=TODAY, required_days=7)
        assert rep.ready is False
        assert len(rep.missing_days) == 7
        assert rep.signal_count_variance == "unknown"
        assert rep.consecutive_days_ok == 0
