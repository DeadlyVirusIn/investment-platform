"""V2 promotion-trigger API — Phase 5.

Read-only state / snapshot / gate inspection endpoints + two write
endpoints (approve, rescind) that INSERT into v2_promotion_approval ONLY.

NEVER updates a snapshot row.
NEVER mutates state directly — state advancements happen only in the
next snapshot job run after an approval row is written.
NEVER touches paper_trade_log, decision_log, paper_shadow_log,
engine_b_router, or any execution / routing surface.
NEVER triggers the snapshot job from within the API.

Endpoints:
    GET  /api/v2-promotion/state             current state + latest snapshot
    GET  /api/v2-promotion/snapshots?weeks=N historical snapshots (default 12)
    GET  /api/v2-promotion/gates             gate detail of latest snapshot
    POST /api/v2-promotion/approve           operator approval
    POST /api/v2-promotion/rescind           operator rescission
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from apps.api.src.db import get_session
from apps.api.src.db.models import (
    V2PromotionApproval,
    V2PromotionSnapshot,
)


# ---------------------------------------------------------------------------
# Frozen module constants — operator-action policy
# ---------------------------------------------------------------------------

# Approver allowlist. Hardcoded per design Phase 5 spec.
# Maintained outside this file is out of scope; modifying this list
# requires a code change + design-doc revision-history update.
APPROVER_ALLOWLIST = frozenset({
    "ops@example.com",
    "kunalkhurana1@gmail.com",
})

RATIONALE_MIN_LEN = 20

# Allowed states for each write endpoint. Strict — no fallthrough.
APPROVE_REQUIRES_STATE = "STRONG_CANDIDATE"
RESCIND_REQUIRES_STATE = "APPROVED_FOR_SHADOW_REPLACEMENT"
RESUME_REQUIRES_STATE = "SUSPENDED"

# Phase 9A — approval staleness window in days (mirror of state-machine constant)
APPROVAL_STALENESS_DAYS = 14


router = APIRouter(prefix="/v2-promotion", tags=["v2-promotion-trigger"])


# ---------------------------------------------------------------------------
# Pydantic request bodies
# ---------------------------------------------------------------------------

class ApprovalRequest(BaseModel):
    snapshot_id: int = Field(..., description="ID of the STRONG_CANDIDATE snapshot being approved")
    approver: str = Field(..., min_length=1, description="Operator email; must be in allowlist")
    rationale: str = Field(..., min_length=RATIONALE_MIN_LEN,
                            description=f"Free-text rationale, ≥ {RATIONALE_MIN_LEN} chars")


class RescissionRequest(BaseModel):
    snapshot_id: int = Field(..., description="ID of the APPROVED snapshot being rescinded")
    approver: str = Field(..., min_length=1)
    rationale: str = Field(..., min_length=RATIONALE_MIN_LEN)


class ResumeRequest(BaseModel):
    """Phase 9A — operator action to exit SUSPENDED state."""
    snapshot_id: int = Field(..., description="ID of the SUSPENDED snapshot")
    approver: str = Field(..., min_length=1, description="Allowlisted operator")
    rationale: str = Field(
        ..., min_length=RATIONALE_MIN_LEN,
        description=f"Rationale ≥ {RATIONALE_MIN_LEN} chars explaining why "
                     f"the tail-risk emergency that triggered SUSPENDED is "
                     f"now considered safe to clear",
    )


# ---------------------------------------------------------------------------
# Snapshot serialization helpers
# ---------------------------------------------------------------------------

def _days_until_approval_expiry(
    session: Session,
    snapshot_id: int,
    snapshot_as_of_date: dt.date,
) -> int | None:
    """Compute days remaining on the latest non-rescinded APPROVE row.

    Returns None if no fresh APPROVE exists. Negative values mean already
    expired. Phase 9A — surfaces approval-staleness countdown in /state.
    """
    approvals = session.scalars(
        select(V2PromotionApproval)
        .where(V2PromotionApproval.snapshot_id == snapshot_id)
        .order_by(V2PromotionApproval.approved_at.desc())
    ).all()
    if not approvals:
        return None
    rescinded = any(a.decision == "RESCIND" for a in approvals)
    if rescinded:
        return None
    approve_row = next(
        (a for a in approvals if a.decision == "APPROVE"), None,
    )
    if approve_row is None:
        return None
    cutoff = dt.datetime(
        snapshot_as_of_date.year,
        snapshot_as_of_date.month,
        snapshot_as_of_date.day,
        tzinfo=dt.timezone.utc,
    )
    age_days = (cutoff - approve_row.approved_at.astimezone(dt.timezone.utc)).days
    return APPROVAL_STALENESS_DAYS - age_days


def _snapshot_summary(
    snap: V2PromotionSnapshot,
    *,
    days_until_expiry: int | None = None,
) -> dict[str, Any]:
    bundle = snap.comparison_bundle_json or {}
    verdict_block = (bundle.get("verdict") or {}) if isinstance(bundle, dict) else {}
    metrics_block = (bundle.get("metrics") or {}) if isinstance(bundle, dict) else {}
    out = {
        "snapshot_id": snap.id,
        "as_of_date": snap.as_of_date.isoformat(),
        "iso_year": snap.iso_year,
        "iso_week": snap.iso_week,
        "state": snap.state,
        "prior_state": snap.prior_state,
        "promotion_confidence": float(snap.promotion_confidence),
        "verdict_streak": snap.verdict_streak,
        "readiness_streak": snap.readiness_streak,
        "rollback_reason": snap.rollback_reason,
        "comparison_verdict": verdict_block.get("verdict"),
        "comparison_readiness": verdict_block.get("readiness"),
        "comparison_confidence": verdict_block.get("confidence"),
        "tail_guard_triggered": bool(verdict_block.get("tail_guard_triggered")),
        "n_divergent_days": metrics_block.get("n_divergent_days"),
        "edge_bps": metrics_block.get("avg_return_diff_1d_bps"),
        "impact_weighted_edge": metrics_block.get("impact_weighted_edge"),
        "comparison_fetch_ok": bool(
            (snap.gates_json or {}).get("comparison_fetch_ok", True)
        ),
        "created_at": snap.created_at.isoformat(),
        # Phase 9A — governance-hardening metadata
        "snapshot_content_hash": snap.snapshot_content_hash,
        "schema_version": snap.schema_version,
        "code_version": snap.code_version,
        "evaluated_at_utc": (
            snap.evaluated_at_utc.isoformat()
            if snap.evaluated_at_utc else None
        ),
        "timezone": snap.timezone,
        "days_until_approval_expiry": days_until_expiry,
        "approval_expiry_warning": (
            days_until_expiry is not None and days_until_expiry <= 4
        ),
    }
    return out


def _gate_passing_map(snap: V2PromotionSnapshot) -> dict[str, bool]:
    gates = (snap.gates_json or {}).get("gates", {})
    return {name: bool(g.get("passed")) for name, g in gates.items()}


def _latest_snapshot(session: Session) -> V2PromotionSnapshot | None:
    return session.scalar(
        select(V2PromotionSnapshot)
        .order_by(desc(V2PromotionSnapshot.as_of_date),
                  desc(V2PromotionSnapshot.id))
        .limit(1)
    )


def _approvals_for_snapshot(
    session: Session, snapshot_id: int,
) -> list[V2PromotionApproval]:
    return list(session.scalars(
        select(V2PromotionApproval)
        .where(V2PromotionApproval.snapshot_id == snapshot_id)
        .order_by(V2PromotionApproval.approved_at.asc())
    ).all())


def _approval_to_dict(a: V2PromotionApproval) -> dict[str, Any]:
    return {
        "id": a.id,
        "snapshot_id": a.snapshot_id,
        "decision": a.decision,
        "approver": a.approver,
        "rationale": a.rationale,
        "approved_at": a.approved_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# READ endpoints
# ---------------------------------------------------------------------------

@router.get("/state")
def get_state(
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Latest snapshot summary + approval history. Read-only."""
    snap = _latest_snapshot(session)
    if snap is None:
        return {
            "snapshot": None,
            "approvals": [],
            "approver_allowlist_size": len(APPROVER_ALLOWLIST),
            "note": "No snapshots yet — snapshot job has not run.",
        }
    approvals = _approvals_for_snapshot(session, snap.id)
    days_until_expiry = _days_until_approval_expiry(
        session, snap.id, snap.as_of_date,
    )
    return {
        "snapshot": _snapshot_summary(snap, days_until_expiry=days_until_expiry),
        "approvals": [_approval_to_dict(a) for a in approvals],
        "gates_passing": _gate_passing_map(snap),
        "approver_allowlist_size": len(APPROVER_ALLOWLIST),
    }


@router.get("/snapshots")
def get_snapshots(
    weeks: int = Query(12, ge=1, le=104,
                          description="Number of trailing snapshots to return (default 12)"),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Trailing N snapshot summaries (newest-first). Read-only.

    `weeks` is interpreted as 'last N snapshots' (one snapshot per ISO
    week by design). Capped at 104 (~2 years) to bound payload.
    """
    rows = list(session.scalars(
        select(V2PromotionSnapshot)
        .order_by(desc(V2PromotionSnapshot.as_of_date),
                  desc(V2PromotionSnapshot.id))
        .limit(weeks)
    ).all())
    return {
        "weeks_requested": weeks,
        "n_returned": len(rows),
        "snapshots": [_snapshot_summary(r) for r in rows],
    }


@router.get("/gates")
def get_gates(
    snapshot_id: int | None = Query(
        None, description="Optional — defaults to latest snapshot",
    ),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Gate detail for a snapshot. Read-only.

    Returns the full gates_json (per-gate name, passed, reason, details)
    plus the confidence breakdown + decision notes that were stored at
    snapshot time.
    """
    if snapshot_id is None:
        snap = _latest_snapshot(session)
    else:
        snap = session.get(V2PromotionSnapshot, snapshot_id)
    if snap is None:
        raise HTTPException(status_code=404, detail="snapshot not found")
    gates_json = snap.gates_json or {}
    return {
        "snapshot_id": snap.id,
        "as_of_date": snap.as_of_date.isoformat(),
        "iso_year": snap.iso_year,
        "iso_week": snap.iso_week,
        "state": snap.state,
        "promotion_confidence": float(snap.promotion_confidence),
        "gates": gates_json.get("gates", {}),
        "confidence_breakdown": gates_json.get("confidence_breakdown", {}),
        "decision": gates_json.get("decision", {}),
        "streaks": gates_json.get("streaks", {}),
        "comparison_fetch_ok": bool(gates_json.get("comparison_fetch_ok", True)),
    }


# ---------------------------------------------------------------------------
# WRITE endpoints — approval / rescission ONLY (INSERT into
# v2_promotion_approval). NO snapshot mutation.
# ---------------------------------------------------------------------------

def _validate_approver(approver: str) -> str:
    a = (approver or "").strip().lower()
    if not a:
        raise HTTPException(status_code=400, detail="approver is required")
    if a not in {x.lower() for x in APPROVER_ALLOWLIST}:
        raise HTTPException(
            status_code=403,
            detail="approver not in allowlist",
        )
    # Return canonical form from allowlist (preserve original casing from list)
    canon = next((x for x in APPROVER_ALLOWLIST if x.lower() == a), approver)
    return canon


def _validate_rationale(rationale: str) -> str:
    r = (rationale or "").strip()
    if len(r) < RATIONALE_MIN_LEN:
        raise HTTPException(
            status_code=400,
            detail=f"rationale must be ≥ {RATIONALE_MIN_LEN} chars after trim",
        )
    return r


def _check_no_existing_decision(
    session: Session,
    snapshot_id: int,
    decision: str,
) -> None:
    """Idempotency guard: skip duplicate decision for same snapshot."""
    existing = session.scalar(
        select(V2PromotionApproval).where(
            V2PromotionApproval.snapshot_id == snapshot_id,
            V2PromotionApproval.decision == decision,
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"snapshot {snapshot_id} already has a {decision} decision",
        )


@router.post("/approve")
def post_approve(
    body: ApprovalRequest,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Operator approves a STRONG_CANDIDATE snapshot.

    Constraints:
      * Latest snapshot's state must equal STRONG_CANDIDATE.
      * `snapshot_id` in the body must equal the latest snapshot id.
      * `approver` must be in APPROVER_ALLOWLIST (case-insensitive).
      * `rationale` must be ≥ 20 chars after trim.
      * Snapshot must not already carry an APPROVE decision (idempotency).

    Side effects: INSERT one row into v2_promotion_approval. NO state
    update. The state advancement to APPROVED_FOR_SHADOW_REPLACEMENT
    occurs in the NEXT snapshot job run.
    """
    approver = _validate_approver(body.approver)
    rationale = _validate_rationale(body.rationale)

    latest = _latest_snapshot(session)
    if latest is None:
        raise HTTPException(status_code=404, detail="no snapshot to approve")
    if body.snapshot_id != latest.id:
        raise HTTPException(
            status_code=409,
            detail=(
                f"snapshot_id mismatch: body={body.snapshot_id}, "
                f"latest={latest.id} — approval must reference the latest snapshot"
            ),
        )
    if latest.state != APPROVE_REQUIRES_STATE:
        raise HTTPException(
            status_code=409,
            detail=(
                f"approval requires state={APPROVE_REQUIRES_STATE}; "
                f"latest snapshot state={latest.state}"
            ),
        )
    _check_no_existing_decision(session, latest.id, "APPROVE")

    approval = V2PromotionApproval(
        snapshot_id=latest.id,
        decision="APPROVE",
        approver=approver,
        rationale=rationale,
        snapshot_content_hash_at_approval=latest.snapshot_content_hash,
    )
    session.add(approval)
    session.commit()
    session.refresh(approval)

    return {
        "status": "inserted",
        "approval": _approval_to_dict(approval),
        "snapshot_id": latest.id,
        "snapshot_state_at_approval": latest.state,
        "snapshot_content_hash": latest.snapshot_content_hash,
        "note": (
            "State advancement to APPROVED_FOR_SHADOW_REPLACEMENT happens "
            "in the next snapshot job run, not via this endpoint. If the "
            "snapshot is recomputed (content hash changes), this approval "
            "is automatically invalidated by the snapshot job."
        ),
    }


@router.post("/rescind")
def post_rescind(
    body: RescissionRequest,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Operator rescinds approval of a previously-APPROVED snapshot.

    Constraints:
      * Latest snapshot's state must equal APPROVED_FOR_SHADOW_REPLACEMENT.
      * `snapshot_id` must reference the snapshot that was originally
        approved (i.e. it has a pre-existing APPROVE row).
      * Approver must be in allowlist; rationale ≥ 20 chars.
      * Snapshot must not already carry a RESCIND decision.
    """
    approver = _validate_approver(body.approver)
    rationale = _validate_rationale(body.rationale)

    latest = _latest_snapshot(session)
    if latest is None:
        raise HTTPException(status_code=404, detail="no snapshot to rescind")
    if latest.state != RESCIND_REQUIRES_STATE:
        raise HTTPException(
            status_code=409,
            detail=(
                f"rescission requires state={RESCIND_REQUIRES_STATE}; "
                f"latest snapshot state={latest.state}"
            ),
        )

    target = session.get(V2PromotionSnapshot, body.snapshot_id)
    if target is None:
        raise HTTPException(
            status_code=404,
            detail=f"snapshot {body.snapshot_id} not found",
        )

    # The rescinded snapshot must already have an APPROVE row
    has_approve = session.scalar(
        select(V2PromotionApproval).where(
            V2PromotionApproval.snapshot_id == target.id,
            V2PromotionApproval.decision == "APPROVE",
        )
    )
    if has_approve is None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"snapshot {target.id} has no prior APPROVE decision; "
                "cannot rescind"
            ),
        )
    _check_no_existing_decision(session, target.id, "RESCIND")

    rescission = V2PromotionApproval(
        snapshot_id=target.id,
        decision="RESCIND",
        approver=approver,
        rationale=rationale,
        snapshot_content_hash_at_approval=target.snapshot_content_hash,
    )
    session.add(rescission)
    session.commit()
    session.refresh(rescission)

    return {
        "status": "inserted",
        "rescission": _approval_to_dict(rescission),
        "rescinded_snapshot_id": target.id,
        "latest_snapshot_state": latest.state,
        "note": (
            "State downgrade from APPROVED_FOR_SHADOW_REPLACEMENT happens "
            "in the next snapshot job run, not via this endpoint."
        ),
    }


@router.post("/resume-from-suspended")
def post_resume_from_suspended(
    body: ResumeRequest,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Phase 9A — operator action to exit SUSPENDED.

    Constraints:
      * Latest snapshot's state must equal SUSPENDED.
      * `snapshot_id` must equal the latest snapshot id (cannot resume
        a stale SUSPENDED that has since been re-evaluated).
      * Approver must be in allowlist; rationale ≥ 20 chars.
      * Snapshot must not already carry a RESUME_FROM_SUSPENDED row.

    Side effects: INSERT one row into v2_promotion_approval with
    `decision='RESUME_FROM_SUSPENDED'`. State exit happens on the NEXT
    snapshot job run; that run re-evaluates from NOT_READY (no streak
    accumulation across SUSPENDED).
    """
    approver = _validate_approver(body.approver)
    rationale = _validate_rationale(body.rationale)

    latest = _latest_snapshot(session)
    if latest is None:
        raise HTTPException(status_code=404, detail="no snapshot to resume")
    if body.snapshot_id != latest.id:
        raise HTTPException(
            status_code=409,
            detail=(
                f"snapshot_id mismatch: body={body.snapshot_id}, "
                f"latest={latest.id}"
            ),
        )
    if latest.state != RESUME_REQUIRES_STATE:
        raise HTTPException(
            status_code=409,
            detail=(
                f"resume requires state={RESUME_REQUIRES_STATE}; "
                f"latest snapshot state={latest.state}"
            ),
        )
    _check_no_existing_decision(session, latest.id, "RESUME_FROM_SUSPENDED")

    resume_row = V2PromotionApproval(
        snapshot_id=latest.id,
        decision="RESUME_FROM_SUSPENDED",
        approver=approver,
        rationale=rationale,
        snapshot_content_hash_at_approval=latest.snapshot_content_hash,
    )
    session.add(resume_row)
    session.commit()
    session.refresh(resume_row)
    return {
        "status": "inserted",
        "resume": _approval_to_dict(resume_row),
        "snapshot_id": latest.id,
        "snapshot_state_at_resume_request": latest.state,
        "note": (
            "Operator RESUME_FROM_SUSPENDED recorded. The state machine "
            "will re-evaluate from NOT_READY on the next snapshot job run. "
            "Streaks remain reset; evidence rebuilds from scratch."
        ),
    }
