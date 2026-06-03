"""Phase H1 — lifecycle advisory unit coverage (pure advise_position)."""

from __future__ import annotations

from apps.api.src.options.portfolio.advisory import advise_position

LEGS = [
    {"option_symbol": "A", "side": "SELL", "qty": 1},
    {"option_symbol": "B", "side": "BUY", "qty": 1},
]


def _trade(**k):
    base = dict(trade_id=1, underlying="QQQ", strategy="SHORT_PUT_CREDIT_SPREAD",
                entry_credit=35.0, max_profit=35.0, max_loss=165.0, dte=30)
    base.update(k)
    return base


def _adv(mids, **tk):
    return advise_position(
        trade=_trade(**tk), legs=LEGS, current_mids=mids,
        value_source="chain", value_as_of=None, assignment=None, roll_preview=None,
    )


def test_take_profit_tiers():
    # cost_to_close = (midA − midB) × 100 ; profit = entry_credit − cost
    assert _adv({"A": 0.20, "B": 0.12})["take_profit"]["level"] == "strong"     # ~77% ≥75
    assert _adv({"A": 0.30, "B": 0.125})["take_profit"]["level"] == "consider"  # 50%
    assert _adv({"A": 0.50, "B": 0.20})["take_profit"]["level"] == "hold"       # ~14%


def test_dte_tiers():
    assert _adv({"A": 0.30, "B": 0.125}, dte=5)["dte_management"]["level"] == "urgent"
    assert _adv({"A": 0.30, "B": 0.125}, dte=15)["dte_management"]["level"] == "manage"
    assert _adv({"A": 0.30, "B": 0.125}, dte=30)["dte_management"]["level"] == "ok"


def test_loss_tiers():
    assert _adv({"A": 1.30, "B": 0.125})["loss_risk"]["level"] == "warn"   # 50% max risk
    assert _adv({"A": 1.70, "B": 0.10})["loss_risk"]["level"] == "high"    # ~76%


def test_sign_and_profit_math():
    r = _adv({"A": 0.30, "B": 0.125})
    assert r["profit_so_far"] == 17.5 and r["pct_max_profit"] == 0.5


def test_value_source_passthrough():
    r = _adv({"A": 0.30, "B": 0.125})
    assert r["value_source"] == "chain"


def test_unpriced_nulls_value_signals_but_keeps_dte():
    r = _adv({"A": 0.30}, dte=5)   # B missing → unpriced
    assert r["pct_max_profit"] is None
    assert r["take_profit"] is None and r["loss_risk"] is None
    assert r["dte_management"]["level"] == "urgent"   # DTE still applies
