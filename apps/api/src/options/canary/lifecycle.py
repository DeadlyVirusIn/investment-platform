"""Phase P6B.0 — canary exit policy (manage open positions).

Smallest defined-risk exit rules: take-profit at TP_PCT of max profit, DTE
management close at/under DTE_CLOSE, expiry settlement at DTE<=0, and HOLD on
stale/unpriced quotes (never force-close on missing data).

`decide_exit` is pure (unit-tested). `manage_one` does MTM + the decision +
release_one, all in the caller's transaction (one commit per position). The
lifecycle path manages EXISTING open positions regardless of
OPTIONS_CANARY_ENABLED (the gate controls promotion only). Paper-only.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.options.canary import selection
from apps.api.src.options.canary.engine import release_one
from apps.api.src.options.paper.engine import record_mtm

CONTRACT_MULTIPLIER = 100


def decide_exit(
    *, dte: int | None, pct_max_profit: float | None, priced: bool,
    tp_pct: float, dte_close: int,
) -> tuple[str | None, str]:
    """Return (action, reason). action ∈ {None(HOLD), 'close', 'expire'}.
    Order: stale→HOLD, expiry, take-profit, DTE management, else HOLD."""
    if not priced:
        return (None, "HOLD_STALE")
    if dte is not None and dte <= 0:
        return ("expire", "EXPIRED")
    if pct_max_profit is not None and pct_max_profit >= tp_pct:
        return ("close", "CLOSED_TAKE_PROFIT")
    if dte is not None and dte <= dte_close:
        return ("close", "CLOSED_DTE_MANAGEMENT")
    return (None, "HOLD")


def _num(v: Any) -> Decimal | None:
    return None if v is None else Decimal(str(v))


def manage_one(
    session: Session, *, portfolio_id: str, trade_id: int, now: dt.datetime,
    tp_pct: float, dte_close: int,
) -> dict:
    """MTM + exit decision + release for one open position (caller commits)."""
    trade = session.execute(text(
        "SELECT entry_credit_dollars, max_profit_dollars, underlying, status "
        "FROM options_paper_trade WHERE id = :tid"
    ), {"tid": trade_id}).mappings().first()
    if trade is None or trade["status"] != "OPEN":
        return {"trade_id": trade_id, "action": None, "reason": "NOT_OPEN"}

    legs = session.execute(text(
        "SELECT option_symbol, side, qty, expiry, option_type "
        "FROM options_paper_trade_leg WHERE trade_id = :tid"
    ), {"tid": trade_id}).mappings().all()
    symbols = [l["option_symbol"] for l in legs]
    quotes = selection.latest_chain_quotes(session, symbols)
    priced = bool(legs) and all(
        s in quotes and quotes[s].mid is not None for s in symbols
    )

    today = now.date()
    expiries = [l["expiry"] for l in legs if l["expiry"]]
    dte = (min(expiries) - today).days if expiries else None

    pct_max_profit = None
    if priced:
        entry_credit = _num(trade["entry_credit_dollars"]) or Decimal("0")
        max_profit = _num(trade["max_profit_dollars"])
        cost = Decimal("0")
        for l in legs:
            mid = quotes[l["option_symbol"]].mid
            close_sign = 1 if str(l["side"]).upper() == "SELL" else -1
            cost += mid * close_sign * int(l["qty"]) * CONTRACT_MULTIPLIER
        profit = entry_credit - cost
        if max_profit and max_profit > 0:
            pct_max_profit = float(profit / max_profit)

    # MTM observation (same txn — rolled back with the position if release fails)
    record_mtm(trade_id, quotes_by_symbol=quotes, session=session)

    action, reason = decide_exit(
        dte=dte, pct_max_profit=pct_max_profit, priced=priced,
        tp_pct=tp_pct, dte_close=dte_close,
    )

    released = False
    if action == "close":
        rel = release_one(session, portfolio_id=portfolio_id, trade_id=trade_id,
                          terminal="close", now=now, quotes=quotes, reason=reason)
        released = rel.status == "released"
    elif action == "expire":
        settle = selection.settlement_price(session, trade["underlying"])
        rel = release_one(session, portfolio_id=portfolio_id, trade_id=trade_id,
                          terminal="expire", now=now, settlement_price=settle)
        released = rel.status == "released"

    return {"trade_id": trade_id, "action": action, "reason": reason,
            "dte": dte, "pct_max_profit": pct_max_profit, "released": released}
