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

from apps.api.src.config import settings
from apps.api.src.options.canary import economics, selection
from apps.api.src.options.canary.engine import release_one
from apps.api.src.options.paper.engine import record_mtm

CONTRACT_MULTIPLIER = 100


def decide_exit(
    *, dte: int | None, pct_max_profit: float | None, priced: bool,
    tp_pct: float, dte_close: int, tp_net_pnl: float | None = None,
    decision_fresh: bool | None = None,
) -> tuple[str | None, str]:
    """Return (action, reason). action ∈ {None(HOLD), 'close', 'expire'}.
    Order: stale→HOLD, expiry, take-profit, DTE management, else HOLD.

    P6D.33A TP guard: when the GROSS take-profit trigger fires but
    `tp_net_pnl` (estimated NET realized P&L of closing now, after close
    drag + round-trip fees — economics.expected_close_net_pnl) is <= 0,
    HOLD instead — never book negative realized labeled
    CLOSED_TAKE_PROFIT. tp_net_pnl=None preserves legacy behavior. DTE and
    expiry branches are UNCHANGED (a DTE-management close may book negative
    P&L — that is risk management, correctly labeled
    CLOSED_DTE_MANAGEMENT).

    P6D.34C decision freshness gate: when `decision_fresh` is False the
    TP branch and the DTE-management branch return
    (None, "HOLD_STALE_QUOTES") instead of closing — never book a close
    against quotes older than OPTIONS_CANARY_MAX_DECISION_AGE_SECONDS.
    The EXPIRY branch is UNAFFECTED (settlement uses the price_bar
    settlement price, independent of chain quotes). decision_fresh=None
    preserves legacy behavior (no gate). ORDER inside the TP branch:
    freshness FIRST, then the 33A uneconomic guard — a stale quote makes
    the pct/net numbers themselves untrustworthy, so HOLD_STALE_QUOTES is
    the more truthful reason when both would hold."""
    if not priced:
        return (None, "HOLD_STALE")
    if dte is not None and dte <= 0:
        return ("expire", "EXPIRED")
    if pct_max_profit is not None and pct_max_profit >= tp_pct:
        if decision_fresh is False:
            return (None, "HOLD_STALE_QUOTES")
        if tp_net_pnl is not None and tp_net_pnl <= 0:
            return (None, "HOLD_TP_UNECONOMIC")
        return ("close", "CLOSED_TAKE_PROFIT")
    if dte is not None and dte <= dte_close:
        if decision_fresh is False:
            return (None, "HOLD_STALE_QUOTES")
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
    # P6D.34A — age quotes as-of the cycle's `now` (deterministic in replay).
    quotes = selection.latest_chain_quotes(session, symbols, now=now)
    priced = bool(legs) and all(
        s in quotes and quotes[s].mid is not None for s in symbols
    )

    today = now.date()
    expiries = [l["expiry"] for l in legs if l["expiry"]]
    dte = (min(expiries) - today).days if expiries else None

    pct_max_profit = None
    tp_net_pnl: float | None = None
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
        # P6D.33A — estimated NET P&L of closing NOW: gross mid cost plus
        # close-side drag (min(half_spread, cap)×100 per leg) plus ROUND-TRIP
        # fees (open fees already incurred + close-side fees = the trade's
        # fees_total at close), subtracted from entry credit.
        half_spreads = []
        for l in legs:
            q = quotes[l["option_symbol"]]
            half_spreads.append(
                (q.ask - q.bid) / Decimal("2")
                if q.ask is not None and q.bid is not None else Decimal("0")
            )
        tp_net_pnl = float(economics.expected_close_net_pnl(
            entry_credit=entry_credit, current_mid_cost=cost,
            leg_half_spreads=half_spreads,
            leg_qtys=[int(l["qty"]) for l in legs],
        ))

    # MTM observation (same txn — rolled back with the position if release fails)
    record_mtm(trade_id, quotes_by_symbol=quotes, session=session)

    # P6D.34C — decision freshness: the WORST (max) effective quote age
    # across the legs must be within the decision-age budget for a close
    # decision to be trusted. None-safe: missing ages → not fresh.
    eff_ages = [q.effective_age_seconds for q in quotes.values()
                if q.effective_age_seconds is not None]
    max_eff = max(eff_ages) if eff_ages else None
    decision_fresh = bool(
        priced and max_eff is not None
        and max_eff <= int(settings.OPTIONS_CANARY_MAX_DECISION_AGE_SECONDS)
    )

    action, reason = decide_exit(
        dte=dte, pct_max_profit=pct_max_profit, priced=priced,
        tp_pct=tp_pct, dte_close=dte_close, tp_net_pnl=tp_net_pnl,
        decision_fresh=decision_fresh,
    )

    released = False
    if action == "close":
        rel = release_one(session, portfolio_id=portfolio_id, trade_id=trade_id,
                          terminal="close", now=now, quotes=quotes, reason=reason)
        released = rel.status == "released"
    elif action == "expire":
        # P6D.36B — settlement must be the close FOR THE EXPIRY DATE
        # (exact-day bar, or last trading-day close before a weekend/
        # holiday expiry within the guard window), never just the latest
        # bar. No valid settlement price → do NOT force settlement:
        # HOLD and let the next lifecycle cycle retry once the bar lands.
        settle = selection.settlement_price(
            session, trade["underlying"],
            expiry=min(expiries), as_of=now,
        )
        if settle is None:
            action, reason = None, "HOLD_AWAITING_SETTLEMENT"
        else:
            rel = release_one(
                session, portfolio_id=portfolio_id, trade_id=trade_id,
                terminal="expire", now=now, settlement_price=settle,
            )
            released = rel.status == "released"

    return {"trade_id": trade_id, "action": action, "reason": reason,
            "dte": dte, "pct_max_profit": pct_max_profit,
            "tp_net_pnl": tp_net_pnl, "released": released,
            "max_effective_age_seconds": max_eff,
            "decision_fresh": decision_fresh}
