"""Learning Loop API — owner-only lesson review workflow (Priority 6).

Mounted ONLY when settings.LEARNING_LOOP_ENABLED is True (fail-closed).
Every route is owner-gated (require_owner, 404 posture) — no public
navigation. The bias posture is enforced in domain/learning/service.py, not
here: proposed lessons are FORCED to review_state='draft' (caller-supplied
review_state is ignored), the hindsight guard containment-checks the
verbatim thesis quote against as-of-decision-time revisions, approval
carries reviewer identity and NEVER mutates thesis status (it may only
attach a thesis_link). No trading or recommendation coupling.
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
from apps.api.src.db.models import Lesson
from apps.api.src.domain.learning import service as learning_service

router = APIRouter(prefix="/admin/lessons", tags=["learning-loop"])


def _raise_http(exc: learning_service.LearningError) -> None:
    if isinstance(exc, (learning_service.LessonNotFound,
                        learning_service.SubjectNotFound)):
        raise HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, learning_service.ReviewStateError):
        raise HTTPException(status_code=409, detail=str(exc))
    # HindsightGuardError / CensoredOutcomeError / InvalidInput / aggregate
    raise HTTPException(status_code=422, detail=str(exc))


def _iso(v: datetime.datetime | None) -> str | None:
    return v.isoformat() if v is not None else None


def _lesson_dict(l: Lesson) -> dict[str, Any]:
    return {
        "id": l.id,
        "recommendation_id": l.recommendation_id,
        "thesis_id": l.thesis_id,
        "paper_trade_id": l.paper_trade_id,
        "outcome_ref": l.outcome_ref,
        "what_happened": l.what_happened,
        "original_thesis_quote": l.original_thesis_quote,
        "expectation": l.expectation,
        "evidence_correct": l.evidence_correct,
        "evidence_misleading": l.evidence_misleading,
        "thesis_effect": l.thesis_effect,
        "calibration_note": l.calibration_note,
        "risk_controls_note": l.risk_controls_note,
        "should_change": l.should_change,
        "provenance": l.provenance,
        "review_state": l.review_state,
        "reviewed_by": l.reviewed_by,
        "reviewed_at": _iso(l.reviewed_at),
        "created_at": _iso(l.created_at),
    }


class LessonProposeBody(BaseModel):
    recommendation_id: str = Field(min_length=1, max_length=36)
    thesis_id: str = Field(min_length=1, max_length=36)
    what_happened: str = Field(min_length=1, max_length=8000)
    original_thesis_quote: str = Field(min_length=1, max_length=8000)
    expectation: str | None = Field(default=None, max_length=8000)
    evidence_correct: list | None = None
    evidence_misleading: list | None = None
    thesis_effect: str = Field(default="none",
                               pattern="^(strengthened|weakened|invalidated|none)$")
    calibration_note: str | None = Field(default=None, max_length=4000)
    risk_controls_note: str | None = Field(default=None, max_length=4000)
    should_change: str | None = Field(default=None, max_length=4000)
    provenance: str = Field(default="generated", pattern="^(generated|human)$")
    paper_trade_id: str | None = Field(default=None, max_length=36)
    outcome_ref: str | None = Field(default=None, max_length=36)
    allow_unresolved_context: bool = False


@router.post("", status_code=201)
def propose_lesson(
    body: LessonProposeBody,
    owner: dict = Depends(require_owner),
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    """Propose a lesson. ALWAYS lands as review_state='draft' — the service
    ignores any attempt to smuggle in an approved row, and the hindsight
    guard rejects quotes that don't exist in as-of-decision-time text."""
    try:
        lesson = learning_service.propose_lesson(
            db,
            recommendation_id=body.recommendation_id,
            thesis_id=body.thesis_id,
            what_happened=body.what_happened,
            original_thesis_quote=body.original_thesis_quote,
            expectation=body.expectation,
            evidence_correct=body.evidence_correct,
            evidence_misleading=body.evidence_misleading,
            thesis_effect=body.thesis_effect,
            calibration_note=body.calibration_note,
            risk_controls_note=body.risk_controls_note,
            should_change=body.should_change,
            provenance=body.provenance,
            paper_trade_id=body.paper_trade_id,
            outcome_ref=body.outcome_ref,
            allow_unresolved_context=body.allow_unresolved_context,
            created_by=owner.get("email") or "owner",
        )
    except learning_service.LearningError as exc:
        _raise_http(exc)
    return _lesson_dict(lesson)


@router.get("")
def list_lessons(
    owner: dict = Depends(require_owner),
    db: Session = Depends(get_session),
    review_state: str | None = Query(default=None,
                                     pattern="^(draft|approved|rejected)$"),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    q = select(Lesson).order_by(Lesson.created_at.desc())
    if review_state:
        q = q.where(Lesson.review_state == review_state)
    rows = list(db.execute(q.limit(limit)).scalars())
    return {"lessons": [_lesson_dict(l) for l in rows]}


@router.post("/{lesson_id}/approve")
def approve_lesson(
    lesson_id: str,
    owner: dict = Depends(require_owner),
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    """Human visibility switch. Never mutates thesis status; only attaches
    a thesis_link(target_type='lesson') in the same transaction."""
    try:
        lesson = learning_service.approve_lesson(
            db, lesson_id, reviewer=owner.get("email") or "owner")
    except learning_service.LearningError as exc:
        _raise_http(exc)
    return _lesson_dict(lesson)


@router.post("/{lesson_id}/reject")
def reject_lesson(
    lesson_id: str,
    owner: dict = Depends(require_owner),
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        lesson = learning_service.reject_lesson(
            db, lesson_id, reviewer=owner.get("email") or "owner")
    except learning_service.LearningError as exc:
        _raise_http(exc)
    return _lesson_dict(lesson)
