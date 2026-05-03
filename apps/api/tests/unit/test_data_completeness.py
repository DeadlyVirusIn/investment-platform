"""Phase 10 — completeness flags + quality indicator tests."""

from __future__ import annotations

import pytest

from apps.api.src.domain.data.completeness import (
    CompletenessFlags,
    EventQuality,
    compute_completeness,
    derive_quality,
)
from apps.api.src.domain.data.time import EventTime


class TestCompleteness:
    def test_all_present(self):
        f = compute_completeness(
            eps_actual=1.0, eps_consensus=1.0,
            revenue_actual=1.0, revenue_consensus=1.0,
            shares_outstanding=100,
        )
        assert f.count == 5
        assert f.has_eps_actual and f.has_shares_outstanding

    def test_all_missing(self):
        f = compute_completeness(
            eps_actual=None, eps_consensus=None,
            revenue_actual=None, revenue_consensus=None,
            shares_outstanding=None,
        )
        assert f.count == 0

    def test_partial(self):
        f = compute_completeness(
            eps_actual=1.0, eps_consensus=None,
            revenue_actual=5.0, revenue_consensus=5.5,
            shares_outstanding=None,
        )
        assert f.count == 3


class TestQuality:
    def _flags(self, n: int) -> CompletenessFlags:
        return CompletenessFlags(
            has_eps_actual=n >= 1,
            has_eps_consensus=n >= 2,
            has_revenue_actual=n >= 3,
            has_revenue_consensus=n >= 4,
            has_shares_outstanding=n >= 5,
        )

    def test_full_quality(self):
        assert derive_quality(self._flags(5), EventTime.AFTER_CLOSE) == EventQuality.FULL

    def test_full_demoted_by_unknown_event_time(self):
        """5 flags True but event_time=UNKNOWN -> PARTIAL (never FULL)."""
        assert derive_quality(self._flags(5), EventTime.UNKNOWN) == EventQuality.PARTIAL

    def test_partial_four_flags(self):
        assert derive_quality(self._flags(4), EventTime.AFTER_CLOSE) == EventQuality.PARTIAL

    def test_partial_three_flags(self):
        assert derive_quality(self._flags(3), EventTime.AFTER_CLOSE) == EventQuality.PARTIAL

    def test_sparse_two_flags(self):
        assert derive_quality(self._flags(2), EventTime.AFTER_CLOSE) == EventQuality.SPARSE

    def test_sparse_zero_flags(self):
        assert derive_quality(self._flags(0), EventTime.AFTER_CLOSE) == EventQuality.SPARSE
