"""Phase G2 — options portfolio DETAIL (read-only explainability).

Assembles the full per-position + per-leg view for the options book so a user
can understand: the setup, current mark / cost-to-close, unrealized P&L,
captured premium, reserved capital, and the lifecycle exit plan.

Reuses the SAME primitives the engine/canary use — `selection.latest_chain_quotes`
(current quotes) and `lifecycle.decide_exit` (exit policy) — plus the paper
trade/leg tables and canary reserved capital. NO mutation, NO fill, NO
lifecycle write, NO accounting duplication. Strictly options_* tables.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.config import settings
from apps.api.src.options.canary import lifecycle, selection

CONTRACT_MULTIPLIER = 100


def _f(v: Any) -> float | None:
    return None if v is None else float(v)


# Plain-language setup explanations keyed by engine strategy name.
SETUP_EXPLANATIONS: dict[str, dict[str, str]] = {
    "SHORT_PUT_CREDIT_SPREAD": {
        "summary": "You sold the higher-strike put and bought the lower-strike put.",
        "max_profit": "Max profit = the net credit you received up front.",
        "max_loss": "Max loss = spread width − credit (defined risk).",
        "profit_when": "Profits when the underlying stays above the short put strike.",
        "risk_when": "At risk if the underlying falls below the short put strike; the long put caps the loss.",
    },
    "SHORT_CALL_CREDIT_SPREAD": {
        "summary": "You sold the lower-strike call and bought the higher-strike call.",
        "max_profit": "Max profit = the net credit you received up front.",
        "max_loss": "Max loss = spread width − credit (defined risk).",
        "profit_when": "Profits when the underlying stays below the short call strike.",
        "risk_when": "At risk if the underlying rises above the short call strike; the long call caps the loss.",
    },
    "IRON_CONDOR": {
        "summary": "You sold an out-of-the-money put spread and call spread around the price.",
        "max_profit": "Max profit = the total net credit received.",
        "max_loss": "Max loss = widest wing width − credit (defined risk).",
        "profit_when": "Profits when the underlying stays between the two short strikes.",
        "risk_when": "At risk if the underlying breaks beyond either short strike; the long wings cap the loss.",
    },
}


def get_portfolio_detail(
    session: Session, portfolio_id: str | None = None,
) -> dict[str, Any]:
    """Full read-only options portfolio detail over OPEN positions."""
    where = ["p.released_at IS NULL"]
    params: dict[str, Any] = {}
    if portfolio_id:
        where.append("p.portfolio_id = :pid")
        params["pid"] = portfolio_id
    prows = session.execute(text(
        f"""
        SELECT p.id AS pos_id, p.portfolio_id, p.reserved_capital,
               t.id AS trade_id, t.underlying, t.strategy_name AS strategy,
               t.status, t.opened_at, t.entry_credit_dollars,
               t.max_profit_dollars, t.max_loss_dollars
        FROM options_paper_position p
        JOIN options_paper_trade t ON t.id = p.trade_id
        WHERE {' AND '.join(where)}
        ORDER BY p.opened_at DESC
        """
    ), params).mappings().all()

    if not prows:
        return {
            "status": "empty",
            "portfolio": {
                "cash": None, "reserved_capital": 0.0, "open_positions": 0,
                "capital_at_risk": 0.0, "max_profit": 0.0,
                "unrealized_pnl": 0.0, "realized_pnl": None,
                "buying_power": None,
            },
            "positions": [],
        }

    pf_id = portfolio_id or prows[0]["portfolio_id"]
    pf = session.execute(text(
        "SELECT cash_current, cash_initial FROM options_paper_portfolio WHERE id = :p"
    ), {"p": pf_id}).mappings().first()
    realized = session.execute(text(
        """
        SELECT COALESCE(SUM(t.realized_pnl_dollars), 0)
        FROM options_paper_position p
        JOIN options_paper_trade t ON t.id = p.trade_id
        WHERE p.portfolio_id = :p AND p.released_at IS NOT NULL
        """
    ), {"p": pf_id}).scalar()

    tp_pct = float(settings.OPTIONS_CANARY_TP_PCT)
    dte_close = int(settings.OPTIONS_CANARY_DTE_CLOSE)
    today = dt.datetime.now(dt.timezone.utc).date()

    positions: list[dict] = []
    total_risk = total_reserved = total_unreal = total_max_profit = 0.0
    for r in prows:
        legs = session.execute(text(
            "SELECT option_symbol, side, qty, strike, expiry, option_type, "
            "entry_fill_price FROM options_paper_trade_leg "
            "WHERE trade_id = :t ORDER BY leg_index"
        ), {"t": r["trade_id"]}).mappings().all()
        syms = [l["option_symbol"] for l in legs]
        quotes = selection.latest_chain_quotes(session, syms)
        priced = bool(legs) and all(
            s in quotes and quotes[s].mid is not None for s in syms)

        expiries = [l["expiry"] for l in legs if l["expiry"]]
        dte = (min(expiries) - today).days if expiries else None

        cost = Decimal("0")
        leg_out: list[dict] = []
        # P6D.34B — true freshness for the UI: oldest snapshot among legs +
        # the worst (max) effective age. effective_age_seconds is populated
        # by latest_chain_quotes (P6D.34A) against the real clock here.
        quotes_as_of: dt.datetime | None = None
        max_effective_age: int | None = None
        for l in legs:
            q = quotes.get(l["option_symbol"])
            mid = q.mid if q else None
            if q is not None:
                if quotes_as_of is None or q.snapshot_at_utc < quotes_as_of:
                    quotes_as_of = q.snapshot_at_utc
                eff = q.effective_age_seconds
                if eff is not None and (
                    max_effective_age is None or eff > max_effective_age
                ):
                    max_effective_age = eff
            close_sign = 1 if str(l["side"]).upper() == "SELL" else -1
            if mid is not None:
                cost += mid * close_sign * int(l["qty"]) * CONTRACT_MULTIPLIER
            entry = _f(l["entry_fill_price"])
            mid_f = _f(mid)
            leg_pnl = None
            if mid_f is not None and entry is not None:
                # SELL: received entry, buy back at mid → (entry-mid). BUY: opposite.
                d = (entry - mid_f) if str(l["side"]).upper() == "SELL" else (mid_f - entry)
                leg_pnl = round(d * int(l["qty"]) * CONTRACT_MULTIPLIER, 2)
            bid, ask = (_f(q.bid), _f(q.ask)) if q else (None, None)
            leg_out.append({
                "side": l["side"],
                "option_symbol": l["option_symbol"],
                "strike": _f(l["strike"]),
                "expiry": l["expiry"].isoformat() if l["expiry"] else None,
                "option_type": l["option_type"],
                "qty": int(l["qty"]),
                "entry_fill_price": entry,
                "bid": bid, "ask": ask, "mid": mid_f,
                "open_interest": (q.open_interest if q else None),
                "spread": (round(ask - bid, 4) if (bid is not None and ask is not None) else None),
                "quote_age_seconds": (q.quote_age_seconds if q else None),
                # P6D.34B — true age right now (stored age is ingest-time ~0).
                "effective_age_seconds": (q.effective_age_seconds if q else None),
                "leg_pnl": leg_pnl,
            })

        entry_credit = _f(r["entry_credit_dollars"])
        max_profit = _f(r["max_profit_dollars"])
        max_loss = _f(r["max_loss_dollars"])
        reserved = _f(r["reserved_capital"])
        cost_f = float(cost) if priced else None
        unreal = (
            (entry_credit - cost_f)
            if (priced and entry_credit is not None) else None
        )
        captured = (
            (unreal / max_profit) if (unreal is not None and max_profit) else None
        )
        unreal_pct = (
            (unreal / reserved * 100.0)
            if (unreal is not None and reserved) else None
        )
        action, reason = lifecycle.decide_exit(
            dte=dte, pct_max_profit=captured, priced=priced,
            tp_pct=tp_pct, dte_close=dte_close,
        )

        total_risk += max_loss or 0.0
        total_reserved += reserved or 0.0
        total_unreal += unreal or 0.0
        total_max_profit += max_profit or 0.0

        positions.append({
            "trade_id": r["trade_id"],
            "underlying": r["underlying"],
            "strategy": r["strategy"],
            "status": r["status"],
            "opened_at": r["opened_at"].isoformat() if r["opened_at"] else None,
            "dte": dte,
            "entry_credit": entry_credit,
            "max_profit": max_profit,
            "max_loss": max_loss,
            "reserved_capital": reserved,
            "current_cost_to_close": (round(cost_f, 2) if cost_f is not None else None),
            "unrealized_pnl": (round(unreal, 2) if unreal is not None else None),
            "unrealized_pnl_pct": (round(unreal_pct, 2) if unreal_pct is not None else None),
            "captured_pct": (round(captured * 100.0, 2) if captured is not None else None),
            "priced": priced,
            # P6D.34B — position-level freshness for the UI banner.
            "quotes_as_of": (quotes_as_of.isoformat() if quotes_as_of else None),
            "max_effective_age_seconds": max_effective_age,
            "lifecycle": {
                "action": action or "HOLD",
                "reason": reason,
                "tp_threshold_pct": round(tp_pct * 100.0, 0),
                "dte_management_days": dte_close,
            },
            "setup": SETUP_EXPLANATIONS.get(r["strategy"]),
            "legs": leg_out,
        })

    cash = _f(pf["cash_current"]) if pf else None
    portfolio = {
        "cash": (round(cash, 2) if cash is not None else None),
        "reserved_capital": round(total_reserved, 2),
        "open_positions": len(positions),
        "capital_at_risk": round(total_risk, 2),
        "max_profit": round(total_max_profit, 2),
        "unrealized_pnl": round(total_unreal, 2),
        "realized_pnl": _f(realized),
        # Buying power = free cash (reserve already debited at open).
        "buying_power": (round(cash, 2) if cash is not None else None),
    }
    return {"status": "live", "portfolio": portfolio, "positions": positions}
