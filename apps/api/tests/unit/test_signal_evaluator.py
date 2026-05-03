"""Unit tests — pure evaluator policy (label + timeout + DD)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.api.src.domain.signal_evaluator.evaluator import (
    BREAKEVEN_THRESHOLD,
    MAX_WAIT_MULTIPLIER,
    OUTCOME_BREAKEVEN,
    OUTCOME_LOSS,
    OUTCOME_TIMEOUT,
    OUTCOME_WIN,
    compute_max_drawdown,
    compute_realized_return,
    evaluate,
    is_timeout,
    label_outcome,
)

D = Decimal


class TestLabelOutcome:
    def test_long_positive_return_is_win(self):
        assert label_outcome(D("0.05"), "long") == OUTCOME_WIN

    def test_long_negative_return_is_loss(self):
        assert label_outcome(D("-0.05"), "long") == OUTCOME_LOSS

    def test_short_negative_return_is_win(self):
        assert label_outcome(D("-0.05"), "short") == OUTCOME_WIN

    def test_short_positive_return_is_loss(self):
        assert label_outcome(D("0.05"), "short") == OUTCOME_LOSS

    def test_breakeven_just_below_threshold_long(self):
        near = BREAKEVEN_THRESHOLD - D("0.00001")
        assert label_outcome(near, "long") == OUTCOME_BREAKEVEN
        assert label_outcome(-near, "long") == OUTCOME_BREAKEVEN

    def test_breakeven_exact_zero(self):
        assert label_outcome(D("0"), "long") == OUTCOME_BREAKEVEN

    def test_win_just_at_threshold_long(self):
        # |x| == threshold is NOT breakeven (strict <)
        assert label_outcome(BREAKEVEN_THRESHOLD, "long") == OUTCOME_WIN
        assert label_outcome(-BREAKEVEN_THRESHOLD, "long") == OUTCOME_LOSS

    def test_neutral_any_material_move_is_loss(self):
        assert label_outcome(D("0.05"), "neutral") == OUTCOME_LOSS
        assert label_outcome(D("-0.05"), "neutral") == OUTCOME_LOSS

    def test_neutral_small_move_is_breakeven(self):
        assert label_outcome(D("0.001"), "neutral") == OUTCOME_BREAKEVEN

    def test_direction_case_insensitive(self):
        assert label_outcome(D("0.05"), "LONG") == OUTCOME_WIN
        assert label_outcome(D("0.05"), "Long") == OUTCOME_WIN


class TestIsTimeout:
    def test_not_timed_out_within_horizon(self):
        assert is_timeout(signal_age_bars=10, holding_period_bars=20) is False

    def test_not_timed_out_at_horizon(self):
        assert is_timeout(signal_age_bars=20, holding_period_bars=20) is False

    def test_not_timed_out_just_below_max_wait(self):
        # 2×20 = 40. Age 40 is NOT past it (strict >).
        assert is_timeout(signal_age_bars=40, holding_period_bars=20) is False

    def test_timed_out_past_max_wait(self):
        assert is_timeout(signal_age_bars=41, holding_period_bars=20) is True

    def test_max_wait_respects_multiplier(self):
        assert MAX_WAIT_MULTIPLIER == 2
        assert is_timeout(signal_age_bars=45, holding_period_bars=20) is True

    def test_zero_holding_period_never_timeouts(self):
        assert is_timeout(signal_age_bars=100, holding_period_bars=0) is False


class TestComputeRealizedReturn:
    def test_positive_return(self):
        assert compute_realized_return(D("100"), D("110")) == D("0.1")

    def test_negative_return(self):
        assert compute_realized_return(D("100"), D("90")) == D("-0.1")

    def test_zero_return(self):
        assert compute_realized_return(D("100"), D("100")) == D("0")

    def test_rejects_non_positive_entry(self):
        with pytest.raises(ValueError):
            compute_realized_return(D("0"), D("10"))
        with pytest.raises(ValueError):
            compute_realized_return(D("-1"), D("10"))


class TestComputeMaxDrawdown:
    def test_long_drawdown_is_min_close(self):
        dd = compute_max_drawdown(
            [D("100"), D("95"), D("92"), D("98")],
            entry_price=D("100"), signal_direction="long",
        )
        assert dd == D("-0.08")

    def test_short_drawdown_is_max_close(self):
        dd = compute_max_drawdown(
            [D("100"), D("105"), D("108"), D("102")],
            entry_price=D("100"), signal_direction="short",
        )
        assert dd == D("-0.08")

    def test_empty_window_returns_none(self):
        assert compute_max_drawdown([], D("100"), "long") is None

    def test_favorable_only_returns_zero(self):
        # All closes above entry for long → no adverse excursion
        dd = compute_max_drawdown(
            [D("101"), D("102")], entry_price=D("100"), signal_direction="long",
        )
        assert dd == D("0")


class TestEvaluateFullPipeline:
    def test_long_win_path(self):
        r = evaluate(
            entry_price=D("100"),
            exit_price=D("110"),
            closes_over_window=[D("105"), D("98"), D("110")],
            signal_direction="long",
            signal_age_bars=10,
            holding_period_bars=20,
        )
        assert r.outcome_label == OUTCOME_WIN
        assert r.realized_return == D("0.1")
        assert r.max_drawdown == D("-0.02")

    def test_timeout_overrides_label(self):
        r = evaluate(
            entry_price=D("100"),
            exit_price=D("110"),
            closes_over_window=[D("110")],
            signal_direction="long",
            signal_age_bars=45,          # > 2 * 20 → timeout
            holding_period_bars=20,
        )
        assert r.outcome_label == OUTCOME_TIMEOUT

    def test_breakeven_when_tiny_move(self):
        r = evaluate(
            entry_price=D("100"),
            exit_price=D("100.1"),   # 0.1% move, below 0.2% threshold
            closes_over_window=[D("100.1")],
            signal_direction="long",
            signal_age_bars=5,
            holding_period_bars=20,
        )
        assert r.outcome_label == OUTCOME_BREAKEVEN
