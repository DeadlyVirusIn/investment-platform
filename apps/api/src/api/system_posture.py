"""Research Safe Mode — posture API (Wave 1B).

Two routers, both mounted ONLY when settings.SYSTEM_POSTURE_ENABLED:

* public_router — GET /system/posture: the calm, beginner-safe projection.
  NEVER exposes provider details, hostnames, job ids, raw signal JSON,
  stack traces, or owner identity.
* owner_router — /admin/posture/*: evaluate-now, event history, full
  reasons + signal snapshot, incident declare/close, recovery
  acknowledgment. Owner-gated (require_owner, 404 posture). Every action
  runs the SAME deterministic evaluator — nothing here can override a
  derived result.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.api.admin_guard import require_owner
from apps.api.src.db import get_session
from apps.api.src.domain.publication import posture as ps

public_router = APIRouter(prefix="/system", tags=["system-posture"])
owner_router = APIRouter(
    prefix="/admin/posture",
    tags=["system-posture-admin"],
    dependencies=[Depends(require_owner)],
)

_BEGINNER_COPY: dict[str, str] = {
    "NORMAL": "All systems normal. New ideas publish as usual.",
    "RESTRICTED": "Some data is delayed. New ideas may include additional "
                  "limitations.",
    "SAFE": "New ideas are paused while ArthOS checks its data. Your "
            "practice portfolio and existing ideas are still available.",
}


@public_router.get("/posture")
def public_posture(db: Session = Depends(get_session)) -> dict[str, Any]:
    posture, _event_id = ps.current_posture_event(db)
    row = ps.latest_event(db)
    evaluated_at = None
    if row is not None:
        v = row.get("created_at")
        evaluated_at = v.isoformat() if hasattr(v, "isoformat") else v
    return {
        "posture": posture,
        "message": _BEGINNER_COPY[posture],
        "evaluated_at": evaluated_at,
        "new_ideas_paused": posture == "SAFE",
        "existing_ideas_available": True,
        "portfolio_available": True,
    }


def _event_payload(row: dict[str, Any], *, full: bool) -> dict[str, Any]:
    out = {
        "id": row["id"],
        "posture": row["posture"],
        "triggered_by": row["triggered_by"],
        "previous_event_id": row["previous_event_id"],
        "evaluator_version": row["evaluator_version"],
        "evaluator_git_sha": row["evaluator_git_sha"],
        "input_hash": row["input_hash"],
        "acknowledged_by": row["acknowledged_by"],
    }
    for k in ("acknowledged_at", "created_at"):
        v = row.get(k)
        out[k] = v.isoformat() if hasattr(v, "isoformat") else v
    try:
        out["reasons"] = json.loads(row.get("reasons_json") or "[]")
    except (ValueError, TypeError):
        out["reasons"] = []
    if full:
        try:
            out["signal_snapshot"] = json.loads(
                row.get("signal_snapshot_json") or "{}")
        except (ValueError, TypeError):
            out["signal_snapshot"] = {}
    return out


@owner_router.post("/evaluate", status_code=201)
def evaluate_now(
    owner: dict = Depends(require_owner), db: Session = Depends(get_session),
) -> dict[str, Any]:
    row = ps.evaluate_and_record(
        db, triggered_by=f"owner:{owner.get('email') or 'owner'}")
    if not row:
        raise HTTPException(status_code=500, detail="evaluation did not persist")
    ps.reset_cache_for_tests()  # owner asked for NOW — drop the lazy cache
    return _event_payload(row, full=True)


@owner_router.get("/events")
def list_events(
    db: Session = Depends(get_session),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    rows = db.execute(text(
        "SELECT id, posture, reasons_json, signal_snapshot_json, "
        "triggered_by, previous_event_id, evaluator_version, "
        "evaluator_git_sha, input_hash, acknowledged_at, acknowledged_by, "
        "created_at FROM system_posture_event "
        "ORDER BY created_at DESC, id DESC LIMIT :lim"
    ), {"lim": limit}).mappings().all()
    return {"events": [_event_payload(dict(r), full=False) for r in rows],
            "count": len(rows)}


@owner_router.get("/events/{event_id}")
def get_event(
    event_id: str, db: Session = Depends(get_session),
) -> dict[str, Any]:
    row = db.execute(text(
        "SELECT id, posture, reasons_json, signal_snapshot_json, "
        "triggered_by, previous_event_id, evaluator_version, "
        "evaluator_git_sha, input_hash, acknowledged_at, acknowledged_by, "
        "created_at FROM system_posture_event WHERE id = :i"
    ), {"i": event_id}).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="event not found")
    return _event_payload(dict(row), full=True)


class IncidentBody(BaseModel):
    severity: str = Field(pattern="^(restricted|safe)$")
    reason: str = Field(min_length=1, max_length=500)


@owner_router.post("/incident", status_code=201)
def declare_incident(
    body: IncidentBody,
    owner: dict = Depends(require_owner),
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        row = ps.declare_incident(
            db, owner.get("email") or "owner", body.severity, body.reason)
    except ps.PostureActionError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    ps.reset_cache_for_tests()
    return _event_payload(row, full=True)


@owner_router.post("/incident/close")
def close_incident(
    owner: dict = Depends(require_owner), db: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        row = ps.close_incident(db, owner.get("email") or "owner")
    except ps.PostureActionError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    ps.reset_cache_for_tests()
    return _event_payload(row, full=True)


@owner_router.post("/acknowledge")
def acknowledge(
    owner: dict = Depends(require_owner), db: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        row = ps.acknowledge_recovery(db, owner.get("email") or "owner")
    except ps.PostureActionError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    ps.reset_cache_for_tests()
    return _event_payload(row, full=True)
