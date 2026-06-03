"""Phase H1 — trade lifecycle ADVISORY (strictly read-only).

Advisory-only guidance for OPEN options paper positions: take-profit, DTE
management, loss/risk, assignment (reuse F1), and an informational
"Potential Roll Preview". NO execution, NO auto-roll/close, NO lifecycle
mutation, NO writes, NO canary, NO scheduler.

Current value (drives % max profit + loss %) resolves: latest MTM lifecycle
event → chain snapshot mids → null. Source + as-of surfaced. Null (omit a
signal) when pricing is unavailable — never fabricated.

`advise_position` is pure for unit testing with synthetic fixtures.
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.options.opportunities.assignment import assess_assignment_risk

CONTRACT_MULTIPLIER = 100

# Advisory thresholds (display-only; not policy, not execution).
TP_STRONG = 0.75       # Strong Take Profit
TP_CONSIDER = 0.50     # Consider Close
DTE_URGENT = 7         # Urgent Management
DTE_MANAGE = 21        # Manage Soon
LOSS_HIGH = 0.75       # High Loss Risk
LOSS_WARN = 0.50       # Loss Warning


def _num(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def advise_position(
    *,
    trade: dict,
    legs: list[dict],
    current_mids: dict[str, float],
    value_source: str | None,
    value_as_of: Any,
    assignment: dict | None,
    roll_preview: dict | None,
) -> dict:
    """Pure advisory for one open position. current_mids maps option_symbol →
    current mid (from MTM or chain). When any leg is unpriced, value-derived
    signals (take-profit / loss) are null; DTE + assignment still apply."""
    entry_credit = _num(trade.get("entry_credit"))
    max_profit = _num(trade.get("max_profit"))
    max_loss = _num(trade.get("max_loss"))
    dte = trade.get("dte")

    priced = bool(legs) and all(current_mids.get(l.get("option_symbol")) is not None for l in legs)
    pct_max_profit = profit_so_far = loss = pct_max_risk = None
    if priced and entry_credit is not None:
        cost = 0.0
        for l in legs:
            mid = current_mids[l["option_symbol"]]
            close_sign = 1 if str(l.get("side", "")).upper() == "SELL" else -1
            cost += mid * close_sign * int(l.get("qty") or 0) * CONTRACT_MULTIPLIER
        profit_so_far = round(entry_credit - cost, 2)
        if max_profit and max_profit > 0:
            pct_max_profit = round(profit_so_far / max_profit, 4)
        loss = max(0.0, -profit_so_far)
        if max_loss and max_loss > 0:
            pct_max_risk = round(loss / max_loss, 4)

    if pct_max_profit is None:
        take_profit = None
    elif pct_max_profit >= TP_STRONG:
        take_profit = {"level": "strong", "reason": f"Strong take profit — captured {round(pct_max_profit*100)}% of max profit."}
    elif pct_max_profit >= TP_CONSIDER:
        take_profit = {"level": "consider", "reason": f"Consider closing — captured {round(pct_max_profit*100)}% of max profit."}
    else:
        take_profit = {"level": "hold", "reason": f"Hold — {round(pct_max_profit*100)}% of max profit captured."}

    if dte is None:
        dte_mgmt = None
    elif dte <= DTE_URGENT:
        dte_mgmt = {"level": "urgent", "reason": f"Urgent management — {dte} DTE."}
    elif dte <= DTE_MANAGE:
        dte_mgmt = {"level": "manage", "reason": f"Manage soon — {dte} DTE."}
    else:
        dte_mgmt = {"level": "ok", "reason": f"{dte} DTE."}

    if pct_max_risk is None:
        loss_risk = None
    elif pct_max_risk >= LOSS_HIGH:
        loss_risk = {"level": "high", "reason": f"High loss risk — {round(pct_max_risk*100)}% of max risk."}
    elif pct_max_risk >= LOSS_WARN:
        loss_risk = {"level": "warn", "reason": f"Loss warning — {round(pct_max_risk*100)}% of max risk."}
    else:
        loss_risk = {"level": "ok", "reason": f"Loss {round(pct_max_risk*100)}% of max risk."}

    return {
        "trade_id": trade.get("trade_id"),
        "underlying": trade.get("underlying"),
        "strategy": trade.get("strategy"),
        "dte": dte,
        "pct_max_profit": pct_max_profit,
        "profit_so_far": profit_so_far,
        "take_profit": take_profit,
        "dte_management": dte_mgmt,
        "loss_risk": loss_risk,
        "assignment_risk": assignment,
        "potential_roll_preview": roll_preview,   # informational only
        "value_source": value_source,
        "value_as_of": value_as_of.isoformat() if hasattr(value_as_of, "isoformat") else value_as_of,
    }


# --- read-only DB layer -----------------------------------------------------


def _fetch_open(session: Session, portfolio_id: str | None) -> list[dict]:
    """Open positions (released_at IS NULL) → trade + legs. Read-only."""
    params: dict[str, Any] = {}
    where = ["p.released_at IS NULL"]
    if portfolio_id:
        where.append("p.portfolio_id = :pid")
        params["pid"] = portfolio_id
    rows = session.execute(text(
        f"""
        SELECT t.id AS trade_id, t.underlying, t.strategy_name AS strategy,
               t.entry_credit_dollars AS entry_credit,
               t.max_profit_dollars AS max_profit, t.max_loss_dollars AS max_loss,
               l.option_symbol, l.side, l.qty, l.option_type, l.expiry,
               l.entry_delta
        FROM options_paper_position p
        JOIN options_paper_trade t ON t.id = p.trade_id
        JOIN options_paper_trade_leg l ON l.trade_id = t.id
        WHERE {' AND '.join(where)}
        """
    ), params).mappings().all()
    return [dict(r) for r in rows]


def _latest_mtm(session: Session, trade_id: int):
    r = session.execute(text(
        """
        SELECT payload_json, event_at_utc FROM options_trade_lifecycle_event
        WHERE trade_id = :tid AND event_type = 'MTM'
        ORDER BY event_at_utc DESC LIMIT 1
        """
    ), {"tid": trade_id}).first()
    if not r:
        return None, None
    payload = r[0] if isinstance(r[0], dict) else json.loads(r[0])
    return payload, r[1]


def _chain_mids(session: Session, symbols: list[str]):
    syms = sorted({s for s in symbols if s})
    if not syms:
        return {}, None
    rows = session.execute(text(
        """
        SELECT DISTINCT ON (option_symbol) option_symbol, mid, snapshot_at_utc
        FROM options_chain_snapshot
        WHERE option_symbol = ANY(:syms)
        ORDER BY option_symbol, snapshot_at_utc DESC
        """
    ), {"syms": syms}).mappings().all()
    mids = {r["option_symbol"]: _num(r["mid"]) for r in rows if _num(r["mid"]) is not None}
    as_of = max((r["snapshot_at_utc"] for r in rows), default=None)
    return mids, as_of


def _build_roll_preview(session: Session, underlying: str, current_expiry: dt.date,
                        short_type: str | None, short_delta: float | None) -> dict | None:
    """Informational next-expiry/same-delta preview. Read-only; null when no
    later expiry is quoted. NEVER an order or recommendation."""
    if not short_type:
        return None
    r = session.execute(text(
        """
        SELECT MIN(expiry) FROM options_chain_snapshot
        WHERE underlying = :u AND expiry > :e
          AND snapshot_at_utc = (SELECT MAX(snapshot_at_utc) FROM options_chain_snapshot WHERE underlying = :u)
        """
    ), {"u": underlying, "e": current_expiry}).first()
    if not r or r[0] is None:
        return None
    next_exp = r[0]
    target = abs(short_delta) if short_delta is not None else 0.30
    s = session.execute(text(
        """
        SELECT strike, mid FROM options_chain_snapshot
        WHERE underlying = :u AND expiry = :e AND option_type = :ot AND delta IS NOT NULL
          AND snapshot_at_utc = (SELECT MAX(snapshot_at_utc) FROM options_chain_snapshot WHERE underlying = :u)
        ORDER BY ABS(ABS(delta) - :tgt) LIMIT 1
        """
    ), {"u": underlying, "e": next_exp, "ot": short_type.upper(), "tgt": target}).first()
    if not s:
        return None
    return {
        "to_expiry": next_exp.isoformat(),
        "short_strike": float(s[0]),
        "short_mid": _num(s[1]),
        "note": "Potential roll preview — informational only, not a recommendation or order.",
    }


def get_advisory(session: Session, portfolio_id: str | None = None) -> dict[str, Any]:
    rows = _fetch_open(session, portfolio_id)
    if not rows:
        return {"status": "empty", "open_count": 0, "positions": []}

    today = dt.datetime.now(dt.timezone.utc).date()
    by_trade: dict[Any, dict] = {}
    for r in rows:
        t = by_trade.setdefault(r["trade_id"], {
            "trade": {
                "trade_id": r["trade_id"], "underlying": r["underlying"],
                "strategy": r["strategy"], "entry_credit": r["entry_credit"],
                "max_profit": r["max_profit"], "max_loss": r["max_loss"],
                "dte": (r["expiry"] - today).days if r["expiry"] else None,
            },
            "legs": [],
        })
        t["legs"].append(r)

    positions = []
    for tid, bundle in by_trade.items():
        legs = bundle["legs"]
        syms = [l["option_symbol"] for l in legs]
        mtm, mtm_at = _latest_mtm(session, tid)
        current_mids: dict[str, float] = {}
        value_source = None
        value_as_of = None
        if mtm and isinstance(mtm.get("per_leg"), list):
            for pl in mtm["per_leg"]:
                m = _num(pl.get("mid"))
                if m is not None and pl.get("option_symbol"):
                    current_mids[pl["option_symbol"]] = m
            if current_mids:
                value_source, value_as_of = "mtm_event", mtm_at
        if not all(s in current_mids for s in syms):
            ch_mids, ch_at = _chain_mids(session, syms)
            for s, m in ch_mids.items():
                current_mids.setdefault(s, m)
            if value_source is None and current_mids:
                value_source, value_as_of = "chain", ch_at
            elif ch_mids:
                value_source = "mixed"

        ch_greeks_rows = session.execute(text(
            """
            SELECT DISTINCT ON (option_symbol) option_symbol, delta
            FROM options_chain_snapshot WHERE option_symbol = ANY(:syms)
            ORDER BY option_symbol, snapshot_at_utc DESC
            """
        ), {"syms": sorted(set(syms))}).mappings().all() if syms else []
        cur_delta = {g["option_symbol"]: g["delta"] for g in ch_greeks_rows}
        assign_legs = [
            {"role": ("short_" if str(l["side"]).upper() == "SELL" else "long_")
                     + ("call" if str(l["option_type"]).upper() == "CALL" else "put"),
             "delta": cur_delta.get(l["option_symbol"], l.get("entry_delta")),
             "option_type": l["option_type"]}
            for l in legs
        ]
        assignment = assess_assignment_risk(assign_legs, bundle["trade"]["dte"])

        roll = None
        if bundle["trade"]["dte"] is not None and bundle["trade"]["dte"] <= DTE_MANAGE:
            short = next((l for l in legs if str(l["side"]).upper() == "SELL"), None)
            if short and short.get("expiry"):
                roll = _build_roll_preview(
                    session, bundle["trade"]["underlying"], short["expiry"],
                    short.get("option_type"), _num(short.get("entry_delta")),
                )

        positions.append(advise_position(
            trade=bundle["trade"], legs=legs, current_mids=current_mids,
            value_source=value_source, value_as_of=value_as_of,
            assignment=assignment, roll_preview=roll,
        ))

    return {"status": "live", "open_count": len(positions), "positions": positions}
