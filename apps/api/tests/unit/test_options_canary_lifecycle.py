"""Phase P6B.0 — pure unit coverage for the canary exit decision."""

from __future__ import annotations

from apps.api.src.options.canary.lifecycle import decide_exit

TP = 0.50
DTE_CLOSE = 7


def _d(**over):
    base = dict(dte=30, pct_max_profit=0.10, priced=True,
                tp_pct=TP, dte_close=DTE_CLOSE)
    base.update(over)
    return decide_exit(**base)


def test_stale_quotes_hold():
    assert _d(priced=False, pct_max_profit=0.99) == (None, "HOLD_STALE")


def test_expiry_takes_precedence():
    # DTE<=0 wins even over a take-profit-worthy pct
    assert _d(dte=0, pct_max_profit=0.9) == ("expire", "EXPIRED")


def test_take_profit_at_threshold():
    assert _d(pct_max_profit=0.50) == ("close", "CLOSED_TAKE_PROFIT")
    assert _d(pct_max_profit=0.55) == ("close", "CLOSED_TAKE_PROFIT")


def test_dte_management_close():
    assert _d(dte=7, pct_max_profit=0.10) == ("close", "CLOSED_DTE_MANAGEMENT")
    assert _d(dte=5, pct_max_profit=0.10) == ("close", "CLOSED_DTE_MANAGEMENT")


def test_take_profit_precedence_over_dte():
    # within DTE window but TP hit → TP reason wins (checked before DTE)
    assert _d(dte=5, pct_max_profit=0.60) == ("close", "CLOSED_TAKE_PROFIT")


def test_hold_when_nothing_triggers():
    assert _d(dte=30, pct_max_profit=0.10) == (None, "HOLD")


def test_unpriced_pct_none_holds_outside_dte():
    assert _d(dte=30, pct_max_profit=None) == (None, "HOLD")
