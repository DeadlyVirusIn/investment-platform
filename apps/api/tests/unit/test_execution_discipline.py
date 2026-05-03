"""Unit tests — Phase 6 execution discipline layer."""

from __future__ import annotations

import datetime as dt

import pytest

from apps.api.src.domain.execution.discipline import (
    DEFAULT_MIN_OPEN_CONVICTION,
    Candidate,
    ExecutionDisciplineConfig,
    HeldPosition,
    PortfolioBook,
    apply_discipline,
    daily_return_from_book,
)


def _cand(
    symbol: str, size: float = 0.1, conviction: float = 0.5,
    per_bar: float = 0.001, n_bars: int = 20,
) -> Candidate:
    return Candidate(
        symbol=symbol, proposed_size=size, conviction=conviction,
        per_bar_return=per_bar, n_bars_forward=n_bars,
    )


# ---------------------------------------------------------------------------
# Config sanity
# ---------------------------------------------------------------------------


class TestConfig:
    def test_default_config_enabled(self):
        c = ExecutionDisciplineConfig()
        assert c.enabled is True
        assert c.min_position_change > 0
        assert c.min_hold_days >= 1
        assert c.cooldown_days >= 0

    def test_regime_floors_populated(self):
        c = ExecutionDisciplineConfig()
        for r in ("low_vol", "sideways", "trend_up"):
            assert r in c.min_open_conviction

    def test_frozen_config(self):
        c = ExecutionDisciplineConfig()
        with pytest.raises(Exception):
            c.min_hold_days = 99   # type: ignore


# ---------------------------------------------------------------------------
# Disabled path — pass-through
# ---------------------------------------------------------------------------


class TestDisabled:
    def test_disabled_passes_candidates_through(self):
        cfg = ExecutionDisciplineConfig(enabled=False)
        book = PortfolioBook()
        cands = [_cand("A", 0.3), _cand("B", 0.5)]
        out = apply_discipline(
            book, cands, dt.date(2026, 1, 5), "trend_up", cfg,
        )
        assert out == {"A": 0.3, "B": 0.5}
        assert set(book.positions) == {"A", "B"}

    def test_disabled_ignores_previous_book(self):
        cfg = ExecutionDisciplineConfig(enabled=False)
        book = PortfolioBook()
        book.positions["STALE"] = HeldPosition(
            symbol="STALE", size=0.9, entry_date=dt.date(2025, 12, 1),
            entry_conviction=0.8, per_bar_return=0.001, n_bars_forward=20,
        )
        out = apply_discipline(
            book, [_cand("A", 0.3)], dt.date(2026, 1, 5), "trend_up", cfg,
        )
        # STALE should be gone (disabled flushes book each day)
        assert set(out) == {"A"}
        assert "STALE" not in book.positions

    def test_disabled_drops_zero_size_candidates(self):
        cfg = ExecutionDisciplineConfig(enabled=False)
        out = apply_discipline(
            PortfolioBook(),
            [_cand("A", 0.0), _cand("B", 0.2)],
            dt.date(2026, 1, 5), "trend_up", cfg,
        )
        assert out == {"B": 0.2}


# ---------------------------------------------------------------------------
# Hysteresis
# ---------------------------------------------------------------------------


class TestHysteresis:
    def test_tiny_rebalance_blocked(self):
        cfg = ExecutionDisciplineConfig(min_position_change=0.02)
        book = PortfolioBook()
        # Open on day 1
        apply_discipline(
            book, [_cand("A", size=0.30, conviction=0.8)],
            dt.date(2026, 1, 5), "trend_up", cfg,
        )
        # Day 2: tiny change (0.01) should be suppressed
        out = apply_discipline(
            book, [_cand("A", size=0.31, conviction=0.8)],
            dt.date(2026, 1, 6), "trend_up", cfg,
        )
        assert out["A"] == 0.30    # old size preserved
        assert book.positions["A"].size == 0.30

    def test_material_rebalance_allowed(self):
        cfg = ExecutionDisciplineConfig(min_position_change=0.02)
        book = PortfolioBook()
        apply_discipline(
            book, [_cand("A", size=0.30, conviction=0.8)],
            dt.date(2026, 1, 5), "trend_up", cfg,
        )
        out = apply_discipline(
            book, [_cand("A", size=0.50, conviction=0.8)],
            dt.date(2026, 1, 6), "trend_up", cfg,
        )
        assert out["A"] == 0.50    # rebalanced


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------


class TestThresholds:
    def test_weak_open_blocked_low_vol(self):
        cfg = ExecutionDisciplineConfig(
            min_open_conviction={"low_vol": 0.40, "trend_up": 0.20},
        )
        out = apply_discipline(
            PortfolioBook(),
            [_cand("A", size=0.3, conviction=0.25)],  # below low_vol floor
            dt.date(2026, 1, 5), "low_vol", cfg,
        )
        assert out == {}

    def test_strong_open_allowed(self):
        cfg = ExecutionDisciplineConfig(
            min_open_conviction={"low_vol": 0.40},
        )
        out = apply_discipline(
            PortfolioBook(),
            [_cand("A", size=0.3, conviction=0.45)],
            dt.date(2026, 1, 5), "low_vol", cfg,
        )
        assert out == {"A": 0.3}

    def test_regime_aware_trend_up_more_permissive(self):
        cfg = ExecutionDisciplineConfig(
            min_open_conviction={"low_vol": 0.40, "trend_up": 0.15},
        )
        conviction = 0.20
        # Blocked in low_vol:
        out_lv = apply_discipline(
            PortfolioBook(),
            [_cand("A", size=0.3, conviction=conviction)],
            dt.date(2026, 1, 5), "low_vol", cfg,
        )
        # Allowed in trend_up:
        out_tu = apply_discipline(
            PortfolioBook(),
            [_cand("A", size=0.3, conviction=conviction)],
            dt.date(2026, 1, 5), "trend_up", cfg,
        )
        assert out_lv == {}
        assert out_tu == {"A": 0.3}

    def test_fallback_threshold_for_unknown_regime(self):
        cfg = ExecutionDisciplineConfig(
            min_open_conviction={},
            min_open_conviction_fallback=0.40,
        )
        out = apply_discipline(
            PortfolioBook(),
            [_cand("A", size=0.3, conviction=0.30)],
            dt.date(2026, 1, 5), "unknown_regime", cfg,
        )
        assert out == {}   # 0.30 < 0.40 fallback


# ---------------------------------------------------------------------------
# Holding rules
# ---------------------------------------------------------------------------


class TestHolding:
    def test_min_hold_prevents_premature_exit(self):
        cfg = ExecutionDisciplineConfig(min_hold_days=3)
        book = PortfolioBook()
        apply_discipline(
            book, [_cand("A", size=0.3, conviction=0.7)],
            dt.date(2026, 1, 5), "trend_up", cfg,
        )
        # Day 2: no signal, but within min_hold -> keep
        out = apply_discipline(
            book, [], dt.date(2026, 1, 6), "trend_up", cfg,
        )
        assert out == {"A": 0.3}

    def test_min_hold_releases_after_n_days(self):
        cfg = ExecutionDisciplineConfig(min_hold_days=3)
        book = PortfolioBook()
        apply_discipline(
            book, [_cand("A", size=0.3, conviction=0.7)],
            dt.date(2026, 1, 5), "trend_up", cfg,
        )
        # Day 5 (4 days later) and no signal -> close
        out = apply_discipline(
            book, [], dt.date(2026, 1, 9), "trend_up", cfg,
        )
        assert out == {}
        assert "A" not in book.positions
        assert book.cooldown["A"] == dt.date(2026, 1, 9)

    def test_cooldown_blocks_reentry(self):
        cfg = ExecutionDisciplineConfig(
            min_hold_days=1, cooldown_days=2,
            min_open_conviction={"trend_up": 0.20},
            override_conviction_gap=0.50,   # very high override bar
        )
        book = PortfolioBook()
        # Day 1: open A
        apply_discipline(
            book, [_cand("A", size=0.3, conviction=0.7)],
            dt.date(2026, 1, 5), "trend_up", cfg,
        )
        # Day 3: close (min_hold=1 satisfied, no new signal)
        apply_discipline(
            book, [], dt.date(2026, 1, 7), "trend_up", cfg,
        )
        # Day 4: inside cooldown window; conviction below override level
        # (floor 0.20 + gap 0.50 = 0.70; 0.60 < 0.70 -> blocked)
        out = apply_discipline(
            book, [_cand("A", size=0.3, conviction=0.60)],
            dt.date(2026, 1, 8), "trend_up", cfg,
        )
        assert out == {}

    def test_cooldown_expires(self):
        cfg = ExecutionDisciplineConfig(min_hold_days=1, cooldown_days=2)
        book = PortfolioBook()
        book.cooldown["A"] = dt.date(2026, 1, 5)
        # 3 days later -> cooldown expired
        out = apply_discipline(
            book, [_cand("A", size=0.3, conviction=0.60)],
            dt.date(2026, 1, 8), "trend_up", cfg,
        )
        assert out == {"A": 0.3}


# ---------------------------------------------------------------------------
# Override path
# ---------------------------------------------------------------------------


class TestOverride:
    def test_strong_reversal_bypasses_cooldown(self):
        cfg = ExecutionDisciplineConfig(
            min_open_conviction={"trend_up": 0.20},
            cooldown_days=5,
            override_conviction_gap=0.30,
        )
        book = PortfolioBook()
        book.cooldown["A"] = dt.date(2026, 1, 5)
        # 2 days later, still in cooldown -- but conviction way above floor+gap
        out = apply_discipline(
            book,
            [_cand("A", size=0.3, conviction=0.70)],  # 0.70 > 0.20 + 0.30
            dt.date(2026, 1, 7), "trend_up", cfg,
        )
        assert out == {"A": 0.3}   # override fired

    def test_cooldown_held_without_override(self):
        cfg = ExecutionDisciplineConfig(
            min_open_conviction={"trend_up": 0.20},
            cooldown_days=5,
            override_conviction_gap=0.30,
        )
        book = PortfolioBook()
        book.cooldown["A"] = dt.date(2026, 1, 5)
        # Conviction insufficient for override
        out = apply_discipline(
            book,
            [_cand("A", size=0.3, conviction=0.40)],   # 0.40 < 0.20 + 0.30
            dt.date(2026, 1, 7), "trend_up", cfg,
        )
        assert out == {}


# ---------------------------------------------------------------------------
# PnL attribution
# ---------------------------------------------------------------------------


class TestPnLAttribution:
    def test_empty_book_zero_return(self):
        book = PortfolioBook()
        r = daily_return_from_book(book, dt.date(2026, 1, 5), {})
        assert r == 0.0

    def test_single_position_return(self):
        book = PortfolioBook()
        book.positions["A"] = HeldPosition(
            symbol="A", size=0.5, entry_date=dt.date(2026, 1, 5),
            entry_conviction=0.8, per_bar_return=0.002, n_bars_forward=20,
        )
        r = daily_return_from_book(
            book, dt.date(2026, 1, 6), {"A": 0.5},
        )
        assert r == pytest.approx(0.002)

    def test_horizon_expired_contributes_zero(self):
        book = PortfolioBook()
        book.positions["A"] = HeldPosition(
            symbol="A", size=0.5, entry_date=dt.date(2026, 1, 5),
            entry_conviction=0.8, per_bar_return=0.002, n_bars_forward=3,
        )
        r = daily_return_from_book(
            book, dt.date(2026, 1, 9),   # 4 days later, beyond n_bars_forward=3
            {"A": 0.5},
        )
        assert r == 0.0

    def test_size_weighted_across_positions(self):
        book = PortfolioBook()
        book.positions["A"] = HeldPosition(
            "A", 0.2, dt.date(2026, 1, 5), 0.8, 0.001, 20,
        )
        book.positions["B"] = HeldPosition(
            "B", 0.8, dt.date(2026, 1, 5), 0.8, 0.005, 20,
        )
        r = daily_return_from_book(
            book, dt.date(2026, 1, 6), {"A": 0.2, "B": 0.8},
        )
        # Expected: (0.2*0.001 + 0.8*0.005) / (0.2+0.8) = 0.0042
        assert r == pytest.approx(0.0042)


# ---------------------------------------------------------------------------
# Zero-cost reproducibility — disabled flag must produce same book structure
# ---------------------------------------------------------------------------


class TestZeroCostCompatibility:
    def test_disabled_config_matches_naive_pass_through(self):
        """With enabled=False the actual sizes == proposed sizes."""
        cfg = ExecutionDisciplineConfig(enabled=False)
        book = PortfolioBook()
        cands = [_cand("A", 0.3), _cand("B", 0.1), _cand("C", 0.4)]
        proposed = {c.symbol: c.proposed_size for c in cands}
        out = apply_discipline(
            book, cands, dt.date(2026, 1, 5), "low_vol", cfg,
        )
        assert out == proposed
