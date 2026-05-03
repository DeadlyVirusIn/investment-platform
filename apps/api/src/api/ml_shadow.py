"""Admin shadow ML API — read-only except manual trigger."""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.config import settings
from apps.api.src.db import SessionLocal
from apps.api.src.ml.shadow import run_nightly_shadow
from apps.api.src.ml.shadow.trainer import ModelType

router = APIRouter(prefix="/ml/shadow", tags=["ml-shadow"])


def _session() -> Session:
    return SessionLocal()


def _require_enabled() -> None:
    if not getattr(settings, "ML_SHADOW_ENABLED", True):
        raise HTTPException(status_code=503,
                              detail="shadow ML disabled")


# ---------------------------------------------------------------------------

@router.get("/status")
async def status() -> dict[str, Any]:
    _require_enabled()
    with _session() as s:
        row = s.execute(text("""
            SELECT id::text AS id, created_at, run_name, model_type,
                   dataset_source, status, row_count, labeled_row_count,
                   blockers, metrics, baseline_comparison, calibration
            FROM ml_model_run
            ORDER BY created_at DESC
            LIMIT 1
        """)).mappings().first()
    if row is None:
        return {"present": False}
    return {"present": True, "latest_model_run": dict(row)}


@router.get("/model-runs")
async def model_runs(limit: int = 30) -> dict[str, Any]:
    _require_enabled()
    with _session() as s:
        rows = s.execute(text("""
            SELECT id::text AS id, created_at, run_name, model_type,
                   dataset_source, status, row_count, labeled_row_count
            FROM ml_model_run
            ORDER BY created_at DESC
            LIMIT :l
        """), {"l": int(limit)}).mappings().all()
    return {"count": len(rows), "runs": [dict(r) for r in rows]}


@router.get("/model-runs/{run_id}")
async def model_run(run_id: str) -> dict[str, Any]:
    _require_enabled()
    with _session() as s:
        row = s.execute(text("""
            SELECT id::text AS id, created_at, run_name, model_type,
                   dataset_source, train_start_date, train_end_date,
                   test_start_date, test_end_date,
                   row_count, labeled_row_count,
                   feature_list, label_target, horizon,
                   hyperparams, metrics, baseline_comparison,
                   leakage_report, feature_health, calibration,
                   status, blockers, notes
            FROM ml_model_run
            WHERE id = :id
        """), {"id": run_id}).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="model run not found")
    return dict(row)


@router.get("/latest-report")
async def latest_report() -> dict[str, Any]:
    _require_enabled()
    with _session() as s:
        mr = s.execute(text("""
            SELECT id::text AS id, created_at, model_type, dataset_source,
                   status, row_count, labeled_row_count, blockers,
                   metrics, baseline_comparison, calibration, feature_health
            FROM ml_model_run
            ORDER BY created_at DESC
            LIMIT 1
        """)).mappings().first()
        if mr is None:
            return {"present": False}
        preds = s.execute(text("""
            SELECT COUNT(*) AS n,
                   SUM(CASE WHEN ml_action='accept' THEN 1 ELSE 0 END) AS n_accept,
                   SUM(CASE WHEN ml_action='avoid'  THEN 1 ELSE 0 END) AS n_avoid,
                   SUM(CASE WHEN ml_action='reduce' THEN 1 ELSE 0 END) AS n_reduce,
                   SUM(CASE WHEN ml_action='needs_more_data' THEN 1 ELSE 0 END) AS n_needs
            FROM ml_shadow_prediction
            WHERE model_run_id = :id
        """), {"id": mr["id"]}).mappings().first()
    return {
        "present": True,
        "latest_model_run": dict(mr),
        "prediction_counts": dict(preds) if preds else None,
    }


@router.get("/predictions")
async def predictions(
    limit: int = 100, run_id: str | None = None,
) -> dict[str, Any]:
    _require_enabled()
    params: dict[str, Any] = {"l": int(limit)}
    where = ""
    if run_id:
        where = "WHERE model_run_id = :r"
        params["r"] = run_id
    with _session() as s:
        rows = s.execute(text(f"""
            SELECT id::text AS id, model_run_id::text AS model_run_id,
                   created_at, source_type, symbol, as_of_date,
                   original_decision, engine, engine_confidence,
                   ml_score, ml_confidence, ml_action, ml_reason_codes,
                   outcome_available, actual_outcome
            FROM ml_shadow_prediction
            {where}
            ORDER BY created_at DESC
            LIMIT :l
        """), params).mappings().all()
    return {"count": len(rows), "predictions": [dict(r) for r in rows]}


@router.get("/disagreements")
async def disagreements(run_id: str | None = None) -> dict[str, Any]:
    _require_enabled()
    # Aggregate from ml_shadow_prediction join with original decision_log
    where = "WHERE 1=1"
    params: dict[str, Any] = {}
    if run_id:
        where += " AND model_run_id = :r"
        params["r"] = run_id
    with _session() as s:
        rows = s.execute(text(f"""
            SELECT source_type, original_decision, ml_action,
                   COUNT(*) AS n,
                   AVG(COALESCE(actual_outcome, 0)) AS mean_outcome
            FROM ml_shadow_prediction
            {where}
            GROUP BY source_type, original_decision, ml_action
            ORDER BY n DESC
            LIMIT 40
        """), params).mappings().all()
    return {"count": len(rows), "matrix": [dict(r) for r in rows]}


@router.get("/calibration")
async def calibration(run_id: str | None = None) -> dict[str, Any]:
    _require_enabled()
    where = ""
    params: dict[str, Any] = {}
    if run_id:
        where = "WHERE id = :r"
        params["r"] = run_id
    with _session() as s:
        row = s.execute(text(f"""
            SELECT id::text AS id, calibration
            FROM ml_model_run
            {where}
            ORDER BY created_at DESC
            LIMIT 1
        """), params).mappings().first()
    if row is None:
        return {"present": False}
    return {"present": True, "run_id": row["id"],
            "calibration": row.get("calibration")}


@router.post("/run")
async def run_manual() -> dict[str, Any]:
    _require_enabled()
    min_rows = int(
        getattr(settings, "ML_SHADOW_MIN_ROWS", 1000),
    )
    types = tuple(
        ModelType(m.strip())
        for m in getattr(
            settings, "ML_SHADOW_MODEL_TYPES", "logistic,ridge,rf",
        ).split(",")
        if m.strip() in {"logistic", "ridge", "rf", "gbm"}
    ) or (ModelType.LOGISTIC,)
    with _session() as s:
        result = run_nightly_shadow(
            s, min_training_rows=min_rows, model_types=types, persist=True,
        )
    return result.to_dict()
