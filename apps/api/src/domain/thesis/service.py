"""Thesis Ledger service — the ONLY mutation path for theses.

Spec: docs/architecture/THESIS_LEDGER_SPEC.md (§3 state machine, §7/§8
provenance + review rules). Invariants enforced here:

* A thesis without a falsifier (`wrong_if`, > 10 chars) is rejected.
* Status changes validate ``ALLOWED_TRANSITIONS`` — no un-invalidating,
  no transition out of ``closed``. A revived idea is a NEW thesis with
  ``supersedes_thesis_id`` set; history is never rewritten.
* EVERY thesis mutation (create + each transition) appends an immutable
  ``ThesisRevision`` row. There is deliberately no update/delete path for
  revisions anywhere in this module.
* Generated evidence is FORCED to ``review_status='pending'`` server-side
  regardless of caller input — the review gate is the prompt-injection
  containment boundary (spec §7).
* Status is NEVER auto-mutated from generated content: approving
  contradicting evidence does not flip a thesis; the owner transitions it
  explicitly (spec NON-GOALS: no auto-transitions).
* No writes to recommendation/paper tables anywhere — link targets are
  existence-checked read-only.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.orm import Session

from apps.api.src.db.models import (
    Thesis,
    ThesisEvidence,
    ThesisLink,
    ThesisRevision,
)

# ---------------------------------------------------------------------------
# vocabulary + state machine (spec §3/§4)
# ---------------------------------------------------------------------------

SCOPES: frozenset[str] = frozenset({"company", "sector", "theme", "macro"})
HORIZONS: frozenset[str] = frozenset({"weeks", "months", "quarters", "years"})
STATUSES: frozenset[str] = frozenset(
    {"forming", "active", "strengthened", "weakened", "invalidated", "closed"}
)
STANCES: frozenset[str] = frozenset({"supports", "contradicts"})
CATEGORIES: frozenset[str] = frozenset(
    {"price_action", "fundamentals", "news", "analyst", "macro", "other"}
)
PROVENANCES: frozenset[str] = frozenset({"generated", "human"})
LINK_TARGET_TYPES: frozenset[str] = frozenset(
    {"recommendation", "paper_trade", "outcome", "lesson"}
)

MIN_WRONG_IF_LEN = 10       # DB CHECK ck_thesis_wrong_if_len: char_length > 10
MAX_SUMMARY_LEN = 1000      # spec §5 API cap

#: spec §3 — the single source of truth for legal moves. ``closed`` is
#: terminal; ``invalidated`` may only be closed (no resurrection).
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "forming": {"active", "closed"},
    "active": {"strengthened", "weakened", "invalidated", "closed"},
    "strengthened": {"active", "weakened", "invalidated", "closed"},
    "weakened": {"active", "strengthened", "invalidated", "closed"},
    "invalidated": {"closed"},
    "closed": set(),
}

#: thesis_link target existence checks (read-only). ``lesson`` maps to a
#: table that does not exist yet (Learning Loop M9) — links of that type
#: are rejected until the table lands.
_LINK_TARGET_TABLES: dict[str, str] = {
    "recommendation": "recommendation",
    "paper_trade": "paper_trade",
    "outcome": "recommendation_outcome",
    "lesson": "lesson",
}


# ---------------------------------------------------------------------------
# errors (mapped to HTTP codes at the router)
# ---------------------------------------------------------------------------

class ThesisError(Exception):
    """Base for thesis-ledger domain errors."""


class FalsifierRequired(ThesisError):
    """Thesis creation without a meaningful `wrong_if` falsifier."""


class InvalidInput(ThesisError):
    """Bad vocabulary / missing required field (422 at the API)."""


class InvalidTransition(ThesisError):
    """Status move not in ALLOWED_TRANSITIONS (409 at the API)."""


class ThesisNotFound(ThesisError):
    pass


class EvidenceNotFound(ThesisError):
    pass


class ReviewStateError(ThesisError):
    """Evidence is not pending — review decisions are one-shot."""


class TargetNotFound(ThesisError):
    """thesis_link target does not exist in its table."""


class DuplicateLink(ThesisError):
    pass


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _clean(value: str | None) -> str:
    return (value or "").strip()


# ---------------------------------------------------------------------------
# revision history — append-only, written on EVERY mutation
# ---------------------------------------------------------------------------

def _append_revision(db: Session, thesis: Thesis, changed_by: str) -> ThesisRevision:
    """Append the next immutable revision row for `thesis`.

    Snapshot captures the user-meaningful mutable surface (statement,
    status, wrong_if, status_reason) as of this mutation. There is NO
    update path for revisions — corrections are new thesis mutations.
    """
    next_no = (
        db.execute(
            select(func.coalesce(func.max(ThesisRevision.revision_no), 0)).where(
                ThesisRevision.thesis_id == thesis.id
            )
        ).scalar_one()
        + 1
    )
    rev = ThesisRevision(
        thesis_id=thesis.id,
        revision_no=next_no,
        snapshot={
            "statement": thesis.statement,
            "status": thesis.status,
            "wrong_if": thesis.wrong_if,
            "status_reason": thesis.status_reason,
        },
        changed_by=changed_by,
    )
    db.add(rev)
    return rev


# ---------------------------------------------------------------------------
# thesis lifecycle
# ---------------------------------------------------------------------------

def create_thesis(
    db: Session,
    *,
    title: str,
    statement: str,
    wrong_if: str,
    scope: str = "company",
    asset_id: str | None = None,
    horizon: str = "months",
    created_by: str = "owner",
    supersedes_thesis_id: str | None = None,
) -> Thesis:
    """Create a thesis in `forming`. The falsifier is mandatory: a belief
    without a stated wrong-if condition is rejected before it exists."""
    title = _clean(title)
    statement = _clean(statement)
    wrong_if = _clean(wrong_if)
    if not title or not statement:
        raise InvalidInput("title and statement are required")
    if len(wrong_if) <= MIN_WRONG_IF_LEN:
        raise FalsifierRequired(
            "a thesis requires a meaningful wrong_if falsifier "
            f"(> {MIN_WRONG_IF_LEN} chars)"
        )
    if scope not in SCOPES:
        raise InvalidInput(f"invalid scope {scope!r}")
    if horizon not in HORIZONS:
        raise InvalidInput(f"invalid horizon {horizon!r}")
    if scope == "company" and not asset_id:
        raise InvalidInput("company-scope theses require asset_id")
    if supersedes_thesis_id:
        superseded = db.get(Thesis, supersedes_thesis_id)
        if superseded is None:
            raise ThesisNotFound(
                f"supersedes_thesis_id {supersedes_thesis_id!r} does not exist"
            )

    thesis = Thesis(
        title=title,
        statement=statement,
        wrong_if=wrong_if,
        scope=scope,
        asset_id=asset_id,
        horizon=horizon,
        status="forming",
        created_by=created_by,
        supersedes_thesis_id=supersedes_thesis_id,
    )
    db.add(thesis)
    db.flush()
    _append_revision(db, thesis, changed_by=created_by)
    db.commit()
    return thesis


def transition_status(
    db: Session,
    thesis_id: str,
    *,
    new_status: str,
    status_reason: str,
    changed_by: str = "owner",
    invalidated_reason: str | None = None,
) -> Thesis:
    """Move a thesis through the §3 state machine.

    Every transition requires a plain-English ``status_reason`` (it is the
    user-visible "What changed since published" line) and appends a
    revision row. Illegal moves raise InvalidTransition — including any
    attempt to leave ``closed`` or to un-invalidate. This function is the
    only status write path; it is never called from generated-content
    pipelines (owner decisions only — spec NON-GOALS)."""
    thesis = db.get(Thesis, thesis_id)
    if thesis is None:
        raise ThesisNotFound(f"thesis {thesis_id!r} does not exist")
    status_reason = _clean(status_reason)
    if not status_reason:
        raise InvalidInput("status_reason is required for every transition")
    if new_status not in STATUSES:
        raise InvalidInput(f"unknown status {new_status!r}")
    allowed = ALLOWED_TRANSITIONS.get(thesis.status, set())
    if new_status not in allowed:
        raise InvalidTransition(
            f"illegal transition {thesis.status!r} -> {new_status!r}; "
            f"allowed from {thesis.status!r}: {sorted(allowed) or 'none (terminal)'}"
        )
    if new_status == "invalidated":
        invalidated_reason = _clean(invalidated_reason)
        if not invalidated_reason:
            raise InvalidInput(
                "invalidated requires invalidated_reason (a met wrong-if "
                "condition or approved contradicting evidence)"
            )
        thesis.invalidated_reason = invalidated_reason

    now = _now()
    if thesis.status == "forming" and new_status == "active":
        thesis.published_at = now
    if new_status == "closed":
        thesis.closed_at = now
    thesis.status = new_status
    thesis.status_reason = status_reason
    thesis.status_changed_at = now
    thesis.updated_at = now
    _append_revision(db, thesis, changed_by=changed_by)
    db.commit()
    return thesis


# ---------------------------------------------------------------------------
# evidence
# ---------------------------------------------------------------------------

def add_evidence(
    db: Session,
    thesis_id: str,
    *,
    stance: str,
    category: str,
    source_name: str,
    summary: str,
    provenance: str,
    source_url: str | None = None,
    published_at: datetime.datetime | None = None,
    weight: Decimal | float | None = None,
    created_by: str = "owner",
    review_status: str | None = None,
) -> ThesisEvidence:
    """Attach evidence to a thesis.

    ``provenance='generated'`` rows are FORCED to ``pending`` no matter
    what ``review_status`` the caller passes — the human review gate is
    the containment boundary for generated content (spec §7.3). Human
    (owner-written) rows are approved on insert with the author as the
    reviewer (spec §8). Never mutates thesis status."""
    thesis = db.get(Thesis, thesis_id)
    if thesis is None:
        raise ThesisNotFound(f"thesis {thesis_id!r} does not exist")
    if stance not in STANCES:
        raise InvalidInput(f"invalid stance {stance!r}")
    if category not in CATEGORIES:
        raise InvalidInput(f"invalid category {category!r}")
    if provenance not in PROVENANCES:
        raise InvalidInput(f"invalid provenance {provenance!r}")
    source_name = _clean(source_name)
    if not source_name:
        raise InvalidInput("source_name is required")
    summary = _clean(summary)
    if not summary:
        raise InvalidInput("summary is required")
    if len(summary) > MAX_SUMMARY_LEN:
        raise InvalidInput(f"summary exceeds {MAX_SUMMARY_LEN} chars")
    if weight is not None and not (0 <= float(weight) <= 1):
        raise InvalidInput("weight must be within [0, 1]")

    if provenance == "generated":
        if not _clean(source_url):
            raise InvalidInput("generated evidence requires source_url")
        # Containment boundary: caller input is ignored, lifecycle starts
        # pending and only approve_evidence/reject_evidence move it.
        effective_status = "pending"
        reviewed_by = None
        reviewed_at = None
    else:  # human — the owner wrote it; author is the reviewer (spec §8)
        effective_status = "approved"
        reviewed_by = created_by
        reviewed_at = _now()

    row = ThesisEvidence(
        thesis_id=thesis.id,
        stance=stance,
        category=category,
        source_name=source_name,
        source_url=_clean(source_url) or None,
        published_at=published_at,
        summary=summary,
        weight=weight,
        provenance=provenance,
        review_status=effective_status,
        reviewed_by=reviewed_by,
        reviewed_at=reviewed_at,
    )
    db.add(row)
    db.commit()
    return row


def _review_evidence(
    db: Session, evidence_id: str, *, reviewer: str, decision: str
) -> ThesisEvidence:
    reviewer = _clean(reviewer)
    if not reviewer:
        raise InvalidInput("reviewer identity is required")
    row = db.get(ThesisEvidence, evidence_id)
    if row is None:
        raise EvidenceNotFound(f"evidence {evidence_id!r} does not exist")
    if row.review_status != "pending":
        raise ReviewStateError(
            f"evidence {evidence_id!r} is already {row.review_status!r}; "
            "review decisions are one-shot (rejected rows are retained, "
            "corrections are new human evidence rows)"
        )
    # Approval never edits content — only the three review fields change.
    row.review_status = decision
    row.reviewed_by = reviewer
    row.reviewed_at = _now()
    db.commit()
    return row


def approve_evidence(db: Session, evidence_id: str, *, reviewer: str) -> ThesisEvidence:
    """Approve a pending row — it becomes user-visible. Never transitions
    the thesis (owner does that explicitly via transition_status)."""
    return _review_evidence(db, evidence_id, reviewer=reviewer, decision="approved")


def reject_evidence(db: Session, evidence_id: str, *, reviewer: str) -> ThesisEvidence:
    """Reject a pending row — retained forever, never shown to users."""
    return _review_evidence(db, evidence_id, reviewer=reviewer, decision="rejected")


# ---------------------------------------------------------------------------
# links
# ---------------------------------------------------------------------------

def link_target(
    db: Session,
    thesis_id: str,
    *,
    target_type: str,
    target_id: str,
    note: str | None = None,
) -> ThesisLink:
    """Attach a recommendation/paper_trade/outcome/lesson to a thesis.

    thesis_link has no hard FK (polymorphic, spec §4) so the target's
    existence is verified here with a read-only SELECT against its table.
    No writes to any target table, ever."""
    thesis = db.get(Thesis, thesis_id)
    if thesis is None:
        raise ThesisNotFound(f"thesis {thesis_id!r} does not exist")
    if target_type not in LINK_TARGET_TYPES:
        raise InvalidInput(f"invalid target_type {target_type!r}")
    target_id = _clean(target_id)
    if not target_id:
        raise InvalidInput("target_id is required")

    table = _LINK_TARGET_TABLES[target_type]
    try:
        exists = db.execute(
            text(f'SELECT 1 FROM "{table}" WHERE id = :tid LIMIT 1'),  # noqa: S608 — table from fixed map
            {"tid": target_id},
        ).scalar()
    except ProgrammingError:
        # Future `lesson` table not present yet — reserved target_type.
        db.rollback()
        raise TargetNotFound(
            f"target table {table!r} does not exist yet"
        ) from None
    if not exists:
        raise TargetNotFound(f"{target_type} {target_id!r} does not exist")

    row = ThesisLink(
        thesis_id=thesis.id,
        target_type=target_type,
        target_id=target_id,
        note=_clean(note) or None,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise DuplicateLink(
            f"thesis {thesis_id!r} already links {target_type} {target_id!r}"
        ) from None
    return row
