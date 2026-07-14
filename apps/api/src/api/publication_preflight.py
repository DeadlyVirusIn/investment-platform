"""Recommendation Publication Preflight — owner API (Wave 1A).

Mounted ONLY when settings.RECOMMENDATION_PREFLIGHT_ENABLED is True. Every
route is owner-gated (require_owner, 404 posture). These endpoints expose the
FULL verdict record — ordered checks, hashes, provenance — which is exactly
what the public projection must never leak (see ``public_projection`` for the
redaction rule the recommendations API applies).

There is no mutation surface here beyond "evaluate", which appends an
immutable row via the idempotent service path. No route can edit or delete a
verdict.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.api.admin_guard import require_owner
from apps.api.src.db import get_session
from apps.api.src.db.models import Recommendation
from apps.api.src.domain.publication import preflight as pf

router = APIRouter(
    prefix="/admin/preflight",
    tags=["publication-preflight"],
    dependencies=[Depends(require_owner)],
)


def _row_payload(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    for k in ("checks_json", "limitations_json", "blocking_reasons_json"):
        try:
            out[k[:-5]] = json.loads(out.pop(k) or "[]")
        except (ValueError, TypeError):
            out[k[:-5]] = []
    for k in ("evaluated_at", "source_freshness_at", "created_at"):
        v = out.get(k)
        out[k] = v.isoformat() if hasattr(v, "isoformat") else v
    return out


@router.post("/recommendations/{rec_id}/evaluate", status_code=201)
def evaluate_candidate(
    rec_id: str, db: Session = Depends(get_session)
) -> dict[str, Any]:
    rec = db.get(Recommendation, rec_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="recommendation not found")
    row = pf.run_and_persist(db, rec)
    if not row:
        raise HTTPException(status_code=500, detail="evaluation did not persist")
    return _row_payload(row)


@router.get("/recommendations/{rec_id}")
def get_verdict_history(
    rec_id: str,
    db: Session = Depends(get_session),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    rows = db.execute(
        text(
            "SELECT id, recommendation_id, verdict, rule_set_version, "
            "input_hash, checks_json, limitations_json, blocking_reasons_json, "
            "evaluated_at, evaluator_git_sha, source_freshness_at, created_at "
            "FROM recommendation_preflight WHERE recommendation_id = :rid "
            "ORDER BY created_at DESC LIMIT :lim"
        ),
        {"rid": rec_id, "lim": limit},
    ).mappings().all()
    if not rows:
        raise HTTPException(status_code=404, detail="no verdicts recorded")
    return {
        "latest": _row_payload(dict(rows[0])),
        "history": [_row_payload(dict(r)) for r in rows],
        "count": len(rows),
    }


@router.get("/verdicts")
def list_recent_verdicts(
    db: Session = Depends(get_session),
    verdict: str | None = Query(
        default=None,
        pattern="^(READY|READY_WITH_LIMITATIONS|HOLD|BLOCKED)$",
    ),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    q = (
        "SELECT id, recommendation_id, verdict, rule_set_version, input_hash, "
        "checks_json, limitations_json, blocking_reasons_json, evaluated_at, "
        "evaluator_git_sha, source_freshness_at, created_at "
        "FROM recommendation_preflight "
    )
    params: dict[str, Any] = {"lim": limit}
    if verdict:
        q += "WHERE verdict = :v "
        params["v"] = verdict
    q += "ORDER BY created_at DESC LIMIT :lim"
    rows = db.execute(text(q), params).mappings().all()
    return {"verdicts": [_row_payload(dict(r)) for r in rows], "count": len(rows)}


@router.get("/recommendations/{rec_id}/explain")
def explain_failures(
    rec_id: str, db: Session = Depends(get_session)
) -> dict[str, Any]:
    row = pf.latest_verdict(db, rec_id)
    if row is None:
        raise HTTPException(status_code=404, detail="no verdicts recorded")
    payload = _row_payload(row)
    failed = [c for c in payload.get("checks", []) if not c.get("passed")]
    return {
        "recommendation_id": rec_id,
        "verdict": payload["verdict"],
        "rule_set_version": payload["rule_set_version"],
        "failed_checks": failed,
        "evaluated_at": payload["evaluated_at"],
    }


# ---------------------------------------------------------------------------
# Public projection helper — used by the recommendations API, NOT a route.
# ---------------------------------------------------------------------------

def public_projection(row: dict[str, Any]) -> dict[str, Any]:
    """Beginner-safe subset of a verdict row. NEVER include: internal ids,
    hashes, raw checks, provider diagnostics, git shas, or stack traces."""
    try:
        limitations = json.loads(row.get("limitations_json") or "[]")
    except (ValueError, TypeError):
        limitations = []
    texts = [
        c["beginner_text"] for c in limitations
        if isinstance(c, dict) and c.get("beginner_text")
    ]
    eat = row.get("evaluated_at")
    sfa = row.get("source_freshness_at")
    return {
        "verdict": row.get("verdict"),
        "limitations": texts,
        "evaluated_at": eat.isoformat() if hasattr(eat, "isoformat") else eat,
        "freshness_summary": (
            sfa.isoformat() if hasattr(sfa, "isoformat") else sfa
        ),
    }
