"""Phase Options-1 — GET-only API surface for the options shadow
evaluator. Read-only against `options_shadow_decision_log`.

NEVER mounts a POST/PUT/DELETE handler. UI consumers see this as a
diagnostics feed only. NEVER returns rows from `options_paper_trade`
(which remains empty in this phase) or `paper_trade`.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from apps.api.src.config import settings
from apps.api.src.db import SessionLocal


router = APIRouter(prefix="/options/shadow", tags=["options"])


def _row_to_payload(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_date": r["run_date"].isoformat() if r.get("run_date") else None,
        "underlying_symbol": r.get("underlying_symbol"),
        "option_symbol": r.get("option_symbol"),
        "expiration": (
            r["expiration"].isoformat() if r.get("expiration") else None
        ),
        "strike": str(r["strike"]) if r.get("strike") is not None else None,
        "option_type": r.get("option_type"),
        "side": r.get("side"),
        "strategy_name": r.get("strategy_name"),
        "would_trade": bool(r.get("would_trade")),
        "reason": r.get("reason"),
        "score": str(r["score"]) if r.get("score") is not None else None,
        "filters": {
            "liquidity": bool(r.get("liquidity_pass")),
            "spread": bool(r.get("spread_pass")),
            "open_interest": bool(r.get("open_interest_pass")),
            "volume": bool(r.get("volume_pass")),
            "greeks": bool(r.get("greeks_pass")),
            "iv_rank": bool(r.get("iv_rank_pass")),
            "risk": bool(r.get("risk_pass")),
        },
        "diagnostics": r.get("diagnostics"),
        "created_at": (
            r["created_at"].isoformat() if r.get("created_at") else None
        ),
    }


@router.get("/summary")
def get_summary() -> dict[str, Any]:
    """Top-level rollup. Latest run + counts."""
    with SessionLocal() as s:
        latest_row = s.execute(text(
            "SELECT max(run_date) AS d FROM options_shadow_decision_log"
        )).first()
        latest_date = latest_row.d if latest_row and latest_row.d else None
        if latest_date is None:
            return {
                "active": bool(settings.OPTIONS_SHADOW_EVAL_ENABLED),
                "latest_run_date": None,
                "total_runs": 0,
                "freshness_warnings": ["no_shadow_decisions_yet"],
            }
        agg = s.execute(text(
            """
            SELECT
                count(*) FILTER (WHERE run_date = :d) AS contracts_evaluated,
                count(*) FILTER (WHERE run_date = :d AND would_trade)
                    AS would_trade_count,
                count(DISTINCT underlying_symbol)
                    FILTER (WHERE run_date = :d) AS underlying_count,
                count(DISTINCT run_date) AS total_runs
            FROM options_shadow_decision_log
            """
        ), {"d": latest_date}).mappings().first()
        reasons = s.execute(text(
            """
            SELECT reason, count(*) AS n
            FROM options_shadow_decision_log
            WHERE run_date = :d AND NOT would_trade
            GROUP BY reason ORDER BY n DESC
            """
        ), {"d": latest_date}).mappings().all()
    return {
        "active": bool(settings.OPTIONS_SHADOW_EVAL_ENABLED),
        "latest_run_date": latest_date.isoformat(),
        "total_runs": int(agg["total_runs"] or 0),
        "underlying_count": int(agg["underlying_count"] or 0),
        "contracts_evaluated": int(agg["contracts_evaluated"] or 0),
        "would_trade_count": int(agg["would_trade_count"] or 0),
        "blocked_reason_counts": {
            r["reason"]: int(r["n"]) for r in reasons
        },
        "freshness_warnings": [],
    }


@router.get("/runs")
def list_runs(limit: int = 30) -> dict[str, Any]:
    """One row per distinct run_date (most recent first)."""
    if limit < 1 or limit > 365:
        raise HTTPException(400, "limit must be 1..365")
    with SessionLocal() as s:
        rows = s.execute(text(
            """
            SELECT run_date,
                   count(*) AS contracts_evaluated,
                   count(*) FILTER (WHERE would_trade) AS would_trade_count,
                   count(DISTINCT underlying_symbol) AS underlying_count
            FROM options_shadow_decision_log
            GROUP BY run_date
            ORDER BY run_date DESC
            LIMIT :n
            """
        ), {"n": limit}).mappings().all()
    return {
        "runs": [
            {
                "run_date": r["run_date"].isoformat(),
                "contracts_evaluated": int(r["contracts_evaluated"]),
                "would_trade_count": int(r["would_trade_count"]),
                "underlying_count": int(r["underlying_count"]),
            }
            for r in rows
        ],
    }


@router.get("/runs/{run_date}")
def get_run(run_date: str, limit: int = 200) -> dict[str, Any]:
    try:
        d = dt.date.fromisoformat(run_date)
    except ValueError as exc:
        raise HTTPException(400, f"invalid date: {exc}") from exc
    if limit < 1 or limit > 1000:
        raise HTTPException(400, "limit must be 1..1000")
    with SessionLocal() as s:
        rows = s.execute(text(
            """
            SELECT run_date, underlying_symbol, option_symbol, expiration,
                   strike, option_type, side, strategy_name,
                   would_trade, reason,
                   liquidity_pass, spread_pass, open_interest_pass,
                   volume_pass, greeks_pass, iv_rank_pass, risk_pass,
                   score, diagnostics, created_at
            FROM options_shadow_decision_log
            WHERE run_date = :d
            ORDER BY would_trade DESC,
                     score DESC NULLS LAST,
                     option_symbol
            LIMIT :n
            """
        ), {"d": d, "n": limit}).mappings().all()
    if not rows:
        raise HTTPException(404, f"no shadow decisions for {run_date}")
    payloads = [_row_to_payload(dict(r)) for r in rows]
    return {
        "run_date": d.isoformat(),
        "decisions": payloads,
        "would_trade_count": sum(1 for p in payloads if p["would_trade"]),
        "blocked_count": sum(1 for p in payloads if not p["would_trade"]),
    }
