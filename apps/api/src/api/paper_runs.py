"""Paper run visibility endpoints.

GET /api/paper/runs/latest
GET /api/paper/runs?limit=N
GET /api/paper/runs/{id}
GET /api/paper/runs/latest/events
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.db import SessionLocal

router = APIRouter(prefix="/paper/runs", tags=["paper-runs"])


def _s() -> Session:
    return SessionLocal()


@router.get("/latest")
async def latest_run() -> dict[str, Any]:
    with _s() as s:
        row = s.execute(text("""
            SELECT id::text AS id, run_date, started_at, finished_at,
                   status, decisions_evaluated, trades_opened,
                   trades_closed, trades_skipped,
                   exploratory_trades, strict_trades,
                   blocked_by_gates, blocked_by_anomaly,
                   blocked_by_data_quality,
                   net_pnl_today, nav_start, nav_end,
                   summary, warnings, details
            FROM paper_run_log
            ORDER BY started_at DESC
            LIMIT 1
        """)).mappings().first()
    if row is None:
        return {"present": False}
    return {"present": True, **dict(row)}


@router.get("")
async def list_runs(limit: int = 30) -> dict[str, Any]:
    with _s() as s:
        rows = s.execute(text("""
            SELECT id::text AS id, run_date, started_at, finished_at,
                   status, trades_opened, trades_closed,
                   exploratory_trades, strict_trades,
                   net_pnl_today, summary
            FROM paper_run_log
            ORDER BY started_at DESC
            LIMIT :l
        """), {"l": int(limit)}).mappings().all()
    return {"count": len(rows), "runs": [dict(r) for r in rows]}


@router.get("/{run_id}")
async def get_run(run_id: str) -> dict[str, Any]:
    with _s() as s:
        row = s.execute(text("""
            SELECT id::text AS id, run_date, started_at, finished_at,
                   status, decisions_evaluated, trades_opened,
                   trades_closed, trades_skipped,
                   exploratory_trades, strict_trades,
                   blocked_by_gates, blocked_by_anomaly,
                   blocked_by_data_quality,
                   net_pnl_today, nav_start, nav_end,
                   summary, warnings, details
            FROM paper_run_log
            WHERE id = :id
        """), {"id": run_id}).mappings().first()
    if row is None:
        raise HTTPException(404, "paper run not found")
    return dict(row)


@router.get("/latest/events")
async def latest_events(limit: int = 50) -> dict[str, Any]:
    """Derive events from decision_log + paper_trade_log on latest run_date."""
    with _s() as s:
        latest = s.execute(text("""
            SELECT run_date FROM paper_run_log
            ORDER BY started_at DESC LIMIT 1
        """)).mappings().first()
        if not latest:
            return {"count": 0, "events": []}
        rd = latest["run_date"]
        decisions = s.execute(text("""
            SELECT decision_ts AS ts, instrument AS symbol, engine,
                   action, gate_mode,
                   exploratory_paper, alpha_rule_size_multiplier,
                   gates_passed, gates_total, reason
            FROM decision_log
            WHERE as_of_date = :d
            ORDER BY decision_ts ASC
            LIMIT :l
        """), {"d": rd, "l": int(limit)}).mappings().all()
        trades = s.execute(text("""
            SELECT entry_date AS ts, instrument AS symbol, engine,
                   'opened' AS event_type, exploratory_paper,
                   position_size_pct, status,
                   gross_ret_pct, net_ret_pct,
                   (alpha_rule_snapshot->>'similarity_matched')    AS sim_matched,
                   (alpha_rule_snapshot->>'similarity_multiplier') AS sim_mult,
                   (alpha_rule_snapshot->'similarity'->>'reason')   AS sim_reason,
                   (alpha_rule_snapshot->'similarity'->>'n_neighbors') AS sim_n,
                   (alpha_rule_snapshot->'similarity'->>'avg_return_pct') AS sim_avg,
                   (alpha_rule_snapshot->'similarity'->>'win_rate') AS sim_wr,
                   (alpha_rule_snapshot->>'ml_shadow_available')    AS ml_avail,
                   (alpha_rule_snapshot->>'ml_shadow_multiplier')   AS ml_mult,
                   (alpha_rule_snapshot->>'ml_hybrid_action')       AS ml_action,
                   (alpha_rule_snapshot->'ml_hybrid'->>'ml_hybrid_reason') AS ml_reason,
                   (alpha_rule_snapshot->'ml_hybrid'->'ml_hybrid_snapshot'->>'status') AS ml_status
            FROM paper_trade_log
            WHERE entry_date = :d
            UNION ALL
            SELECT exit_date AS ts, instrument, engine,
                   'closed' AS event_type, exploratory_paper,
                   position_size_pct, status,
                   gross_ret_pct, net_ret_pct,
                   (alpha_rule_snapshot->>'similarity_matched')    AS sim_matched,
                   (alpha_rule_snapshot->>'similarity_multiplier') AS sim_mult,
                   (alpha_rule_snapshot->'similarity'->>'reason')   AS sim_reason,
                   (alpha_rule_snapshot->'similarity'->>'n_neighbors') AS sim_n,
                   (alpha_rule_snapshot->'similarity'->>'avg_return_pct') AS sim_avg,
                   (alpha_rule_snapshot->'similarity'->>'win_rate') AS sim_wr,
                   (alpha_rule_snapshot->>'ml_shadow_available')    AS ml_avail,
                   (alpha_rule_snapshot->>'ml_shadow_multiplier')   AS ml_mult,
                   (alpha_rule_snapshot->>'ml_hybrid_action')       AS ml_action,
                   (alpha_rule_snapshot->'ml_hybrid'->>'ml_hybrid_reason') AS ml_reason,
                   (alpha_rule_snapshot->'ml_hybrid'->'ml_hybrid_snapshot'->>'status') AS ml_status
            FROM paper_trade_log
            WHERE exit_date = :d
            ORDER BY ts ASC
        """), {"d": rd}).mappings().all()
    return {
        "run_date": rd.isoformat() if rd else None,
        "count": len(decisions) + len(trades),
        "decisions": [dict(r) for r in decisions],
        "trades":    [dict(r) for r in trades],
    }
