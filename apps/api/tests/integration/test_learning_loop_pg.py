"""Learning Loop (migration 113) — service invariants + shape safety.

Pins (spec docs/architecture/LEARNING_LOOP_SPEC.md, Priority-6 slice):
  * HINDSIGHT GUARD — original_thesis_quote must be a VERBATIM substring
    of a thesis_revision snapshot at-or-before the recommendation's
    generated_at; paraphrase and post-decision revision text are rejected;
  * generated lessons FORCED to review_state='draft' — caller input is
    ignored (containment boundary, thesis-evidence precedent);
  * approve/reject require reviewer identity and are one-shot;
  * NO AUTOMATIC THESIS MUTATION — approving a lesson leaves the thesis
    row byte-identical (row_to_json compare) and appends no revision;
  * approval's only side effect is a thesis_link(target_type='lesson')
    row; rejection attaches nothing;
  * aggregate_guard — n=29 raises, n=30 passes (spec §4.4 N_MIN_AGG);
  * censored outcomes (barrier_label IS NULL) are refused unless
    allow_unresolved_context=True, which stores thesis_effect='none' ONLY.

CHECK-dependent asserts detect missing constraints (create_all vs
migration drift) and skip honestly instead of vacuously passing
(thesis-ledger precedent). ORM CHECKs are mirrored in __table_args__ so
create_all enforces them here.
"""

from __future__ import annotations

import datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from apps.api.src.db.models import (
    Asset,
    Lesson,
    Recommendation,
    RecommendationOutcome,
    Thesis,
    ThesisLink,
)
from apps.api.src.domain.learning import service as svc
from apps.api.src.domain.thesis import service as thesis_svc

pytestmark = pytest.mark.integration

UTC = datetime.timezone.utc

STATEMENT = ("ArthOS currently believes NVDA data-center revenue keeps "
             "compounding through 2027 on accelerator demand.")
WRONG_IF = ("Hyperscaler capex guidance is cut in two consecutive quarters.")
QUOTE = "NVDA data-center revenue keeps compounding through 2027"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _asset(db: Session) -> Asset:
    a = Asset(symbol="NVDA", asset_class="equity", exchange="XNAS")
    db.add(a)
    db.commit()
    return a


def _thesis(db: Session, **kw) -> Thesis:
    defaults = dict(
        title="NVDA data-center compounding",
        statement=STATEMENT,
        wrong_if=WRONG_IF,
        scope="theme",
    )
    defaults.update(kw)
    return thesis_svc.create_thesis(db, **defaults)


def _recommendation(db: Session, asset: Asset,
                    generated_at: datetime.datetime | None = None,
                    ) -> Recommendation:
    r = Recommendation(
        asset_id=asset.id,
        action="buy",
        rationale="breakout continuation with earnings-revision support",
        generated_at=generated_at or datetime.datetime.now(UTC),
    )
    db.add(r)
    db.commit()
    return r


def _outcome(db: Session, rec: Recommendation,
             barrier_label: int | None = 1) -> RecommendationOutcome:
    o = RecommendationOutcome(
        recommendation_id=rec.id, barrier_label=barrier_label,
    )
    db.add(o)
    db.commit()
    return o


def _subject(db: Session, *, barrier_label: int | None = 1):
    """thesis + recommendation (decision AFTER thesis revision 1) + outcome."""
    asset = _asset(db)
    t = _thesis(db)
    rec = _recommendation(db, asset)
    out = _outcome(db, rec, barrier_label=barrier_label)
    return t, rec, out


def _propose(db: Session, t: Thesis, rec: Recommendation, **kw) -> Lesson:
    defaults = dict(
        recommendation_id=rec.id,
        thesis_id=t.id,
        what_happened="Price hit the +8% barrier in 11 bars; the position "
                      "closed at take-profit.",
        original_thesis_quote=QUOTE,
        expectation="The thesis expected data-center demand to keep the "
                    "trend intact.",
        thesis_effect="strengthened",
    )
    defaults.update(kw)
    return svc.propose_lesson(db, **defaults)


def _has_check(db: Session, name: str) -> bool:
    """create_all/migration drift guard: CHECK-dependent asserts must skip
    honestly when the named constraint is absent (thesis-ledger precedent)."""
    n = db.execute(text(
        "SELECT count(*) FROM information_schema.check_constraints "
        "WHERE constraint_name = :n"
    ), {"n": name}).scalar()
    return bool(n)


def _thesis_row_json(db: Session, thesis_id: str) -> str:
    return db.execute(text(
        "SELECT row_to_json(t)::text FROM thesis t WHERE id = :i"
    ), {"i": thesis_id}).scalar_one()


# ---------------------------------------------------------------------------
# propose + approve happy path
# ---------------------------------------------------------------------------

def test_propose_and_approve_happy_path(pg_session: Session) -> None:
    t, rec, out = _subject(pg_session)
    lesson = _propose(pg_session, t, rec, outcome_ref=out.id)
    assert lesson.review_state == "draft"
    assert lesson.provenance == "generated"
    assert lesson.original_thesis_quote == QUOTE
    assert lesson.thesis_effect == "strengthened"
    assert lesson.reviewed_by is None and lesson.reviewed_at is None

    approved = svc.approve_lesson(pg_session, lesson.id,
                                  reviewer="owner@arthos")
    assert approved.review_state == "approved"
    assert approved.reviewed_by == "owner@arthos"     # identity recorded
    assert approved.reviewed_at is not None
    # decisions are one-shot
    with pytest.raises(svc.ReviewStateError):
        svc.reject_lesson(pg_session, lesson.id, reviewer="owner@arthos")


def test_subject_existence_checked(pg_session: Session) -> None:
    t, rec, _ = _subject(pg_session)
    missing = "00000000-0000-0000-0000-000000000000"
    with pytest.raises(svc.SubjectNotFound):
        _propose(pg_session, t, rec, recommendation_id=missing)
    with pytest.raises(svc.SubjectNotFound):
        _propose(pg_session, t, rec, thesis_id=missing)
    with pytest.raises(svc.SubjectNotFound):
        _propose(pg_session, t, rec, outcome_ref=missing)
    with pytest.raises(svc.SubjectNotFound):
        _propose(pg_session, t, rec, paper_trade_id=missing)


# ---------------------------------------------------------------------------
# hindsight guard — the load-bearing bias control
# ---------------------------------------------------------------------------

def test_hindsight_guard_accepts_verbatim_and_rejects_paraphrase(
    pg_session: Session,
) -> None:
    t, rec, _ = _subject(pg_session)
    # verbatim substring of revision-1 statement → accepted
    ok = _propose(pg_session, t, rec, original_thesis_quote=QUOTE)
    assert ok.id is not None
    # verbatim substring of wrong_if (also in the snapshot) → accepted
    ok2 = _propose(pg_session, t, rec,
                   original_thesis_quote="capex guidance is cut")
    assert ok2.id is not None
    # paraphrase → rejected
    with pytest.raises(svc.HindsightGuardError):
        _propose(pg_session, t, rec,
                 original_thesis_quote="NVDA datacenter revenue would keep "
                                       "compounding thru 2027")
    # case drift is not verbatim
    with pytest.raises(svc.HindsightGuardError):
        _propose(pg_session, t, rec,
                 original_thesis_quote=QUOTE.upper())
    # empty quote is invalid input, not a guard bypass
    with pytest.raises(svc.InvalidInput):
        _propose(pg_session, t, rec, original_thesis_quote="   ")


def test_hindsight_guard_rejects_post_decision_revision_text(
    pg_session: Session,
) -> None:
    """A revision written AFTER the decision cannot be quoted as 'the
    original thesis' — even though it belongs to the same thesis."""
    asset = _asset(pg_session)
    t = _thesis(pg_session)
    rec = _recommendation(pg_session, asset)            # decision time = now

    post = ("Post-decision reassessment: demand signal was weaker than "
            "the thesis assumed all along.")
    thesis_svc.transition_status(pg_session, t.id, new_status="active",
                                 status_reason=post)    # revision 2, later

    # quoting the post-decision revision text → rejected
    with pytest.raises(svc.HindsightGuardError):
        _propose(pg_session, t, rec, original_thesis_quote=post)
    # the decision-time statement still quotes fine
    ok = _propose(pg_session, t, rec, original_thesis_quote=QUOTE)
    assert ok.id is not None

    # a recommendation older than every revision has nothing to quote
    ancient = _recommendation(
        pg_session, asset,
        generated_at=datetime.datetime(2020, 1, 1, tzinfo=UTC),
    )
    with pytest.raises(svc.HindsightGuardError):
        _propose(pg_session, t, ancient, original_thesis_quote=QUOTE)


# ---------------------------------------------------------------------------
# forced draft + review identity
# ---------------------------------------------------------------------------

def test_generated_lesson_forced_draft(pg_session: Session) -> None:
    t, rec, _ = _subject(pg_session)
    # caller tries to smuggle an approved lesson — forced draft
    lesson = _propose(pg_session, t, rec, review_state="approved")
    assert lesson.review_state == "draft"
    # human-authored lessons also enter the draft→review flow
    human = _propose(pg_session, t, rec, provenance="human",
                     review_state="approved")
    assert human.review_state == "draft"
    # vocabulary enforced
    with pytest.raises(svc.InvalidInput):
        _propose(pg_session, t, rec, provenance="oracle")
    with pytest.raises(svc.InvalidInput):
        _propose(pg_session, t, rec, thesis_effect="proved_right")


def test_review_requires_reviewer_identity(pg_session: Session) -> None:
    t, rec, _ = _subject(pg_session)
    lesson = _propose(pg_session, t, rec)
    with pytest.raises(svc.InvalidInput):
        svc.approve_lesson(pg_session, lesson.id, reviewer="   ")
    with pytest.raises(svc.InvalidInput):
        svc.reject_lesson(pg_session, lesson.id, reviewer="")
    # still a reviewable draft after the rejected attempts
    pg_session.refresh(lesson)
    assert lesson.review_state == "draft"
    rejected = svc.reject_lesson(pg_session, lesson.id, reviewer="owner@arthos")
    assert rejected.review_state == "rejected"
    assert rejected.reviewed_by == "owner@arthos"
    # rejected rows are retained — no delete path
    n = pg_session.execute(text("SELECT count(*) FROM lesson")).scalar()
    assert n == 1


# ---------------------------------------------------------------------------
# no automatic thesis mutation — spec §1 rule 1
# ---------------------------------------------------------------------------

def test_approve_never_mutates_thesis(pg_session: Session) -> None:
    t, rec, out = _subject(pg_session)
    lesson = _propose(pg_session, t, rec, outcome_ref=out.id)

    before = _thesis_row_json(pg_session, t.id)
    revs_before = pg_session.execute(text(
        "SELECT count(*) FROM thesis_revision WHERE thesis_id = :i"
    ), {"i": t.id}).scalar()

    svc.approve_lesson(pg_session, lesson.id, reviewer="owner@arthos")

    # THE pin: thesis row is byte-identical — approval stamped nothing on
    # it (status, status_reason, updated_at, everything unchanged)
    after = _thesis_row_json(pg_session, t.id)
    assert after == before
    revs_after = pg_session.execute(text(
        "SELECT count(*) FROM thesis_revision WHERE thesis_id = :i"
    ), {"i": t.id}).scalar()
    assert revs_after == revs_before   # no revision appended either
    pg_session.refresh(t)
    assert t.status == "forming"       # untouched


def test_thesis_link_created_on_approve_only(pg_session: Session) -> None:
    t, rec, _ = _subject(pg_session)
    approved = _propose(pg_session, t, rec)
    rejected = _propose(pg_session, t, rec)

    svc.approve_lesson(pg_session, approved.id, reviewer="owner@arthos")
    svc.reject_lesson(pg_session, rejected.id, reviewer="owner@arthos")

    links = pg_session.execute(
        text("SELECT target_type, target_id FROM thesis_link "
             "WHERE thesis_id = :i"), {"i": t.id}
    ).all()
    assert links == [("lesson", approved.id)]   # approve links; reject doesn't
    # and the ORM row agrees
    link = pg_session.query(ThesisLink).filter_by(
        target_type="lesson", target_id=approved.id).one()
    assert link.thesis_id == t.id


# ---------------------------------------------------------------------------
# aggregate sample floor — spec §4.4
# ---------------------------------------------------------------------------

def test_aggregate_guard_minimum_n() -> None:
    with pytest.raises(svc.AggregateSampleError):
        svc.aggregate_guard(29)
    with pytest.raises(svc.AggregateSampleError):
        svc.aggregate_guard(0)
    assert svc.aggregate_guard(30) == 30      # boundary passes
    assert svc.aggregate_guard(120) == 120
    with pytest.raises(svc.InvalidInput):
        svc.aggregate_guard("30")             # type discipline
    assert svc.N_MIN_AGG == 30                # spec §4.4 pin


# ---------------------------------------------------------------------------
# censored outcomes — preserve unresolved
# ---------------------------------------------------------------------------

def test_censored_outcome_refused_then_explicit_context_path(
    pg_session: Session,
) -> None:
    t, rec, unresolved = _subject(pg_session, barrier_label=None)

    # unresolved outcome → refusal by default
    with pytest.raises(svc.CensoredOutcomeError):
        _propose(pg_session, t, rec, outcome_ref=unresolved.id)

    # explicit allow path stores the lesson with thesis_effect='none' ONLY
    # — the caller's directional judgment is discarded
    ctx = _propose(pg_session, t, rec, outcome_ref=unresolved.id,
                   allow_unresolved_context=True,
                   thesis_effect="strengthened")
    assert ctx.thesis_effect == "none"
    assert ctx.review_state == "draft"

    # a resolved outcome keeps the caller's directional effect
    asset2 = Asset(symbol="TSM", asset_class="equity", exchange="XNYS")
    pg_session.add(asset2)
    pg_session.commit()
    rec2 = _recommendation(pg_session, asset2)
    resolved = _outcome(pg_session, rec2, barrier_label=-1)
    ok = _propose(pg_session, t, rec2, outcome_ref=resolved.id,
                  thesis_effect="weakened")
    assert ok.thesis_effect == "weakened"

    # outcome_ref must belong to the recommendation being judged
    with pytest.raises(svc.InvalidInput):
        _propose(pg_session, t, rec, outcome_ref=resolved.id)


# ---------------------------------------------------------------------------
# DB-layer CHECKs — honest-skip pattern (create_all vs migration drift)
# ---------------------------------------------------------------------------

def test_effect_check_db_layer(pg_session: Session) -> None:
    if not _has_check(pg_session, "ck_lesson_effect"):
        pytest.skip("schema lacks ck_lesson_effect — verified on the "
                    "alembic-built DB")
    pg_session.add(Lesson(what_happened="x", original_thesis_quote="q",
                          thesis_effect="proved_right", provenance="human"))
    with pytest.raises(IntegrityError):
        pg_session.commit()
    pg_session.rollback()


def test_provenance_check_db_layer(pg_session: Session) -> None:
    if not _has_check(pg_session, "ck_lesson_provenance"):
        pytest.skip("schema lacks ck_lesson_provenance — verified on the "
                    "alembic-built DB")
    pg_session.add(Lesson(what_happened="x", original_thesis_quote="q",
                          provenance="oracle"))
    with pytest.raises(IntegrityError):
        pg_session.commit()
    pg_session.rollback()


def test_review_state_check_db_layer(pg_session: Session) -> None:
    if not _has_check(pg_session, "ck_lesson_review"):
        pytest.skip("schema lacks ck_lesson_review — verified on the "
                    "alembic-built DB")
    pg_session.add(Lesson(what_happened="x", original_thesis_quote="q",
                          provenance="human", review_state="published"))
    with pytest.raises(IntegrityError):
        pg_session.commit()
    pg_session.rollback()


def test_reviewed_identity_check_db_layer(pg_session: Session) -> None:
    """approved/rejected rows must carry reviewer identity — even a raw
    insert bypassing the service cannot mint an anonymous approval."""
    if not _has_check(pg_session, "ck_lesson_reviewed"):
        pytest.skip("schema lacks ck_lesson_reviewed — verified on the "
                    "alembic-built DB")
    pg_session.add(Lesson(what_happened="x", original_thesis_quote="q",
                          provenance="human", review_state="approved"))
    with pytest.raises(IntegrityError):
        pg_session.commit()
    pg_session.rollback()
