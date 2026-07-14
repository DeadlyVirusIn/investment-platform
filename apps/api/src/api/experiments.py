"""Experiment Lab API — Wave 3A. Owner-only, flag-mounted (fail-closed).

Mounted ONLY when settings.EXPERIMENT_LAB_ENABLED is True. Every route is
owner-gated (require_owner, 404 posture). The create route accepts a
BOUNDED structured specification (validated in domain/evaluation/lab.py)
— never code, SQL, paths, or shell. Runs execute synchronously under hard
resource caps (seconds, not minutes — measured in the validation report);
no second scheduler exists. Reproduction creates a NEW linked run
(parent_run_id) and never edits the original. Nothing here promotes a
model — promotion_readiness is a read-only verdict.

Redaction: run payloads carry no stack traces (bounded categorized
error_summary only), no env vars, no filesystem paths beyond the registry
artifact manifest, no secrets, no internal hostnames.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from apps.api.src.api.admin_guard import require_owner
from apps.api.src.db import get_session
from apps.api.src.db.models import ResearchRun
from apps.api.src.domain.evaluation import lab

router = APIRouter(prefix="/admin/experiments", tags=["experiment-lab"])

LIST_CAP = 50


def _map_error(exc: lab.LabError):
    if isinstance(exc, lab.ConcurrentRunError):
        raise HTTPException(status_code=409, detail=str(exc)[:200])
    raise HTTPException(status_code=422, detail=str(exc)[:200])


@router.post("/runs", status_code=201)
def create_run(
    spec: dict,
    owner: dict = Depends(require_owner),
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    """Create + execute one experiment run from a bounded structured spec.
    Optional spec field research_task_id records migration-121 provenance
    in the run parameters (validated existence)."""
    task_id = None
    if isinstance(spec, dict) and spec.get("research_task_id"):
        task_id = str(spec.pop("research_task_id"))[:36]
        exists = db.execute(
            text("SELECT 1 FROM research_task WHERE id = :t"),
            {"t": task_id}).scalar()
        if not exists:
            raise HTTPException(status_code=422,
                                detail="unknown research_task_id")
    try:
        return lab.execute_experiment(
            db, spec, created_by="owner", research_task_id=task_id)
    except lab.LabError as exc:
        db.rollback()
        _map_error(exc)


@router.get("/runs")
def list_runs(
    owner: dict = Depends(require_owner),
    db: Session = Depends(get_session),
    limit: int = Query(default=25, ge=1, le=LIST_CAP),
) -> dict[str, Any]:
    """Recent Lab runs, newest first (bounded). Lab runs are identified by
    the 'lab: ' name prefix written by execute_experiment."""
    rows = list(db.execute(
        select(ResearchRun)
        .where(ResearchRun.name.like("lab: %"))
        .order_by(ResearchRun.created_at.desc(), ResearchRun.run_uid)
        .limit(limit)
    ).scalars())
    out = []
    for r in rows:
        m = r.metrics or {}
        readiness = m.get("promotion_readiness") or {}
        summary = m.get("summary") or {}
        costs = m.get("cost_sensitivity") or {}
        expected = costs.get("expected_cost") or {}
        out.append({
            "run_uid": r.run_uid,
            "name": r.name,
            "status": r.status,
            "engine": r.model_version,
            "data_start": r.data_start.isoformat() if r.data_start else None,
            "data_end": r.data_end.isoformat() if r.data_end else None,
            "n_folds": summary.get("n_folds"),
            "total_resolved": summary.get("total_resolved"),
            "mean_hit_rate": summary.get("mean_hit_rate"),
            "net_mean_30d_expected_cost": expected.get("net_mean_30d"),
            "calibration_reported": any(
                f.get("ece") is not None for f in m.get("folds", [])),
            "verdict": readiness.get("verdict"),
            "reproducibility": (m.get("reproducibility") or {}).get(
                "matches"),
            "warnings": len(m.get("warnings", [])),
            "error_summary": r.error_summary,
            "created_at": r.created_at.isoformat(),
        })
    return {"runs": out, "limit": limit}


@router.get("/runs/{run_uid}")
def get_run(
    run_uid: str,
    owner: dict = Depends(require_owner),
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    row = db.execute(
        select(ResearchRun).where(ResearchRun.run_uid == run_uid[:32])
    ).scalar_one_or_none()
    if row is None or not (row.name or "").startswith("lab: "):
        raise HTTPException(status_code=404)
    out = lab.run_public(row)
    if row.parent_run_id:
        parent = db.get(ResearchRun, row.parent_run_id)
        out["parent_run_uid"] = parent.run_uid if parent else None
    return out


@router.post("/runs/{run_uid}/reproduce", status_code=201)
def reproduce_run(
    run_uid: str,
    owner: dict = Depends(require_owner),
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    """Re-execute the ORIGINAL immutable spec as a NEW run linked via
    parent_run_id; compares metric hashes and records the reproducibility
    outcome on the new run. The original run is never modified."""
    row = db.execute(
        select(ResearchRun).where(ResearchRun.run_uid == run_uid[:32])
    ).scalar_one_or_none()
    if row is None or not (row.name or "").startswith("lab: "):
        raise HTTPException(status_code=404)
    if row.status not in ("completed",):
        raise HTTPException(
            status_code=409,
            detail="only completed runs can be reproduced")
    params = dict(row.parameters or {})
    # strip derived/identity fields; the spec fields remain
    raw = {k: v for k, v in params.items()
           if k in {f.name for f in
                    lab.ExperimentSpec.__dataclass_fields__.values()}}
    try:
        return lab.execute_experiment(
            db, raw, created_by="owner", parent_run_uid=run_uid,
            research_task_id=params.get("research_task_id"))
    except lab.LabError as exc:
        db.rollback()
        _map_error(exc)
