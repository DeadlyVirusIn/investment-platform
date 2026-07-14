"""Thesis Ledger (migrations 110+111) — service invariants + shape safety.

Pins (spec docs/architecture/THESIS_LEDGER_SPEC.md):
  * mandatory falsifier — no thesis without a meaningful wrong_if
    (service + DB CHECK ck_thesis_wrong_if_len);
  * §3 state machine — illegal transitions rejected, closed terminal,
    no un-invalidating (no-resurrection: revival = NEW thesis via
    supersedes_thesis_id);
  * generated evidence FORCED pending server-side and absent from the
    public payload until approved (the serialization-leak test);
  * engine vocabulary (stance/provenance/weight/review_status) never
    appears in public payload keys;
  * revision rows appended on EVERY mutation — append-only companion,
    the service exposes no update/delete path for revisions;
  * polymorphic link creation with read-only existence validation.

CHECK-dependent asserts detect missing constraints (create_all vs
migration drift) and skip honestly instead of vacuously passing.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from apps.api.src.api.thesis import get_thesis, list_theses
from apps.api.src.db.models import (
    Asset,
    Recommendation,
    Thesis,
    ThesisEvidence,
    ThesisRevision,
)
from apps.api.src.domain.thesis import service as svc

pytestmark = pytest.mark.integration

WRONG_IF = "Membership renewal rate drops below 88% for two straight quarters."


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _asset(db: Session) -> Asset:
    a = Asset(symbol="COST", asset_class="equity", exchange="XNAS")
    db.add(a)
    db.commit()
    return a


def _thesis(db: Session, **kw) -> Thesis:
    defaults = dict(
        title="Costco keeps compounding membership income",
        statement="ArthOS currently believes Costco can keep growing "
                  "membership income even in a weak economy.",
        wrong_if=WRONG_IF,
        scope="theme",          # no asset needed unless the test wants one
    )
    defaults.update(kw)
    return svc.create_thesis(db, **defaults)


def _has_check(db: Session, name: str) -> bool:
    """create_all/migration drift guard: CHECK-dependent asserts must skip
    honestly when the named constraint is absent (research_run precedent)."""
    n = db.execute(text(
        "SELECT count(*) FROM information_schema.check_constraints "
        "WHERE constraint_name = :n"
    ), {"n": name}).scalar()
    return bool(n)


# ---------------------------------------------------------------------------
# mandatory falsifier
# ---------------------------------------------------------------------------

def test_falsifier_required_by_service(pg_session: Session) -> None:
    for bad in ("", "   ", "too short"):
        with pytest.raises(svc.FalsifierRequired):
            _thesis(pg_session, wrong_if=bad)
    # exactly at the boundary (10 chars) is still rejected — CHECK is > 10
    with pytest.raises(svc.FalsifierRequired):
        _thesis(pg_session, wrong_if="0123456789")
    t = _thesis(pg_session)  # meaningful falsifier passes
    assert t.status == "forming" and t.wrong_if == WRONG_IF


def test_falsifier_enforced_at_db_layer(pg_session: Session) -> None:
    if not _has_check(pg_session, "ck_thesis_wrong_if_len"):
        pytest.skip("schema lacks ck_thesis_wrong_if_len — falsifier CHECK "
                    "verified on the alembic-built DB")
    pg_session.add(Thesis(title="t", statement="s", wrong_if="short",
                          scope="theme"))
    with pytest.raises(IntegrityError):
        pg_session.commit()
    pg_session.rollback()


def test_company_scope_requires_asset(pg_session: Session) -> None:
    with pytest.raises(svc.InvalidInput):
        _thesis(pg_session, scope="company", asset_id=None)
    a = _asset(pg_session)
    t = _thesis(pg_session, scope="company", asset_id=a.id)
    assert t.asset_id == a.id


# ---------------------------------------------------------------------------
# state machine
# ---------------------------------------------------------------------------

def test_transition_table_is_exhaustive() -> None:
    # every status has an entry; terminal states are truly terminal
    assert set(svc.ALLOWED_TRANSITIONS) == set(svc.STATUSES)
    assert svc.ALLOWED_TRANSITIONS["closed"] == set()
    assert svc.ALLOWED_TRANSITIONS["invalidated"] == {"closed"}
    # nothing ever transitions INTO forming
    for targets in svc.ALLOWED_TRANSITIONS.values():
        assert "forming" not in targets


def test_invalid_transitions_rejected(pg_session: Session) -> None:
    t = _thesis(pg_session)
    # forming may not jump to evidence-derived labels
    for illegal in ("strengthened", "weakened", "invalidated"):
        with pytest.raises(svc.InvalidTransition):
            svc.transition_status(pg_session, t.id, new_status=illegal,
                                  status_reason="nope",
                                  invalidated_reason="nope nope nope")
    # unknown status is invalid input, not a transition
    with pytest.raises(svc.InvalidInput):
        svc.transition_status(pg_session, t.id, new_status="excellent",
                              status_reason="nope")
    # every transition requires a reason
    with pytest.raises(svc.InvalidInput):
        svc.transition_status(pg_session, t.id, new_status="active",
                              status_reason="   ")

    t = svc.transition_status(pg_session, t.id, new_status="active",
                              status_reason="Published for current Buy idea.")
    assert t.status == "active" and t.published_at is not None

    with pytest.raises(svc.InvalidTransition):   # active -> forming never
        svc.transition_status(pg_session, t.id, new_status="forming",
                              status_reason="rewind")
    # invalidated requires a stated reason
    with pytest.raises(svc.InvalidInput):
        svc.transition_status(pg_session, t.id, new_status="invalidated",
                              status_reason="wrong-if met")


def test_no_resurrection_and_supersede(pg_session: Session) -> None:
    t = _thesis(pg_session)
    svc.transition_status(pg_session, t.id, new_status="active",
                          status_reason="Published.")
    svc.transition_status(
        pg_session, t.id, new_status="invalidated",
        status_reason="The wrong-if condition was met.",
        invalidated_reason="Renewal rate printed 86% for a second quarter.",
    )
    # invalidated thesis can never re-activate — in any direction but closed
    for illegal in ("active", "strengthened", "weakened", "forming"):
        with pytest.raises(svc.InvalidTransition):
            svc.transition_status(pg_session, t.id, new_status=illegal,
                                  status_reason="bring it back")
    # revival is a NEW thesis pointing back via supersedes_thesis_id
    revived = _thesis(pg_session, title="Costco thesis, take two",
                      supersedes_thesis_id=t.id)
    assert revived.id != t.id
    assert revived.supersedes_thesis_id == t.id
    assert revived.status == "forming"
    # superseding a nonexistent thesis is rejected
    with pytest.raises(svc.ThesisNotFound):
        _thesis(pg_session, supersedes_thesis_id="00000000-0000-0000-0000-000000000000")

    # closed is terminal
    svc.transition_status(pg_session, t.id, new_status="closed",
                          status_reason="Wrapped up after invalidation.")
    for illegal in ("active", "invalidated", "closed"):
        with pytest.raises(svc.InvalidTransition):
            svc.transition_status(pg_session, t.id, new_status=illegal,
                                  status_reason="zombie")


# ---------------------------------------------------------------------------
# evidence review pipeline
# ---------------------------------------------------------------------------

def _gen_evidence(db: Session, thesis_id: str, **kw) -> ThesisEvidence:
    defaults = dict(
        stance="supports",
        category="news",
        source_name="Tiingo news",
        source_url="https://example.com/article",
        summary="Renewal rates held at 92% in the latest quarter.",
        provenance="generated",
    )
    defaults.update(kw)
    return svc.add_evidence(db, thesis_id, **defaults)


def test_generated_evidence_forced_pending(pg_session: Session) -> None:
    t = _thesis(pg_session)
    # caller tries to smuggle an approved generated row — server forces pending
    row = _gen_evidence(pg_session, t.id, review_status="approved")
    assert row.review_status == "pending"
    assert row.reviewed_by is None and row.reviewed_at is None
    # generated without source_url is rejected (service + DB CHECK)
    with pytest.raises(svc.InvalidInput):
        _gen_evidence(pg_session, t.id, source_url=None)


def test_generated_source_url_db_check(pg_session: Session) -> None:
    if not _has_check(pg_session, "ck_thesis_evidence_gen_url"):
        pytest.skip("schema lacks ck_thesis_evidence_gen_url — verified on "
                    "the alembic-built DB")
    t = _thesis(pg_session)
    pg_session.add(ThesisEvidence(
        thesis_id=t.id, stance="supports", category="news",
        source_name="x", summary="y", provenance="generated", source_url=None,
    ))
    with pytest.raises(IntegrityError):
        pg_session.commit()
    pg_session.rollback()


def test_human_evidence_author_is_reviewer(pg_session: Session) -> None:
    t = _thesis(pg_session)
    row = svc.add_evidence(
        pg_session, t.id, stance="contradicts", category="other",
        source_name="owner note", summary="Warehouse traffic looked thin.",
        provenance="human", created_by="owner@arthos",
    )
    assert row.review_status == "approved"
    assert row.reviewed_by == "owner@arthos" and row.reviewed_at is not None


def test_review_requires_identity_and_is_one_shot(pg_session: Session) -> None:
    t = _thesis(pg_session)
    row = _gen_evidence(pg_session, t.id)
    with pytest.raises(svc.InvalidInput):
        svc.approve_evidence(pg_session, row.id, reviewer="  ")
    approved = svc.approve_evidence(pg_session, row.id, reviewer="owner@arthos")
    assert approved.review_status == "approved"
    assert approved.reviewed_by == "owner@arthos"
    with pytest.raises(svc.ReviewStateError):     # decisions are one-shot
        svc.reject_evidence(pg_session, row.id, reviewer="owner@arthos")
    # approving evidence NEVER auto-transitions the thesis
    assert pg_session.get(Thesis, t.id).status == "forming"


def test_pending_evidence_never_serialized_publicly(pg_session: Session) -> None:
    """The critical leak test: generated (pending) evidence is invisible to
    users until approved; rejected stays invisible forever; and the public
    payload never carries engine vocabulary keys."""
    t = _thesis(pg_session)
    svc.transition_status(pg_session, t.id, new_status="active",
                          status_reason="Published.")
    pending = _gen_evidence(
        pg_session, t.id,
        summary="PENDING-MARKER renewal data point.")
    rejected = _gen_evidence(
        pg_session, t.id, stance="contradicts",
        source_url="https://example.com/other",
        summary="REJECTED-MARKER contradicting take.")
    svc.reject_evidence(pg_session, rejected.id, reviewer="owner@arthos")

    payload = get_thesis(t.id, db=pg_session)
    blob = json.dumps(payload)
    assert "PENDING-MARKER" not in blob
    assert "REJECTED-MARKER" not in blob
    assert payload["supports"] == []
    assert payload["wrong_if"]["against"] == []
    # engine vocabulary never appears in public payload keys
    for word in ("stance", "provenance", "review_status", '"weight"'):
        assert word not in blob, f"engine vocab leaked: {word}"

    # approval makes it user-visible, mapped into the plain supports list
    svc.approve_evidence(pg_session, pending.id, reviewer="owner@arthos")
    payload = get_thesis(t.id, db=pg_session)
    assert [e["summary"] for e in payload["supports"]] == \
        ["PENDING-MARKER renewal data point."]
    blob = json.dumps(payload)
    for word in ("stance", "provenance", "review_status", '"weight"'):
        assert word not in blob, f"engine vocab leaked: {word}"


def test_forming_theses_hidden_from_reads(pg_session: Session) -> None:
    forming = _thesis(pg_session, title="Still forming")
    published = _thesis(pg_session, title="Published one")
    svc.transition_status(pg_session, published.id, new_status="active",
                          status_reason="Published.")
    listed = list_theses(asset_id=None, status=None, db=pg_session)
    ids = {row["id"] for row in listed["theses"]}
    assert published.id in ids and forming.id not in ids
    # asking for forming explicitly returns nothing
    assert list_theses(asset_id=None, status="forming",
                       db=pg_session) == {"theses": []}
    # detail 404s for forming
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        get_thesis(forming.id, db=pg_session)
    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# revision history
# ---------------------------------------------------------------------------

def test_revision_appended_on_every_mutation(pg_session: Session) -> None:
    t = _thesis(pg_session)
    svc.transition_status(pg_session, t.id, new_status="active",
                          status_reason="Published.")
    svc.transition_status(pg_session, t.id, new_status="weakened",
                          status_reason="Two analysts cut estimates.")
    revs = list(pg_session.execute(
        text("SELECT revision_no, snapshot FROM thesis_revision "
             "WHERE thesis_id = :t ORDER BY revision_no"),
        {"t": t.id},
    ).all())
    assert [r.revision_no for r in revs] == [1, 2, 3]
    assert revs[0].snapshot["status"] == "forming"
    assert revs[0].snapshot["status_reason"] is None
    assert revs[1].snapshot["status"] == "active"
    assert revs[2].snapshot["status"] == "weakened"
    assert revs[2].snapshot["status_reason"] == "Two analysts cut estimates."
    assert revs[2].snapshot["wrong_if"] == WRONG_IF

    # immutability: the service exposes no revision update/delete path
    import inspect
    mutators = [n for n, f in vars(svc).items()
                if inspect.isfunction(f) and not n.startswith("_")
                and "revision" in n.lower()]
    assert mutators == [], f"unexpected public revision mutators: {mutators}"

    # DB-level: duplicate revision_no is impossible (append-only ordering pin)
    pg_session.add(ThesisRevision(thesis_id=t.id, revision_no=1,
                                  snapshot={"status": "forged"}))
    with pytest.raises(IntegrityError):
        pg_session.commit()
    pg_session.rollback()

    # the status history surfaces in block 4, newest first
    payload = get_thesis(t.id, db=pg_session)
    assert [c["note"] for c in payload["changes"]] == \
        ["Two analysts cut estimates.", "Published."]


# ---------------------------------------------------------------------------
# links
# ---------------------------------------------------------------------------

def test_link_creation_and_target_validation(pg_session: Session) -> None:
    a = _asset(pg_session)
    rec = Recommendation(asset_id=a.id, action="buy")
    pg_session.add(rec)
    pg_session.commit()

    t = _thesis(pg_session, scope="company", asset_id=a.id)
    link = svc.link_target(pg_session, t.id,
                           target_type="recommendation", target_id=rec.id,
                           note="opening idea")
    assert link.target_type == "recommendation" and link.target_id == rec.id

    # duplicate link rejected (uq_thesis_link)
    with pytest.raises(svc.DuplicateLink):
        svc.link_target(pg_session, t.id,
                        target_type="recommendation", target_id=rec.id)
    # bogus target id -> not found (existence validated read-only)
    with pytest.raises(svc.TargetNotFound):
        svc.link_target(pg_session, t.id, target_type="recommendation",
                        target_id="00000000-0000-0000-0000-000000000000")
    # unknown type rejected
    with pytest.raises(svc.InvalidInput):
        svc.link_target(pg_session, t.id, target_type="tweet",
                        target_id=rec.id)
    # reserved future type: lesson table absent -> honest not-found
    with pytest.raises(svc.TargetNotFound):
        svc.link_target(pg_session, t.id, target_type="lesson",
                        target_id=rec.id)
    # linking never wrote to the recommendation table
    n = pg_session.execute(
        text("SELECT count(*) FROM recommendation")).scalar()
    assert n == 1
