"""Admin API — historical catalyst backfill + coverage + readiness."""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Body, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.config import settings
from apps.api.src.data.catalysts.backfill import (
    BackfillRunConfig, BackfillService, build_coverage_report,
    coverage_for_symbol,
)
from apps.api.src.db import SessionLocal
from apps.api.src.ml.replay.comparator import compare_replay_to_real
from apps.api.src.ml.replay.validation_harness import (
    replay_training_readiness,
)

router = APIRouter(prefix="/catalysts/backfill", tags=["catalyst-backfill"])
replay_router = APIRouter(prefix="/ml/replay", tags=["ml-replay"])


def _session() -> Session:
    return SessionLocal()


def _require_enabled() -> None:
    if not getattr(settings, "ML_ADVISORY_ENABLED", True):
        raise HTTPException(status_code=503, detail="ML advisory disabled")


# ---------------------------------------------------------------------------
# backfill run endpoints
# ---------------------------------------------------------------------------

@router.post("/run")
async def run_backfill(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    _require_enabled()
    symbols_raw = body.get("symbols") or []
    if not isinstance(symbols_raw, list) or not symbols_raw:
        raise HTTPException(status_code=400, detail="symbols required")
    try:
        start = dt.date.fromisoformat(str(body["start_date"]))
        end   = dt.date.fromisoformat(str(body["end_date"]))
    except (KeyError, ValueError) as e:
        raise HTTPException(
            status_code=400, detail=f"bad date: {e}",
        ) from e
    providers = tuple(
        str(p).lower() for p in
        (body.get("providers")
          or getattr(settings,
                      "CATALYST_BACKFILL_PROVIDER_PRIORITY",
                      "finnhub,yahoo").split(","))
    )
    dry_run = bool(body.get("dry_run", True))
    cfg = BackfillRunConfig(
        symbols=tuple(s.upper() for s in symbols_raw),
        start_date=start,
        end_date=end,
        providers=providers,
        window_days=int(body.get("window_days", 30)),
        rate_limit_per_min=int(body.get("rate_limit_per_min", 60)),
        dry_run=dry_run,
    )
    with _session() as s:
        result = BackfillService(s).run(cfg)
    return {
        "run_id": result.run_id,
        "news_inserted": result.news_inserted,
        "news_skipped":  result.news_skipped,
        "earnings_inserted": result.earnings_inserted,
        "earnings_skipped":  result.earnings_skipped,
        "provider_errors": result.provider_errors[:20],
        "warnings": result.warnings[:20],
        "symbol_counts": result.symbol_counts,
        "persisted": result.persisted,
    }


@router.get("/runs")
async def list_backfill_runs(limit: int = 30) -> dict[str, Any]:
    _require_enabled()
    with _session() as s:
        rows = s.execute(text("""
            SELECT id::text AS id, started_at, finished_at, status,
                   symbols, start_date, end_date, providers, dry_run,
                   summary, warnings
            FROM catalyst_backfill_run
            ORDER BY started_at DESC
            LIMIT :l
        """), {"l": int(limit)}).mappings().all()
    return {"count": len(rows), "runs": [dict(r) for r in rows]}


@router.get("/runs/{run_id}")
async def get_backfill_run(run_id: str) -> dict[str, Any]:
    _require_enabled()
    with _session() as s:
        row = s.execute(text("""
            SELECT id::text AS id, started_at, finished_at, status,
                   symbols, start_date, end_date, providers, dry_run,
                   config, summary, warnings
            FROM catalyst_backfill_run
            WHERE id = :id
        """), {"id": run_id}).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="backfill run not found")
    return dict(row)


# ---------------------------------------------------------------------------
# coverage endpoints
# ---------------------------------------------------------------------------

@router.get("/coverage")
async def coverage(
    symbols: str, start_date: str, end_date: str,
) -> dict[str, Any]:
    _require_enabled()
    syms = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    try:
        ws = dt.date.fromisoformat(start_date)
        we = dt.date.fromisoformat(end_date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    with _session() as s:
        rep = build_coverage_report(
            s, syms, window_start=ws, window_end=we,
        )
    return rep.to_dict()


@router.get("/coverage/{symbol}")
async def coverage_single(
    symbol: str, start_date: str, end_date: str,
) -> dict[str, Any]:
    _require_enabled()
    try:
        ws = dt.date.fromisoformat(start_date)
        we = dt.date.fromisoformat(end_date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    with _session() as s:
        c = coverage_for_symbol(
            s, symbol.upper(), window_start=ws, window_end=we,
        )
    return c.to_dict()


# ---------------------------------------------------------------------------
# replay readiness + compare endpoints
# ---------------------------------------------------------------------------

@replay_router.post("/runs/{run_id}/compare-real")
async def compare_real(run_id: str) -> dict[str, Any]:
    _require_enabled()
    with _session() as s:
        r = compare_replay_to_real(s, run_id)
    return r.to_dict()


@replay_router.get("/runs/{run_id}/comparison-report")
async def comparison_report(run_id: str) -> dict[str, Any]:
    _require_enabled()
    with _session() as s:
        r = compare_replay_to_real(s, run_id)
    return r.to_dict()


@replay_router.get("/training-readiness")
async def training_readiness(
    symbols: str | None = None,
    start_date: str | None = None,
    end_date:   str | None = None,
    replay_run_id: str | None = None,
) -> dict[str, Any]:
    _require_enabled()
    sym_list = (
        [s.strip().upper() for s in symbols.split(",") if s.strip()]
        if symbols else None
    )
    ws = dt.date.fromisoformat(start_date) if start_date else None
    we = dt.date.fromisoformat(end_date)   if end_date   else None
    with _session() as s:
        rep = replay_training_readiness(
            s,
            replay_run_id=replay_run_id,
            coverage_symbols=sym_list,
            coverage_start=ws,
            coverage_end=we,
        )
    return rep.to_dict()
