"""Research Inbox API — owner-only review workflow (Elite ArthOS Priority 5).

Mounted ONLY when settings.RESEARCH_INBOX_ENABLED is True (fail-closed).
Every route is owner-gated (require_owner, 404 posture) — the inbox is an
operator surface, never public navigation. State machine is enforced in
domain/research_inbox/service.py: generated reports are FORCED to
review_status='pending' (the router cannot override it — the service ignores
any caller-supplied review_status), approval/rejection carry reviewer
identity, rejected reports are retained forever, staleness is derived at
read time. No trading or recommendation coupling exists in this module.
"""

from __future__ import annotations

import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.src.api.admin_guard import require_owner
from apps.api.src.db import get_session
from apps.api.src.db.models import ResearchReport, ResearchTask
from apps.api.src.domain.research_inbox import service as inbox_service

router = APIRouter(prefix="/admin/inbox", tags=["research-inbox"])


def _raise_http(exc: inbox_service.ResearchInboxError) -> None:
    if isinstance(exc, (inbox_service.TaskNotFound,
                        inbox_service.ReportNotFound)):
        raise HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, inbox_service.ReviewStateError):
        raise HTTPException(status_code=409, detail=str(exc))
    raise HTTPException(status_code=422, detail=str(exc))


def _iso(v: datetime.datetime | None) -> str | None:
    return v.isoformat() if v is not None else None


def _report_dict(db: Session, r: ResearchReport) -> dict[str, Any]:
    return {
        "id": r.id,
        "task_id": r.task_id,
        "version": r.version,
        "body": r.body,
        "citations": r.citations,
        "provenance": r.provenance,
        "review_status": r.review_status,
        "reviewed_by": r.reviewed_by,
        "reviewed_at": _iso(r.reviewed_at),
        "created_at": _iso(r.created_at),
        # fresh | stale | superseded — derived, never stored
        "state": inbox_service.report_state(db, r),
    }


class TaskCreateBody(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    question: str = Field(min_length=1, max_length=4000)
    scope: str | None = Field(default=None, max_length=64)
    schedule_expr: str | None = Field(default=None, max_length=64)


class ReportCreateBody(BaseModel):
    body: str = Field(min_length=1, max_length=100_000)
    citations: list[dict] | None = None
    provenance: str = Field(default="generated", pattern="^(generated|human)$")
    expires_at: datetime.datetime | None = None


class ReviewBody(BaseModel):
    pass  # reviewer identity comes from the owner session, never the body


@router.post("/tasks", status_code=201)
def create_task(
    body: TaskCreateBody,
    owner: dict = Depends(require_owner),
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        t = inbox_service.create_task(
            db, title=body.title, question=body.question, scope=body.scope,
            schedule_expr=body.schedule_expr,
            created_by=owner.get("email") or "owner",
        )
    except inbox_service.ResearchInboxError as exc:
        _raise_http(exc)
    return {"id": t.id, "title": t.title, "question": t.question,
            "scope": t.scope, "schedule_expr": t.schedule_expr}


@router.get("/tasks")
def list_tasks(
    owner: dict = Depends(require_owner),
    db: Session = Depends(get_session),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    rows = list(db.execute(
        select(ResearchTask).order_by(ResearchTask.created_at.desc()).limit(limit)
    ).scalars())
    return {"tasks": [
        {"id": t.id, "title": t.title, "question": t.question,
         "scope": t.scope, "created_at": _iso(t.created_at)}
        for t in rows
    ]}


@router.post("/tasks/{task_id}/reports", status_code=201)
def create_report(
    task_id: str,
    body: ReportCreateBody,
    owner: dict = Depends(require_owner),
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    """Deliver a report version. Generated reports land 'pending' no matter
    what the caller claims (service-forced); human reports are auto-approved
    with the author as reviewer — both server-side decisions."""
    try:
        r = inbox_service.create_report(
            db, task_id, body=body.body, citations=body.citations,
            provenance=body.provenance,
            created_by=owner.get("email") or "owner",
            expires_at=body.expires_at,
        )
    except inbox_service.ResearchInboxError as exc:
        _raise_http(exc)
    return _report_dict(db, r)


@router.get("/reports")
def list_reports(
    owner: dict = Depends(require_owner),
    db: Session = Depends(get_session),
    review_status: str | None = Query(default=None,
                                      pattern="^(pending|approved|rejected)$"),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    q = select(ResearchReport).order_by(ResearchReport.created_at.desc())
    if review_status:
        q = q.where(ResearchReport.review_status == review_status)
    rows = list(db.execute(q.limit(limit)).scalars())
    return {"reports": [_report_dict(db, r) for r in rows]}


@router.post("/reports/{report_id}/approve")
def approve_report(
    report_id: str,
    owner: dict = Depends(require_owner),
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        r = inbox_service.approve_report(
            db, report_id, reviewer=owner.get("email") or "owner")
    except inbox_service.ResearchInboxError as exc:
        _raise_http(exc)
    return _report_dict(db, r)


@router.post("/reports/{report_id}/reject")
def reject_report(
    report_id: str,
    owner: dict = Depends(require_owner),
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        r = inbox_service.reject_report(
            db, report_id, reviewer=owner.get("email") or "owner")
    except inbox_service.ResearchInboxError as exc:
        _raise_http(exc)
    return _report_dict(db, r)
