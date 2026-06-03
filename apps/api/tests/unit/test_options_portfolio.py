"""Phase G1 — options portfolio aggregation unit coverage. Pure, no DB."""

from __future__ import annotations

import datetime as dt

from apps.api.src.options.portfolio.service import aggregate_portfolio

AO = dt.datetime(2026, 6, 3, 14, 0, 0)


def _leg(trade_id, underlying, side, sym, *, max_loss, max_profit,
         entry_delta=None, entry_theta=None, entry_vega=None, qty=1, dte=30,
         strategy="SHORT_PUT_CREDIT_SPREAD"):
    return {
        "trade_id": trade_id, "underlying": underlying, "strategy": strategy,
        "max_loss": max_loss, "max_profit": max_profit, "dte": dte,
        "option_symbol": sym, "side": side, "qty": qty,
        "entry_delta": entry_delta, "entry_theta": entry_theta, "entry_vega": entry_vega,
    }


def test_empty_portfolio_honest():
    r = aggregate_portfolio([], {})
    assert r["status"] == "empty"
    assert r["open_count"] == 0
    assert r["capital_at_risk"] == 0.0 and r["max_profit"] == 0.0
    assert r["net_delta"] is None and r["net_theta"] is None and r["net_vega"] is None
    assert r["greeks_source"] is None
    assert r["concentration"] == [] and r["positions"] == []


def test_sign_conventions_and_multiplier_current_greeks():
    # one put credit spread: SELL short put + BUY long put, qty 1.
    legs = [
        _leg(1, "QQQ", "SELL", "A", max_loss=75, max_profit=25),
        _leg(1, "QQQ", "BUY", "B", max_loss=75, max_profit=25),
    ]
    cur = {
        "A": {"delta": -0.30, "theta": -0.05, "vega": 0.10, "as_of": AO},
        "B": {"delta": -0.20, "theta": -0.03, "vega": 0.08, "as_of": AO},
    }
    r = aggregate_portfolio(legs, cur)
    # net delta = (-0.30·SELL=-1·100) + (-0.20·BUY=+1·100) = +30 − 20 = 10
    assert r["net_delta"] == 10.0
    assert r["net_theta"] == 2.0     # (−0.05·−1·100)+(−0.03·+1·100)=5−3
    assert r["net_vega"] == -2.0     # (0.10·−1·100)+(0.08·+1·100)=−10+8
    assert r["greeks_source"] == "current"
    assert r["greeks_as_of"] == AO.isoformat()
    assert r["open_count"] == 1
    assert r["capital_at_risk"] == 75.0 and r["max_profit"] == 25.0


def test_capital_profit_sums_and_concentration():
    legs = [
        _leg(1, "QQQ", "SELL", "A", max_loss=75, max_profit=25),
        _leg(1, "QQQ", "BUY", "B", max_loss=75, max_profit=25),
        _leg(2, "SPY", "SELL", "C", max_loss=100, max_profit=50),
        _leg(2, "SPY", "BUY", "D", max_loss=100, max_profit=50),
    ]
    r = aggregate_portfolio(legs, {})
    assert r["open_count"] == 2
    assert r["capital_at_risk"] == 175.0 and r["max_profit"] == 75.0
    conc = {c["underlying"]: c for c in r["concentration"]}
    assert conc["SPY"]["pct"] == 0.5714 and conc["SPY"]["high"] is True   # 100/175 >40%
    assert conc["QQQ"]["pct"] == 0.4286 and conc["QQQ"]["high"] is True   # 75/175 >40%


def test_high_concentration_threshold_boundary():
    # single underlying = 100% → high
    legs = [_leg(1, "QQQ", "SELL", "A", max_loss=100, max_profit=40)]
    r = aggregate_portfolio(legs, {})
    assert r["concentration"][0]["pct"] == 1.0 and r["concentration"][0]["high"] is True


def test_entry_fallback_and_mixed_source():
    legs = [
        _leg(1, "QQQ", "SELL", "A", max_loss=75, max_profit=25,
             entry_delta=-0.28, entry_theta=-0.04, entry_vega=0.09),  # entry only
        _leg(1, "QQQ", "BUY", "B", max_loss=75, max_profit=25),       # current only
    ]
    cur = {"B": {"delta": -0.20, "theta": -0.03, "vega": 0.08, "as_of": AO}}
    r = aggregate_portfolio(legs, cur)
    assert r["greeks_source"] == "mixed"
    # A entry delta −0.28 SELL → +28 ; B current −0.20 BUY → −20 ; net 8
    assert r["net_delta"] == 8.0

    # entry-only (no current at all)
    r2 = aggregate_portfolio(
        [_leg(1, "QQQ", "SELL", "A", max_loss=75, max_profit=25, entry_delta=-0.30)], {})
    assert r2["greeks_source"] == "entry" and r2["net_delta"] == 30.0


def test_no_greeks_at_all_null():
    legs = [_leg(1, "QQQ", "SELL", "A", max_loss=75, max_profit=25)]
    r = aggregate_portfolio(legs, {})
    assert r["greeks_source"] is None
    assert r["net_delta"] is None and r["net_theta"] is None and r["net_vega"] is None
    assert r["capital_at_risk"] == 75.0   # capital still sums without greeks
