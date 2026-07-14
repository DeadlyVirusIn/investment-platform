"""Learning Loop service — the ONLY mutation path for lessons.

Spec: docs/architecture/LEARNING_LOOP_SPEC.md. Invariants enforced here:

* HINDSIGHT GUARD (§4.1): ``original_thesis_quote`` must be a VERBATIM
  substring of the linked thesis's revision snapshots as-of the
  recommendation's ``generated_at``. Text written after the decision —
  including later thesis revisions — can never be quoted as "the original
  thesis". Mechanically enforced, not requested politely.
* Generated lessons are FORCED to ``review_state='draft'`` regardless of
  caller input (thesis-evidence containment precedent). Approval is a
  human action and requires reviewer identity.
* CENSORED-OUTCOME GUARD: a lesson about an unresolved outcome
  (``recommendation_outcome.barrier_label IS NULL``) is refused, unless
  ``allow_unresolved_context=True`` — and then the lesson is stored with
  ``thesis_effect='none'`` ONLY (no directional judgment before the
  outcome resolves).
* NO AUTOMATIC THESIS MUTATION: approving a lesson NEVER changes thesis
  status (spec §1 rule 1 / NON-GOALS). Approval may only attach a
  ``thesis_link(target_type='lesson')`` row — inserted directly here (the
  thesis service rejects that target type while the table is "reserved";
  this module owns the lesson table, so the link row is written after the
  lesson exists). The thesis owner transitions status separately via the
  thesis service.
* AGGREGATE SAMPLE FLOOR (§4.4): ``aggregate_guard(n)`` raises below
  N_MIN_AGG=30 — any future aggregate-lesson caller must pass through it.
* Review decisions are one-shot; rejected lessons are retained (generator
  quality data), never deleted. No update/delete surface for reviewed
  rows exists in this module.
"""

from __future__ import annotations

import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from apps.api.src.db.models import (
    Lesson,
    PaperTrade,
    Recommendation,
    RecommendationOutcome,
    Thesis,
    ThesisLink,
    ThesisRevision,
)

# ---------------------------------------------------------------------------
# vocabulary + limits (spec §2 / §4.4)
# ---------------------------------------------------------------------------

THESIS_EFFECTS: frozenset[str] = frozenset(
    {"strengthened", "weakened", "invalidated", "none"}
)
PROVENANCES: frozenset[str] = frozenset({"generated", "human"})
REVIEW_STATES: frozenset[str] = frozenset({"draft", "approved", "rejected"})

#: spec §4.4 — minimum resolved outcomes per cohort cell before ANY
#: aggregate lesson may exist. Below this the Wilson interval is so wide
#: that any directional sentence overstates the evidence.
N_MIN_AGG = 30


# ---------------------------------------------------------------------------
# errors (mapped to HTTP codes at a future router)
# ---------------------------------------------------------------------------

class LearningError(Exception):
    """Base for learning-loop domain errors."""


class InvalidInput(LearningError):
    """Bad vocabulary / missing required field (422 at a future API)."""


class LessonNotFound(LearningError):
    pass


class SubjectNotFound(LearningError):
    """A linked recommendation/thesis/trade/outcome does not exist."""


class HindsightGuardError(LearningError):
    """original_thesis_quote is not verbatim decision-time text."""


class CensoredOutcomeError(LearningError):
    """The referenced outcome is unresolved (barrier_label IS NULL)."""


class AggregateSampleError(LearningError):
    """Aggregate claim attempted below the N_MIN_AGG sample floor."""


class ReviewStateError(LearningError):
    """Lesson is not draft — review decisions are one-shot."""


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _clean(value: str | None) -> str:
    return (value or "").strip()


# ---------------------------------------------------------------------------
# aggregate sample floor — spec §4.4
# ---------------------------------------------------------------------------

def aggregate_guard(n: int) -> int:
    """Gate for ANY future aggregate-lesson caller. Raises below N_MIN_AGG.

    Returns n unchanged when the cohort is large enough, so callers can
    write ``n = aggregate_guard(len(cohort))`` inline."""
    if not isinstance(n, int) or isinstance(n, bool):
        raise InvalidInput(f"aggregate sample size must be an int, got {n!r}")
    if n < N_MIN_AGG:
        raise AggregateSampleError(
            f"aggregate lessons require n >= {N_MIN_AGG} resolved outcomes "
            f"per cohort cell; got n={n}. Cells below minimum produce NO "
            "aggregate lesson at all — not a hedged one (spec §4.4)."
        )
    return n


# ---------------------------------------------------------------------------
# hindsight guard — spec §4.1
# ---------------------------------------------------------------------------

def _decision_time_texts(
    db: Session, thesis_id: str, as_of: datetime.datetime
) -> list[str]:
    """All thesis_revision snapshot texts at-or-before the decision time.

    The snapshot captures {statement, status, wrong_if, status_reason} —
    the quotable text surface is the three free-text fields."""
    rows = (
        db.execute(
            select(ThesisRevision)
            .where(
                ThesisRevision.thesis_id == thesis_id,
                ThesisRevision.changed_at <= as_of,
            )
            .order_by(ThesisRevision.revision_no)
        )
        .scalars()
        .all()
    )
    texts: list[str] = []
    for rev in rows:
        snap = rev.snapshot or {}
        for field in ("statement", "wrong_if", "status_reason"):
            value = snap.get(field)
            if value:
                texts.append(str(value))
    return texts


def _enforce_hindsight_guard(
    db: Session, *, thesis_id: str, quote: str, decision_time: datetime.datetime
) -> None:
    """Reject any quote that is not a verbatim substring of decision-time
    thesis text. Paraphrase, case drift, and post-decision revisions all
    fail — 'the thesis was obviously wrong' is unwritable unless the
    stored original text supports it (spec §4.1)."""
    texts = _decision_time_texts(db, thesis_id, decision_time)
    if not texts:
        raise HindsightGuardError(
            f"thesis {thesis_id!r} has no revision at or before the "
            f"decision time {decision_time.isoformat()} — nothing existed "
            "to quote"
        )
    if not any(quote in t for t in texts):
        raise HindsightGuardError(
            "original_thesis_quote is not a verbatim substring of any "
            "thesis revision at or before the decision time "
            f"({decision_time.isoformat()}). Lessons may only quote what "
            "the thesis actually said before the outcome was known."
        )


# ---------------------------------------------------------------------------
# propose — the only insert path
# ---------------------------------------------------------------------------

def propose_lesson(
    db: Session,
    *,
    recommendation_id: str,
    thesis_id: str,
    what_happened: str,
    original_thesis_quote: str,
    expectation: str | None = None,
    evidence_correct: list | None = None,
    evidence_misleading: list | None = None,
    thesis_effect: str = "none",
    calibration_note: str | None = None,
    risk_controls_note: str | None = None,
    should_change: str | None = None,
    provenance: str = "generated",
    paper_trade_id: str | None = None,
    outcome_ref: str | None = None,
    allow_unresolved_context: bool = False,
    created_by: str = "owner",
    review_state: str | None = None,  # deliberately IGNORED — forced draft
) -> Lesson:
    """Insert a lesson draft. Every lesson starts ``draft`` — the
    ``review_state`` argument is accepted and ignored so a generator (or a
    prompt-injected payload) cannot smuggle in an approved row.

    Requires recommendation_id + thesis_id: the hindsight guard is
    checked against the thesis's revisions as-of the recommendation's
    ``generated_at``. Columns are nullable at the DB layer only for the
    future aggregate-lesson shape (which must pass ``aggregate_guard``)."""
    what_happened = _clean(what_happened)
    original_thesis_quote = _clean(original_thesis_quote)
    if not what_happened:
        raise InvalidInput("what_happened is required")
    if not original_thesis_quote:
        raise InvalidInput("original_thesis_quote is required (verbatim "
                           "as-of-decision-time text — the hindsight guard)")
    if provenance not in PROVENANCES:
        raise InvalidInput(f"invalid provenance {provenance!r}")
    if thesis_effect not in THESIS_EFFECTS:
        raise InvalidInput(f"invalid thesis_effect {thesis_effect!r}")
    if evidence_correct is not None and not isinstance(evidence_correct, list):
        raise InvalidInput("evidence_correct must be a list")
    if evidence_misleading is not None and not isinstance(
        evidence_misleading, list
    ):
        raise InvalidInput("evidence_misleading must be a list")

    recommendation = db.get(Recommendation, _clean(recommendation_id))
    if recommendation is None:
        raise SubjectNotFound(
            f"recommendation {recommendation_id!r} does not exist"
        )
    thesis = db.get(Thesis, _clean(thesis_id))
    if thesis is None:
        raise SubjectNotFound(f"thesis {thesis_id!r} does not exist")
    if paper_trade_id is not None:
        if db.get(PaperTrade, paper_trade_id) is None:
            raise SubjectNotFound(
                f"paper_trade {paper_trade_id!r} does not exist"
            )

    # -- censored-outcome guard: no directional judgment before resolution
    if outcome_ref is not None:
        outcome = db.get(RecommendationOutcome, outcome_ref)
        if outcome is None:
            raise SubjectNotFound(
                f"recommendation_outcome {outcome_ref!r} does not exist"
            )
        if outcome.recommendation_id != recommendation.id:
            raise InvalidInput(
                f"outcome_ref {outcome_ref!r} belongs to recommendation "
                f"{outcome.recommendation_id!r}, not {recommendation.id!r}"
            )
        if outcome.barrier_label is None:
            if not allow_unresolved_context:
                raise CensoredOutcomeError(
                    f"outcome {outcome_ref!r} is unresolved (barrier_label "
                    "IS NULL) — lessons wait for resolution. Pass "
                    "allow_unresolved_context=True to store context with "
                    "thesis_effect='none' only."
                )
            # unresolved context may never carry a directional judgment
            thesis_effect = "none"

    # -- hindsight guard: quote must be verbatim decision-time text
    _enforce_hindsight_guard(
        db,
        thesis_id=thesis.id,
        quote=original_thesis_quote,
        decision_time=recommendation.generated_at,
    )

    lesson = Lesson(
        recommendation_id=recommendation.id,
        paper_trade_id=paper_trade_id,
        outcome_ref=outcome_ref,
        thesis_id=thesis.id,
        what_happened=what_happened,
        original_thesis_quote=original_thesis_quote,
        expectation=_clean(expectation) or None,
        evidence_correct=evidence_correct or [],
        evidence_misleading=evidence_misleading or [],
        thesis_effect=thesis_effect,
        calibration_note=_clean(calibration_note) or None,
        risk_controls_note=_clean(risk_controls_note) or None,
        should_change=_clean(should_change) or None,
        provenance=provenance,
        review_state="draft",   # forced — caller input ignored
        created_by=created_by,
    )
    db.add(lesson)
    db.commit()
    return lesson


# ---------------------------------------------------------------------------
# review — one-shot, identity-carrying; NEVER mutates the thesis
# ---------------------------------------------------------------------------

def _review_lesson(
    db: Session, lesson_id: str, *, reviewer: str, decision: str
) -> Lesson:
    reviewer = _clean(reviewer)
    if not reviewer:
        raise InvalidInput("reviewer identity is required")
    lesson = db.get(Lesson, lesson_id)
    if lesson is None:
        raise LessonNotFound(f"lesson {lesson_id!r} does not exist")
    if lesson.review_state != "draft":
        raise ReviewStateError(
            f"lesson {lesson_id!r} is already {lesson.review_state!r}; "
            "review decisions are one-shot (rejected rows are retained, "
            "corrections are new lesson rows)"
        )
    # Review never edits lesson content — only the three review fields.
    lesson.review_state = decision
    lesson.reviewed_by = reviewer
    lesson.reviewed_at = _now()
    return lesson


def approve_lesson(db: Session, lesson_id: str, *, reviewer: str) -> Lesson:
    """Approve a draft lesson — the human visibility switch.

    NEVER mutates thesis status, status_reason, or revisions (spec §1
    rule 1 / NON-GOALS: no auto-transitions). The ONLY side effect beyond
    the three review fields is a thesis_link(target_type='lesson') row,
    inserted directly here in the same transaction — the thesis service
    keeps rejecting that target type as reserved, and this module owns
    the lesson table, so the attach happens at the one moment a lesson
    becomes citable. The thesis owner changes thesis status separately
    via the thesis service."""
    lesson = _review_lesson(db, lesson_id, reviewer=reviewer,
                            decision="approved")
    if lesson.thesis_id is not None:
        db.add(ThesisLink(
            thesis_id=lesson.thesis_id,
            target_type="lesson",
            target_id=lesson.id,
            note="attached on lesson approval",
        ))
    try:
        db.commit()
    except IntegrityError:  # pragma: no cover — approve is one-shot
        db.rollback()
        raise LearningError(
            f"thesis {lesson.thesis_id!r} already links lesson {lesson_id!r}"
        ) from None
    return lesson


def reject_lesson(db: Session, lesson_id: str, *, reviewer: str) -> Lesson:
    """Reject a draft lesson — retained forever (generator-quality data),
    never linked to the thesis, never user-visible."""
    lesson = _review_lesson(db, lesson_id, reviewer=reviewer,
                            decision="rejected")
    db.commit()
    return lesson
