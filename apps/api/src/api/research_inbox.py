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
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, aliased

from apps.api.src.api.admin_guard import require_owner
from apps.api.src.db import get_session
from apps.api.src.db.models import ResearchReport, ResearchTask
from apps.api.src.domain.research_inbox import mission_board
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


class CorrectionBody(BaseModel):
    body: str = Field(min_length=1, max_length=100_000)
    citations: list[dict] | None = None
    # Bounded reason. LIMITATION (documented): research_report has no
    # structured reason column; the reason is echoed in the response and
    # audit-logged (bounded), never hidden inside free-text content.
    # Structured storage arrives with entity linking (migration 121).
    reason: str = Field(min_length=1, max_length=500)
    expires_at: datetime.datetime | None = None


class FollowUpBody(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    question: str = Field(min_length=1, max_length=4000)
    scope: str | None = Field(default=None, max_length=64)


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
    # Wave 2C — resolve source-report versions in ONE bounded query and
    # mark whether that exact version is now superseded (a newer version
    # exists in its chain). Historical follow-ups without a stored source
    # simply carry nulls — never guessed.
    src_ids = [t.source_report_id for t in rows if t.source_report_id]
    src_meta: dict[str, dict] = {}
    if src_ids:
        newer = aliased(ResearchReport)
        for rid, ver, maxv in db.execute(
            select(
                ResearchReport.id,
                ResearchReport.version,
                select(func.max(newer.version))
                .where(newer.task_id == ResearchReport.task_id)
                .correlate(ResearchReport)
                .scalar_subquery(),
            ).where(ResearchReport.id.in_(src_ids))
        ):
            src_meta[rid] = {"version": ver, "max": maxv}
    return {"tasks": [
        {"id": t.id, "title": t.title, "question": t.question,
         "scope": t.scope, "created_at": _iso(t.created_at),
         "status": t.status,
         "follow_up_of_task_id": t.follow_up_of_task_id,
         "source_report_id": t.source_report_id,
         "source_report_version": src_meta.get(
             t.source_report_id, {}).get("version"),
         "source_report_superseded": (
             src_meta[t.source_report_id]["version"]
             < src_meta[t.source_report_id]["max"]
             if t.source_report_id in src_meta else None),
        }
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


@router.post("/reports/{report_id}/correct", status_code=201)
def correct_report(
    report_id: str,
    body: CorrectionBody,
    owner: dict = Depends(require_owner),
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    """Wave 2A — immutable correction. ALWAYS inserts version N+1 via the
    audited service path; the prior row stays byte-identical (service-
    pinned). Review policy follows the EXISTING service contract: the
    correction is authored by the authenticated human owner (provenance
    'human', server-stamped), so it is recorded as approved with the author
    as reviewer — generated content can never ride this path, and Gateway
    agent tokens cannot reach it (session-cookie owner gate). Correcting a
    non-latest (already superseded) version is refused with 409; a
    concurrent-correction race collapses on the DB UNIQUE(task_id, version)
    constraint and the loser receives 409."""
    from loguru import logger
    from sqlalchemy.exc import IntegrityError

    old = db.get(ResearchReport, report_id)
    if old is None:
        raise HTTPException(status_code=404, detail="report not found")
    if inbox_service.report_state(db, old) == "superseded":
        raise HTTPException(
            status_code=409,
            detail="only the latest version of a report can be corrected")
    try:
        r = inbox_service.correct_report(
            db, report_id, new_body=body.body, citations=body.citations,
            provenance="human",
            created_by=owner.get("email") or "owner",
            expires_at=body.expires_at,
        )
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="a concurrent correction created this version first")
    except inbox_service.ResearchInboxError as exc:
        _raise_http(exc)
    # Bounded audit line — reason + identities only, never report content.
    logger.info(
        "inbox_correction report={} new_version={} by={} reason={}",
        report_id, r.version, owner.get("email"), body.reason[:200],
    )
    out = _report_dict(db, r)
    out["correction_reason"] = body.reason
    out["corrects_report_id"] = report_id
    return out


EXECUTION_HISTORY_CAP = 50
_SUMMARY_CLIP = 160


@router.get("/tasks/{task_id}/execution-history")
def execution_history(
    task_id: str,
    owner: dict = Depends(require_owner),
    db: Session = Depends(get_session),
    limit: int = Query(default=EXECUTION_HISTORY_CAP, ge=1,
                       le=EXECUTION_HISTORY_CAP),
) -> dict[str, Any]:
    """Wave 2C — read-only execution provenance for ONE task: gateway jobs
    whose research_task_id links here (migration 121). Owner-only (404
    posture), zero writes, bounded and deterministic (created_at DESC,
    job_uid tiebreak; hard cap + overflow disclosure). Redaction: no
    request_hash, no params payload, no token hash, no created_by, no
    stack traces — summaries are the already-capped columns re-clipped.
    Attempts are numbered oldest=1; 'retry_of' marks any attempt that has
    an earlier attempt on the same task (task linkage, not param
    matching). No cancel action exists on this surface."""
    task = db.get(ResearchTask, task_id)
    if task is None:
        raise HTTPException(status_code=404)
    try:
        rows = db.execute(
            text(
                "SELECT job_uid, job_type, status, token_prefix, "
                "created_at, started_at, finished_at, "
                "result_summary, error_summary "
                "FROM agent_job WHERE research_task_id = :t "
                "ORDER BY created_at DESC, job_uid LIMIT :lim"
            ),
            {"t": task_id, "lim": limit + 1},
        ).mappings().all()
        total = db.execute(
            text("SELECT count(*) FROM agent_job "
                 "WHERE research_task_id = :t"),
            {"t": task_id},
        ).scalar() or 0
    except Exception:  # noqa: BLE001 — gateway store absent (pre-116 envs)
        db.rollback()
        return {"task_id": task_id, "attempts": [], "total": 0,
                "overflow": 0,
                "note": "gateway job store unavailable"}

    shown = rows[:limit]
    n = len(shown)

    def _clip(s: str | None) -> str | None:
        return (s or None) and s[:_SUMMARY_CLIP]

    return {
        "task_id": task_id,
        "total": total,
        "overflow": max(0, total - n),
        "attempts": [
            {
                # newest-first list; attempt numbers count from oldest=1
                "attempt": total - i,
                "job_uid": r["job_uid"],
                "job_type": r["job_type"],
                "status": r["status"],
                "token_prefix": r["token_prefix"],   # public display prefix
                "queued_at": _iso(r["created_at"]),
                "started_at": _iso(r["started_at"]),
                "finished_at": _iso(r["finished_at"]),
                "result_summary": _clip(r["result_summary"]),
                "error_summary": _clip(r["error_summary"]),
                "is_retry": (total - i) > 1,
            }
            for i, r in enumerate(shown)
        ],
    }


@router.get("/mission-board")
def get_mission_board(
    owner: dict = Depends(require_owner),
    db: Session = Depends(get_session),
    column: str | None = Query(
        default=None,
        pattern="^(queued|running|review_needed|delivered|corrected|stale|"
                "failed)$"),
    q: str | None = Query(default=None, max_length=64),
    provenance: str | None = Query(default=None,
                                   pattern="^(generated|human)$"),
    freshness: str | None = Query(default=None,
                                  pattern="^(fresh|aging|stale|unknown)$"),
    per_column: int = Query(default=mission_board.PER_COLUMN_DEFAULT,
                            ge=1, le=mission_board.PER_COLUMN_MAX),
) -> dict[str, Any]:
    """Wave 2B — Research Mission Board. Pure READ aggregation over the
    existing task/report/gateway-job state (mission-board-1 rule set):
    at most four bounded SELECTs, zero writes, zero job launches, no
    report bodies / raw citations / secrets / emails in the payload.
    Route exists only when RESEARCH_INBOX_ENABLED is on (router mount)
    and is owner-gated with the standard 404 posture."""
    return mission_board.build_mission_board(
        db, column=column, q=q, provenance=provenance,
        freshness=freshness, per_column=per_column,
    )


@router.post("/reports/{report_id}/follow-up", status_code=201)
def create_follow_up(
    report_id: str,
    body: FollowUpBody,
    owner: dict = Depends(require_owner),
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    """Wave 2A + 2C — create a follow-up task from a report. The server
    stamps BOTH provenance facts (never client-supplied):
    follow_up_of_task_id = the source report's task, and (migration 121)
    source_report_id = the EXACT report row/version this follow-up came
    from. The composite FK makes a cross-task source structurally
    impossible; the DB trigger makes both immutable after insert.

    VERSION POLICY (pinned): a follow-up may be created from ANY retained
    version — pending, approved, rejected, or superseded (the Inbox UI
    offers "Create follow-up" on every retained card, and asking a new
    question about an old version is legitimate research). The stored link
    names that exact version; surfaces render "from vN (superseded)"
    rather than implying it is current. Never mutates the report; never
    launches any agent job."""
    from loguru import logger

    src = db.get(ResearchReport, report_id)
    if src is None:
        raise HTTPException(status_code=404, detail="report not found")
    try:
        t = inbox_service.create_task(
            db, title=body.title, question=body.question, scope=body.scope,
            schedule_expr=None,
            created_by=owner.get("email") or "owner",
            follow_up_of_task_id=src.task_id,
            source_report_id=src.id,           # server-stamped, exact version
        )
    except inbox_service.ResearchInboxError as exc:
        _raise_http(exc)
    logger.info(
        "inbox_follow_up task={} from_report={} v{} by={}",
        t.id, report_id, src.version, owner.get("email"),
    )
    return {
        "id": t.id, "title": t.title, "question": t.question,
        "scope": t.scope, "follow_up_of_task_id": src.task_id,
        "source_report_id": src.id,             # structured (migration 121)
        "source_report_version": src.version,
    }
