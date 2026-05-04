"""Personal-Analytics Phase — read-only paper-trading performance.

Surfaces the metrics a personal operator wants out of the
account-path paper-trading data: live-vs-replay split counts,
realized P&L, unrealized P&L when last-price data exists,
exposure-by-symbol, win rate (only when there are closed trades),
and best/worst realized trade.

Distinct from the existing `/performance/*` router which serves the
selector-strategy reports. These endpoints read from
`paper_trade` + `paper_position` and respect
`replay_recovery_manifest` provenance.

Hard rules:
  * GET-only. NO POST/PUT/PATCH/DELETE handlers may be added here.
  * No writes to any table.
  * Never call replay rows "live trades".
  * If there are zero closed trades, return `win_rate=null` and
    `note="no_closed_outcomes_yet"`. Never fabricate a denominator.
  * Default exclusion of replay rows mirrors `/paper/executed/*`:
    `?include_replay=false` (default) hides them; the response always
    surfaces split counts + `has_replay_recovered_rows` so the UI can
    show recovered availability without flipping the toggle.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.db import get_session


router = APIRouter(prefix="/performance/paper", tags=["performance"])


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
_REPLAY_NOT_EXISTS = """
NOT EXISTS (
  SELECT 1 FROM replay_recovery_manifest m
  WHERE m.entity_type = :etype
    AND m.entity_id = :eid
    AND m.source IN ('replay','test')
)
""".strip()


def _excl(include_replay: bool, etype: str, alias: str) -> str:
    """Inline NOT-EXISTS exclusion clause; bound parameters injected
    separately. `etype` is restricted to a literal allow-list and the
    alias must be alnum so we never interpolate untrusted values."""
    if include_replay:
        return ""
    if etype not in ("paper_trade", "paper_position"):
        raise ValueError(f"unknown entity type: {etype!r}")
    if not all(c.isalnum() or c == "_" for c in alias):
        raise ValueError(f"bad alias: {alias!r}")
    return (
        f" AND NOT EXISTS (SELECT 1 FROM replay_recovery_manifest m "
        f"WHERE m.entity_type = '{etype}' "
        f"AND m.entity_id = {alias}.id::text "
        f"AND m.source IN ('replay','test'))"
    )


def _f(v: Any) -> float | None:
    """Decimal → float; None passthrough."""
    if v is None:
        return None
    return float(v) if isinstance(v, Decimal) else float(v)


# ---------------------------------------------------------------------------
# /performance/paper/summary
# ---------------------------------------------------------------------------
@router.get("/summary")
def paper_summary(
    db: Session = Depends(get_session),
    include_replay: bool = Query(False),
) -> dict[str, Any]:
    """High-level rollup. Always returns split counts; trade-bound
    aggregates honor `include_replay` for the headline numbers."""
    excl = _excl(include_replay, "paper_trade", "pt")
    excl_pos = _excl(include_replay, "paper_position", "pp")

    # Headline counts.
    total_trades = db.execute(text(
        f"SELECT count(*) FROM paper_trade pt WHERE 1=1 {excl}"
    )).scalar() or 0
    closed_trades = db.execute(text(
        f"SELECT count(*) FROM paper_trade pt "
        f"WHERE pt.realized_pnl IS NOT NULL {excl}"
    )).scalar() or 0
    open_trades = int(total_trades) - int(closed_trades)
    open_positions = db.execute(text(
        f"SELECT count(*) FROM paper_position pp "
        f"WHERE pp.is_open = true {excl_pos}"
    )).scalar() or 0
    realized_pnl_sum = db.execute(text(
        f"SELECT coalesce(sum(pt.realized_pnl), 0) FROM paper_trade pt "
        f"WHERE pt.realized_pnl IS NOT NULL {excl}"
    )).scalar() or 0
    win_count = db.execute(text(
        f"SELECT count(*) FROM paper_trade pt "
        f"WHERE pt.realized_pnl IS NOT NULL "
        f"  AND pt.realized_pnl > 0 {excl}"
    )).scalar() or 0
    loss_count = db.execute(text(
        f"SELECT count(*) FROM paper_trade pt "
        f"WHERE pt.realized_pnl IS NOT NULL "
        f"  AND pt.realized_pnl < 0 {excl}"
    )).scalar() or 0
    breakeven_count = int(closed_trades) - int(win_count) - int(loss_count)
    avg_realized = db.execute(text(
        f"SELECT avg(pt.realized_pnl) FROM paper_trade pt "
        f"WHERE pt.realized_pnl IS NOT NULL {excl}"
    )).scalar()
    best = db.execute(text(
        f"SELECT max(pt.realized_pnl) FROM paper_trade pt "
        f"WHERE pt.realized_pnl IS NOT NULL {excl}"
    )).scalar()
    worst = db.execute(text(
        f"SELECT min(pt.realized_pnl) FROM paper_trade pt "
        f"WHERE pt.realized_pnl IS NOT NULL {excl}"
    )).scalar()

    # Always-on split counts (independent of include_replay).
    live_trades = db.execute(text("""
        SELECT count(*) FROM paper_trade pt
        WHERE NOT EXISTS (
          SELECT 1 FROM replay_recovery_manifest m
          WHERE m.entity_type = 'paper_trade'
            AND m.entity_id = pt.id::text
            AND m.source IN ('replay','test')
        )
    """)).scalar() or 0
    replay_trades = db.execute(text("""
        SELECT count(*) FROM paper_trade pt
        WHERE EXISTS (
          SELECT 1 FROM replay_recovery_manifest m
          WHERE m.entity_type = 'paper_trade'
            AND m.entity_id = pt.id::text
            AND m.source IN ('replay','test')
        )
    """)).scalar() or 0
    has_replay = bool(replay_trades and replay_trades > 0)

    # Source breakdown ('live' is the absence of a manifest row).
    src_rows = db.execute(text("""
        SELECT
          coalesce(m.source, 'live') AS source,
          count(*)                   AS n
        FROM paper_trade pt
        LEFT JOIN replay_recovery_manifest m
          ON m.entity_type = 'paper_trade' AND m.entity_id = pt.id::text
        GROUP BY 1
        ORDER BY 2 DESC
    """)).mappings().all()
    source_breakdown = {r["source"]: int(r["n"]) for r in src_rows}

    # Win rate ONLY if there are closed trades; never fabricate a 0/0.
    win_rate: float | None
    note: str | None
    decided = int(win_count) + int(loss_count)
    if decided == 0:
        win_rate = None
        note = "no_closed_outcomes_yet"
    else:
        win_rate = float(win_count) / decided
        note = None

    # Outcome breakdown — uses paper_position to determine open vs closed.
    outcome_rows = db.execute(text(
        f"SELECT pt.realized_pnl IS NOT NULL AS closed, count(*) AS n "
        f"FROM paper_trade pt WHERE 1=1 {excl} GROUP BY 1"
    )).mappings().all()
    outcomes = {
        "closed": sum(int(r["n"]) for r in outcome_rows if r["closed"]),
        "open_pending": sum(int(r["n"]) for r in outcome_rows if not r["closed"]),
    }

    return {
        "include_replay": include_replay,
        "total_trades": int(total_trades),
        "open_trades": int(open_trades),
        "closed_trades": int(closed_trades),
        "open_positions": int(open_positions),
        "win_count": int(win_count),
        "loss_count": int(loss_count),
        "breakeven_count": int(breakeven_count),
        "win_rate": win_rate,
        "note": note,
        "realized_pnl_total": _f(realized_pnl_sum),
        "avg_realized_pnl": _f(avg_realized),
        "best_realized_pnl": _f(best),
        "worst_realized_pnl": _f(worst),
        "has_replay_recovered_rows": has_replay,
        "live_trades_count": int(live_trades),
        "replay_trades_count": int(replay_trades),
        "source_breakdown": source_breakdown,
        "outcomes": outcomes,
    }


# ---------------------------------------------------------------------------
# /performance/paper/trades
# ---------------------------------------------------------------------------
@router.get("/trades")
def paper_trades(
    db: Session = Depends(get_session),
    limit: int = Query(500, ge=1, le=2000),
    include_replay: bool = Query(False),
    closed_only: bool = Query(False),
) -> dict[str, Any]:
    """Trade-level rows with provenance + outcome status."""
    excl = _excl(include_replay, "paper_trade", "pt")
    closed_clause = (
        " AND pt.realized_pnl IS NOT NULL " if closed_only else ""
    )
    rows = db.execute(text(f"""
        SELECT
          pt.id            AS trade_id,
          a.symbol         AS symbol,
          pt.side          AS side,
          pt.quantity      AS quantity,
          pt.fill_price    AS fill_price,
          pt.fill_ts       AS fill_ts,
          pt.realized_pnl  AS realized_pnl,
          pt.reason        AS reason,
          coalesce(m.source, 'live') AS source,
          m.replay_run_id  AS replay_run_id,
          (pt.realized_pnl IS NOT NULL) AS is_closed
        FROM paper_trade pt
        JOIN asset a ON a.id = pt.asset_id
        LEFT JOIN replay_recovery_manifest m
          ON m.entity_type = 'paper_trade' AND m.entity_id = pt.id::text
        WHERE 1=1 {excl} {closed_clause}
        ORDER BY pt.fill_ts DESC
        LIMIT :limit
    """), {"limit": limit}).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append({
            "trade_id": r.trade_id,
            "symbol": r.symbol,
            "side": r.side,
            "quantity": _f(r.quantity),
            "fill_price": _f(r.fill_price),
            "fill_ts": r.fill_ts.isoformat() if r.fill_ts else None,
            "realized_pnl": _f(r.realized_pnl),
            "reason": r.reason,
            "source": r.source or "live",
            "replay_run_id": r.replay_run_id,
            "outcome_status": "closed" if r.is_closed else "open_pending",
        })
    return {
        "include_replay": include_replay,
        "count": len(out),
        "trades": out,
    }


# ---------------------------------------------------------------------------
# /performance/paper/equity
# ---------------------------------------------------------------------------
@router.get("/equity")
def paper_equity(
    db: Session = Depends(get_session),
    include_replay: bool = Query(False),
) -> dict[str, Any]:
    """Open-position exposure by symbol + sector aggregate (when
    sector data is available). Computes `unrealized_pnl_usd` only
    when a recent price_bar exists for the asset; otherwise returns
    `unrealized_status='unavailable'` for that row."""
    excl_pos = _excl(include_replay, "paper_position", "pp")

    rows = db.execute(text(f"""
        WITH last_px AS (
            SELECT DISTINCT ON (asset_id) asset_id, close, ts
            FROM price_bar
            ORDER BY asset_id, ts DESC
        )
        SELECT
          a.symbol           AS symbol,
          a.sector           AS sector,
          pp.quantity        AS quantity,
          pp.avg_cost        AS avg_cost,
          last_px.close      AS last_price,
          last_px.ts         AS last_price_ts,
          coalesce(m.source, 'live') AS source
        FROM paper_position pp
        JOIN asset a ON a.id = pp.asset_id
        LEFT JOIN last_px ON last_px.asset_id = pp.asset_id
        LEFT JOIN replay_recovery_manifest m
          ON m.entity_type = 'paper_position' AND m.entity_id = pp.id::text
        WHERE pp.is_open = true {excl_pos}
        ORDER BY pp.opened_at DESC
    """)).mappings().all()

    by_symbol: dict[str, dict[str, Any]] = {}
    by_sector: dict[str, dict[str, Any]] = {}
    total_market_value = 0.0
    total_cost_basis = 0.0
    total_unrealized = 0.0
    unrealized_unavailable_count = 0

    for r in rows:
        sym = r["symbol"]
        sector = r["sector"] or "unknown"
        qty = float(r["quantity"]) if r["quantity"] is not None else 0.0
        avg_cost = float(r["avg_cost"]) if r["avg_cost"] is not None else 0.0
        last = (
            float(r["last_price"]) if r["last_price"] is not None else None
        )
        cost_basis = qty * avg_cost
        if last is not None and qty != 0:
            mv = qty * last
            unrealized = mv - cost_basis
            total_market_value += mv
            total_cost_basis += cost_basis
            total_unrealized += unrealized
            unrealized_status = "ok"
        else:
            mv = None
            unrealized = None
            unrealized_unavailable_count += 1
            unrealized_status = "unavailable"

        sym_entry = by_symbol.setdefault(sym, {
            "symbol": sym,
            "sector": sector,
            "quantity": 0.0,
            "cost_basis_usd": 0.0,
            "market_value_usd": 0.0,
            "unrealized_pnl_usd": 0.0,
            "unrealized_status": "ok",
            "source": r["source"] or "live",
        })
        sym_entry["quantity"] += qty
        sym_entry["cost_basis_usd"] += cost_basis
        if mv is not None:
            sym_entry["market_value_usd"] += mv
            sym_entry["unrealized_pnl_usd"] += unrealized
        else:
            sym_entry["unrealized_status"] = "unavailable"

        sec_entry = by_sector.setdefault(sector, {
            "sector": sector,
            "cost_basis_usd": 0.0,
            "market_value_usd": 0.0,
            "unrealized_pnl_usd": 0.0,
            "n_positions": 0,
        })
        sec_entry["cost_basis_usd"] += cost_basis
        if mv is not None:
            sec_entry["market_value_usd"] += mv
            sec_entry["unrealized_pnl_usd"] += unrealized
        sec_entry["n_positions"] += 1

    return {
        "include_replay": include_replay,
        "n_open_positions": len(rows),
        "total_cost_basis_usd": total_cost_basis,
        "total_market_value_usd": total_market_value,
        "total_unrealized_pnl_usd": total_unrealized,
        "unrealized_unavailable_count": unrealized_unavailable_count,
        "by_symbol": list(by_symbol.values()),
        "by_sector": list(by_sector.values()),
    }


# ---------------------------------------------------------------------------
# /performance/paper/attribution
# ---------------------------------------------------------------------------
@router.get("/attribution")
def paper_attribution(
    db: Session = Depends(get_session),
    include_replay: bool = Query(False),
) -> dict[str, Any]:
    """Realized-P&L attribution by symbol + by source (live vs replay).

    Honest about pending: `outcome_status` per row is one of
    {closed, open_pending}. Pending rows are aggregated separately
    so the operator never sees a derived metric mixing realized and
    unrealized values."""
    excl = _excl(include_replay, "paper_trade", "pt")

    sym_rows = db.execute(text(f"""
        SELECT
          a.symbol AS symbol,
          count(*) FILTER (WHERE pt.realized_pnl IS NOT NULL) AS closed,
          count(*) FILTER (WHERE pt.realized_pnl IS NULL)     AS open_pending,
          coalesce(sum(pt.realized_pnl), 0)                   AS realized_pnl,
          count(*)                                            AS total
        FROM paper_trade pt
        JOIN asset a ON a.id = pt.asset_id
        WHERE 1=1 {excl}
        GROUP BY 1
        ORDER BY 4 DESC
    """)).mappings().all()
    by_symbol = [
        {
            "symbol": r["symbol"],
            "total_trades": int(r["total"]),
            "closed_trades": int(r["closed"]),
            "open_pending_trades": int(r["open_pending"]),
            "realized_pnl_usd": _f(r["realized_pnl"]),
        }
        for r in sym_rows
    ]

    src_rows = db.execute(text("""
        SELECT
          coalesce(m.source, 'live') AS source,
          count(*) FILTER (WHERE pt.realized_pnl IS NOT NULL) AS closed,
          count(*) FILTER (WHERE pt.realized_pnl IS NULL)     AS open_pending,
          coalesce(sum(pt.realized_pnl), 0)                   AS realized_pnl,
          count(*)                                            AS total
        FROM paper_trade pt
        LEFT JOIN replay_recovery_manifest m
          ON m.entity_type = 'paper_trade' AND m.entity_id = pt.id::text
        GROUP BY 1
        ORDER BY 5 DESC
    """)).mappings().all()
    by_source = [
        {
            "source": r["source"],
            "total_trades": int(r["total"]),
            "closed_trades": int(r["closed"]),
            "open_pending_trades": int(r["open_pending"]),
            "realized_pnl_usd": _f(r["realized_pnl"]),
        }
        for r in src_rows
    ]

    return {
        "include_replay": include_replay,
        "as_of": dt.datetime.now(dt.timezone.utc).isoformat(),
        "by_symbol": by_symbol,
        "by_source": by_source,
    }
