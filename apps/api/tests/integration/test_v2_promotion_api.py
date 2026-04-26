"""Phase 5 integration tests for v2_promotion API.

Covers:
  * READ: /state, /snapshots?weeks=N, /gates
  * APPROVE: success path + rejections
      - wrong state
      - stale snapshot id
      - invalid approver (not in allowlist)
      - short rationale
      - duplicate approval (idempotency)
  * RESCIND: success path + rejections (wrong state, missing prior APPROVE)
  * Multi-approval: only the latest valid one is surfaced through state
  * No snapshot table mutation by any endpoint
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from apps.api.src.db import get_session
from apps.api.src.db.models import (
    V2PromotionApproval,
    V2PromotionSnapshot,
)
from apps.api.src.main import app
from apps.api.src.api.v2_promotion import APPROVER_ALLOWLIST


pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client_factory(pg_engine):
    """Build a FastAPI TestClient bound to the integration Postgres."""
    SessionCls = sessionmaker(bind=pg_engine, class_=Session, expire_on_commit=False)

    def _override():
        s = SessionCls()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_session, None)


def _seed_snapshot(
    pg_session: Session,
    *,
    state: str,
    iso_year: int = 2026,
    iso_week: int = 21,
    as_of_date: dt.date | None = None,
    confidence: float = 0.85,
    verdict_streak: int = 4,
    readiness_streak: int = 2,
    bundle: dict | None = None,
    gates_json: dict | None = None,
    rollback_reason: str | None = None,
    prior_state: str | None = None,
) -> V2PromotionSnapshot:
    if as_of_date is None:
        # Monday of the given ISO week
        as_of_date = dt.date.fromisocalendar(iso_year, iso_week, 1)
    if bundle is None:
        bundle = {
            "metrics": {
                "n_divergent_days": 60,
                "avg_return_diff_1d_bps": 12.0,
                "impact_weighted_edge": 0.10,
            },
            "verdict": {
                "verdict": "V2_BETTER",
                "readiness": "STRONG_CANDIDATE",
                "confidence": 0.85,
                "tail_guard_triggered": False,
            },
        }
    if gates_json is None:
        gates_json = {
            "gates": {
                "gate_1_minimum_sample": {"name": "gate_1_minimum_sample",
                                           "passed": True, "reason": "ok",
                                           "details": {}},
                "gate_2_verdict_stability": {"name": "gate_2_verdict_stability",
                                              "passed": True, "reason": "ok",
                                              "details": {}},
                "gate_3_edge_quality": {"name": "gate_3_edge_quality",
                                         "passed": True, "reason": "ok",
                                         "details": {}},
                "gate_4_tail_risk": {"name": "gate_4_tail_risk",
                                      "passed": True, "reason": "ok",
                                      "details": {}},
                "gate_5_regime_validation": {"name": "gate_5_regime_validation",
                                              "passed": True, "reason": "ok",
                                              "details": {}},
                "gate_6_stability": {"name": "gate_6_stability",
                                      "passed": True, "reason": "ok",
                                      "details": {}},
                "gate_7_governance": {"name": "gate_7_governance",
                                       "passed": True, "reason": "ok",
                                       "details": {}},
                "gate_8_operator_approval": {"name": "gate_8_operator_approval",
                                              "passed": False,
                                              "reason": "no approval yet",
                                              "details": {}},
            },
            "confidence_breakdown": {
                "sample": 1.0, "verdict_streak": 1.0, "readiness_streak": 1.0,
                "edge": 0.5, "tail": 1.0, "regime": 1.0, "stability": 1.0,
                "total": confidence,
            },
            "decision": {"new_state": state, "notes": []},
            "streaks": {"verdict_streak": verdict_streak,
                          "readiness_streak": readiness_streak},
            "comparison_fetch_ok": True,
        }
    snap = V2PromotionSnapshot(
        as_of_date=as_of_date,
        iso_year=iso_year,
        iso_week=iso_week,
        comparison_bundle_json=bundle,
        state=state,
        prior_state=prior_state,
        promotion_confidence=Decimal(str(confidence)),
        gates_json=gates_json,
        verdict_streak=verdict_streak,
        readiness_streak=readiness_streak,
        rollback_reason=rollback_reason,
    )
    pg_session.add(snap)
    pg_session.commit()
    pg_session.refresh(snap)
    return snap


def _allowlisted_approver() -> str:
    return next(iter(APPROVER_ALLOWLIST))


# ===========================================================================
# READ — /state
# ===========================================================================

def test_get_state_no_snapshots_yet(client_factory):
    r = client_factory.get("/api/v2-promotion/state")
    assert r.status_code == 200
    body = r.json()
    assert body["snapshot"] is None
    assert body["approvals"] == []
    assert body["approver_allowlist_size"] == len(APPROVER_ALLOWLIST)


def test_get_state_returns_latest_snapshot(client_factory, pg_session):
    _seed_snapshot(pg_session, state="WATCH", iso_week=18)
    snap2 = _seed_snapshot(pg_session, state="STRONG_CANDIDATE", iso_week=21)
    r = client_factory.get("/api/v2-promotion/state")
    assert r.status_code == 200
    body = r.json()
    assert body["snapshot"]["snapshot_id"] == snap2.id
    assert body["snapshot"]["state"] == "STRONG_CANDIDATE"
    assert body["gates_passing"]["gate_1_minimum_sample"] is True


# ===========================================================================
# READ — /snapshots
# ===========================================================================

def test_get_snapshots_default_12(client_factory, pg_session):
    for w in range(15, 22):
        _seed_snapshot(pg_session, state="WATCH", iso_week=w)
    r = client_factory.get("/api/v2-promotion/snapshots")
    assert r.status_code == 200
    body = r.json()
    assert body["weeks_requested"] == 12
    assert body["n_returned"] == 7   # only 7 seeded
    # Newest-first ordering
    iso_weeks = [s["iso_week"] for s in body["snapshots"]]
    assert iso_weeks == sorted(iso_weeks, reverse=True)


def test_get_snapshots_with_limit(client_factory, pg_session):
    for w in range(15, 25):
        _seed_snapshot(pg_session, state="WATCH", iso_week=w)
    r = client_factory.get("/api/v2-promotion/snapshots?weeks=3")
    assert r.status_code == 200
    body = r.json()
    assert body["weeks_requested"] == 3
    assert body["n_returned"] == 3


@pytest.mark.parametrize("bad_weeks", [0, -1, 200, 1000])
def test_get_snapshots_validates_weeks_range(client_factory, bad_weeks):
    r = client_factory.get(f"/api/v2-promotion/snapshots?weeks={bad_weeks}")
    assert r.status_code == 422


# ===========================================================================
# READ — /gates
# ===========================================================================

def test_get_gates_returns_latest_when_id_omitted(client_factory, pg_session):
    snap = _seed_snapshot(pg_session, state="STRONG_CANDIDATE", iso_week=21)
    r = client_factory.get("/api/v2-promotion/gates")
    assert r.status_code == 200
    body = r.json()
    assert body["snapshot_id"] == snap.id
    assert set(body["gates"].keys()) == {
        "gate_1_minimum_sample", "gate_2_verdict_stability",
        "gate_3_edge_quality", "gate_4_tail_risk",
        "gate_5_regime_validation", "gate_6_stability",
        "gate_7_governance", "gate_8_operator_approval",
    }


def test_get_gates_by_explicit_id(client_factory, pg_session):
    snap1 = _seed_snapshot(pg_session, state="WATCH", iso_week=18)
    _seed_snapshot(pg_session, state="STRONG_CANDIDATE", iso_week=21)
    r = client_factory.get(f"/api/v2-promotion/gates?snapshot_id={snap1.id}")
    assert r.status_code == 200
    assert r.json()["snapshot_id"] == snap1.id
    assert r.json()["state"] == "WATCH"


def test_get_gates_404_unknown_id(client_factory):
    r = client_factory.get("/api/v2-promotion/gates?snapshot_id=999999")
    assert r.status_code == 404


# ===========================================================================
# APPROVE — happy path + idempotency
# ===========================================================================

def test_approve_success_path(client_factory, pg_session):
    snap = _seed_snapshot(pg_session, state="STRONG_CANDIDATE", iso_week=21)
    r = client_factory.post(
        "/api/v2-promotion/approve",
        json={
            "snapshot_id": snap.id,
            "approver": _allowlisted_approver(),
            "rationale": "test approval rationale long enough text",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "inserted"
    assert body["approval"]["decision"] == "APPROVE"
    assert body["snapshot_id"] == snap.id
    assert body["snapshot_state_at_approval"] == "STRONG_CANDIDATE"

    # DB row exists
    row = pg_session.scalar(
        select(V2PromotionApproval).where(
            V2PromotionApproval.snapshot_id == snap.id,
            V2PromotionApproval.decision == "APPROVE",
        )
    )
    assert row is not None
    assert row.approver in APPROVER_ALLOWLIST


def test_approve_does_not_mutate_snapshot_state(client_factory, pg_session):
    snap = _seed_snapshot(pg_session, state="STRONG_CANDIDATE", iso_week=21)
    r = client_factory.post(
        "/api/v2-promotion/approve",
        json={
            "snapshot_id": snap.id,
            "approver": _allowlisted_approver(),
            "rationale": "explicit no-mutation verification rationale",
        },
    )
    assert r.status_code == 200
    pg_session.expire_all()
    snap_after = pg_session.get(V2PromotionSnapshot, snap.id)
    # State, confidence, streaks, rollback_reason all unchanged
    assert snap_after.state == "STRONG_CANDIDATE"
    assert snap_after.promotion_confidence == snap.promotion_confidence
    assert snap_after.verdict_streak == snap.verdict_streak
    assert snap_after.readiness_streak == snap.readiness_streak
    assert snap_after.rollback_reason == snap.rollback_reason


def test_approve_duplicate_returns_409(client_factory, pg_session):
    snap = _seed_snapshot(pg_session, state="STRONG_CANDIDATE", iso_week=21)
    body_json = {
        "snapshot_id": snap.id,
        "approver": _allowlisted_approver(),
        "rationale": "duplicate-approval idempotency test rationale",
    }
    r1 = client_factory.post("/api/v2-promotion/approve", json=body_json)
    assert r1.status_code == 200
    r2 = client_factory.post("/api/v2-promotion/approve", json=body_json)
    assert r2.status_code == 409
    assert "already" in r2.json()["detail"].lower()


# ===========================================================================
# APPROVE — rejection paths
# ===========================================================================

@pytest.mark.parametrize("state", [
    "NOT_READY", "WATCH", "READY_FOR_REVIEW",
    "APPROVED_FOR_SHADOW_REPLACEMENT",
])
def test_approve_rejected_when_wrong_state(client_factory, pg_session, state):
    snap = _seed_snapshot(pg_session, state=state, iso_week=21)
    r = client_factory.post(
        "/api/v2-promotion/approve",
        json={
            "snapshot_id": snap.id,
            "approver": _allowlisted_approver(),
            "rationale": "wrong state approval rejection test rationale",
        },
    )
    assert r.status_code == 409
    assert "state" in r.json()["detail"].lower()


def test_approve_rejected_when_snapshot_id_stale(client_factory, pg_session):
    snap_old = _seed_snapshot(pg_session, state="STRONG_CANDIDATE", iso_week=18)
    _seed_snapshot(pg_session, state="STRONG_CANDIDATE", iso_week=21)
    r = client_factory.post(
        "/api/v2-promotion/approve",
        json={
            "snapshot_id": snap_old.id,   # stale
            "approver": _allowlisted_approver(),
            "rationale": "stale snapshot id approval rejection rationale",
        },
    )
    assert r.status_code == 409
    assert "snapshot_id" in r.json()["detail"]


def test_approve_rejected_when_approver_not_in_allowlist(client_factory, pg_session):
    snap = _seed_snapshot(pg_session, state="STRONG_CANDIDATE", iso_week=21)
    r = client_factory.post(
        "/api/v2-promotion/approve",
        json={
            "snapshot_id": snap.id,
            "approver": "stranger@example.com",
            "rationale": "invalid-approver rejection rationale text here",
        },
    )
    assert r.status_code == 403


def test_approve_rejected_when_rationale_too_short(client_factory, pg_session):
    _seed_snapshot(pg_session, state="STRONG_CANDIDATE", iso_week=21)
    r = client_factory.post(
        "/api/v2-promotion/approve",
        json={
            "snapshot_id": 1,
            "approver": _allowlisted_approver(),
            "rationale": "too short",
        },
    )
    # Pydantic min_length=20 → 422
    assert r.status_code == 422


def test_approve_rejected_when_no_snapshots(client_factory):
    r = client_factory.post(
        "/api/v2-promotion/approve",
        json={
            "snapshot_id": 1,
            "approver": _allowlisted_approver(),
            "rationale": "no-snapshot rejection scenario rationale here",
        },
    )
    assert r.status_code == 404


# ===========================================================================
# RESCIND — happy path + rejections
# ===========================================================================

def test_rescind_success_path(client_factory, pg_session):
    """Setup: STRONG_CANDIDATE snapshot + APPROVE row + APPROVED snapshot.
    Rescind references the original STRONG_CANDIDATE snapshot."""
    snap_strong = _seed_snapshot(
        pg_session, state="STRONG_CANDIDATE", iso_week=20,
    )
    pg_session.add(V2PromotionApproval(
        snapshot_id=snap_strong.id,
        decision="APPROVE",
        approver=_allowlisted_approver(),
        rationale="prior approval row to support rescission test",
    ))
    pg_session.commit()
    _seed_snapshot(
        pg_session, state="APPROVED_FOR_SHADOW_REPLACEMENT", iso_week=21,
        prior_state="STRONG_CANDIDATE",
    )

    r = client_factory.post(
        "/api/v2-promotion/rescind",
        json={
            "snapshot_id": snap_strong.id,
            "approver": _allowlisted_approver(),
            "rationale": "rescission of prior approval test rationale text",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "inserted"
    assert body["rescission"]["decision"] == "RESCIND"
    assert body["rescinded_snapshot_id"] == snap_strong.id


def test_rescind_does_not_mutate_snapshot_state(client_factory, pg_session):
    snap_strong = _seed_snapshot(pg_session, state="STRONG_CANDIDATE", iso_week=20)
    pg_session.add(V2PromotionApproval(
        snapshot_id=snap_strong.id, decision="APPROVE",
        approver=_allowlisted_approver(),
        rationale="prior approval row for rescission no-mutation test",
    ))
    pg_session.commit()
    snap_app = _seed_snapshot(
        pg_session, state="APPROVED_FOR_SHADOW_REPLACEMENT", iso_week=21,
    )
    r = client_factory.post(
        "/api/v2-promotion/rescind",
        json={
            "snapshot_id": snap_strong.id,
            "approver": _allowlisted_approver(),
            "rationale": "rescission no-mutation verification rationale text",
        },
    )
    assert r.status_code == 200
    pg_session.expire_all()
    after_strong = pg_session.get(V2PromotionSnapshot, snap_strong.id)
    after_app = pg_session.get(V2PromotionSnapshot, snap_app.id)
    assert after_strong.state == "STRONG_CANDIDATE"
    assert after_app.state == "APPROVED_FOR_SHADOW_REPLACEMENT"


@pytest.mark.parametrize("state", [
    "NOT_READY", "WATCH", "READY_FOR_REVIEW", "STRONG_CANDIDATE",
])
def test_rescind_rejected_when_wrong_state(client_factory, pg_session, state):
    snap = _seed_snapshot(pg_session, state=state, iso_week=21)
    r = client_factory.post(
        "/api/v2-promotion/rescind",
        json={
            "snapshot_id": snap.id,
            "approver": _allowlisted_approver(),
            "rationale": "wrong-state rescission rejection test rationale",
        },
    )
    assert r.status_code == 409


def test_rescind_rejected_when_no_prior_approve(client_factory, pg_session):
    snap = _seed_snapshot(
        pg_session, state="APPROVED_FOR_SHADOW_REPLACEMENT", iso_week=21,
    )
    r = client_factory.post(
        "/api/v2-promotion/rescind",
        json={
            "snapshot_id": snap.id,    # never had APPROVE
            "approver": _allowlisted_approver(),
            "rationale": "no-prior-approve rescission rejection rationale",
        },
    )
    assert r.status_code == 409
    assert "no prior APPROVE" in r.json()["detail"]


def test_rescind_rejected_when_already_rescinded(client_factory, pg_session):
    snap_strong = _seed_snapshot(pg_session, state="STRONG_CANDIDATE", iso_week=20)
    pg_session.add(V2PromotionApproval(
        snapshot_id=snap_strong.id, decision="APPROVE",
        approver=_allowlisted_approver(), rationale="approve row for re-rescind test",
    ))
    pg_session.add(V2PromotionApproval(
        snapshot_id=snap_strong.id, decision="RESCIND",
        approver=_allowlisted_approver(), rationale="prior rescission row already exists",
    ))
    pg_session.commit()
    _seed_snapshot(
        pg_session, state="APPROVED_FOR_SHADOW_REPLACEMENT", iso_week=21,
    )
    r = client_factory.post(
        "/api/v2-promotion/rescind",
        json={
            "snapshot_id": snap_strong.id,
            "approver": _allowlisted_approver(),
            "rationale": "duplicate rescission attempt rejection rationale",
        },
    )
    assert r.status_code == 409


# ===========================================================================
# Multi-approval surfacing
# ===========================================================================

def test_state_endpoint_lists_all_approvals_in_order(client_factory, pg_session):
    snap = _seed_snapshot(pg_session, state="STRONG_CANDIDATE", iso_week=21)
    base_dt = dt.datetime(2026, 5, 1, tzinfo=dt.timezone.utc)
    pg_session.add(V2PromotionApproval(
        snapshot_id=snap.id, decision="APPROVE",
        approver=_allowlisted_approver(),
        rationale="first approval row for multi-approval listing test",
        approved_at=base_dt,
    ))
    # Move to APPROVED then re-rescind in a later snapshot scenario isn't
    # required here; just verify multi-row surfacing under one snapshot.
    pg_session.add(V2PromotionApproval(
        snapshot_id=snap.id, decision="RESCIND",
        approver=_allowlisted_approver(),
        rationale="second decision (rescind) row for listing test",
        approved_at=base_dt + dt.timedelta(hours=2),
    ))
    pg_session.commit()
    r = client_factory.get("/api/v2-promotion/state")
    body = r.json()
    decisions = [a["decision"] for a in body["approvals"]]
    assert decisions == ["APPROVE", "RESCIND"]    # ascending order


# ===========================================================================
# No snapshot mutation by any endpoint — comprehensive check
# ===========================================================================

def test_no_endpoint_modifies_existing_snapshot_columns(client_factory, pg_session):
    snap = _seed_snapshot(pg_session, state="STRONG_CANDIDATE", iso_week=21)
    snapshot_dump_before = {
        "state": snap.state,
        "prior_state": snap.prior_state,
        "promotion_confidence": str(snap.promotion_confidence),
        "verdict_streak": snap.verdict_streak,
        "readiness_streak": snap.readiness_streak,
        "rollback_reason": snap.rollback_reason,
        "comparison_bundle_json": dict(snap.comparison_bundle_json or {}),
        "gates_json": dict(snap.gates_json or {}),
    }

    # Hit every read endpoint
    client_factory.get("/api/v2-promotion/state")
    client_factory.get("/api/v2-promotion/snapshots?weeks=5")
    client_factory.get(f"/api/v2-promotion/gates?snapshot_id={snap.id}")
    # Approve
    client_factory.post(
        "/api/v2-promotion/approve",
        json={"snapshot_id": snap.id,
              "approver": _allowlisted_approver(),
              "rationale": "comprehensive no-mutation verification rationale"},
    )

    pg_session.expire_all()
    after = pg_session.get(V2PromotionSnapshot, snap.id)
    assert after.state == snapshot_dump_before["state"]
    assert after.prior_state == snapshot_dump_before["prior_state"]
    assert str(after.promotion_confidence) == snapshot_dump_before["promotion_confidence"]
    assert after.verdict_streak == snapshot_dump_before["verdict_streak"]
    assert after.readiness_streak == snapshot_dump_before["readiness_streak"]
    assert after.rollback_reason == snapshot_dump_before["rollback_reason"]
    assert dict(after.comparison_bundle_json or {}) == snapshot_dump_before["comparison_bundle_json"]
    assert dict(after.gates_json or {}) == snapshot_dump_before["gates_json"]
