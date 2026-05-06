"""Unit tests for `paper_quality.scoring` — pure functions, no DB.

Covers each component scorer individually + the composer + grade
ladder + thesis classification + completeness flag.
"""

from __future__ import annotations

from apps.api.src.domain.paper_quality.scoring import (
    ENTRY_MAX, RETURN_MAX, HOLD_MAX, EXIT_MAX, COMPLETENESS_MAX,
    TOTAL_MAX, ScoreInputs, score_trade,
)


def _open_buy(**overrides) -> ScoreInputs:
    base = dict(
        side="buy", is_closed=False,
        entry_price=100.0, qty=1.0,
        held_days=3, max_hold_days=10,
        bar_open=100.0, bar_high=102.0, bar_low=99.0, bar_close=101.0,
        current_price=105.0,
    )
    base.update(overrides)
    return ScoreInputs(**base)


def _closed_sell(**overrides) -> ScoreInputs:
    base = dict(
        side="sell", is_closed=True,
        entry_price=100.0, qty=1.0,
        held_days=5, max_hold_days=10,
        bar_open=100.5, bar_high=102.0, bar_low=99.0, bar_close=100.5,
        realized_pnl=-5.0,           # 5% loss on 100 cost basis
        exit_reason="exit_cycle: stop_loss(-0.0545 <= -0.04)",
    )
    base.update(overrides)
    return ScoreInputs(**base)


# -- Entry quality ------------------------------------------------

def test_entry_buy_in_lower_quartile_full_points():
    inp = _open_buy(entry_price=99.25, bar_low=99.0, bar_high=102.0)
    r = score_trade(inp)
    assert r.components["entry"] == ENTRY_MAX


def test_entry_buy_in_top_quartile_zero_points():
    inp = _open_buy(entry_price=101.75, bar_low=99.0, bar_high=102.0)
    r = score_trade(inp)
    assert r.components["entry"] == 0


def test_entry_neutral_when_bar_range_missing():
    inp = _open_buy(bar_low=None, bar_high=None)
    r = score_trade(inp)
    assert r.components["entry"] == ENTRY_MAX // 2


def test_entry_sell_high_in_range_full_points():
    inp = _closed_sell(entry_price=101.75, bar_low=99.0, bar_high=102.0)
    r = score_trade(inp)
    assert r.components["entry"] == ENTRY_MAX


# -- Return quality -----------------------------------------------

def test_return_open_positive_unrealized_max_at_plus10pct():
    inp = _open_buy(current_price=110.0)  # +10%
    r = score_trade(inp)
    assert r.components["return"] == RETURN_MAX


def test_return_open_negative_unrealized_zero_at_minus10pct():
    inp = _open_buy(current_price=90.0)
    r = score_trade(inp)
    assert r.components["return"] == 0


def test_return_open_neutral_at_entry():
    inp = _open_buy(current_price=100.0)
    r = score_trade(inp)
    # 0% maps to mid-range
    assert r.components["return"] == RETURN_MAX // 2


def test_return_closed_uses_realized_pnl_pct():
    # +5% on 100 cost → 22 of 30 (mid + 5/10 * 15 = 15+7.5)
    inp = _closed_sell(realized_pnl=5.0, exit_reason="take_profit")
    r = score_trade(inp)
    assert 20 <= r.components["return"] <= 25


def test_return_zero_when_neither_realized_nor_mark():
    inp = _open_buy(current_price=None)
    r = score_trade(inp)
    assert r.components["return"] == 0


# -- Hold discipline ----------------------------------------------

def test_hold_within_budget_full_points():
    inp = _open_buy(held_days=3, max_hold_days=10)
    r = score_trade(inp)
    assert r.components["hold"] == HOLD_MAX


def test_hold_overheld_partial():
    inp = _open_buy(held_days=12, max_hold_days=10)
    r = score_trade(inp)
    assert 0 < r.components["hold"] < HOLD_MAX


def test_hold_far_overheld_low():
    inp = _open_buy(held_days=30, max_hold_days=10)
    r = score_trade(inp)
    assert r.components["hold"] < HOLD_MAX // 2


def test_hold_neutral_when_held_days_unknown():
    inp = _open_buy(held_days=None)
    r = score_trade(inp)
    assert r.components["hold"] == HOLD_MAX // 2


# -- Exit / status & thesis ---------------------------------------

def test_thesis_open_positive():
    inp = _open_buy(current_price=110.0)
    r = score_trade(inp)
    assert r.thesis == "open_positive"


def test_thesis_open_negative():
    inp = _open_buy(current_price=90.0)
    r = score_trade(inp)
    assert r.thesis == "open_negative"


def test_thesis_open_insufficient_data_when_no_mark():
    inp = _open_buy(current_price=None)
    r = score_trade(inp)
    assert r.thesis == "insufficient_data"


def test_thesis_stopped_out_recognised_from_reason():
    inp = _closed_sell(exit_reason="exit_cycle: stop_loss(-0.06)")
    r = score_trade(inp)
    assert r.thesis == "stopped_out"


def test_thesis_take_profit():
    inp = _closed_sell(
        exit_reason="exit_cycle: take_profit(0.09 >= 0.08)",
        realized_pnl=9.0,
    )
    r = score_trade(inp)
    assert r.thesis == "take_profit"
    assert r.components["exit_or_status"] == EXIT_MAX


def test_thesis_max_hold():
    inp = _closed_sell(
        exit_reason="exit_cycle: max_hold(10d >= 10d)",
        realized_pnl=0.0,
    )
    r = score_trade(inp)
    assert r.thesis == "max_hold"


def test_thesis_closed_other_for_unmatched_reason():
    inp = _closed_sell(exit_reason="manual_close_by_operator")
    r = score_trade(inp)
    assert r.thesis == "closed_other"


def test_thesis_pending_next_bar_overrides():
    inp = _open_buy(pending_next_bar=True)
    r = score_trade(inp)
    assert r.thesis == "pending_next_bar"


# -- Completeness flag --------------------------------------------

def test_completeness_full_when_all_present():
    inp = _open_buy()  # all fields present
    r = score_trade(inp)
    assert r.completeness == "full"
    assert r.components["completeness"] == COMPLETENESS_MAX


def test_completeness_partial_when_one_missing():
    inp = _open_buy(bar_high=None, bar_low=None)
    r = score_trade(inp)
    assert r.completeness == "partial"


def test_completeness_low_when_multiple_missing():
    inp = _open_buy(
        bar_high=None, bar_low=None,
        current_price=None, held_days=None,
    )
    r = score_trade(inp)
    assert r.completeness == "low"


# -- Composer + grade ladder --------------------------------------

def test_score_bounded_0_to_100():
    inp = _open_buy()
    r = score_trade(inp)
    assert 0 <= r.score <= TOTAL_MAX


def test_grade_ladder_a_to_f():
    # Construct deliberately strong / weak inputs and check grade
    # transitions.
    strong = _closed_sell(
        entry_price=99.5, bar_low=99.0, bar_high=102.0,  # top entry
        realized_pnl=10.0,                                # +10%
        exit_reason="take_profit",
        held_days=4, max_hold_days=10,
    )
    weak = _closed_sell(
        entry_price=101.5, bar_low=99.0, bar_high=102.0,  # bad sell entry
        realized_pnl=-12.0, exit_reason="manual_close",
        held_days=18, max_hold_days=10,
    )
    rs = score_trade(strong)
    rw = score_trade(weak)
    assert rs.grade in ("A", "B")
    assert rw.grade in ("D", "F")
    assert rs.score > rw.score


def test_reasons_present_for_every_component():
    inp = _open_buy()
    r = score_trade(inp)
    # one bullet per component (entry/return/hold/exit/completeness)
    assert len(r.reasons) == 5
    # bullets reference component names so the UI can hint
    joined = " ".join(r.reasons).lower()
    assert "entry" in joined
    assert "return" in joined
    assert "hold" in joined
    assert "status" in joined or "exit" in joined
    assert "completeness" in joined
