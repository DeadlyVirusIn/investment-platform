"""Phase G1 — options portfolio aggregation (read-only).

Aggregates OPEN options paper positions into portfolio-level risk + greeks.
Open = `options_paper_position.released_at IS NULL` (positions exist only for
filled trades). Pure aggregation (`aggregate_portfolio`) is split out for
unit testing with synthetic fixtures — the DB wrappers only fetch rows.

NO mutation, NO fill, NO lifecycle/canary/execution, NO fabricated position.
Honest: empty when no open positions; greeks null when unresolvable.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

CONTRACT_MULTIPLIER = 100
HIGH_CONCENTRATION_PCT = 0.40   # >40% of capital-at-risk in one underlying


def _num(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def aggregate_portfolio(
    legs: list[dict], current_greeks: dict[str, dict],
) -> dict[str, Any]:
    """Pure aggregation. `legs` carry trade-level fields (deduped by trade_id
    for capital/profit) + per-leg side/qty/option_symbol/entry greeks.
    `current_greeks` maps option_symbol → {delta, theta, vega, as_of}.

    net greek = Σ  greek × qty × sign × 100   (sign +1 BUY / −1 SELL).
    Current greeks preferred; entry greeks fallback. Source labelled.
    """
    if not legs:
        return {
            "status": "empty",
            "open_count": 0,
            "capital_at_risk": 0.0,
            "max_profit": 0.0,
            "net_delta": None, "net_theta": None, "net_vega": None,
            "greeks_source": None, "greeks_as_of": None,
            "concentration": [],
            "positions": [],
        }

    trades: dict[Any, dict] = {}
    net = {"delta": 0.0, "theta": 0.0, "vega": 0.0}
    have_any_greek = False
    used_current = False
    used_entry = False
    greeks_as_of: dt.datetime | None = None

    for lg in legs:
        tid = lg["trade_id"]
        t = trades.setdefault(tid, {
            "trade_id": tid,
            "underlying": lg.get("underlying"),
            "strategy": lg.get("strategy"),
            "capital_at_risk": _num(lg.get("max_loss")) or 0.0,
            "max_profit": _num(lg.get("max_profit")) or 0.0,
            "dte": lg.get("dte"),
            "net_delta": 0.0, "net_theta": 0.0, "net_vega": 0.0,
        })
        sign = 1 if str(lg.get("side", "")).upper() == "BUY" else -1
        qty = int(lg.get("qty") or 0)
        cg = current_greeks.get(lg.get("option_symbol"))
        for greek in ("delta", "theta", "vega"):
            cur = _num(cg.get(greek)) if cg else None
            val = cur if cur is not None else _num(lg.get(f"entry_{greek}"))
            if val is None:
                continue
            have_any_greek = True
            if cur is not None:
                used_current = True
                ao = cg.get("as_of") if cg else None
                if ao is not None and (greeks_as_of is None or ao > greeks_as_of):
                    greeks_as_of = ao
            else:
                used_entry = True
            contrib = val * qty * sign * CONTRACT_MULTIPLIER
            net[greek] += contrib
            t[f"net_{greek}"] += contrib

    capital = sum(t["capital_at_risk"] for t in trades.values())
    max_profit = sum(t["max_profit"] for t in trades.values())

    # concentration by underlying (share of capital-at-risk)
    by_und: dict[str, float] = {}
    for t in trades.values():
        by_und[t["underlying"]] = by_und.get(t["underlying"], 0.0) + t["capital_at_risk"]
    concentration = []
    for und, car in sorted(by_und.items(), key=lambda kv: kv[1], reverse=True):
        pct = (car / capital) if capital > 0 else 0.0
        concentration.append({
            "underlying": und,
            "capital_at_risk": round(car, 2),
            "pct": round(pct, 4),
            "high": pct > HIGH_CONCENTRATION_PCT,
        })

    if not have_any_greek:
        source = None
    elif used_current and used_entry:
        source = "mixed"
    elif used_current:
        source = "current"
    else:
        source = "entry"

    def _g(x: float) -> float | None:
        return round(x, 2) if have_any_greek else None

    return {
        "status": "live",
        "open_count": len(trades),
        "capital_at_risk": round(capital, 2),
        "max_profit": round(max_profit, 2),
        "net_delta": _g(net["delta"]),
        "net_theta": _g(net["theta"]),
        "net_vega": _g(net["vega"]),
        "greeks_source": source,
        "greeks_as_of": greeks_as_of.isoformat() if greeks_as_of else None,
        "concentration": concentration,
        "positions": [
            {
                "trade_id": t["trade_id"],
                "underlying": t["underlying"],
                "strategy": t["strategy"],
                "capital_at_risk": round(t["capital_at_risk"], 2),
                "max_profit": round(t["max_profit"], 2),
                "net_delta": round(t["net_delta"], 2) if have_any_greek else None,
                "net_theta": round(t["net_theta"], 2) if have_any_greek else None,
                "net_vega": round(t["net_vega"], 2) if have_any_greek else None,
                "dte": t["dte"],
            }
            for t in sorted(trades.values(), key=lambda x: x["capital_at_risk"], reverse=True)
        ],
    }


def _fetch_open_legs(session: Session, portfolio_id: str | None) -> list[dict]:
    """Open-position legs (released_at IS NULL) joined to trade + leg, with
    trade-level max_loss/max_profit and per-leg entry greeks. Read-only."""
    params: dict[str, Any] = {}
    where = ["p.released_at IS NULL"]
    if portfolio_id:
        where.append("p.portfolio_id = :pid")
        params["pid"] = portfolio_id
    rows = session.execute(text(
        f"""
        SELECT t.id AS trade_id, t.underlying, t.strategy_name AS strategy,
               t.max_loss_dollars AS max_loss, t.max_profit_dollars AS max_profit,
               l.option_symbol, l.side, l.qty, l.expiry,
               l.entry_delta, l.entry_theta, l.entry_vega
        FROM options_paper_position p
        JOIN options_paper_trade t ON t.id = p.trade_id
        JOIN options_paper_trade_leg l ON l.trade_id = t.id
        WHERE {' AND '.join(where)}
        """
    ), params).mappings().all()
    today = dt.datetime.now(dt.timezone.utc).date()
    out: list[dict] = []
    for r in rows:
        d = dict(r)
        d["dte"] = (r["expiry"] - today).days if r["expiry"] else None
        out.append(d)
    return out


def _resolve_current_greeks(session: Session, symbols: list[str]) -> dict[str, dict]:
    """Latest chain greeks per option_symbol. Empty when none."""
    syms = sorted({s for s in symbols if s})
    if not syms:
        return {}
    rows = session.execute(text(
        """
        SELECT DISTINCT ON (option_symbol)
               option_symbol, delta, theta, vega, snapshot_at_utc
        FROM options_chain_snapshot
        WHERE option_symbol = ANY(:syms)
        ORDER BY option_symbol, snapshot_at_utc DESC
        """
    ), {"syms": syms}).mappings().all()
    return {
        r["option_symbol"]: {
            "delta": r["delta"], "theta": r["theta"], "vega": r["vega"],
            "as_of": r["snapshot_at_utc"],
        }
        for r in rows
    }


def get_portfolio(session: Session, portfolio_id: str | None = None) -> dict[str, Any]:
    """Read-only options portfolio aggregate over open positions."""
    legs = _fetch_open_legs(session, portfolio_id)
    greeks = _resolve_current_greeks(session, [l["option_symbol"] for l in legs])
    return aggregate_portfolio(legs, greeks)
