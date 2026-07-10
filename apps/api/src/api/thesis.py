"""Thesis Ledger API — Elite ArthOS Sprint 6, Priority 2.

NOT mounted yet: the orchestrator wires `router` into main.py behind the
THESIS_LEDGER feature gate. Route split per spec §5:

* Reads (`/theses…`) are public-app surface — theses are global engine
  content. Public payloads are shape-safe: only APPROVED evidence is ever
  serialized, `forming` theses are never serialized, and engine vocabulary
  (stance / provenance / weight / review_status) never appears — evidence
  is mapped into plain `supports` / `against` lists per the spec §6
  five-blocks model.
* Writes (`/admin/…`) are owner-only via require_owner (404 for anonymous
  and non-owner — admin surface stays undiscoverable). Input caps follow
  the feedback.py style. Admin responses may carry engine vocabulary; the
  public read shape may not.

All mutations delegate to domain/thesis/service.py — no status or
recommendation writes here.
"""

from __future__ import annotations

import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from apps.api.src.api.admin_guard import require_owner
from apps.api.src.db import get_session
from apps.api.src.db.models import (
    Thesis,
    ThesisCatalyst,
    ThesisEvidence,
    ThesisLink,
    ThesisRevision,
    ThesisRisk,
)
from apps.api.src.domain.thesis import service as thesis_service

router = APIRouter(tags=["thesis"])

# Beginner status chips (spec §6.1). `forming` is never user-visible.
_STATUS_CHIP = {
    "active": "Watching",
    "strengthened": "Looking stronger",
    "weakened": "Looking shakier",
    "invalidated": "This turned out wrong",
    "closed": "Wrapped up",
}
# Beginner severity copy (spec §6.3)
_SEVERITY_COPY = {"high": "big deal", "medium": "worth watching", "low": "minor"}


def _iso(dt: datetime.datetime | datetime.date | None) -> str | None:
    return dt.isoformat() if dt is not None else None


def _evidence_public(row: ThesisEvidence) -> dict[str, Any]:
    """Public evidence shape — NO stance/provenance/weight/review_status.
    Stance is expressed by which list the item lives in (supports/against)."""
    return {
        "summary": row.summary,
        "source_name": row.source_name,
        "source_url": row.source_url,
        "published_at": _iso(row.published_at),
        "seen_at": _iso(row.observed_at),
    }


def _approved_evidence(db: Session, thesis_id: str, stance: str) -> list[ThesisEvidence]:
    return list(
        db.execute(
            select(ThesisEvidence)
            .where(
                ThesisEvidence.thesis_id == thesis_id,
                ThesisEvidence.review_status == "approved",
                ThesisEvidence.stance == stance,
            )
            .order_by(ThesisEvidence.observed_at.desc())
        ).scalars()
    )


# ---------------------------------------------------------------------------
# reads — public app surface (mounted under /api)
# ---------------------------------------------------------------------------

@router.get("/theses")
def list_theses(
    asset_id: str | None = Query(default=None, max_length=36),
    status: str | None = Query(default=None, max_length=16),
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    """Published theses only — `forming` is never serialized (spec §5)."""
    q = select(Thesis).where(Thesis.status != "forming")
    if asset_id:
        q = q.where(Thesis.asset_id == asset_id)
    if status:
        if status == "forming":
            return {"theses": []}
        q = q.where(Thesis.status == status)
    q = q.order_by(Thesis.published_at.desc().nulls_last(), Thesis.created_at.desc())
    theses = list(db.execute(q).scalars())

    # approved-evidence counts per stance, one grouped query
    counts: dict[tuple[str, str], int] = {}
    if theses:
        rows = db.execute(
            select(
                ThesisEvidence.thesis_id,
                ThesisEvidence.stance,
                func.count(ThesisEvidence.id),
            )
            .where(
                ThesisEvidence.thesis_id.in_([t.id for t in theses]),
                ThesisEvidence.review_status == "approved",
            )
            .group_by(ThesisEvidence.thesis_id, ThesisEvidence.stance)
        ).all()
        counts = {(tid, st): n for tid, st, n in rows}

    return {
        "theses": [
            {
                "id": t.id,
                "title": t.title,
                "statement": t.statement,
                "scope": t.scope,
                "horizon": t.horizon,
                "asset_id": t.asset_id,
                "status": t.status,
                "status_label": _STATUS_CHIP.get(t.status, t.status),
                "published_at": _iso(t.published_at),
                "supports_count": counts.get((t.id, "supports"), 0),
                "against_count": counts.get((t.id, "contradicts"), 0),
            }
            for t in theses
        ]
    }


@router.get("/theses/{thesis_id}")
def get_thesis(thesis_id: str, db: Session = Depends(get_session)) -> dict[str, Any]:
    """Full thesis in the spec §6 five-blocks shape. Pending/rejected
    evidence is NEVER serialized here; forming theses 404."""
    t = db.get(Thesis, thesis_id)
    if t is None or t.status == "forming":
        raise HTTPException(status_code=404)

    supports = _approved_evidence(db, t.id, "supports")
    against = _approved_evidence(db, t.id, "contradicts")
    risks = list(
        db.execute(
            select(ThesisRisk)
            .where(ThesisRisk.thesis_id == t.id)
            .order_by(ThesisRisk.created_at.asc())
        ).scalars()
    )
    catalysts = list(
        db.execute(
            select(ThesisCatalyst)
            .where(ThesisCatalyst.thesis_id == t.id)
            .order_by(ThesisCatalyst.expected_at.asc().nulls_last())
        ).scalars()
    )
    revisions = list(
        db.execute(
            select(ThesisRevision)
            .where(ThesisRevision.thesis_id == t.id)
            .order_by(ThesisRevision.revision_no.desc())
        ).scalars()
    )
    links = list(
        db.execute(
            select(ThesisLink)
            .where(ThesisLink.thesis_id == t.id)
            .order_by(ThesisLink.created_at.asc())
        ).scalars()
    )

    # Block 4 — "What changed since published": one line per transition
    # that carried a reason, newest first (creation row has no reason).
    changes = [
        {
            "date": _iso(r.changed_at),
            "note": (r.snapshot or {}).get("status_reason"),
        }
        for r in revisions
        if (r.snapshot or {}).get("status_reason")
    ]

    graded = t.status in ("invalidated", "closed")
    learned_links = [
        {"type": ln.target_type, "target_id": ln.target_id, "note": ln.note}
        for ln in links
        if ln.target_type in ("outcome", "lesson")
    ]

    return {
        "id": t.id,
        "title": t.title,
        "scope": t.scope,
        "horizon": t.horizon,
        "asset_id": t.asset_id,
        "status": t.status,
        "status_label": _STATUS_CHIP.get(t.status, t.status),
        "published_at": _iso(t.published_at),
        "closed_at": _iso(t.closed_at),
        "superseded_by_new_idea": t.supersedes_thesis_id is not None,
        # 1. What ArthOS currently believes
        "believes": t.statement,
        # 2. What supports this (approved supports, newest first)
        "supports": [_evidence_public(e) for e in supports],
        # 3. What could prove it wrong
        "wrong_if": {
            "condition": t.wrong_if,
            "against": [_evidence_public(e) for e in against],
            "risks": [
                {
                    "title": r.title,
                    "detail": r.detail,
                    "level": _SEVERITY_COPY.get(r.severity, r.severity),
                    "materialized_at": _iso(r.materialized_at),
                }
                for r in risks
            ],
            "turned_out_wrong_because": t.invalidated_reason
            if t.status == "invalidated" else None,
        },
        # watch-fors (catalysts) — plain fields
        "catalysts": [
            {
                "title": c.title,
                "expected_at": _iso(c.expected_at),
                "window_days": c.window_days,
                "direction": c.direction,
                "resolved_at": _iso(c.resolved_at),
                "resolution": c.resolution,
            }
            for c in catalysts
        ],
        # 4. What changed since published
        "changes": changes,
        # 5. What we learned — honest empty state before grading
        "learned": learned_links if graded else [],
        "learned_empty_note": None if (graded and learned_links)
        else "Still playing out — nothing to grade yet.",
    }


# ---------------------------------------------------------------------------
# writes — owner-only (spec §5; mounted under /api, paths carry /admin)
# ---------------------------------------------------------------------------

class ThesisCreateBody(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    statement: str = Field(min_length=1, max_length=5000)
    wrong_if: str = Field(min_length=1, max_length=2000)
    scope: str = Field(default="company", max_length=16)
    horizon: str = Field(default="months", max_length=16)
    asset_id: str | None = Field(default=None, max_length=36)
    supersedes_thesis_id: str | None = Field(default=None, max_length=36)


class ThesisStatusBody(BaseModel):
    status: str = Field(max_length=16)
    status_reason: str = Field(min_length=1, max_length=2000)
    invalidated_reason: str | None = Field(default=None, max_length=2000)


class EvidenceBody(BaseModel):
    stance: str = Field(max_length=16)
    category: str = Field(max_length=16)
    source_name: str = Field(min_length=1, max_length=128)
    source_url: str | None = Field(default=None, max_length=2000)
    summary: str = Field(min_length=1, max_length=1000)
    provenance: str = Field(max_length=16)
    published_at: datetime.datetime | None = None
    weight: float | None = Field(default=None, ge=0, le=1)
    # advisory only — the service forces 'pending' for generated rows
    review_status: str | None = Field(default=None, max_length=16)


class ReviewBody(BaseModel):
    decision: str = Field(max_length=8)   # approve | reject
    note: str | None = Field(default=None, max_length=2000)


class LinkBody(BaseModel):
    target_type: str = Field(max_length=24)
    target_id: str = Field(min_length=1, max_length=36)
    note: str | None = Field(default=None, max_length=2000)


def _raise_http(exc: thesis_service.ThesisError) -> None:
    """Domain error -> HTTP status. 409 for state conflicts, 404 for
    missing rows, 422 for bad input."""
    if isinstance(exc, (thesis_service.InvalidTransition,
                        thesis_service.ReviewStateError,
                        thesis_service.DuplicateLink)):
        raise HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, (thesis_service.ThesisNotFound,
                        thesis_service.EvidenceNotFound,
                        thesis_service.TargetNotFound)):
        raise HTTPException(status_code=404, detail=str(exc))
    # FalsifierRequired / InvalidInput / anything else invalid
    raise HTTPException(status_code=422, detail=str(exc))


def _thesis_admin(t: Thesis) -> dict[str, Any]:
    return {
        "id": t.id,
        "title": t.title,
        "scope": t.scope,
        "asset_id": t.asset_id,
        "horizon": t.horizon,
        "status": t.status,
        "status_reason": t.status_reason,
        "wrong_if": t.wrong_if,
        "supersedes_thesis_id": t.supersedes_thesis_id,
        "published_at": _iso(t.published_at),
        "closed_at": _iso(t.closed_at),
    }


@router.post("/admin/theses", status_code=201)
def admin_create_thesis(
    body: ThesisCreateBody,
    owner: dict = Depends(require_owner),
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        t = thesis_service.create_thesis(
            db,
            title=body.title,
            statement=body.statement,
            wrong_if=body.wrong_if,
            scope=body.scope,
            asset_id=body.asset_id,
            horizon=body.horizon,
            created_by=owner.get("email") or owner.get("id") or "owner",
            supersedes_thesis_id=body.supersedes_thesis_id,
        )
    except thesis_service.ThesisError as exc:
        _raise_http(exc)
    return _thesis_admin(t)


@router.patch("/admin/theses/{thesis_id}/status")
def admin_transition_status(
    thesis_id: str,
    body: ThesisStatusBody,
    owner: dict = Depends(require_owner),
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        t = thesis_service.transition_status(
            db,
            thesis_id,
            new_status=body.status,
            status_reason=body.status_reason,
            changed_by=owner.get("email") or owner.get("id") or "owner",
            invalidated_reason=body.invalidated_reason,
        )
    except thesis_service.ThesisError as exc:
        _raise_http(exc)
    return _thesis_admin(t)


@router.post("/admin/theses/{thesis_id}/evidence", status_code=201)
def admin_add_evidence(
    thesis_id: str,
    body: EvidenceBody,
    owner: dict = Depends(require_owner),
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        row = thesis_service.add_evidence(
            db,
            thesis_id,
            stance=body.stance,
            category=body.category,
            source_name=body.source_name,
            source_url=body.source_url,
            summary=body.summary,
            provenance=body.provenance,
            published_at=body.published_at,
            weight=body.weight,
            created_by=owner.get("email") or owner.get("id") or "owner",
            review_status=body.review_status,
        )
    except thesis_service.ThesisError as exc:
        _raise_http(exc)
    # admin/owner surface — full row incl. review lifecycle is appropriate
    return {
        "id": row.id,
        "thesis_id": row.thesis_id,
        "stance": row.stance,
        "category": row.category,
        "provenance": row.provenance,
        "review_status": row.review_status,
        "source_name": row.source_name,
        "source_url": row.source_url,
    }


@router.post("/admin/evidence/{evidence_id}/review")
def admin_review_evidence(
    evidence_id: str,
    body: ReviewBody,
    owner: dict = Depends(require_owner),
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    reviewer = owner.get("email") or owner.get("id") or "owner"
    try:
        if body.decision == "approve":
            row = thesis_service.approve_evidence(db, evidence_id, reviewer=reviewer)
        elif body.decision == "reject":
            row = thesis_service.reject_evidence(db, evidence_id, reviewer=reviewer)
        else:
            raise HTTPException(status_code=422, detail="decision must be approve|reject")
    except thesis_service.ThesisError as exc:
        _raise_http(exc)
    return {
        "id": row.id,
        "review_status": row.review_status,
        "reviewed_by": row.reviewed_by,
        "reviewed_at": _iso(row.reviewed_at),
    }


@router.post("/admin/theses/{thesis_id}/links", status_code=201)
def admin_link_target(
    thesis_id: str,
    body: LinkBody,
    owner: dict = Depends(require_owner),
    db: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        row = thesis_service.link_target(
            db,
            thesis_id,
            target_type=body.target_type,
            target_id=body.target_id,
            note=body.note,
        )
    except thesis_service.ThesisError as exc:
        _raise_http(exc)
    return {
        "id": row.id,
        "thesis_id": row.thesis_id,
        "target_type": row.target_type,
        "target_id": row.target_id,
    }
