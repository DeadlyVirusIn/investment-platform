"""Paper-performance aggregator (Phase 11G).

Pure read over options_paper_trade + lifecycle/expiration/assignment
events. Produces win-rate, max-loss-hit-rate, assignment-rate,
pin-risk-frequency, fee-drag, expiry outcome distribution, broken
out by strategy / underlying / expiry-bucket.

NEVER writes. NEVER recommends. NEVER ranks strategies as "best".
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.options.paper.expiration import (
    FLAG_ASSIGNMENT_SIMPLIFIED_EXIT,
    FLAG_MISSING_SETTLEMENT,
    FLAG_PIN_RISK_UNCERTAIN_OUTCOME,
)


# Tolerance for "max loss hit" classification — within $5 of stated
# max loss is treated as the max-loss outcome.
MAX_LOSS_HIT_TOLERANCE_DOLLARS = Decimal("5.00")


def _safe_div(num, den) -> str | None:
    if den == 0:
        return None
    return str(Decimal(num) / Decimal(den))


def get_performance_summary(
    session: Session,
    *,
    underlying: str | None = None,
    strategy_name: str | None = None,
) -> dict[str, Any]:
    """Aggregate paper-performance metrics for closed trades.

    Open trades are excluded — only realized outcomes are counted.

    Returns dict shaped for the WebUI; every numeric is `str` so the
    frontend can decide on display precision (and so we never serve
    a JSON `0` where the truthful answer is "no data".)
    """
    where = ["status IN ('CLOSED', 'EXPIRED', 'ASSIGNED')"]
    params: dict[str, Any] = {}
    if underlying is not None:
        where.append("underlying = :underlying")
        params["underlying"] = underlying
    if strategy_name is not None:
        where.append("strategy_name = :strategy_name")
        params["strategy_name"] = strategy_name
    where_sql = " AND ".join(where)

    rows = session.execute(text(
        f"""
        SELECT id, status, underlying, strategy_name,
               realized_pnl_dollars, max_loss_dollars, fees_total_dollars
        FROM options_paper_trade
        WHERE {where_sql}
        """
    ), params).all()

    n = len(rows)
    n_wins = sum(
        1 for r in rows
        if r.realized_pnl_dollars is not None
        and Decimal(str(r.realized_pnl_dollars)) > 0
    )
    n_losses = sum(
        1 for r in rows
        if r.realized_pnl_dollars is not None
        and Decimal(str(r.realized_pnl_dollars)) < 0
    )
    n_max_loss_hits = sum(
        1 for r in rows
        if r.realized_pnl_dollars is not None
        and r.max_loss_dollars is not None
        and Decimal(str(r.realized_pnl_dollars))
            <= -(Decimal(str(r.max_loss_dollars)) - MAX_LOSS_HIT_TOLERANCE_DOLLARS)
    )
    n_assigned = sum(1 for r in rows if r.status == "ASSIGNED")
    n_expired  = sum(1 for r in rows if r.status == "EXPIRED")
    n_closed   = sum(1 for r in rows if r.status == "CLOSED")

    total_pnl = sum(
        (Decimal(str(r.realized_pnl_dollars or 0)) for r in rows),
        start=Decimal("0"),
    )
    total_fees = sum(
        (Decimal(str(r.fees_total_dollars or 0)) for r in rows),
        start=Decimal("0"),
    )
    abs_pnl = sum(
        (abs(Decimal(str(r.realized_pnl_dollars or 0))) for r in rows),
        start=Decimal("0"),
    )

    pin_count = session.execute(text(
        "SELECT COUNT(*) FROM options_expiration_event "
        "WHERE classification = 'PIN_RISK'"
    )).scalar_one()
    expiry_event_count = session.execute(text(
        "SELECT COUNT(*) FROM options_expiration_event"
    )).scalar_one()

    by_strategy = session.execute(text(
        f"""
        SELECT strategy_name,
               COUNT(*) AS n,
               COUNT(*) FILTER (WHERE status='ASSIGNED') AS n_assigned,
               COUNT(*) FILTER (WHERE realized_pnl_dollars > 0) AS n_wins,
               SUM(realized_pnl_dollars) AS total_pnl,
               SUM(fees_total_dollars) AS total_fees
        FROM options_paper_trade
        WHERE {where_sql}
        GROUP BY strategy_name
        ORDER BY strategy_name
        """
    ), params).all()

    by_underlying = session.execute(text(
        f"""
        SELECT underlying,
               COUNT(*) AS n,
               COUNT(*) FILTER (WHERE realized_pnl_dollars > 0) AS n_wins,
               SUM(realized_pnl_dollars) AS total_pnl
        FROM options_paper_trade
        WHERE {where_sql}
        GROUP BY underlying
        ORDER BY underlying
        """
    ), params).all()

    flags: list[str] = []
    if n_assigned > 0:
        flags.append(FLAG_ASSIGNMENT_SIMPLIFIED_EXIT)
    if pin_count > 0:
        flags.append(FLAG_PIN_RISK_UNCERTAIN_OUTCOME)
    missing_count = session.execute(text(
        "SELECT COUNT(*) FROM options_expiration_event "
        "WHERE classification = 'MISSING_DATA'"
    )).scalar_one()
    if missing_count > 0:
        flags.append(FLAG_MISSING_SETTLEMENT)

    return {
        "n_closed_trades": n,
        "n_wins": n_wins,
        "n_losses": n_losses,
        "n_max_loss_hits": n_max_loss_hits,
        "n_assigned": n_assigned,
        "n_expired_otm": n_expired,
        "n_closed_pre_expiry": n_closed,
        "win_rate": _safe_div(n_wins, n),
        "max_loss_hit_rate": _safe_div(n_max_loss_hits, n),
        "assignment_rate": _safe_div(n_assigned, n),
        "pin_risk_frequency_per_expiration_event":
            _safe_div(pin_count, expiry_event_count),
        "missing_settlement_per_expiration_event":
            _safe_div(missing_count, expiry_event_count),
        "total_realized_pnl_dollars": str(total_pnl),
        "total_fees_dollars": str(total_fees),
        "fee_drag_ratio_of_abs_pnl":
            _safe_div(total_fees, abs_pnl) if abs_pnl > 0 else None,
        "by_strategy": [
            {
                "strategy_name": r.strategy_name,
                "n": int(r.n),
                "n_assigned": int(r.n_assigned),
                "n_wins": int(r.n_wins),
                "win_rate": _safe_div(int(r.n_wins), int(r.n)),
                "total_pnl_dollars": str(r.total_pnl) if r.total_pnl is not None else None,
                "total_fees_dollars": str(r.total_fees) if r.total_fees is not None else None,
            }
            for r in by_strategy
        ],
        "by_underlying": [
            {
                "underlying": r.underlying,
                "n": int(r.n),
                "n_wins": int(r.n_wins),
                "win_rate": _safe_div(int(r.n_wins), int(r.n)),
                "total_pnl_dollars": str(r.total_pnl) if r.total_pnl is not None else None,
            }
            for r in by_underlying
        ],
        "data_quality_flags": flags,
        "observation_only_notice":
            "Observation only — not investment advice or execution guidance",
    }
