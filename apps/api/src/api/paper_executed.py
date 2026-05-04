"""Phase 11Z — operator-facing executed-trade endpoints.

These read from `paper_trade` + `paper_position` (the account /
recommendation execution path). They are SEPARATE from
`/paper/trades` in `operator.py` which reads `paper_trade_log`
(the selector strategy log).

Why two endpoints exist:
  * The system has two paper-trading engines:
    - **Selector path** (Engine A/B) — writes paper_trade_log
    - **Account path** (recs → auto_trader → submit_trade) —
      writes paper_trade + paper_position
  * Pre-Phase 11Z the WebUI only surfaced the selector path,
    which made executed trades from the account path invisible
    after the 2026-05-02 wipe + replay (replay regenerated
    paper_trade=18 but paper_trade_log stayed at 0).

Endpoints:
  * GET /api/paper/executed/summary
  * GET /api/paper/executed/trades
  * GET /api/paper/executed/positions

All three accept `?include_replay=false|true` (default false).
When false, rows tagged in `replay_recovery_manifest` with
source IN ('replay','test') are excluded.

GET-only. NO writes. NO scheduler. NO POST.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.db import get_session


router = APIRouter()


# ---------------------------------------------------------------------------
# /paper/executed/summary
# ---------------------------------------------------------------------------
@router.get("/paper/executed/summary")
def executed_summary(
    db: Session = Depends(get_session),
    include_replay: bool = Query(False),
) -> dict[str, Any]:
    """Counts of executed trades / open positions across portfolios.

    `include_replay=False` (default) excludes rows tagged as replay
    in `replay_recovery_manifest`. Audit dashboards pass `true`."""
    excl = _exclusion_clause(include_replay, "paper_trade", "pt")
    excl_pos = _exclusion_clause(include_replay, "paper_position", "pp")

    trades_total = db.execute(text(f"""
        SELECT count(*) FROM paper_trade pt WHERE 1=1 {excl}
    """)).scalar() or 0
    trades_buy = db.execute(text(f"""
        SELECT count(*) FROM paper_trade pt
        WHERE side = 'buy' {excl}
    """)).scalar() or 0
    trades_sell = db.execute(text(f"""
        SELECT count(*) FROM paper_trade pt
        WHERE side = 'sell' {excl}
    """)).scalar() or 0
    open_positions = db.execute(text(f"""
        SELECT count(*) FROM paper_position pp
        WHERE is_open = true {excl_pos}
    """)).scalar() or 0
    distinct_symbols = db.execute(text(f"""
        SELECT count(DISTINCT pt.asset_id) FROM paper_trade pt WHERE 1=1 {excl}
    """)).scalar() or 0
    portfolios_with_activity = db.execute(text(f"""
        SELECT count(DISTINCT pt.portfolio_id) FROM paper_trade pt WHERE 1=1 {excl}
    """)).scalar() or 0
    first_fill = db.execute(text(f"""
        SELECT min(pt.fill_ts)::date FROM paper_trade pt WHERE 1=1 {excl}
    """)).scalar()
    last_fill = db.execute(text(f"""
        SELECT max(pt.fill_ts)::date FROM paper_trade pt WHERE 1=1 {excl}
    """)).scalar()
    has_replay_rows = db.execute(text("""
        SELECT count(*) > 0 FROM replay_recovery_manifest
        WHERE entity_type = 'paper_trade' AND source IN ('replay','test')
    """)).scalar() or False

    # Always-on split counts so the UI can show
    # "live + recovered replay" simultaneously regardless of the
    # include_replay toggle. NOT filtered by `excl`.
    live_trades_count = db.execute(text("""
        SELECT count(*) FROM paper_trade pt
        WHERE NOT EXISTS (
          SELECT 1 FROM replay_recovery_manifest m
          WHERE m.entity_type = 'paper_trade'
            AND m.entity_id = pt.id::text
            AND m.source IN ('replay','test')
        )
    """)).scalar() or 0
    replay_trades_count = db.execute(text("""
        SELECT count(*) FROM paper_trade pt
        WHERE EXISTS (
          SELECT 1 FROM replay_recovery_manifest m
          WHERE m.entity_type = 'paper_trade'
            AND m.entity_id = pt.id::text
            AND m.source IN ('replay','test')
        )
    """)).scalar() or 0
    live_open_positions_count = db.execute(text("""
        SELECT count(*) FROM paper_position pp
        WHERE pp.is_open = true
          AND NOT EXISTS (
            SELECT 1 FROM replay_recovery_manifest m
            WHERE m.entity_type = 'paper_position'
              AND m.entity_id = pp.id::text
              AND m.source IN ('replay','test')
          )
    """)).scalar() or 0
    replay_open_positions_count = db.execute(text("""
        SELECT count(*) FROM paper_position pp
        WHERE pp.is_open = true
          AND EXISTS (
            SELECT 1 FROM replay_recovery_manifest m
            WHERE m.entity_type = 'paper_position'
              AND m.entity_id = pp.id::text
              AND m.source IN ('replay','test')
          )
    """)).scalar() or 0

    return {
        "include_replay": include_replay,
        "trades_total": int(trades_total),
        "trades_buy": int(trades_buy),
        "trades_sell": int(trades_sell),
        "open_positions": int(open_positions),
        "distinct_symbols": int(distinct_symbols),
        "portfolios_with_activity": int(portfolios_with_activity),
        "first_fill_date": first_fill.isoformat() if first_fill else None,
        "last_fill_date": last_fill.isoformat() if last_fill else None,
        "has_replay_recovered_rows": bool(has_replay_rows),
        # Always-on split counts (independent of include_replay).
        "live_trades_count": int(live_trades_count),
        "replay_trades_count": int(replay_trades_count),
        "live_open_positions_count": int(live_open_positions_count),
        "replay_open_positions_count": int(replay_open_positions_count),
    }


# ---------------------------------------------------------------------------
# /paper/executed/trades
# ---------------------------------------------------------------------------
@router.get("/paper/executed/trades")
def executed_trades(
    db: Session = Depends(get_session),
    side: Literal["buy", "sell"] | None = None,
    portfolio_id: str | None = None,
    limit: int = Query(500, ge=1, le=2000),
    include_replay: bool = Query(False),
) -> dict[str, Any]:
    """Executed paper_trade rows joined to asset symbol + portfolio
    name + provenance flag."""
    where = ["1=1"]
    params: dict[str, Any] = {"limit": limit}
    if side is not None:
        where.append("pt.side = :side"); params["side"] = side
    if portfolio_id is not None:
        where.append("pt.portfolio_id = :pid"); params["pid"] = portfolio_id
    where_sql = " AND ".join(where)
    excl = _exclusion_clause(include_replay, "paper_trade", "pt")

    rows = db.execute(text(f"""
        SELECT
          pt.id            AS trade_id,
          pt.portfolio_id  AS portfolio_id,
          pp.name          AS portfolio_name,
          a.symbol         AS symbol,
          pt.side          AS side,
          pt.quantity      AS quantity,
          pt.fill_price    AS fill_price,
          pt.fill_ts       AS fill_ts,
          pt.realized_pnl  AS realized_pnl,
          pt.reason        AS reason,
          m.source         AS source,
          m.replay_run_id  AS replay_run_id
        FROM paper_trade pt
        JOIN paper_portfolio pp ON pp.id = pt.portfolio_id
        JOIN asset a            ON a.id = pt.asset_id
        LEFT JOIN replay_recovery_manifest m
          ON m.entity_type = 'paper_trade' AND m.entity_id = pt.id::text
        WHERE {where_sql} {excl}
        ORDER BY pt.fill_ts DESC
        LIMIT :limit
    """), params).fetchall()

    out: list[dict] = []
    for r in rows:
        notional = (
            float(r.quantity) * float(r.fill_price)
            if r.quantity is not None and r.fill_price is not None else None
        )
        out.append({
            "trade_id": r.trade_id,
            "portfolio_id": r.portfolio_id,
            "portfolio_name": r.portfolio_name,
            "symbol": r.symbol,
            "side": r.side,
            "quantity": float(r.quantity) if r.quantity is not None else None,
            "fill_price": (
                float(r.fill_price) if r.fill_price is not None else None
            ),
            "notional_usd": notional,
            "fill_ts": r.fill_ts.isoformat() if r.fill_ts else None,
            "realized_pnl": (
                float(r.realized_pnl) if r.realized_pnl is not None else None
            ),
            "reason": r.reason,
            "source": r.source or "live",
            "replay_run_id": r.replay_run_id,
        })
    return {
        "include_replay": include_replay,
        "count": len(out),
        "trades": out,
    }


# ---------------------------------------------------------------------------
# /paper/executed/positions
# ---------------------------------------------------------------------------
@router.get("/paper/executed/positions")
def executed_positions(
    db: Session = Depends(get_session),
    is_open: bool | None = Query(None),
    portfolio_id: str | None = None,
    include_replay: bool = Query(False),
) -> dict[str, Any]:
    """paper_position rows joined to symbol + portfolio name + provenance."""
    where = ["1=1"]
    params: dict[str, Any] = {}
    if is_open is not None:
        where.append("pp2.is_open = :io"); params["io"] = is_open
    if portfolio_id is not None:
        where.append("pp2.portfolio_id = :pid"); params["pid"] = portfolio_id
    where_sql = " AND ".join(where)
    excl = _exclusion_clause(include_replay, "paper_position", "pp2")

    rows = db.execute(text(f"""
        SELECT
          pp2.id           AS position_id,
          pp2.portfolio_id AS portfolio_id,
          pp.name          AS portfolio_name,
          a.symbol         AS symbol,
          pp2.quantity     AS quantity,
          pp2.avg_cost     AS avg_cost,
          pp2.is_open      AS is_open,
          pp2.opened_at    AS opened_at,
          pp2.closed_at    AS closed_at,
          m.source         AS source,
          m.replay_run_id  AS replay_run_id
        FROM paper_position pp2
        JOIN paper_portfolio pp ON pp.id = pp2.portfolio_id
        JOIN asset a            ON a.id = pp2.asset_id
        LEFT JOIN replay_recovery_manifest m
          ON m.entity_type = 'paper_position' AND m.entity_id = pp2.id::text
        WHERE {where_sql} {excl}
        ORDER BY pp2.opened_at DESC
    """), params).fetchall()

    out: list[dict] = []
    for r in rows:
        out.append({
            "position_id": r.position_id,
            "portfolio_id": r.portfolio_id,
            "portfolio_name": r.portfolio_name,
            "symbol": r.symbol,
            "quantity": float(r.quantity) if r.quantity is not None else None,
            "avg_cost": (
                float(r.avg_cost) if r.avg_cost is not None else None
            ),
            "is_open": bool(r.is_open),
            "opened_at": r.opened_at.isoformat() if r.opened_at else None,
            "closed_at": r.closed_at.isoformat() if r.closed_at else None,
            "source": r.source or "live",
            "replay_run_id": r.replay_run_id,
        })
    return {
        "include_replay": include_replay,
        "count": len(out),
        "positions": out,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_ALLOWED_TYPES = {"paper_trade", "paper_position"}


def _exclusion_clause(include_replay: bool, entity_type: str, alias: str) -> str:
    """SQL fragment that NOT-EXISTS-excludes replay rows when
    include_replay=False. Returns empty string when caller opts in.

    `entity_type` and `alias` are validated to literals — never accept
    user input here."""
    if include_replay:
        return ""
    if entity_type not in _ALLOWED_TYPES:
        raise ValueError(f"unknown entity_type: {entity_type!r}")
    if not (alias and all(c.isalnum() or c == "_" for c in alias)):
        raise ValueError(f"bad alias: {alias!r}")
    return (
        f" AND NOT EXISTS (SELECT 1 FROM replay_recovery_manifest m "
        f"WHERE m.entity_type = '{entity_type}' "
        f"AND m.entity_id = {alias}.id::text "
        f"AND m.source IN ('replay','test'))"
    )
