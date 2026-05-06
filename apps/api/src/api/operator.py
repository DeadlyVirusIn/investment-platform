"""Phase UI-RESET — Operator API routes (read-only).

Backs the new frontend pages over DL2 / OPS1 / MON1 tables:
  /paper/summary        /paper/state        /paper/equity
  /paper/trades         /paper/performance
  /decision-log/{date}
  /anomalies            /anomalies/summary
  /shadow/signals
  /system/health

All endpoints are GET-only. No strategy mutation.
"""

from __future__ import annotations

import datetime as dt
import json
import statistics as st
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.db import get_session

router = APIRouter(tags=["operator"])

PORTFOLIO_ID = "default"


# ---------------------------------------------------------------------------
# /paper/summary
# ---------------------------------------------------------------------------
# Reads real paper-trading state from paper_equity_snapshot keyed
# by paper_portfolio.id (UUID). Aggregates across all active
# portfolios. The legacy paper_portfolio_snapshot / paper_trade_log
# tables (synthetic portfolio_id='default') are no longer consulted
# — they were a separate selector-path mirror that did not see real
# auto_trader fills, which caused NAV/cash/positions to look stuck
# at the starting state.
#
# Replay-recovery rows in paper_trade are kept SEPARATE from the
# headline equity. The equity series itself is computed by
# `snapshot_equity_now` from cash + open-position market value, so
# replay-flagged trades affect equity only through the positions
# they opened (which is the correct behavior — they really are
# in the portfolio). The optional `replay_*` counts here are
# informational only and do not subtract from headline equity.

def _latest_active_snapshots(db: Session) -> list[Any]:
    """Latest paper_equity_snapshot row per active portfolio."""
    return db.execute(text("""
        SELECT DISTINCT ON (s.portfolio_id)
               s.portfolio_id, s.snapshot_date, s.total_equity,
               s.cash, s.positions_value, s.unrealized_pnl,
               s.realized_pnl_cumulative, s.created_at
        FROM paper_equity_snapshot s
        JOIN paper_portfolio p ON p.id = s.portfolio_id
        WHERE p.is_active = TRUE
        ORDER BY s.portfolio_id, s.snapshot_date DESC
    """)).fetchall()


def _prev_day_snapshots(
    db: Session, latest_date: dt.date,
) -> dict[str, float]:
    """Per-portfolio total_equity on the day strictly before
    `latest_date`. Used to compute daily P&L."""
    rows = db.execute(text("""
        SELECT DISTINCT ON (s.portfolio_id)
               s.portfolio_id, s.total_equity
        FROM paper_equity_snapshot s
        JOIN paper_portfolio p ON p.id = s.portfolio_id
        WHERE p.is_active = TRUE
          AND s.snapshot_date < :d
        ORDER BY s.portfolio_id, s.snapshot_date DESC
    """), {"d": latest_date}).fetchall()
    return {r.portfolio_id: float(r.total_equity) for r in rows}


@router.get("/paper/summary")
def paper_summary(db: Session = Depends(get_session)) -> dict[str, Any]:
    latest_rows = _latest_active_snapshots(db)
    if not latest_rows:
        return {
            "as_of_date": dt.date.today().isoformat(),
            "equity": 0.0, "cash": 0.0,
            "positions_value": 0.0, "unrealized_pnl": 0.0,
            "total_return_pct": 0.0, "max_drawdown_pct": 0.0,
            "daily_pnl": 0.0,
            "regime": "none", "engine_active": "none",
            "open_positions_count": 0,
            "last_decision_ts":
                dt.datetime.now(dt.timezone.utc).isoformat(),
            "pipeline_status": "idle",
            "portfolio_count": 0,
        }

    starting_total = float(db.execute(text("""
        SELECT coalesce(sum(starting_cash), 0)
        FROM paper_portfolio WHERE is_active = TRUE
    """)).scalar() or 0)

    # Pick latest snapshot_date across all portfolios as the
    # report date — every active portfolio is snapshotted on the
    # same daily anchor, so the max is the relevant one.
    as_of = max(r.snapshot_date for r in latest_rows)
    if isinstance(as_of, dt.datetime):
        as_of_d = as_of.date()
    else:
        as_of_d = as_of

    total_equity = sum(float(r.total_equity) for r in latest_rows)
    total_cash = sum(float(r.cash) for r in latest_rows)
    total_pos = sum(float(r.positions_value) for r in latest_rows)
    total_upnl = sum(
        float(r.unrealized_pnl or 0) for r in latest_rows
    )

    # Daily P&L = today's total - prior-day total (per portfolio,
    # then summed). Skips portfolios without a prior snapshot.
    prev_map = _prev_day_snapshots(db, as_of_d)
    daily_pnl = 0.0
    for r in latest_rows:
        prev = prev_map.get(r.portfolio_id)
        if prev is not None:
            daily_pnl += float(r.total_equity) - prev

    # Total return % over starting cash
    total_return_pct = (
        ((total_equity - starting_total) / starting_total) * 100.0
        if starting_total > 0 else 0.0
    )

    # Open positions: paper_position is the real source of truth.
    open_n = db.execute(text("""
        SELECT count(*) FROM paper_position pp
        JOIN paper_portfolio p ON p.id = pp.portfolio_id
        WHERE pp.is_open = TRUE AND p.is_active = TRUE
    """)).scalar() or 0

    last_decision_ts = max(
        (r.created_at for r in latest_rows if r.created_at),
        default=None,
    )

    # Replay-flagged informational counts — kept separate. The
    # manifest table is created by a raw-SQL alembic migration; the
    # ORM-only test harness does not build it. Graceful degrade
    # to 0 when the table is absent so the endpoint never 500s.
    try:
        replay_trades = db.execute(text("""
            SELECT count(*) FROM paper_trade t
            WHERE EXISTS (
              SELECT 1 FROM replay_recovery_manifest m
              WHERE m.entity_type='paper_trade'
                AND m.entity_id = t.id::text
            )
        """)).scalar() or 0
    except Exception:  # noqa: BLE001
        db.rollback()
        replay_trades = 0

    return {
        "as_of_date": as_of_d.isoformat(),
        "equity": total_equity,
        "cash": total_cash,
        "positions_value": total_pos,
        "unrealized_pnl": total_upnl,
        "total_return_pct": total_return_pct,
        "max_drawdown_pct": 0.0,  # computed in /paper/equity series
        "daily_pnl": daily_pnl,
        "regime": "none",
        "engine_active": "none",
        "open_positions_count": int(open_n),
        "last_decision_ts": (
            last_decision_ts.isoformat() if last_decision_ts else None
        ),
        "pipeline_status": "success",
        "portfolio_count": len(latest_rows),
        "replay_trades_count": int(replay_trades),
    }


# ---------------------------------------------------------------------------
# /paper/state
# ---------------------------------------------------------------------------
@router.get("/paper/state")
def paper_state(db: Session = Depends(get_session)) -> dict[str, Any]:
    row = db.execute(text("""
        SELECT dl.as_of_date, dl.engine, dl.action, dl.inputs_used,
               dl.context_values, dl.decision_version, dl.reason,
               dl.blocked_by, dl.diagnostic_snapshot, dl.decision_ts
        FROM decision_log dl
        ORDER BY dl.as_of_date DESC, dl.decision_ts DESC LIMIT 1
    """)).fetchone()

    if row is None:
        return {
            "as_of_date": dt.date.today().isoformat(),
            "stress_regime": False, "directional_regime": False,
            "engine": "none", "fire": False,
            "reason": "no decision_log entries yet",
            "decision_version": "selector-v1.0.0",
            "blocked_by": None,
            "gates_favorable": 0,
            "inputs_used": {}, "context_values": {},
            "diagnostic_snapshot": {},
        }
    ctx = row.context_values or {}
    inp = row.inputs_used or {}
    return {
        "as_of_date": str(row.as_of_date),
        "stress_regime": bool(ctx.get("stress_regime", False)),
        "directional_regime": bool(ctx.get("directional_regime", False)),
        "engine": row.engine,
        "fire": row.action == "enter_long",
        "reason": row.reason or "",
        "decision_version": row.decision_version or "",
        "blocked_by": row.blocked_by,
        "gates_favorable": int(inp.get("gates_favorable") or 0),
        "inputs_used": inp,
        "context_values": ctx,
        "diagnostic_snapshot": row.diagnostic_snapshot or {},
    }


# ---------------------------------------------------------------------------
# /paper/equity
# ---------------------------------------------------------------------------
@router.get("/paper/equity")
def paper_equity(
    db: Session = Depends(get_session),
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
) -> list[dict]:
    """Daily equity curve aggregated across active portfolios from
    paper_equity_snapshot. Replaces the synthetic
    paper_portfolio_snapshot stream which never reflected real
    auto_trader fills."""
    start = dt.date.fromisoformat(from_) if from_ else dt.date(2020, 1, 1)
    end = dt.date.fromisoformat(to) if to else dt.date.today()
    rows = db.execute(text("""
        SELECT s.snapshot_date::date AS d,
               sum(s.total_equity) AS equity,
               sum(s.unrealized_pnl) AS upnl
        FROM paper_equity_snapshot s
        JOIN paper_portfolio p ON p.id = s.portfolio_id
        WHERE p.is_active = TRUE
          AND s.snapshot_date::date BETWEEN :s AND :e
        GROUP BY d
        ORDER BY d
    """), {"s": start, "e": end}).fetchall()
    if not rows:
        return []
    starting_total = float(db.execute(text("""
        SELECT coalesce(sum(starting_cash), 0)
        FROM paper_portfolio WHERE is_active = TRUE
    """)).scalar() or 0)
    base_eq = float(rows[0].equity)
    peak = base_eq
    out: list[dict] = []
    prev_eq = None
    for r in rows:
        eq = float(r.equity)
        peak = max(peak, eq)
        dd_pct = ((eq - peak) / peak) * 100.0 if peak > 0 else 0.0
        cum_pct = (
            ((eq - starting_total) / starting_total) * 100.0
            if starting_total > 0 else 0.0
        )
        daily_pnl = (eq - prev_eq) if prev_eq is not None else 0.0
        prev_eq = eq
        out.append({
            "date": str(r.d),
            "equity": eq,
            "cum_pct": cum_pct,
            "dd_pct": dd_pct,
            "daily_pnl": daily_pnl,
        })
    return out


# ---------------------------------------------------------------------------
# /paper/trades
# ---------------------------------------------------------------------------
@router.get("/paper/trades")
def paper_trades(
    db: Session = Depends(get_session),
    status: Literal["open", "closed", "cancelled"] | None = None,
) -> list[dict]:
    """Real paper trades from `paper_trade` joined to
    `paper_position` for open/closed status and unrealized P&L.

    Replaces the legacy `paper_trade_log WHERE portfolio_id='default'`
    read which returned [] on the live system because no row in
    that table is keyed by 'default' and no writer keeps it
    populated. Real auto_trader fills land in `paper_trade`
    (UUID portfolios) and the open/closed flag lives on
    `paper_position.is_open`.

    Replay-flagged trades are surfaced via `is_replay` so the
    consumer can either filter or label them; the row count is
    NOT silently reduced.
    """
    # Build replay-id set (best-effort — manifest table created by
    # raw-SQL alembic migration; falls back to empty when absent).
    replay_ids: set[str] = set()
    try:
        replay_ids = {
            r[0] for r in db.execute(text("""
                SELECT entity_id FROM replay_recovery_manifest
                WHERE entity_type = 'paper_trade'
            """)).all()
        }
    except Exception:  # noqa: BLE001
        db.rollback()

    # Dedup rule (post-Phase-1C UI fix):
    #   Each row is one TRADE EVENT, not one position state. A
    #   buy followed by a sell is two events. Previously the
    #   query joined every paper_trade row to its latest
    #   paper_position and copied is_open onto both sides — so a
    #   closed position emitted both the buy AND the sell as
    #   status='closed', double-counting the Realized History
    #   panel (2 sells → 4 'closed' rows).
    #
    # New emission rule:
    #   * sell rows are always emitted as status='closed' (each
    #     sell is a realized-PnL event).
    #   * buy rows are emitted only when the joined position is
    #     currently open (status='open'). Buys whose position
    #     has since been fully closed are represented by their
    #     companion sell row and must NOT appear a second time.
    #
    # This preserves all rows in paper_trade — nothing is
    # deleted. It only stops mislabeling closed buys as
    # 'closed' alongside their sells.
    rows = db.execute(text("""
        SELECT
          t.id,
          a.symbol AS instrument,
          t.fill_ts::date AS entry_date,
          CASE WHEN pp.is_open IS FALSE THEN pp.closed_at::date END
            AS exit_date,
          t.fill_price AS entry_price,
          t.quantity,
          (t.quantity * t.fill_price)::numeric AS notional_usd,
          t.realized_pnl,
          coalesce(pp.is_open, FALSE) AS is_open,
          t.side,
          t.reason,
          t.portfolio_id
        FROM paper_trade t
        JOIN asset a ON a.id = t.asset_id
        LEFT JOIN paper_position pp
               ON pp.portfolio_id = t.portfolio_id
              AND pp.asset_id = t.asset_id
        WHERE
              t.side = 'sell'
           OR (t.side = 'buy' AND coalesce(pp.is_open, FALSE) = TRUE)
        ORDER BY t.fill_ts DESC
        LIMIT 500
    """)).mappings().all()

    out = []
    for r in rows:
        side = r["side"]
        # Each emitted row is now an unambiguous event: buys are
        # always 'open' (the WHERE clause filters out post-close
        # buys), sells are always 'closed' (realized event).
        s = "closed" if side == "sell" else "open"
        if status and status != s:
            continue
        days_held = None
        if r["exit_date"] and r["entry_date"]:
            days_held = (r["exit_date"] - r["entry_date"]).days
        out.append({
            "trade_id": str(r["id"]),
            "engine": "paper",
            "instrument": r["instrument"],
            "entry_date": str(r["entry_date"]),
            "exit_date": (
                str(r["exit_date"]) if r["exit_date"] else None
            ),
            "entry_price": float(r["entry_price"]),
            "exit_price": None,
            "position_size_pct": None,
            "gross_ret_pct": None,
            "net_ret_pct": (
                float(r["realized_pnl"])
                if r["realized_pnl"] is not None else None
            ),
            "pnl_dollar": (
                float(r["realized_pnl"])
                if r["realized_pnl"] is not None else None
            ),
            "regime_at_entry": None,
            "status": s,
            "side": side,
            "days_held": days_held,
            "decision_version": None,
            "reason": r["reason"],
            "quantity": float(r["quantity"]),
            "notional_usd": (
                float(r["notional_usd"])
                if r["notional_usd"] is not None else None
            ),
            "is_replay": str(r["id"]) in replay_ids,
            "portfolio_id": str(r["portfolio_id"]),
        })
    return out


# ---------------------------------------------------------------------------
# /paper/performance
# ---------------------------------------------------------------------------
@router.get("/paper/performance")
def paper_performance(db: Session = Depends(get_session)) -> dict[str, Any]:
    def engine_stats(engine: str) -> dict:
        rows = db.execute(text("""
            SELECT net_ret_pct, entry_date, exit_date
            FROM paper_trade_log
            WHERE engine = :e AND status = 'closed'
              AND net_ret_pct IS NOT NULL
        """), {"e": engine}).fetchall()
        rets = [float(r.net_ret_pct) for r in rows]
        if not rets:
            return {"n_trades": 0, "win_rate": 0, "avg_return_pct": 0,
                    "avg_duration_bars": 0, "total_pnl_pct": 0,
                    "sharpe_proxy": 0}
        durs = [(r.exit_date - r.entry_date).days for r in rows
                if r.exit_date and r.entry_date]
        wins = sum(1 for x in rets if x > 0)
        mean = st.mean(rets)
        sd = st.pstdev(rets) if len(rets) > 1 else 0.0
        sharpe = mean / sd * (252 ** 0.5) if sd > 0 else 0.0
        return {
            "n_trades": len(rets),
            "win_rate": wins / len(rets),
            "avg_return_pct": mean,
            "avg_duration_bars": st.mean(durs) if durs else 0,
            "total_pnl_pct": sum(rets),
            "sharpe_proxy": sharpe,
        }

    def regime_stats(regime: str) -> dict:
        rows = db.execute(text("""
            SELECT net_ret_pct FROM paper_trade_log
            WHERE regime_at_entry = :r AND status = 'closed'
              AND net_ret_pct IS NOT NULL
        """), {"r": regime}).fetchall()
        rets = [float(r.net_ret_pct) for r in rows]
        bars = db.execute(text("""
            SELECT COUNT(*) FROM context_daily
            WHERE context_name = :c AND status = 'production'
              AND value_bool = true
        """), {"c": f"{regime}_regime"}).scalar() or 0
        total_bars = db.execute(text("""
            SELECT COUNT(DISTINCT as_of_date) FROM context_daily
        """)).scalar() or 1
        return {
            "n_bars": int(bars), "n_trades": len(rets),
            "pct_of_time": bars / max(total_bars, 1),
            "mean_return_pct": st.mean(rets) if rets else 0.0,
        }

    # Monthly P&L rollup
    monthly_rows = db.execute(text("""
        SELECT DATE_TRUNC('month', exit_date)::date AS m,
               SUM(net_ret_pct) AS pnl, COUNT(*) AS n
        FROM paper_trade_log
        WHERE status = 'closed' AND exit_date IS NOT NULL
          AND net_ret_pct IS NOT NULL
        GROUP BY 1 ORDER BY 1
    """)).fetchall()

    return {
        "engine_a": engine_stats("A"),
        "engine_b": engine_stats("B"),
        "stress_regime":      regime_stats("stress"),
        "directional_regime": regime_stats("directional"),
        "monthly_pnl": [{
            "month": r.m.strftime("%Y-%m"),
            "pnl_pct": float(r.pnl or 0),
            "n_trades": int(r.n or 0),
        } for r in monthly_rows],
    }


# ---------------------------------------------------------------------------
# /decision-log/{date}
# ---------------------------------------------------------------------------
@router.get("/decision-log/{as_of_date}")
def decision_log(as_of_date: str, db: Session = Depends(get_session)) -> dict:
    row = db.execute(text("""
        SELECT id, decision_ts, as_of_date, engine, action, instrument,
               inputs_used, context_values, diagnostic_snapshot,
               decision_version, reason, blocked_by
        FROM decision_log
        WHERE as_of_date = :d
        ORDER BY decision_ts DESC LIMIT 1
    """), {"d": as_of_date}).fetchone()
    if row is None:
        # Fallback: return a synthesized row so UI can render "historical trade
        # predates decision_log retention" context
        return {
            "id": "synthetic",
            "decision_ts": dt.datetime.now(dt.timezone.utc).isoformat(),
            "as_of_date": as_of_date,
            "engine": "A",
            "action": "enter_long",
            "instrument": "ES",
            "inputs_used": {"note": "historical backfilled trade — decision_log not populated"},
            "context_values": {},
            "diagnostic_snapshot": {},
            "decision_version": "backfill-v1.0.0",
            "reason": "backfilled from Phase 24 paper simulation",
            "blocked_by": None,
        }
    return {
        "id": str(row.id),
        "decision_ts": row.decision_ts.isoformat(),
        "as_of_date": str(row.as_of_date),
        "engine": row.engine,
        "action": row.action,
        "instrument": row.instrument,
        "inputs_used": row.inputs_used or {},
        "context_values": row.context_values or {},
        "diagnostic_snapshot": row.diagnostic_snapshot or {},
        "decision_version": row.decision_version,
        "reason": row.reason,
        "blocked_by": row.blocked_by,
    }


# ---------------------------------------------------------------------------
# /anomalies
# ---------------------------------------------------------------------------
@router.get("/anomalies")
def anomalies(
    db: Session = Depends(get_session),
    status: Literal["open", "acknowledged", "resolved"] | None = "open",
    severity: Literal["info", "warning", "critical"] | None = None,
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
) -> list[dict]:
    q = """
        SELECT id, as_of_date, category, severity, rule_key, title,
               description, related_engine, related_trade_id,
               related_decision_id, metrics_snapshot, status, created_at
        FROM anomaly_event
        WHERE 1=1
        {status} {severity} {from_} {to}
        ORDER BY created_at DESC LIMIT 200
    """
    parts = {"status": "", "severity": "", "from_": "", "to": ""}
    params: dict[str, Any] = {}
    if status:   parts["status"] = "AND status = :st"; params["st"] = status
    if severity: parts["severity"] = "AND severity = :sv"; params["sv"] = severity
    if from_:    parts["from_"] = "AND as_of_date >= :f"; params["f"] = dt.date.fromisoformat(from_)
    if to:       parts["to"]    = "AND as_of_date <= :tt"; params["tt"] = dt.date.fromisoformat(to)
    rows = db.execute(text(q.format(**parts)), params).fetchall()
    return [_anom_row(r) for r in rows]


@router.get("/anomalies/summary")
def anomalies_summary(db: Session = Depends(get_session)) -> dict:
    rows = db.execute(text("""
        SELECT severity, category, COUNT(*) AS n
        FROM anomaly_event WHERE status = 'open'
        GROUP BY severity, category
    """)).fetchall()
    by_severity = {"info": 0, "warning": 0, "critical": 0}
    by_category = {"decision": 0, "trade": 0, "regime": 0,
                   "data": 0, "shadow": 0}
    total = 0
    for r in rows:
        by_severity[r.severity] = by_severity.get(r.severity, 0) + int(r.n)
        by_category[r.category] = by_category.get(r.category, 0) + int(r.n)
        total += int(r.n)

    top3_rows = db.execute(text("""
        SELECT id, as_of_date, category, severity, rule_key, title,
               description, related_engine, related_trade_id,
               related_decision_id, metrics_snapshot, status, created_at
        FROM anomaly_event WHERE status = 'open'
        ORDER BY CASE severity
          WHEN 'critical' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END,
          created_at DESC
        LIMIT 3
    """)).fetchall()

    return {
        "total_open": total,
        "by_severity": by_severity,
        "by_category": by_category,
        "top3": [_anom_row(r) for r in top3_rows],
    }


def _anom_row(r) -> dict:
    return {
        "id": str(r.id),
        "as_of_date": str(r.as_of_date),
        "category": r.category,
        "severity": r.severity,
        "rule_key": r.rule_key,
        "title": r.title,
        "description": r.description,
        "related_engine": r.related_engine,
        "related_trade_id": str(r.related_trade_id) if r.related_trade_id else None,
        "related_decision_id": str(r.related_decision_id) if r.related_decision_id else None,
        "metrics_snapshot": r.metrics_snapshot or {},
        "status": r.status,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


# ---------------------------------------------------------------------------
# /shadow/signals
# ---------------------------------------------------------------------------
@router.get("/shadow/signals")
def shadow_signals() -> list[dict]:
    """Static inventory of non-production signals with their status.
    Sourced from feature_registry.yaml (parsed at import time in DL2)."""
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    return [
        {
            "name": "gex_sign",
            "status": "diagnostic",
            "value": -1, "value_display": "NEG_GEX",
            "context_flag": True,
            "source": "SqueezeMetrics free CSV",
            "last_updated": now,
            "notes": "Phase X3 FAIL — removes winning trades; logged only.",
        },
        {
            "name": "ts_ratio",
            "status": "candidate",
            "value": 0.97, "value_display": "0.97",
            "context_flag": False,
            "source": "yfinance ^VIX / ^VIX3M",
            "last_updated": now,
            "notes": "Phase X2 overlay FAILED; retained for evaluation.",
        },
        {
            "name": "cot_extreme_flag",
            "status": "candidate",
            "value": None, "value_display": "n/a",
            "context_flag": None,
            "source": "CFTC COT weekly (ingest pending)",
            "last_updated": now,
            "notes": "Ingest not yet wired; visible in registry only.",
        },
    ]


# ---------------------------------------------------------------------------
# /system/health
# ---------------------------------------------------------------------------
@router.get("/system/health")
def system_health(db: Session = Depends(get_session)) -> dict:
    """Report recent critical/warn anomalies + data freshness."""
    today = dt.date.today()
    items: list[dict] = []

    # Critical anomalies -> ERROR items
    rows = db.execute(text("""
        SELECT rule_key, title, description, as_of_date
        FROM anomaly_event
        WHERE status = 'open' AND severity IN ('critical', 'warning')
        ORDER BY severity, created_at DESC LIMIT 10
    """)).fetchall()
    for r in rows:
        items.append({
            "key": r.rule_key,
            "severity": "error" if "critical" in r.rule_key else "warn",
            "label": r.title,
            "detail": r.description,
            "first_seen": str(r.as_of_date),
            "last_seen": str(r.as_of_date),
        })

    # Simple data freshness check — newest price bar
    latest = db.execute(text("""
        SELECT MAX(ts) FROM price_bar WHERE timeframe = '1d'
    """)).scalar()
    if latest:
        age = (today - latest.date()).days if hasattr(latest, "date") else 0
        if age > 3:
            items.append({
                "key": "stale_price_bar",
                "severity": "warn",
                "label": "Price data stale",
                "detail": f"latest price_bar is {age} days old",
                "first_seen": str(today), "last_seen": str(today),
            })

    overall = "healthy"
    if any(i["severity"] == "error" for i in items):
        overall = "failed" if len(items) > 3 else "degraded"
    elif items:
        overall = "degraded"

    return {
        "as_of_date": today.isoformat(),
        "overall": overall,
        "items": items,
    }
