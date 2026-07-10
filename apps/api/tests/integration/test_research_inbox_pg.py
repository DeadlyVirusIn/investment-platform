"""Research Inbox (migration 112) — service invariants + shape safety.

Pins (spec docs/architecture/RESEARCH_INBOX_SPEC.md, Priority-5 slice):
  * task creation + follow-up linkage (provenance chain via
    follow_up_of_task_id, RESTRICT at the DB layer);
  * generated reports FORCED to review_status='pending' server-side —
    caller input is ignored (containment boundary);
  * citations are validated before insert: every citation needs a
    non-empty url + parseable observed_at (evidence without provenance
    is rejected);
  * review decisions are one-shot (pending → approved|rejected) and only
    touch the three review fields;
  * IMMUTABILITY — corrections insert version+1 with supersedes link and
    leave the old row BYTE-IDENTICAL (row_to_json compare); the module
    exposes no update/delete path for delivered reports (introspection);
  * UNIQUE(task_id, version) enforced at the DB layer;
  * staleness derived, never stored: fresh | stale (expires_at passed OR
    newest citation observed_at older than N days) | superseded.

CHECK-dependent asserts detect missing constraints (create_all vs
migration drift) and skip honestly instead of vacuously passing
(thesis-ledger precedent). ORM CHECKs are mirrored in __table_args__ so
create_all enforces them here.
"""

from __future__ import annotations

import datetime
import inspect

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from apps.api.src.db.models import ResearchReport, ResearchTask
from apps.api.src.domain.research_inbox import service as svc

pytestmark = pytest.mark.integration

UTC = datetime.timezone.utc


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _task(db: Session, **kw) -> ResearchTask:
    defaults = dict(
        title="Semiconductor capex trajectory",
        question="Is hyperscaler semiconductor capex still accelerating "
                 "quarter over quarter?",
        scope="NVDA,TSM,AVGO",
        schedule_expr="0 13 * * 1",   # DEFINITION ONLY — nothing executes it
    )
    defaults.update(kw)
    return svc.create_task(db, **defaults)


def _citation(days_old: float = 0.0, **kw) -> dict:
    c = {
        "source": "Tiingo news",
        "url": "https://example.com/article",
        "observed_at": (
            datetime.datetime.now(UTC) - datetime.timedelta(days=days_old)
        ).isoformat(),
    }
    c.update(kw)
    return c


def _report(db: Session, task_id: str, **kw) -> ResearchReport:
    defaults = dict(
        body="Capex guidance was raised at 3 of 4 hyperscalers this quarter.",
        citations=[_citation()],
        provenance="generated",
    )
    defaults.update(kw)
    return svc.create_report(db, task_id, **defaults)


def _has_check(db: Session, name: str) -> bool:
    """create_all/migration drift guard: CHECK-dependent asserts must skip
    honestly when the named constraint is absent (thesis-ledger precedent)."""
    n = db.execute(text(
        "SELECT count(*) FROM information_schema.check_constraints "
        "WHERE constraint_name = :n"
    ), {"n": name}).scalar()
    return bool(n)


def _row_json(db: Session, report_id: str) -> str:
    """Full-row snapshot for byte-compare immutability pins."""
    return db.execute(text(
        "SELECT row_to_json(r)::text FROM research_report r WHERE id = :i"
    ), {"i": report_id}).scalar_one()


# ---------------------------------------------------------------------------
# tasks + follow-up linkage
# ---------------------------------------------------------------------------

def test_task_creation_and_follow_up_linkage(pg_session: Session) -> None:
    t = _task(pg_session)
    assert t.status == "open"
    assert t.scope == "NVDA,TSM,AVGO"
    assert t.schedule_expr == "0 13 * * 1"
    assert t.follow_up_of_task_id is None

    follow = _task(
        pg_session,
        title="Capex follow-up: memory suppliers",
        question="Does the capex acceleration extend to memory suppliers?",
        follow_up_of_task_id=t.id,
    )
    assert follow.follow_up_of_task_id == t.id
    assert follow.id != t.id

    # follow-up must point at an existing task
    with pytest.raises(svc.TaskNotFound):
        _task(pg_session,
              follow_up_of_task_id="00000000-0000-0000-0000-000000000000")


def test_task_requires_title_and_question(pg_session: Session) -> None:
    with pytest.raises(svc.InvalidInput):
        _task(pg_session, title="   ")
    with pytest.raises(svc.InvalidInput):
        _task(pg_session, question="")


def test_task_status_check_db_layer(pg_session: Session) -> None:
    if not _has_check(pg_session, "ck_research_task_status"):
        pytest.skip("schema lacks ck_research_task_status — verified on the "
                    "alembic-built DB")
    pg_session.add(ResearchTask(title="t", question="q", status="done"))
    with pytest.raises(IntegrityError):
        pg_session.commit()
    pg_session.rollback()


# ---------------------------------------------------------------------------
# report delivery + review gate
# ---------------------------------------------------------------------------

def test_report_v1_pending_for_generated(pg_session: Session) -> None:
    t = _task(pg_session)
    # caller tries to smuggle an approved generated report — forced pending
    r = _report(pg_session, t.id, review_status="approved")
    assert r.version == 1
    assert r.provenance == "generated"
    assert r.review_status == "pending"
    assert r.reviewed_by is None and r.reviewed_at is None
    assert r.delivered_at is not None
    # unknown task rejected
    with pytest.raises(svc.TaskNotFound):
        _report(pg_session, "00000000-0000-0000-0000-000000000000")


def test_human_report_author_is_reviewer(pg_session: Session) -> None:
    t = _task(pg_session)
    r = _report(pg_session, t.id, provenance="human",
                created_by="owner@arthos")
    assert r.review_status == "approved"
    assert r.reviewed_by == "owner@arthos" and r.reviewed_at is not None


def test_citation_validation(pg_session: Session) -> None:
    t = _task(pg_session)
    # not a list
    with pytest.raises(svc.CitationInvalid):
        _report(pg_session, t.id, citations={"url": "https://x.example"})
    # non-object entry
    with pytest.raises(svc.CitationInvalid):
        _report(pg_session, t.id, citations=["https://x.example"])
    # missing / empty url
    bad = _citation()
    del bad["url"]
    with pytest.raises(svc.CitationInvalid):
        _report(pg_session, t.id, citations=[bad])
    with pytest.raises(svc.CitationInvalid):
        _report(pg_session, t.id, citations=[_citation(url="   ")])
    # missing / unparseable observed_at
    bad = _citation()
    del bad["observed_at"]
    with pytest.raises(svc.CitationInvalid):
        _report(pg_session, t.id, citations=[bad])
    with pytest.raises(svc.CitationInvalid):
        _report(pg_session, t.id, citations=[_citation(observed_at="last week")])
    # nothing was written by the rejected attempts
    n = pg_session.execute(
        text("SELECT count(*) FROM research_report")).scalar()
    assert n == 0

    # valid citations normalize observed_at to ISO and pass through source
    r = _report(pg_session, t.id, citations=[
        _citation(source="Polygon"), _citation(observed_at="2026-07-01T00:00:00Z"),
    ])
    assert len(r.citations) == 2
    assert r.citations[0]["source"] == "Polygon"
    assert r.citations[1]["observed_at"].startswith("2026-07-01T00:00:00")
    for c in r.citations:
        datetime.datetime.fromisoformat(c["observed_at"])  # parseable


def test_review_requires_identity_and_is_one_shot(pg_session: Session) -> None:
    t = _task(pg_session)
    r = _report(pg_session, t.id)
    with pytest.raises(svc.InvalidInput):
        svc.approve_report(pg_session, r.id, reviewer="  ")
    approved = svc.approve_report(pg_session, r.id, reviewer="owner@arthos")
    assert approved.review_status == "approved"
    assert approved.reviewed_by == "owner@arthos"
    assert approved.reviewed_at is not None
    with pytest.raises(svc.ReviewStateError):   # decisions are one-shot
        svc.reject_report(pg_session, r.id, reviewer="owner@arthos")

    r2 = svc.create_report(pg_session, t.id, body="second take",
                           citations=[_citation()])
    rejected = svc.reject_report(pg_session, r2.id, reviewer="owner@arthos")
    assert rejected.review_status == "rejected"
    with pytest.raises(svc.ReviewStateError):
        svc.approve_report(pg_session, r2.id, reviewer="owner@arthos")
    # rejected rows are retained — no delete path
    n = pg_session.execute(
        text("SELECT count(*) FROM research_report")).scalar()
    assert n == 2


# ---------------------------------------------------------------------------
# immutability: corrections are versions, old rows never change
# ---------------------------------------------------------------------------

def test_correction_creates_v2_and_v1_unchanged(pg_session: Session) -> None:
    t = _task(pg_session)
    v1 = _report(pg_session, t.id)
    svc.approve_report(pg_session, v1.id, reviewer="owner@arthos")
    before = _row_json(pg_session, v1.id)

    v2 = svc.correct_report(
        pg_session, v1.id,
        new_body="Correction: only 2 of 4 hyperscalers raised guidance.",
        provenance="human", created_by="owner@arthos",
    )
    assert v2.version == 2
    assert v2.task_id == t.id
    assert v2.supersedes_report_id == v1.id
    # citations carried forward when not replaced
    assert v2.citations == v1.citations

    # THE pin: v1 is byte-identical — correction stamped nothing on it
    after = _row_json(pg_session, v1.id)
    assert after == before

    # correcting a nonexistent report is rejected
    with pytest.raises(svc.ReportNotFound):
        svc.correct_report(pg_session,
                           "00000000-0000-0000-0000-000000000000",
                           new_body="x")
    # chain continues: v3 supersedes v2
    v3 = svc.correct_report(pg_session, v2.id, new_body="Third pass.",
                            citations=[_citation(source="EDGAR")])
    assert v3.version == 3 and v3.supersedes_report_id == v2.id
    assert v3.citations[0]["source"] == "EDGAR"


def test_unique_task_version_enforced(pg_session: Session) -> None:
    t = _task(pg_session)
    _report(pg_session, t.id)
    pg_session.add(ResearchReport(
        task_id=t.id, version=1, body="forged duplicate",
        citations=[], provenance="human",
    ))
    with pytest.raises(IntegrityError):
        pg_session.commit()
    pg_session.rollback()


def test_version_floor_check_db_layer(pg_session: Session) -> None:
    if not _has_check(pg_session, "ck_research_report_version"):
        pytest.skip("schema lacks ck_research_report_version — verified on "
                    "the alembic-built DB")
    t = _task(pg_session)
    pg_session.add(ResearchReport(
        task_id=t.id, version=0, body="x", citations=[], provenance="human",
    ))
    with pytest.raises(IntegrityError):
        pg_session.commit()
    pg_session.rollback()


def test_provenance_check_db_layer(pg_session: Session) -> None:
    if not _has_check(pg_session, "ck_research_report_provenance"):
        pytest.skip("schema lacks ck_research_report_provenance — verified "
                    "on the alembic-built DB")
    t = _task(pg_session)
    pg_session.add(ResearchReport(
        task_id=t.id, version=1, body="x", citations=[], provenance="oracle",
    ))
    with pytest.raises(IntegrityError):
        pg_session.commit()
    pg_session.rollback()


def test_no_update_or_delete_path_for_reports(pg_session: Session) -> None:
    """The service is the only mutation path; it must expose NO update or
    delete surface for delivered reports (corrections are new versions)."""
    public = {
        n: f for n, f in vars(svc).items()
        if inspect.isfunction(f) and not n.startswith("_")
        and f.__module__ == svc.__name__
    }
    # exact public surface — anything new here is a deliberate API change
    assert set(public) == {
        "create_task", "create_report", "correct_report",
        "approve_report", "reject_report", "report_state",
    }
    forbidden = [n for n in public
                 if "update" in n.lower() or "delete" in n.lower()]
    assert forbidden == [], f"unexpected mutators: {forbidden}"
    # and no source-level DELETE / bulk-UPDATE constructs anywhere in the
    # module (the only writes are inserts + the three review fields)
    src = inspect.getsource(svc)
    for construct in ("db.delete", ".delete()", "sqlalchemy import update",
                      "update(ResearchReport", "delete(ResearchReport"):
        assert construct not in src, f"forbidden construct in service: {construct}"


# ---------------------------------------------------------------------------
# staleness — derived, never stored
# ---------------------------------------------------------------------------

def test_staleness_states(pg_session: Session) -> None:
    t = _task(pg_session)

    # fresh: recent citation, no expiry
    fresh = _report(pg_session, t.id, citations=[_citation(days_old=1)])
    assert svc.report_state(pg_session, fresh) == "fresh"

    # stale via citation age: newest citation older than the window
    old = svc.create_report(
        pg_session, t.id, body="old data",
        citations=[_citation(days_old=30), _citation(days_old=45)],
    )
    assert svc.report_state(pg_session, old) == "stale"
    # the NEWEST citation drives the age check
    mixed = svc.create_report(
        pg_session, t.id, body="mixed ages",
        citations=[_citation(days_old=30), _citation(days_old=1)],
    )
    assert svc.report_state(pg_session, mixed) == "fresh"
    # window is a parameter
    assert svc.report_state(pg_session, mixed,
                            max_citation_age_days=0) == "stale"

    # stale via expires_at, even with fresh citations
    expired = svc.create_report(
        pg_session, t.id, body="earnings-dated",
        citations=[_citation(days_old=0)],
        expires_at=datetime.datetime.now(UTC) - datetime.timedelta(hours=1),
    )
    assert svc.report_state(pg_session, expired) == "stale"

    # no citations: judged on expires_at alone
    bare = svc.create_report(pg_session, t.id, body="no evidence yet",
                             citations=[])
    assert svc.report_state(pg_session, bare) == "fresh"

    # superseded wins over everything once a correction lands
    svc.correct_report(pg_session, fresh.id, new_body="v2 corrects fresh")
    assert svc.report_state(pg_session, fresh) == "superseded"
    # explicit `now` is honored (fresh report viewed far in the future)
    future = datetime.datetime.now(UTC) + datetime.timedelta(days=365)
    assert svc.report_state(pg_session, mixed, now=future) == "stale"
