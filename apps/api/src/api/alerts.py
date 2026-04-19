"""Alerts API — create, list, evaluate."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from apps.api.src.db import get_session
from apps.api.src.domain.alerts.alert_engine import (
    AlertCreate,
    create_alert,
    evaluate_alerts,
    list_alerts,
)

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("")
def get_alerts(session: Session = Depends(get_session)) -> dict[str, Any]:
    alerts = [a.model_dump(mode="json") for a in list_alerts(session)]
    return {"alerts": alerts, "count": len(alerts)}


@router.post("", status_code=201)
def post_alert(
    payload: AlertCreate,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        out = create_alert(session, payload)
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session.commit()
    return out.model_dump(mode="json")


@router.post("/evaluate")
def run_alert_evaluation(session: Session = Depends(get_session)) -> dict[str, Any]:
    """Evaluate all active alerts once. Returns the list of alerts that fired."""
    fired = evaluate_alerts(session)
    session.commit()
    return {"fired": fired, "count": len(fired)}
