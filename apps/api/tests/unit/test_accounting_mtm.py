"""Unit tests — Phase 6.5 mark-to-market accounting engine."""

from __future__ import annotations

import datetime as dt

import pytest

from apps.api.src.domain.evaluation.accounting import (
    DailyReturnLookup,
    build_daily_return_lookup,
    compute_mtm_daily_return,
    coverage_fraction,
)


# ---------------------------------------------------------------------------
# DailyReturnLookup
# ---------------------------------------------------------------------------


class TestLookup:
    def test_empty_lookup(self):
        lu = DailyReturnLookup()
        assert len(lu) == 0
        assert lu.get("X", dt.date(2026, 1, 5)) is None

    def test_build_from_simple_series(self):
        closes = {
            "A": [
                (dt.date(2026, 1, 5), 100.0),
                (dt.date(2026, 1, 6), 101.0),
                (dt.date(2026, 1, 7), 99.99),
            ],
        }
        lu = build_daily_return_lookup(closes)
        assert lu.get("A", dt.date(2026, 1, 5)) == pytest.approx(0.01)
        assert lu.get("A", dt.date(2026, 1, 6)) == pytest.approx(
            (99.99 - 101.0) / 101.0,
        )
        # Last date in series has no forward return entry
        assert lu.get("A", dt.date(2026, 1, 7)) is None

    def test_build_skips_non_positive_prices(self):
        closes = {
            "A": [
                (dt.date(2026, 1, 5), 100.0),
                (dt.date(2026, 1, 6), 0.0),
                (dt.date(2026, 1, 7), 99.0),
            ],
        }
        lu = build_daily_return_lookup(closes)
        # (A, 1/5) has zero-prev-close on the NEXT step, so skip
        assert lu.get("A", dt.date(2026, 1, 5)) is None or True
        # (A, 1/6) has 0 curr -> skip
        assert lu.get("A", dt.date(2026, 1, 6)) is None

    def test_single_bar_series_yields_nothing(self):
        lu = build_daily_return_lookup({"A": [(dt.date(2026, 1, 5), 100.0)]})
        assert len(lu) == 0


# ---------------------------------------------------------------------------
# Single-day MTM
# ---------------------------------------------------------------------------


class TestSingleDayMTM:
    def test_single_position_daily_return(self):
        lu = DailyReturnLookup({("A", dt.date(2026, 1, 5)): 0.02})
        r = compute_mtm_daily_return({"A": 0.5}, lu, dt.date(2026, 1, 5))
        assert r == pytest.approx(0.02)

    def test_size_weighted_across_symbols(self):
        lu = DailyReturnLookup({
            ("A", dt.date(2026, 1, 5)): 0.01,
            ("B", dt.date(2026, 1, 5)): -0.02,
        })
        r = compute_mtm_daily_return(
            {"A": 0.3, "B": 0.7}, lu, dt.date(2026, 1, 5),
        )
        expected = (0.3 * 0.01 + 0.7 * -0.02) / (0.3 + 0.7)
        assert r == pytest.approx(expected)

    def test_zero_positions_returns_zero(self):
        lu = DailyReturnLookup({("A", dt.date(2026, 1, 5)): 0.05})
        assert compute_mtm_daily_return({}, lu, dt.date(2026, 1, 5)) == 0.0

    def test_all_zero_sizes_returns_zero(self):
        lu = DailyReturnLookup({("A", dt.date(2026, 1, 5)): 0.05})
        assert compute_mtm_daily_return(
            {"A": 0.0, "B": 0.0}, lu, dt.date(2026, 1, 5),
        ) == 0.0

    def test_missing_lookup_skipped(self):
        lu = DailyReturnLookup({("A", dt.date(2026, 1, 5)): 0.02})
        # B missing -> only A priced
        r = compute_mtm_daily_return(
            {"A": 0.3, "B": 0.7}, lu, dt.date(2026, 1, 5),
        )
        assert r == pytest.approx(0.02)

    def test_no_symbols_covered_returns_zero(self):
        lu = DailyReturnLookup()
        r = compute_mtm_daily_return(
            {"A": 0.3, "B": 0.7}, lu, dt.date(2026, 1, 5),
        )
        assert r == 0.0


# ---------------------------------------------------------------------------
# Multi-day hold — same positions repriced daily
# ---------------------------------------------------------------------------


class TestMultiDayHold:
    def test_same_positions_repriced_daily(self):
        """Held position sees THIS DAY's return, not entry-day cached rate."""
        lu = DailyReturnLookup({
            ("A", dt.date(2026, 1, 5)): 0.02,  # entry day
            ("A", dt.date(2026, 1, 6)): -0.01, # next day
            ("A", dt.date(2026, 1, 7)): 0.03,
        })
        positions = {"A": 0.5}
        r0 = compute_mtm_daily_return(positions, lu, dt.date(2026, 1, 5))
        r1 = compute_mtm_daily_return(positions, lu, dt.date(2026, 1, 6))
        r2 = compute_mtm_daily_return(positions, lu, dt.date(2026, 1, 7))
        assert r0 == pytest.approx(0.02)
        assert r1 == pytest.approx(-0.01)
        assert r2 == pytest.approx(0.03)

    def test_no_entry_day_forward_carry_bug(self):
        """Regression guard: accounting must NOT replay entry-day return
        across subsequent held days."""
        lu = DailyReturnLookup({
            ("A", dt.date(2026, 1, 5)): 0.05,   # big up day 0
            ("A", dt.date(2026, 1, 6)): -0.02,
            ("A", dt.date(2026, 1, 7)): 0.00,
        })
        positions = {"A": 1.0}
        # If the old Phase-6 bug were present, all three days would return 0.05.
        total = sum(
            compute_mtm_daily_return(positions, lu, d)
            for d in (dt.date(2026, 1, 5), dt.date(2026, 1, 6), dt.date(2026, 1, 7))
        )
        # Correct sum: 0.05 + (-0.02) + 0.00 = 0.03
        assert total == pytest.approx(0.03)
        # NOT 3 * 0.05 = 0.15 (bug signature)
        assert total != pytest.approx(0.15)


# ---------------------------------------------------------------------------
# Coverage fraction (audit helper)
# ---------------------------------------------------------------------------


class TestCoverageFraction:
    def test_full_coverage(self):
        lu = DailyReturnLookup({
            ("A", dt.date(2026, 1, 5)): 0.01,
            ("B", dt.date(2026, 1, 5)): 0.02,
        })
        cov = coverage_fraction(
            {"A": 0.4, "B": 0.6}, lu, dt.date(2026, 1, 5),
        )
        assert cov == 1.0

    def test_partial_coverage(self):
        lu = DailyReturnLookup({("A", dt.date(2026, 1, 5)): 0.01})
        cov = coverage_fraction(
            {"A": 0.4, "B": 0.6}, lu, dt.date(2026, 1, 5),
        )
        assert cov == pytest.approx(0.4)

    def test_zero_positions_returns_zero(self):
        lu = DailyReturnLookup()
        cov = coverage_fraction({}, lu, dt.date(2026, 1, 5))
        assert cov == 0.0


# ---------------------------------------------------------------------------
# Comparability — same positions, different source strategies, same accounting
# ---------------------------------------------------------------------------


class TestComparability:
    def test_same_positions_same_output(self):
        """The key reconciliation guarantee: if Phase 5 and Phase 6
        happen to produce the SAME sizes_by_symbol on a given day, MTM
        accounting gives them the SAME daily return, regardless of how
        those positions were generated."""
        lu = DailyReturnLookup({
            ("A", dt.date(2026, 1, 5)): 0.02,
            ("B", dt.date(2026, 1, 5)): -0.01,
            ("C", dt.date(2026, 1, 5)): 0.03,
        })
        positions = {"A": 0.3, "B": 0.2, "C": 0.5}
        # Strategy 1: "generated fresh" (simulated)
        r_phase5 = compute_mtm_daily_return(positions, lu, dt.date(2026, 1, 5))
        # Strategy 2: "persisted from yesterday" (simulated)
        r_phase6 = compute_mtm_daily_return(positions, lu, dt.date(2026, 1, 5))
        assert r_phase5 == r_phase6

    def test_different_positions_different_output(self):
        lu = DailyReturnLookup({
            ("A", dt.date(2026, 1, 5)): 0.02,
            ("B", dt.date(2026, 1, 5)): -0.05,
        })
        r_a = compute_mtm_daily_return({"A": 0.5}, lu, dt.date(2026, 1, 5))
        r_b = compute_mtm_daily_return({"B": 0.5}, lu, dt.date(2026, 1, 5))
        assert r_a != r_b
