"""Integration tests for v2_oos_monitoring fetch_and_build_weekly_report.

Read-only DB access. Asserts:
  * SELECT-only — row counts unchanged before/after report build
  * Latest snapshot used when snapshot_id omitted
  * Specific snapshot retrievable by id
  * Returns None when no snapshots exist
  * Handles NULL optional fields gracefully
  * Uses stored state field verbatim (no recomputation)
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from apps.api.src.db.models import (
    V2PromotionApproval,
    V2PromotionSnapshot,
)
from apps.api.src.research.v2_oos_monitoring import (
    LATEST_KNOWN_BUNDLE_SCHEMA,
    REPORT_SCHEMA_VERSION,
    fetch_and_build_weekly_report,
)


pytestmark = pytest.mark.integration


@pytest.fixture
def pg_factory(pg_engine):
    return sessionmaker(bind=pg_engine, class_=Session, expire_on_commit=False)


def _make_snapshot(
    pg_session: Session,
    *,
    iso_year: int = 2026,
    iso_week: int = 21,
    state: str = "WATCH",
    confidence: float = 0.5,
    verdict_streak: int = 0,
    readiness_streak: int = 0,
    rollback_reason: str | None = None,
    snapshot_content_hash: str | None = "hash_a",
    schema_version: int = LATEST_KNOWN_BUNDLE_SCHEMA,
    code_version: str | None = "0.1.0",
    timezone: str | None = "UTC",
    bundle: dict | None = None,
    gates: dict | None = None,
    prior_state: str | None = None,
) -> V2PromotionSnapshot:
    as_of_date = dt.date.fromisocalendar(iso_year, iso_week, 1)
    if bundle is None:
        bundle = {
            "metrics": {
                "avg_return_diff_1d_bps": 5.0,
                "impact_weighted_edge": 0.05,
                "n_divergent_days": 50,
            },
            "tail": {
                "tail_delta_p99_bps": 0.0,
                "tail_delta_p95_bps": 0.0,
            },
            "tail_by_regime": {},
            "verdict": {
                "verdict": "V2_BETTER", "readiness": "STRONG_CANDIDATE",
                "confidence": confidence, "tail_guard_triggered": False,
            },
        }
    if gates is None:
        gates_inner = {
            f"gate_{i}_x": {
                "name": f"gate_{i}_x", "passed": True,
                "reason": "ok", "details": {},
            } for i in range(1, 9)
        }
        gates = {
            "gates": gates_inner,
            "confidence_breakdown": {
                "total": confidence, "basis_warnings": [],
            },
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
        gates_json=gates,
        verdict_streak=verdict_streak,
        readiness_streak=readiness_streak,
        rollback_reason=rollback_reason,
        snapshot_content_hash=snapshot_content_hash,
        schema_version=schema_version,
        code_version=code_version,
        timezone=timezone,
    )
    pg_session.add(snap)
    pg_session.commit()
    pg_session.refresh(snap)
    return snap


# ===========================================================================
# Empty + basic retrieval
# ===========================================================================

def test_fetch_and_build_returns_none_when_empty(pg_factory):
    with pg_factory() as s:
        out = fetch_and_build_weekly_report(s)
    assert out is None


def test_fetch_latest_snapshot_when_id_omitted(pg_factory, pg_session):
    _make_snapshot(pg_session, iso_week=18, state="WATCH")
    snap2 = _make_snapshot(pg_session, iso_week=21, state="STRONG_CANDIDATE",
                            confidence=0.85, verdict_streak=4, readiness_streak=2)
    pg_session.close()
    with pg_factory() as s:
        rep = fetch_and_build_weekly_report(s)
    assert rep is not None
    assert rep.snapshot_id == snap2.id
    assert rep.state == "STRONG_CANDIDATE"
    assert rep.confidence == 0.85


def test_fetch_specific_snapshot_by_id(pg_factory, pg_session):
    snap1 = _make_snapshot(pg_session, iso_week=18, state="WATCH")
    _make_snapshot(pg_session, iso_week=21, state="STRONG_CANDIDATE")
    pg_session.close()
    with pg_factory() as s:
        rep = fetch_and_build_weekly_report(s, snapshot_id=snap1.id)
    assert rep is not None
    assert rep.snapshot_id == snap1.id
    assert rep.state == "WATCH"


def test_fetch_returns_none_for_unknown_id(pg_factory, pg_session):
    _make_snapshot(pg_session, iso_week=21)
    pg_session.close()
    with pg_factory() as s:
        rep = fetch_and_build_weekly_report(s, snapshot_id=999_999)
    assert rep is None


# ===========================================================================
# Read-only invariant: row counts unchanged
# ===========================================================================

def test_no_writes_to_database(pg_factory, pg_session):
    snap = _make_snapshot(pg_session, iso_week=21)
    pg_session.add(V2PromotionApproval(
        snapshot_id=snap.id, decision="APPROVE",
        approver="ops@example.com",
        rationale="approval rationale long enough text here",
    ))
    pg_session.commit()
    pg_session.close()

    with pg_factory() as s:
        snap_count_before = s.scalar(
            text("SELECT COUNT(*) FROM v2_promotion_snapshot")
        )
        approval_count_before = s.scalar(
            text("SELECT COUNT(*) FROM v2_promotion_approval")
        )

    with pg_factory() as s:
        rep = fetch_and_build_weekly_report(s)
    assert rep is not None

    with pg_factory() as s:
        snap_count_after = s.scalar(
            text("SELECT COUNT(*) FROM v2_promotion_snapshot")
        )
        approval_count_after = s.scalar(
            text("SELECT COUNT(*) FROM v2_promotion_approval")
        )
    assert snap_count_after == snap_count_before
    assert approval_count_after == approval_count_before


def test_no_writes_to_database_when_running_many_reports(pg_factory, pg_session):
    """Multi-week history; multi-build invocations; row counts unchanged."""
    snaps = [
        _make_snapshot(pg_session, iso_week=w, state="WATCH")
        for w in range(15, 22)
    ]
    pg_session.close()

    with pg_factory() as s:
        before = s.scalar(text("SELECT COUNT(*) FROM v2_promotion_snapshot"))

    with pg_factory() as s:
        for snap in snaps:
            r = fetch_and_build_weekly_report(s, snapshot_id=snap.id)
            assert r is not None

    with pg_factory() as s:
        after = s.scalar(text("SELECT COUNT(*) FROM v2_promotion_snapshot"))
    assert before == after


# ===========================================================================
# Optional field handling
# ===========================================================================

def test_handles_missing_optional_fields_gracefully(pg_factory, pg_session):
    """Snapshot with NULL snapshot_content_hash + NULL evaluated_at_utc
    + NULL timezone should still build a report without raising."""
    snap = V2PromotionSnapshot(
        as_of_date=dt.date(2026, 5, 18),
        iso_year=2026, iso_week=21,
        comparison_bundle_json={
            "metrics": {"avg_return_diff_1d_bps": 5.0,
                         "impact_weighted_edge": 0.05,
                         "n_divergent_days": 50},
            "tail": {},
            "verdict": {"verdict": "V2_BETTER",
                         "readiness": "WATCH",
                         "confidence": 0.5,
                         "tail_guard_triggered": False},
        },
        state="WATCH", prior_state=None,
        promotion_confidence=Decimal("0.5"),
        gates_json={"gates": {}, "comparison_fetch_ok": True,
                     "confidence_breakdown": {"basis_warnings": []}},
        verdict_streak=0, readiness_streak=0, rollback_reason=None,
        snapshot_content_hash=None,
        schema_version=1,
        code_version=None,
        evaluated_at_utc=None,
        timezone=None,
    )
    pg_session.add(snap)
    pg_session.commit()
    pg_session.close()

    with pg_factory() as s:
        rep = fetch_and_build_weekly_report(s)
    assert rep is not None
    assert rep.governance.code_version is None
    assert rep.governance.timezone is None
    # No tail_by_regime present → notes mention it
    assert any("tail_by_regime" in n for n in rep.notes)


def test_no_recompute_uses_stored_state_field_verbatim(pg_factory, pg_session):
    """Manually-stored state="WATCH" with bundle implying STRONG_CANDIDATE-
    quality numbers → report says WATCH."""
    bundle = {
        "metrics": {
            "avg_return_diff_1d_bps": 100.0,   # huge edge
            "impact_weighted_edge": 0.5,
            "n_divergent_days": 200,
        },
        "tail": {"tail_delta_p99_bps": 5.0,
                  "tail_delta_p95_bps": 5.0},
        "tail_by_regime": {},
        "verdict": {"verdict": "V2_BETTER", "readiness": "STRONG_CANDIDATE",
                     "confidence": 0.95, "tail_guard_triggered": False},
    }
    _make_snapshot(
        pg_session, iso_week=21, state="WATCH",   # mismatched on purpose
        confidence=0.95, verdict_streak=99, readiness_streak=99,
        bundle=bundle,
    )
    pg_session.close()

    with pg_factory() as s:
        rep = fetch_and_build_weekly_report(s)
    assert rep is not None
    assert rep.state == "WATCH"   # stored state wins
    assert rep.confidence == 0.95
    assert rep.streaks.verdict_streak == 99


# ===========================================================================
# Approval staleness end-to-end
# ===========================================================================

def test_expired_approval_surfaces_in_report(pg_factory, pg_session):
    snap = _make_snapshot(
        pg_session, iso_week=21, state="APPROVED_FOR_SHADOW_REPLACEMENT",
        confidence=0.92, verdict_streak=6, readiness_streak=4,
    )
    snap_dt = dt.datetime(snap.as_of_date.year, snap.as_of_date.month,
                            snap.as_of_date.day, tzinfo=dt.timezone.utc)
    pg_session.add(V2PromotionApproval(
        snapshot_id=snap.id, decision="APPROVE",
        approver="ops@example.com",
        rationale="approval rationale long enough for the test",
        approved_at=snap_dt - dt.timedelta(days=20),
        snapshot_content_hash_at_approval="hash_a",
    ))
    pg_session.commit()
    pg_session.close()

    with pg_factory() as s:
        rep = fetch_and_build_weekly_report(s)
    assert rep is not None
    assert rep.governance.approval_status == "EXPIRED"
    codes = {f.code for f in rep.red_flags}
    assert "APPROVAL_EXPIRED" in codes
    assert rep.recommended_action in ("REVIEW", "INVESTIGATE")
    # Recommended action enum bounded
    assert rep.recommended_action != "APPROVE"
