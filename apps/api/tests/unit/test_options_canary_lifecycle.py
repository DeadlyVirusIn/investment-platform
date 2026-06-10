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


# ── P6D.33A — net-TP economic guard ────────────────────────────────────────

def test_tp_net_negative_holds_uneconomic():
    assert _d(pct_max_profit=0.60, tp_net_pnl=-5.80) == \
        (None, "HOLD_TP_UNECONOMIC")


def test_tp_net_positive_closes():
    assert _d(pct_max_profit=0.60, tp_net_pnl=21.20) == \
        ("close", "CLOSED_TAKE_PROFIT")


# ── P6D.34C — decision freshness gate ──────────────────────────────────────

def test_tp_eligible_stale_decision_holds():
    assert _d(pct_max_profit=0.60, decision_fresh=False) == \
        (None, "HOLD_STALE_QUOTES")


def test_dte_close_stale_decision_holds():
    assert _d(dte=5, pct_max_profit=0.10, decision_fresh=False) == \
        (None, "HOLD_STALE_QUOTES")


def test_expiry_unaffected_by_stale_decision():
    # Settlement uses price_bar settlement_price — independent of chain
    # quotes, so the expiry branch ignores decision_fresh.
    assert _d(dte=0, pct_max_profit=0.9, decision_fresh=False) == \
        ("expire", "EXPIRED")


def test_tp_fresh_with_positive_net_closes():
    assert _d(pct_max_profit=0.60, decision_fresh=True, tp_net_pnl=21.20) == \
        ("close", "CLOSED_TAKE_PROFIT")


def test_dte_fresh_closes():
    assert _d(dte=5, pct_max_profit=0.10, decision_fresh=True) == \
        ("close", "CLOSED_DTE_MANAGEMENT")


def test_decision_fresh_none_legacy_unchanged():
    # decision_fresh=None (legacy/back-compat) → no gate, identical behavior.
    assert _d(pct_max_profit=0.60, decision_fresh=None) == \
        ("close", "CLOSED_TAKE_PROFIT")
    assert _d(dte=5, pct_max_profit=0.10, decision_fresh=None) == \
        ("close", "CLOSED_DTE_MANAGEMENT")


def test_stale_decision_precedes_uneconomic_guard():
    # Documented order inside the TP branch: freshness FIRST — stale quotes
    # make the pct/net numbers themselves untrustworthy.
    assert _d(pct_max_profit=0.60, decision_fresh=False,
              tp_net_pnl=-5.80) == (None, "HOLD_STALE_QUOTES")


def test_unpriced_precedes_freshness_gate():
    # not-priced HOLD_STALE keeps top precedence regardless of the gate.
    assert _d(priced=False, pct_max_profit=0.99, decision_fresh=False) == \
        (None, "HOLD_STALE")
