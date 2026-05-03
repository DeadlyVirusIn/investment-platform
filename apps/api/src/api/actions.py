"""Decision UX v1 — action_item API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from apps.api.src.db import get_session
from apps.api.src.domain.actions import repo

router = APIRouter(prefix="/actions", tags=["actions"])

ALLOWED_STATUS = {"pending", "acted", "dismissed", "expired", "blocked"}


@router.get("")
def list_actions(
    status: str = Query("pending", description="pending|acted|dismissed|expired|blocked"),
    limit: int = Query(50, ge=1, le=500),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    if status not in ALLOWED_STATUS:
        raise HTTPException(400, detail=f"invalid status; allowed={sorted(ALLOWED_STATUS)}")
    rows = repo.list_pending(session, status=status, limit=limit)
    return {"actions": rows, "count": len(rows), "status": status}


@router.get("/{action_id}")
def get_action(
    action_id: str, session: Session = Depends(get_session),
) -> dict[str, Any]:
    row = repo.get(session, action_id)
    if row is None:
        raise HTTPException(404, detail="action_not_found")
    return row


@router.post("/{action_id}/act")
def post_act(
    action_id: str, session: Session = Depends(get_session),
) -> dict[str, Any]:
    result = repo.act_on(session, action_id)
    if not result.ok:
        # 404 for not_found, 409 for state conflicts, 422 for exec-layer rejects.
        if result.reason == "action_not_found":
            session.rollback()
            raise HTTPException(404, detail=result.reason)
        if result.reason and (
            result.reason.startswith("exec_rejected")
            or result.reason in {"sizing_below_threshold", "zero_quantity"}
        ):
            session.rollback()
            raise HTTPException(422, detail=result.reason)
        session.rollback()
        raise HTTPException(409, detail=result.reason)
    session.commit()
    return result.payload or {}


@router.post("/{action_id}/dismiss")
def post_dismiss(
    action_id: str,
    body: dict[str, Any] = Body(default_factory=dict),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    reason = str(body.get("reason") or "user_dismiss")[:64]
    result = repo.dismiss(session, action_id, reason=reason)
    if not result.ok:
        if result.reason == "action_not_found":
            session.rollback()
            raise HTTPException(404, detail=result.reason)
        session.rollback()
        raise HTTPException(409, detail=result.reason)
    session.commit()
    return result.payload or {}
