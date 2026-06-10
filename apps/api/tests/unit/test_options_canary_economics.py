"""P6D.33A — pure unit coverage for the economic viability gate + TP guard.

Pins the trade-3 audit numbers exactly (entry $10 / max_loss $90 /
half-spreads 0.045 → fees_rt $2.80, drag $9.00, min_viable $23.60,
expected TP net −$6.80) and the decide_exit HOLD_TP_UNECONOMIC branch.
No DB.
"""

from __future__ import annotations

from decimal import Decimal

from apps.api.src.options.canary.economics import (
    assess_economics,
    expected_close_net_pnl,
)
from apps.api.src.options.canary.lifecycle import decide_exit

TP = 0.50
DTE_CLOSE = 7
HALF_SPREADS = [Decimal("0.045"), Decimal("0.045")]
QTYS = [1, 1]


def _assess(entry, max_loss, **over):
    base = dict(
        entry_credit=Decimal(str(entry)),
        max_loss=Decimal(str(max_loss)) if max_loss is not None else None,
        leg_half_spreads=HALF_SPREADS,
        leg_qtys=QTYS,
        tp_pct=TP,
        min_credit_multiple=2.0,
        min_net_reward_risk=0.10,
    )
    base.update(over)
    return assess_economics(**base)


# --- assess_economics: trade-3 pin -------------------------------------------

def test_trade3_pin_uneconomic():
    a = _assess("10.00", "90")
    assert a.fees_round_trip == Decimal("2.80")
    assert a.close_drag == Decimal("9.00")
    assert a.min_viable_credit == Decimal("23.60")
    assert a.expected_tp_close_net_pnl == Decimal("-6.80")
    assert a.net_max_profit == Decimal("7.20")
    assert a.net_reward_risk == Decimal("0.08")
    assert a.viable is False
    assert a.reason == "below_min_viable_credit"


def test_healthy_spread_viable():
    # $0.35-credit $1-wide SPCS → max_loss $65. tp_net 17.5−11.8=5.70>0,
    # 35 >= 23.60, net_rr (35−2.8)/65 ≈ 0.495 >= 0.10.
    a = _assess("35.00", "65")
    assert a.viable is True
    assert a.reason is None
    assert a.expected_tp_close_net_pnl == Decimal("5.70")
    assert a.net_max_profit == Decimal("32.20")
    assert float(a.net_reward_risk) == float(Decimal("32.20") / Decimal("65"))


def test_boundary_entry_exactly_min_viable():
    # entry == min_viable (23.60) passes the credit gate at equality, but
    # tp_net = 0.5×2×(drag+fees) − (drag+fees) = 0 → not > 0 → second gate.
    a = _assess("23.60", "76.40")
    assert a.entry_credit == a.min_viable_credit
    assert a.expected_tp_close_net_pnl == Decimal("0.00")
    assert a.viable is False
    assert a.reason == "tp_close_net_negative"


def test_reward_risk_gate():
    # Credit clears min_viable and tp_net>0 but net reward/risk below floor:
    # entry $30, max_loss $400 → net_rr = 27.2/400 = 0.068 < 0.10.
    a = _assess("30.00", "400")
    assert a.expected_tp_close_net_pnl > 0
    assert a.viable is False
    assert a.reason == "net_reward_risk_below_threshold"


def test_all_checks_fail_first_reason_wins():
    # entry $5: below min_viable AND tp_net negative AND rr tiny →
    # first failing check ('below_min_viable_credit') is reported.
    a = _assess("5.00", "95")
    assert a.expected_tp_close_net_pnl < 0
    assert a.net_reward_risk < Decimal("0.10")
    assert a.viable is False
    assert a.reason == "below_min_viable_credit"


def test_zero_max_loss_safety():
    # max_loss 0 (degenerate credit >= width) must not divide-by-zero;
    # net_reward_risk is None and the rr gate passes.
    a = _assess("35.00", "0")
    assert a.net_reward_risk is None
    assert a.viable is True
    a2 = _assess("35.00", None)
    assert a2.net_reward_risk is None
    assert a2.viable is True


def test_negative_half_spread_floored():
    a = _assess("35.00", "65",
                leg_half_spreads=[Decimal("-0.01"), Decimal("0.02")])
    assert a.close_drag == Decimal("2.00")   # negative floored to 0


def test_half_spread_capped_at_slippage_cap():
    a = _assess("35.00", "65",
                leg_half_spreads=[Decimal("0.30"), Decimal("0.30")])
    assert a.close_drag == Decimal("10.00")  # 2 × min(0.30, 0.05) × 100


# --- expected_close_net_pnl helper -------------------------------------------

def test_expected_close_net_pnl_trade3_at_tp():
    # At the gross TP trigger, mid_cost = (1−0.5)×10 = $5 →
    # net = 10 − (5 + 9) − 2.80 = −6.80 (the audit number).
    net = expected_close_net_pnl(
        entry_credit=Decimal("10.00"), current_mid_cost=Decimal("5.00"),
        leg_half_spreads=HALF_SPREADS, leg_qtys=QTYS,
    )
    assert net == Decimal("-6.80")


def test_expected_close_net_pnl_healthy():
    # entry $35, cost $7, tight spreads (half 0.02 → drag $4):
    # net = 35 − 11 − 2.80 = 21.20.
    net = expected_close_net_pnl(
        entry_credit=Decimal("35.00"), current_mid_cost=Decimal("7.00"),
        leg_half_spreads=[Decimal("0.02"), Decimal("0.02")], leg_qtys=QTYS,
    )
    assert net == Decimal("21.20")


# --- decide_exit TP guard -----------------------------------------------------

def _d(**over):
    base = dict(dte=30, pct_max_profit=0.60, priced=True,
                tp_pct=TP, dte_close=DTE_CLOSE)
    base.update(over)
    return decide_exit(**base)


def test_tp_crossed_net_negative_holds():
    assert _d(tp_net_pnl=-6.8) == (None, "HOLD_TP_UNECONOMIC")


def test_tp_crossed_net_zero_holds():
    assert _d(tp_net_pnl=0.0) == (None, "HOLD_TP_UNECONOMIC")


def test_tp_crossed_net_positive_closes():
    assert _d(tp_net_pnl=5.0) == ("close", "CLOSED_TAKE_PROFIT")


def test_tp_crossed_net_none_legacy_closes():
    assert _d(tp_net_pnl=None) == ("close", "CLOSED_TAKE_PROFIT")


def test_dte_close_with_negative_net_still_closes():
    # TP NOT crossed, DTE<=7, net negative → DTE management close UNCHANGED
    # (risk management may book negative, correctly labeled).
    assert _d(dte=5, pct_max_profit=0.10, tp_net_pnl=-12.8) == (
        "close", "CLOSED_DTE_MANAGEMENT")


def test_expiry_with_negative_net_still_expires():
    assert _d(dte=0, pct_max_profit=0.90, tp_net_pnl=-6.8) == (
        "expire", "EXPIRED")


def test_stale_still_holds_regardless_of_net():
    assert _d(priced=False, tp_net_pnl=5.0) == (None, "HOLD_STALE")
