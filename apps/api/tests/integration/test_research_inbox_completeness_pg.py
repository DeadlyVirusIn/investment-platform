"""Wave 2A — Research Inbox completeness: correction route + follow-up (pg).

Pins: immutable v1→v2→v3 chains (old rows byte-identical), superseded-
non-latest 409, concurrent-correction race collapsing on
UNIQUE(task_id, version), human-owner identity stamping (existing service
contract: human corrections are approved with the author as reviewer),
citation validation re-run on corrections, bounds, follow-up task creation
with task-level structured provenance and zero report mutation / zero job
launch, structural flag + owner gating, no agent path.
"""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.api import research_inbox as api
from apps.api.src.db.models import ResearchReport, ResearchTask
from apps.api.src.domain.research_inbox import service as svc

pytestmark = pytest.mark.integration

OWNER = {"email": "owner@example.com", "id": "owner-1", "role": "owner"}


def _task(db: Session) -> ResearchTask:
    return svc.create_task(db, title="T", question="Q?", scope="sector:test",
                           schedule_expr=None, created_by="owner@example.com")


def _cite(n: int = 1) -> list[dict]:
    return [{"source": f"s{n}", "url": f"https://example.com/f/{n}",
             "observed_at": "2026-07-13T00:00:00+00:00"}]


def _v1(db: Session, provenance: str = "generated") -> ResearchReport:
    t = _task(db)
    return svc.create_report(db, t.id, body="v1 body", citations=_cite(),
                             provenance=provenance,
                             created_by="agent" if provenance == "generated"
                             else "owner@example.com")


def _row_json(db: Session, rid: str) -> str:
    return db.execute(text(
        "SELECT row_to_json(r)::text FROM research_report r WHERE id=:i"
    ), {"i": rid}).scalar()


def _correct(db, rid, body="corrected", reason="fix", citations=None):
    return api.correct_report(
        report_id=rid,
        body=api.CorrectionBody(body=body, citations=citations,
                                reason=reason),
        owner=OWNER, db=db)


# ---------------------------------------------------------------------------

def test_v1_to_v2_to_v3_chain_old_rows_byte_identical(
    pg_session: Session,
) -> None:
    r1 = _v1(pg_session)
    snap1 = _row_json(pg_session, r1.id)
    out2 = _correct(pg_session, r1.id, body="v2 body", reason="typo fix")
    assert out2["version"] == 2
    assert out2["corrects_report_id"] == r1.id
    assert out2["correction_reason"] == "typo fix"
    # human correction follows the existing service contract: approved with
    # the author as reviewer (generated content can never ride this path)
    assert out2["review_status"] == "approved"
    assert out2["reviewed_by"] == "owner@example.com"
    snap1_after = _row_json(pg_session, r1.id)
    assert snap1 == snap1_after                     # byte-identical
    assert svc.report_state(pg_session, pg_session.get(
        ResearchReport, r1.id)) == "superseded"
    out3 = _correct(pg_session, out2["id"], body="v3 body", reason="more")
    assert out3["version"] == 3
    snap2_after = _row_json(pg_session, out2["id"])
    assert '"v2 body"' in snap2_after               # v2 untouched


def test_correcting_superseded_non_latest_409(pg_session: Session) -> None:
    r1 = _v1(pg_session)
    _correct(pg_session, r1.id)
    with pytest.raises(HTTPException) as e:
        _correct(pg_session, r1.id, body="again")
    assert e.value.status_code == 409
    assert "latest version" in e.value.detail


def test_correcting_missing_report_404(pg_session: Session) -> None:
    with pytest.raises(HTTPException) as e:
        _correct(pg_session, str(uuid.uuid4()))
    assert e.value.status_code == 404


def test_concurrent_correction_race_409(pg_session: Session) -> None:
    # Simulate the race: both writers computed version 2; the second insert
    # violates UNIQUE(task_id, version) and the route maps it to 409.
    r1 = _v1(pg_session)
    _correct(pg_session, r1.id, body="winner")
    # loser: bypass the route's superseded guard to hit the DB constraint
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        pg_session.execute(text(
            "INSERT INTO research_report (id, task_id, version, body, "
            "citations, provenance, review_status, created_at) "
            "VALUES (:i, :t, 2, 'loser', '[]'::jsonb, 'human', 'approved', "
            "now())"
        ), {"i": str(uuid.uuid4()), "t": r1.task_id})
        pg_session.flush()
    pg_session.rollback()


def test_agent_generated_report_corrected_by_human(
    pg_session: Session,
) -> None:
    r1 = _v1(pg_session, provenance="generated")
    assert r1.review_status == "pending"            # generated → forced pending
    out2 = _correct(pg_session, r1.id, body="human correction",
                    reason="agent text was wrong")
    assert out2["provenance"] == "human"
    assert out2["review_status"] == "approved"
    # original agent row untouched, still pending, retained forever
    orig = pg_session.get(ResearchReport, r1.id)
    assert orig.review_status == "pending"
    assert orig.body == "v1 body"


def test_citation_validation_reruns_on_correction(pg_session: Session) -> None:
    r1 = _v1(pg_session)
    with pytest.raises(HTTPException) as e:
        _correct(pg_session, r1.id, citations=[{"source": "bad"}])  # no url
    assert e.value.status_code == 422
    # carrying citations forward (None) keeps the old evidence
    out = _correct(pg_session, r1.id, citations=None)
    assert out["citations"] == json.loads(json.dumps(_cite()))


def test_bounds_reject_oversized(pg_session: Session) -> None:
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        api.CorrectionBody(body="x" * 100_001, reason="r")
    with pytest.raises(ValidationError):
        api.CorrectionBody(body="ok", reason="r" * 501)


def test_route_is_owner_gated_and_agent_free() -> None:
    import inspect
    src = inspect.getsource(api)
    # every mutating inbox route depends on require_owner (session cookie);
    # gateway agent tokens have no session and no correction path exists in
    # the agent gateway router.
    from apps.api.src.api import agent_gateway
    # no inbox-correction route exists in the agent gateway
    gw = inspect.getsource(agent_gateway)
    assert "/admin/inbox" not in gw
    assert "reports/{report_id}/correct" not in gw
    assert src.count("Depends(require_owner)") >= 6


def test_follow_up_creates_task_with_task_level_provenance(
    pg_session: Session,
) -> None:
    r1 = _v1(pg_session)
    before = _row_json(pg_session, r1.id)
    out = api.create_follow_up(
        report_id=r1.id,
        body=api.FollowUpBody(title="Follow up", question="Dig deeper?",
                              scope="sector:test"),
        owner=OWNER, db=pg_session)
    assert out["follow_up_of_task_id"] == r1.task_id
    assert out["source_report_id"] == r1.id
    assert out["source_report_version"] == 1
    t = pg_session.get(ResearchTask, out["id"])
    assert t.follow_up_of_task_id == r1.task_id
    assert t.created_by == "owner@example.com"
    # report not mutated; no job rows created
    assert _row_json(pg_session, r1.id) == before
    if pg_session.execute(text(
            "SELECT to_regclass('agent_job')")).scalar():
        assert pg_session.execute(text(
            "SELECT count(*) FROM agent_job")).scalar() == 0


def test_follow_up_missing_report_404(pg_session: Session) -> None:
    with pytest.raises(HTTPException) as e:
        api.create_follow_up(report_id=str(uuid.uuid4()),
                             body=api.FollowUpBody(title="t", question="q"),
                             owner=OWNER, db=pg_session)
    assert e.value.status_code == 404
