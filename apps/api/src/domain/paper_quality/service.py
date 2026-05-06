"""DB-aware orchestration for trade-quality scoring.

Reads paper_trade + paper_position + price_bar (latest 1d bar)
to assemble `ScoreInputs` per row, then calls
`scoring.score_trade`. Read-only.

Eligibility rules (mirror /paper/trades dedup):
  * BUY rows whose `paper_position.is_open` is TRUE → "open" item.
  * SELL rows (always represent a closure event) → "closed" item.
  * Closed BUY rows are intentionally skipped — they are
    already represented by their companion SELL row.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from .scoring import (
    DEFAULT_MAX_HOLD_DAYS, ScoreInputs, score_trade, to_float,
)


def _trading_days(a: dt.date, b: dt.date) -> int:
    """Inclusive Mon-Fri count, mirrors run_paper_exit_cycle."""
    if b < a:
        return 0
    n = 0
    cur = a
    while cur <= b:
        if cur.weekday() < 5:
            n += 1
        cur = cur + dt.timedelta(days=1)
    return n


def _fetch_trade_rows(
    session: Session, *, include_replay: bool, limit: int,
) -> list[dict[str, Any]]:
    """Eligible paper_trade rows joined to symbol + position state +
    fill-day bar + latest bar. SELL rows are always emitted; BUY
    rows only when their position is currently open."""
    excl = ""
    if not include_replay:
        # Soft NOT-EXISTS — same shape used by other read-only paper
        # endpoints. Falls back gracefully when the manifest table
        # is missing (testcontainer)."""
        excl = (
            " AND NOT EXISTS ("
            "  SELECT 1 FROM replay_recovery_manifest m"
            "  WHERE m.entity_type = 'paper_trade'"
            "    AND m.entity_id = t.id::text"
            "    AND m.source IN ('replay','test')"
            ")"
        )
    sql = f"""
        SELECT
          t.id, t.side, t.fill_ts, t.fill_price, t.quantity,
          t.realized_pnl, t.reason, t.portfolio_id,
          a.symbol AS instrument, a.id AS asset_id,
          p.name AS portfolio_name,
          coalesce(pp.is_open, FALSE) AS is_open,
          pp.opened_at AS pos_opened_at,
          pp.closed_at AS pos_closed_at,
          pp.avg_cost AS pos_avg_cost,
          pp.quantity AS pos_quantity,
          fb.open  AS fill_bar_open,
          fb.high  AS fill_bar_high,
          fb.low   AS fill_bar_low,
          fb.close AS fill_bar_close,
          lb.close AS latest_close,
          lb.ts::date AS latest_close_date
        FROM paper_trade t
        JOIN asset a ON a.id = t.asset_id
        JOIN paper_portfolio p ON p.id = t.portfolio_id
        LEFT JOIN paper_position pp
               ON pp.portfolio_id = t.portfolio_id
              AND pp.asset_id = t.asset_id
        LEFT JOIN LATERAL (
          SELECT open, high, low, close
          FROM price_bar
          WHERE asset_id = a.id AND timeframe = '1d'
            AND ts::date = t.fill_ts::date
          ORDER BY ts DESC LIMIT 1
        ) fb ON TRUE
        LEFT JOIN LATERAL (
          SELECT close, ts
          FROM price_bar
          WHERE asset_id = a.id AND timeframe = '1d'
          ORDER BY ts DESC LIMIT 1
        ) lb ON TRUE
        WHERE
              t.side = 'sell'
           OR (t.side = 'buy' AND coalesce(pp.is_open, FALSE) = TRUE)
          {excl}
        ORDER BY t.fill_ts DESC
        LIMIT :n
    """
    rows = session.execute(text(sql), {"n": limit}).mappings().all()
    return [dict(r) for r in rows]


def _row_to_inputs(
    row: dict[str, Any], *, as_of: dt.date,
    max_hold_days: int,
) -> ScoreInputs:
    side = row["side"]
    is_closed = (side == "sell")
    fill_ts: dt.datetime = row["fill_ts"]
    held_days: int | None
    if is_closed and row["pos_opened_at"]:
        # closed: hold span from position open → sell fill day
        held_days = _trading_days(
            row["pos_opened_at"].date(), fill_ts.date(),
        )
    elif not is_closed and row["pos_opened_at"]:
        held_days = _trading_days(row["pos_opened_at"].date(), as_of)
    else:
        held_days = None
    # Latest close mark only matters for open trades. For closed,
    # realized_pnl on the SELL row is the truth.
    current = (
        to_float(row["latest_close"]) if not is_closed else None
    )
    return ScoreInputs(
        side=side,
        is_closed=is_closed,
        entry_price=float(row["fill_price"]),
        qty=float(row["quantity"]),
        held_days=held_days,
        max_hold_days=max_hold_days,
        bar_open=to_float(row["fill_bar_open"]),
        bar_high=to_float(row["fill_bar_high"]),
        bar_low=to_float(row["fill_bar_low"]),
        bar_close=to_float(row["fill_bar_close"]),
        current_price=current,
        realized_pnl=(
            to_float(row["realized_pnl"]) if is_closed else None
        ),
        exit_reason=row["reason"] if is_closed else None,
        # No pending-fill queue table in this codebase — submit_trade
        # is synchronous via find_next_open. The pending state only
        # appears in the artifact dimension (exit cycle / options).
        pending_next_bar=False,
    )


def assemble_quality_report(
    session: Session, *,
    include_replay: bool = False,
    max_hold_days: int = DEFAULT_MAX_HOLD_DAYS,
    limit: int = 200,
    as_of: dt.date | None = None,
) -> dict[str, Any]:
    """Top-level entry. Returns scored items + an aggregate
    breakdown the frontend can render."""
    if as_of is None:
        as_of = dt.datetime.now(dt.timezone.utc).date()
    rows = _fetch_trade_rows(
        session, include_replay=include_replay, limit=limit,
    )
    items: list[dict[str, Any]] = []
    grade_counts: dict[str, int] = {}
    thesis_counts: dict[str, int] = {}
    completeness_counts: dict[str, int] = {}
    score_sum = 0
    for r in rows:
        inp = _row_to_inputs(
            r, as_of=as_of, max_hold_days=max_hold_days,
        )
        result = score_trade(inp)
        items.append({
            "trade_id": str(r["id"]),
            "symbol": r["instrument"],
            "portfolio_id": str(r["portfolio_id"]),
            "portfolio_name": r["portfolio_name"],
            "side": r["side"],
            "is_open": (r["side"] == "buy"),
            "fill_ts": (
                r["fill_ts"].isoformat() if r["fill_ts"] else None
            ),
            "entry_price": float(r["fill_price"]),
            "qty": float(r["quantity"]),
            "held_days": inp.held_days,
            "current_price": inp.current_price,
            "realized_pnl": inp.realized_pnl,
            "exit_reason": inp.exit_reason,
            "score": result.score,
            "grade": result.grade,
            "thesis": result.thesis,
            "completeness": result.completeness,
            "components": result.components,
            "reasons": result.reasons,
        })
        grade_counts[result.grade] = (
            grade_counts.get(result.grade, 0) + 1
        )
        thesis_counts[result.thesis] = (
            thesis_counts.get(result.thesis, 0) + 1
        )
        completeness_counts[result.completeness] = (
            completeness_counts.get(result.completeness, 0) + 1
        )
        score_sum += result.score
    n = len(items)
    return {
        "notice": "pre-ML diagnostic — read-only; not a trading signal",
        "as_of_date": as_of.isoformat(),
        "include_replay": include_replay,
        "n_items": n,
        "n_open": sum(1 for i in items if i["is_open"]),
        "n_closed": sum(1 for i in items if not i["is_open"]),
        "average_score": (score_sum / n) if n else None,
        "grade_distribution": grade_counts,
        "thesis_distribution": thesis_counts,
        "completeness_distribution": completeness_counts,
        "items": items,
    }
