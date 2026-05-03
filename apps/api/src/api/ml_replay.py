"""ML replay API — admin-only endpoints, safe + read-only by default.

No endpoint may affect live trading. Even /run writes ONLY to replay tables.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Body, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.config import settings
from apps.api.src.db import SessionLocal
from apps.api.src.ml.replay import (
    Replayer, ReplayRunConfig, build_replay_report,
    label_outcomes_for_run, resolve_universe, validate_replay_leakage,
)

router = APIRouter(prefix="/ml/replay", tags=["ml-replay"])


def _open_session() -> Session:
    return SessionLocal()


def _require_enabled() -> None:
    if not getattr(settings, "ML_ADVISORY_ENABLED", True):
        raise HTTPException(status_code=503, detail="ML advisory disabled")


# ---------------------------------------------------------------------------
# runs
# ---------------------------------------------------------------------------

@router.post("/run")
async def run_replay(
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    _require_enabled()
    start = _parse_date(body.get("start_date"), "start_date")
    end = _parse_date(body.get("end_date"), "end_date")
    if end > dt.date.today():
        raise HTTPException(
            status_code=400,
            detail="end_date must be ≤ today",
        )
    universe_raw = body.get("universe")
    max_symbols = body.get("max_symbols")
    uni = resolve_universe(
        explicit=universe_raw if isinstance(universe_raw, list) else None,
        max_symbols=int(max_symbols) if max_symbols else None,
    )
    cfg = ReplayRunConfig(
        replay_name=str(body.get("replay_name") or f"replay-{start}-{end}"),
        start_date=start,
        end_date=end,
        universe=uni.symbols,
        max_symbols=int(max_symbols) if max_symbols else None,
        dry_run=bool(body.get("dry_run", False)),
        every_n_days=int(body.get("every_n_days", 1)),
    )
    with _open_session() as s:
        result = Replayer(s).run(cfg)
        # Attach universe warnings to the run row (if persisted)
        if result.persisted:
            s.execute(text("""
                UPDATE ml_replay_run
                   SET warnings = CAST(:w AS jsonb)
                 WHERE id = :id
            """), {"w": _json_list(uni.warnings), "id": result.run_id})
            s.commit()
    return {
        "run_id": result.run_id,
        "n_decisions": result.n_decisions,
        "n_symbols": result.n_symbols,
        "n_dates": result.n_dates,
        "persisted": result.persisted,
        "universe_warnings": list(uni.warnings),
    }


@router.get("/runs")
async def list_runs(limit: int = 30) -> dict[str, Any]:
    _require_enabled()
    with _open_session() as s:
        rows = s.execute(text("""
            SELECT id::text AS id, replay_name, replay_version,
                   created_at, start_date, end_date, status,
                   summary
            FROM ml_replay_run
            ORDER BY created_at DESC
            LIMIT :lim
        """), {"lim": int(limit)}).mappings().all()
    return {"count": len(rows), "runs": [dict(r) for r in rows]}


@router.get("/runs/{run_id}")
async def get_run(run_id: str) -> dict[str, Any]:
    _require_enabled()
    with _open_session() as s:
        row = s.execute(text("""
            SELECT id::text AS id, replay_name, replay_version,
                   created_at, start_date, end_date,
                   universe, engine_versions, config, provider_priority,
                   status, warnings, leakage_report, summary
            FROM ml_replay_run
            WHERE id = :id
        """), {"id": run_id}).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="replay run not found")
    return dict(row)


@router.get("/runs/{run_id}/decisions")
async def get_run_decisions(
    run_id: str, limit: int = 200, offset: int = 0,
) -> dict[str, Any]:
    _require_enabled()
    with _open_session() as s:
        rows = s.execute(text("""
            SELECT id::text AS id, as_of_date, decision_ts, symbol,
                   engine, decision, confidence, skip_reason,
                   data_quality, catalyst, regime
            FROM ml_replay_decision
            WHERE replay_run_id = :r
            ORDER BY as_of_date ASC, symbol ASC
            LIMIT :lim OFFSET :off
        """), {"r": run_id, "lim": int(limit), "off": int(offset)}).mappings().all()
    return {"count": len(rows), "decisions": [dict(r) for r in rows]}


@router.get("/runs/{run_id}/report")
async def get_run_report(run_id: str) -> dict[str, Any]:
    _require_enabled()
    with _open_session() as s:
        rep = build_replay_report(s, run_id)
    return rep.to_dict()


@router.post("/runs/{run_id}/label-outcomes")
async def label_outcomes(
    run_id: str,
    horizons: list[int] | None = Body(default=None),
) -> dict[str, Any]:
    _require_enabled()
    hz = tuple(horizons) if horizons else (1, 3, 5, 10)
    with _open_session() as s:
        rows = label_outcomes_for_run(
            s, run_id, horizons=hz, persist=True,
        )
    return {"labeled": len(rows), "horizons": list(hz)}


@router.post("/runs/{run_id}/validate-leakage")
async def validate_leakage(run_id: str) -> dict[str, Any]:
    _require_enabled()
    with _open_session() as s:
        rep = validate_replay_leakage(s, run_id, strict=False)
        # Persist latest leakage report on the run row
        s.execute(text("""
            UPDATE ml_replay_run
               SET leakage_report = CAST(:r AS jsonb),
                   status = CASE WHEN :ok THEN status
                                 ELSE 'failed_leakage' END
             WHERE id = :id
        """), {
            "r":  _json_dict(rep.to_dict()),
            "ok": rep.ok,
            "id": run_id,
        })
        s.commit()
    return rep.to_dict()


@router.get("/runs/latest")
async def latest_run() -> dict[str, Any]:
    _require_enabled()
    with _open_session() as s:
        row = s.execute(text("""
            SELECT id::text AS id, replay_name, replay_version,
                   created_at, start_date, end_date, status,
                   warnings, summary
            FROM ml_replay_run
            ORDER BY created_at DESC
            LIMIT 1
        """)).mappings().first()
    if row is None:
        return {"present": False}
    return {"present": True, "run": dict(row)}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _parse_date(v: Any, name: str) -> dt.date:
    if not v:
        raise HTTPException(status_code=400, detail=f"{name} required")
    try:
        return dt.date.fromisoformat(str(v))
    except ValueError as e:
        raise HTTPException(
            status_code=400, detail=f"{name}: invalid ISO date"
        ) from e


def _json_dict(d: dict) -> str:
    import json
    return json.dumps(d, default=str)


def _json_list(xs) -> str:
    import json
    return json.dumps(list(xs), default=str)
