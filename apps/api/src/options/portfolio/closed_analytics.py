"""Phase 2 — closed options trade ANALYTICS (read-only, display-only).

Aggregates CLOSED / released options paper trades into win/loss, realized
P&L, expectancy, profit factor, and per-strategy / per-exit-reason breakdowns.

Closed = `options_paper_position.released_at IS NOT NULL` (positions exist only
for filled trades; a release marks the terminal exit). The pure aggregation
(`aggregate_closed`) is split out for unit testing with synthetic fixtures —
the DB wrapper (`get_closed_analytics`) only fetches rows.

NO mutation, NO fill, NO lifecycle/canary/execution, NO accounting write.
Honest: empty when no closed trades; metrics null when undefined.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def _num(v: Any) -> float:
    """Realized P&L coercion. None / unparseable → 0.0."""
    if v is None:
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def aggregate_closed(trades: list[dict]) -> dict[str, Any]:
    """Pure aggregation over closed trades.

    Each trade dict supplies at least:
      - realized_pnl_dollars (float|None → 0.0)
      - strategy (str)
      - exit_reason (str|None)

    profit_factor = Σ(winning realized) / |Σ(losing realized)|, and is None
    when there are NO losses (undefined) or when total_closed == 0.
    """
    if not trades:
        return {
            "status": "empty",
            "total_closed": 0,
            "wins": 0,
            "losses": 0,
            "breakeven": 0,
            "win_rate": None,
            "total_realized": 0.0,
            "avg_winner": None,
            "avg_loser": None,
            "expectancy": None,
            "profit_factor": None,
            "by_strategy": [],
            "by_exit_reason": [],
        }

    total_closed = len(trades)
    wins = losses = breakeven = 0
    total_realized = 0.0
    gross_win = 0.0
    gross_loss = 0.0   # sum of losing realized (negative)

    strat: dict[str, dict[str, float]] = {}
    reason: dict[str, dict[str, float]] = {}

    for tr in trades:
        pnl = _num(tr.get("realized_pnl_dollars"))
        total_realized += pnl

        if pnl > 0:
            wins += 1
            gross_win += pnl
        elif pnl < 0:
            losses += 1
            gross_loss += pnl
        else:
            breakeven += 1

        s_key = tr.get("strategy") or "UNKNOWN"
        s = strat.setdefault(
            s_key, {"count": 0, "wins": 0, "losses": 0, "realized": 0.0})
        s["count"] += 1
        s["realized"] += pnl
        if pnl > 0:
            s["wins"] += 1
        elif pnl < 0:
            s["losses"] += 1

        r_key = tr.get("exit_reason") or "UNKNOWN"
        r = reason.setdefault(r_key, {"count": 0, "realized": 0.0})
        r["count"] += 1
        r["realized"] += pnl

    win_rate = (wins / total_closed) if total_closed else None
    avg_winner = (gross_win / wins) if wins else None
    avg_loser = (gross_loss / losses) if losses else None
    expectancy = (total_realized / total_closed) if total_closed else None
    # No losses → profit_factor undefined (None). Otherwise gross_win / |gross_loss|.
    profit_factor = (
        (gross_win / abs(gross_loss)) if gross_loss != 0 else None
    )

    by_strategy = [
        {
            "strategy": k,
            "count": v["count"],
            "wins": int(v["wins"]),
            "losses": int(v["losses"]),
            "realized": round(v["realized"], 2),
            "win_rate": (v["wins"] / v["count"]) if v["count"] else None,
        }
        for k, v in sorted(
            strat.items(), key=lambda kv: kv[1]["realized"], reverse=True)
    ]
    by_exit_reason = [
        {
            "exit_reason": k,
            "count": int(v["count"]),
            "realized": round(v["realized"], 2),
        }
        for k, v in sorted(
            reason.items(), key=lambda kv: kv[1]["realized"], reverse=True)
    ]

    return {
        "status": "live",
        "total_closed": total_closed,
        "wins": wins,
        "losses": losses,
        "breakeven": breakeven,
        "win_rate": (round(win_rate, 4) if win_rate is not None else None),
        "total_realized": round(total_realized, 2),
        "avg_winner": (round(avg_winner, 2) if avg_winner is not None else None),
        "avg_loser": (round(avg_loser, 2) if avg_loser is not None else None),
        "expectancy": (round(expectancy, 2) if expectancy is not None else None),
        "profit_factor": (
            round(profit_factor, 4) if profit_factor is not None else None),
        "by_strategy": by_strategy,
        "by_exit_reason": by_exit_reason,
    }


def get_closed_analytics(
    session: Session, portfolio_id: str | None = None,
) -> dict[str, Any]:
    """Read-only analytics over CLOSED (released) options paper trades.

    released_at IS NOT NULL marks the terminal exit; release_reason carries
    the exit reason. No writes.
    """
    where = ["p.released_at IS NOT NULL"]
    params: dict[str, Any] = {}
    if portfolio_id:
        where.append("p.portfolio_id = :pid")
        params["pid"] = portfolio_id
    rows = session.execute(text(
        f"""
        SELECT t.id AS trade_id,
               t.realized_pnl_dollars,
               t.strategy_name AS strategy,
               t.status,
               t.closed_at,
               p.release_reason AS exit_reason
        FROM options_paper_position p
        JOIN options_paper_trade t ON t.id = p.trade_id
        WHERE {' AND '.join(where)}
        """
    ), params).mappings().all()
    return aggregate_closed([dict(r) for r in rows])
