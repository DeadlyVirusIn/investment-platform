"""Unit tests for v2_oos_monitoring (Phase 10B.2).

Pure-function tests over hand-built snapshot dicts. No DB. All scenarios
deterministic. Verifies:
  * 12 red-flag triggers
  * Assessment rollup (REVIEW > WATCH > NORMAL)
  * recommended_action bounded enum (NEVER APPROVE / EXECUTE)
  * Trend INSUFFICIENT handling
  * Source-of-truth: stored state used verbatim, no recomputation
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import re
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.research.v2_oos_monitoring import (
    APPROVAL_EXPIRY_WARN_DAYS,
    APPROVAL_STALENESS_DAYS,
    EDGE_TREND_DEAD_ZONE_BPS,
    INSUFFICIENT_SAMPLE_PERSIST_WEEKS,
    LATEST_KNOWN_BUNDLE_SCHEMA,
    RAPID_ASCENT_MAX_WEEKS,
    REPORT_SCHEMA_VERSION,
    STREAK_RESET_FREQUENT_THRESHOLD,
    SUSPENDED_REPEAT_THRESHOLD,
    SUSPENDED_REPEAT_WINDOW_WEEKS,
    STATE_APPROVED,
    STATE_NOT_READY,
    STATE_READY_FOR_REVIEW,
    STATE_STRONG_CANDIDATE,
    STATE_SUSPENDED,
    STATE_WATCH,
    TREND_LOOKBACK_WEEKS,
    TREND_PRIOR_WEEKS,
    WeeklyOOSReport,
    build_weekly_report,
    to_jsonable,
)


# ---------------------------------------------------------------------------
# Snapshot stub factory — duck-typed, no DB
# ---------------------------------------------------------------------------

def _snap(
    *,
    snapshot_id: int = 1,
    as_of_date: dt.date | None = None,
    state: str = STATE_WATCH,
    prior_state: str | None = None,
    confidence: float = 0.50,
    verdict_streak: int = 0,
    readiness_streak: int = 0,
    rollback_reason: str | None = None,
    edge_bps: float | None = 5.0,
    impact_weighted_edge: float | None = 0.05,
    n_divergent_days: int = 50,
    tail_guard_triggered: bool = False,
    tail_delta_p99_bps: float | None = 0.0,
    tail_delta_p95_bps: float | None = 0.0,
    tail_by_regime: bool = True,
    gates_passed: dict[str, bool] | None = None,
    gates_reasons: dict[str, str] | None = None,
    comparison_fetch_ok: bool = True,
    basis_warnings: list[str] | None = None,
    snapshot_content_hash: str | None = "hash_a",
    schema_version: int | None = LATEST_KNOWN_BUNDLE_SCHEMA,
    code_version: str | None = "0.1.0",
    timezone: str | None = "UTC",
):
    if as_of_date is None:
        as_of_date = dt.date(2026, 5, 18)
    if gates_passed is None:
        gates_passed = {
            f"gate_{i}_x": True for i in range(1, 9)
        }
    if gates_reasons is None:
        gates_reasons = {k: "ok" for k in gates_passed}
    gates = {
        name: {"name": name,
               "passed": gates_passed[name],
               "reason": gates_reasons.get(name, "ok"),
               "details": {}}
        for name in gates_passed
    }
    return SimpleNamespace(
        id=snapshot_id,
        as_of_date=as_of_date,
        iso_year=as_of_date.isocalendar().year,
        iso_week=as_of_date.isocalendar().week,
        state=state,
        prior_state=prior_state,
        promotion_confidence=Decimal(str(confidence)),
        verdict_streak=verdict_streak,
        readiness_streak=readiness_streak,
        rollback_reason=rollback_reason,
        snapshot_content_hash=snapshot_content_hash,
        schema_version=schema_version,
        code_version=code_version,
        evaluated_at_utc=dt.datetime(
            as_of_date.year, as_of_date.month, as_of_date.day,
            tzinfo=dt.timezone.utc,
        ),
        timezone=timezone,
        comparison_bundle_json={
            "metrics": {
                "avg_return_diff_1d_bps": edge_bps,
                "impact_weighted_edge": impact_weighted_edge,
                "n_divergent_days": n_divergent_days,
            },
            "tail": {
                "tail_delta_p99_bps": tail_delta_p99_bps,
                "tail_delta_p95_bps": tail_delta_p95_bps,
            },
            "tail_by_regime": {} if tail_by_regime else None,
            "verdict": {
                "verdict": "V2_BETTER",
                "readiness": "STRONG_CANDIDATE",
                "confidence": confidence,
                "tail_guard_triggered": tail_guard_triggered,
            },
        },
        gates_json={
            "gates": gates,
            "confidence_breakdown": {
                "total": confidence,
                "basis_warnings": basis_warnings or [],
            },
            "comparison_fetch_ok": comparison_fetch_ok,
        },
    )


def _approval(
    *,
    snapshot_id: int = 1,
    decision: str = "APPROVE",
    approver: str = "ops@example.com",
    rationale: str = "approval rationale text long enough text",
    approved_at: dt.datetime | None = None,
    snapshot_content_hash_at_approval: str | None = "hash_a",
):
    if approved_at is None:
        approved_at = dt.datetime(2026, 5, 18, tzinfo=dt.timezone.utc)
    return SimpleNamespace(
        id=1,
        snapshot_id=snapshot_id,
        decision=decision,
        approver=approver,
        rationale=rationale,
        approved_at=approved_at,
        snapshot_content_hash_at_approval=snapshot_content_hash_at_approval,
    )


def _series_priors(
    n: int,
    *,
    state: str = STATE_WATCH,
    edge_bps: float | None = 5.0,
    base_date: dt.date | None = None,
    verdict_streak: int = 1,
    rollback_reason: str | None = None,
    comparison_fetch_ok: bool = True,
    gates_reasons: dict[str, str] | None = None,
    gates_passed: dict[str, bool] | None = None,
):
    base_date = base_date or dt.date(2026, 1, 5)
    out = []
    for i in range(n):
        d = base_date + dt.timedelta(weeks=i)
        out.append(_snap(
            snapshot_id=100 + i,
            as_of_date=d,
            state=state,
            edge_bps=edge_bps,
            verdict_streak=verdict_streak,
            rollback_reason=rollback_reason,
            comparison_fetch_ok=comparison_fetch_ok,
            gates_reasons=gates_reasons,
            gates_passed=gates_passed,
        ))
    return out


# ===========================================================================
# 1. NORMAL assessment + clean progression
# ===========================================================================

def test_stable_progression_normal_assessment():
    prior = _series_priors(8, state=STATE_STRONG_CANDIDATE, edge_bps=10.0,
                           verdict_streak=4)
    current = _snap(state=STATE_STRONG_CANDIDATE, edge_bps=12.0,
                    confidence=0.85, verdict_streak=5,
                    readiness_streak=3)
    rep = build_weekly_report(
        snapshot=current, prior_snapshots=prior,
        approvals_for_snapshot=[],
    )
    assert rep.assessment == "NORMAL"
    assert rep.red_flags == ()
    assert rep.recommended_action == "NONE"
    # Trend uses prior snapshots only; all priors have same edge → FLAT
    assert rep.edge.trend == "FLAT"


def test_normal_when_no_red_flags():
    prior = _series_priors(8, state=STATE_WATCH, edge_bps=5.0)
    current = _snap(state=STATE_WATCH, edge_bps=5.0, confidence=0.50)
    rep = build_weekly_report(
        snapshot=current, prior_snapshots=prior,
        approvals_for_snapshot=[],
    )
    assert rep.assessment == "NORMAL"
    assert rep.recommended_action == "NONE"


# ===========================================================================
# 2. Streak reset frequent
# ===========================================================================

def test_streak_reset_scenario_flags_watch():
    base = dt.date(2026, 1, 5)
    # Manually craft 8 priors with 4 verdict-streak decreases
    prior = []
    streaks = [1, 2, 0, 1, 2, 0, 1, 0]  # → 3 decreases (idx 1→2, 4→5, 6→7)
    for i, vs in enumerate(streaks):
        prior.append(_snap(
            snapshot_id=100 + i,
            as_of_date=base + dt.timedelta(weeks=i),
            state=STATE_WATCH, edge_bps=5.0,
            verdict_streak=vs,
        ))
    current = _snap(state=STATE_WATCH, verdict_streak=1)
    rep = build_weekly_report(
        snapshot=current, prior_snapshots=prior,
        approvals_for_snapshot=[],
    )
    codes = {f.code for f in rep.red_flags}
    assert "STREAK_RESET_FREQUENT" in codes
    assert rep.assessment == "WATCH"
    assert rep.recommended_action == "REVIEW"


# ===========================================================================
# 3. Tail emergency → REVIEW_REQUIRED
# ===========================================================================

def test_tail_emergency_flags_review_required():
    prior = _series_priors(8, state=STATE_WATCH)
    current = _snap(
        state=STATE_SUSPENDED, edge_bps=12.0, confidence=0.47,
        verdict_streak=0, readiness_streak=0,
        rollback_reason="tail-risk emergency: tail_delta_p99_bps -28.00 < hard floor -25.0",
        tail_guard_triggered=True, tail_delta_p99_bps=-28.0,
    )
    rep = build_weekly_report(
        snapshot=current, prior_snapshots=prior,
        approvals_for_snapshot=[],
    )
    codes = {f.code for f in rep.red_flags}
    assert "TAIL_EMERGENCY" in codes
    assert rep.assessment == "REVIEW_REQUIRED"
    assert rep.recommended_action == "INVESTIGATE"


def test_repeated_suspended_within_window():
    base = dt.date(2026, 1, 5)
    prior = []
    # First SUSPENDED 6 weeks ago, current also SUSPENDED → 2 in 12-week window
    for i in range(6):
        prior.append(_snap(
            snapshot_id=100 + i,
            as_of_date=base + dt.timedelta(weeks=i),
            state=STATE_WATCH,
        ))
    prior.append(_snap(
        snapshot_id=200,
        as_of_date=base + dt.timedelta(weeks=6),
        state=STATE_SUSPENDED,
        rollback_reason="tail-risk emergency: 2 consecutive guards",
    ))
    for i in range(7, 11):
        prior.append(_snap(
            snapshot_id=210 + i,
            as_of_date=base + dt.timedelta(weeks=i),
            state=STATE_NOT_READY,
        ))
    current = _snap(
        as_of_date=base + dt.timedelta(weeks=11),
        state=STATE_SUSPENDED,
        rollback_reason="tail-risk emergency: hard p99 breach",
    )
    rep = build_weekly_report(
        snapshot=current, prior_snapshots=prior,
        approvals_for_snapshot=[],
    )
    codes = {f.code for f in rep.red_flags}
    assert "REPEATED_SUSPENDED" in codes
    assert rep.assessment == "REVIEW_REQUIRED"


# ===========================================================================
# 4. Approval staleness
# ===========================================================================

def test_stale_approval_flags_watch():
    prior = _series_priors(8, state=STATE_APPROVED, verdict_streak=4)
    snap_date = dt.date(2026, 5, 18)
    current = _snap(
        as_of_date=snap_date,
        state=STATE_APPROVED, confidence=0.92,
        verdict_streak=6, readiness_streak=4,
    )
    # Approval 20 days ago → expired
    old_approval = _approval(
        approved_at=dt.datetime(snap_date.year, snap_date.month,
                                  snap_date.day, tzinfo=dt.timezone.utc)
            - dt.timedelta(days=20),
    )
    rep = build_weekly_report(
        snapshot=current, prior_snapshots=prior,
        approvals_for_snapshot=[old_approval],
    )
    codes = {f.code for f in rep.red_flags}
    assert "APPROVAL_EXPIRED" in codes
    assert rep.governance.approval_status == "EXPIRED"
    assert rep.governance.is_stale is True


def test_approval_expiring_soon_flag():
    prior = _series_priors(8, state=STATE_APPROVED, verdict_streak=4)
    snap_date = dt.date(2026, 5, 18)
    current = _snap(
        as_of_date=snap_date, state=STATE_APPROVED,
        confidence=0.92, verdict_streak=6, readiness_streak=4,
    )
    # Approval 11 days ago → 3 days until expiry
    fresh_approval = _approval(
        approved_at=dt.datetime(snap_date.year, snap_date.month,
                                  snap_date.day, tzinfo=dt.timezone.utc)
            - dt.timedelta(days=11),
    )
    rep = build_weekly_report(
        snapshot=current, prior_snapshots=prior,
        approvals_for_snapshot=[fresh_approval],
    )
    codes = {f.code for f in rep.red_flags}
    assert "APPROVAL_EXPIRING_SOON" in codes
    assert rep.governance.days_until_expiry == 3


def test_approval_hash_mismatch_flags_review():
    prior = _series_priors(8, state=STATE_APPROVED)
    snap_date = dt.date(2026, 5, 18)
    current = _snap(
        as_of_date=snap_date, state=STATE_APPROVED,
        snapshot_content_hash="hash_NEW",
        confidence=0.92, verdict_streak=5, readiness_streak=3,
    )
    # Approval against an OLD hash
    stale = _approval(
        snapshot_content_hash_at_approval="hash_OLD",
        approved_at=dt.datetime(snap_date.year, snap_date.month,
                                  snap_date.day, tzinfo=dt.timezone.utc)
            - dt.timedelta(days=2),
    )
    rep = build_weekly_report(
        snapshot=current, prior_snapshots=prior,
        approvals_for_snapshot=[stale],
    )
    codes = {f.code for f in rep.red_flags}
    assert "APPROVAL_HASH_MISMATCH" in codes
    assert rep.assessment == "REVIEW_REQUIRED"


# ===========================================================================
# 5. High confidence + failing gate
# ===========================================================================

def test_high_conf_with_failing_gate():
    prior = _series_priors(8, state=STATE_READY_FOR_REVIEW, edge_bps=7.0)
    gates_passed = {f"gate_{i}_x": True for i in range(1, 9)}
    gates_passed["gate_5_regime_validation"] = False
    current = _snap(
        state=STATE_READY_FOR_REVIEW, edge_bps=7.0,
        confidence=0.78,
        gates_passed=gates_passed,
    )
    rep = build_weekly_report(
        snapshot=current, prior_snapshots=prior,
        approvals_for_snapshot=[],
    )
    codes = {f.code for f in rep.red_flags}
    assert "HIGH_CONF_FAILING_GATES" in codes
    assert rep.assessment == "REVIEW_REQUIRED"
    assert rep.recommended_action == "INVESTIGATE"


def test_failing_gate8_alone_does_not_trigger_high_conf_flag():
    """Gate 8 (operator approval) failing is normal in non-APPROVED states."""
    prior = _series_priors(8, state=STATE_STRONG_CANDIDATE)
    gates_passed = {f"gate_{i}_x": True for i in range(1, 8)}
    gates_passed["gate_8_operator_approval"] = False
    current = _snap(
        state=STATE_STRONG_CANDIDATE, confidence=0.85,
        gates_passed=gates_passed,
    )
    rep = build_weekly_report(
        snapshot=current, prior_snapshots=prior,
        approvals_for_snapshot=[],
    )
    codes = {f.code for f in rep.red_flags}
    assert "HIGH_CONF_FAILING_GATES" not in codes


# ===========================================================================
# 6. Rapid ascent
# ===========================================================================

def test_rapid_ascent_flagged():
    base = dt.date(2026, 1, 5)
    prior = []
    # NOT_READY at idx 0, then WATCH→READY→STRONG by idx 4 = 4 weeks
    states_seq = [STATE_NOT_READY, STATE_WATCH, STATE_READY_FOR_REVIEW,
                  STATE_READY_FOR_REVIEW]
    for i, st in enumerate(states_seq):
        prior.append(_snap(
            snapshot_id=100 + i,
            as_of_date=base + dt.timedelta(weeks=i),
            state=st,
        ))
    current = _snap(
        as_of_date=base + dt.timedelta(weeks=4),
        state=STATE_STRONG_CANDIDATE, confidence=0.81,
        verdict_streak=4, readiness_streak=2,
    )
    rep = build_weekly_report(
        snapshot=current, prior_snapshots=prior,
        approvals_for_snapshot=[],
    )
    codes = {f.code for f in rep.red_flags}
    assert "RAPID_ASCENT" in codes


# ===========================================================================
# 7. Insufficient sample persist
# ===========================================================================

def test_insufficient_sample_persist():
    prior = []
    base = dt.date(2026, 1, 5)
    for i in range(2):
        prior.append(_snap(
            snapshot_id=100 + i,
            as_of_date=base + dt.timedelta(weeks=i),
            state=STATE_NOT_READY,
            gates_reasons={
                "gate_4_x": "INSUFFICIENT_TAIL_SAMPLE: n_div=20"
            } | {f"gate_{i}_x": "ok" for i in (1, 2, 3, 5, 6, 7, 8)},
            gates_passed={"gate_4_x": False} |
                {f"gate_{i}_x": True for i in (1, 2, 3, 5, 6, 7, 8)},
        ))
    current = _snap(
        as_of_date=base + dt.timedelta(weeks=2),
        state=STATE_NOT_READY,
        gates_reasons={
            "gate_4_x": "INSUFFICIENT_TAIL_SAMPLE: n_div=22"
        } | {f"gate_{i}_x": "ok" for i in (1, 2, 3, 5, 6, 7, 8)},
        gates_passed={"gate_4_x": False} |
            {f"gate_{i}_x": True for i in (1, 2, 3, 5, 6, 7, 8)},
    )
    rep = build_weekly_report(
        snapshot=current, prior_snapshots=prior,
        approvals_for_snapshot=[],
    )
    codes = {f.code for f in rep.red_flags}
    assert "INSUFFICIENT_SAMPLE_PERSIST" in codes


# ===========================================================================
# 8. Comparison framework health degraded
# ===========================================================================

def test_comparison_fetch_degraded_flagged():
    base = dt.date(2026, 1, 5)
    prior = []
    # 6 priors with 2 fetch failures + current with another → 3/7 failures
    fetch_states = [True, False, True, True, False, True]
    for i, ok in enumerate(fetch_states):
        prior.append(_snap(
            snapshot_id=100 + i,
            as_of_date=base + dt.timedelta(weeks=i),
            state=STATE_WATCH, comparison_fetch_ok=ok,
        ))
    current = _snap(
        as_of_date=base + dt.timedelta(weeks=6),
        state=STATE_WATCH, comparison_fetch_ok=False,
    )
    rep = build_weekly_report(
        snapshot=current, prior_snapshots=prior,
        approvals_for_snapshot=[],
    )
    codes = {f.code for f in rep.red_flags}
    assert "COMPARISON_HEALTH_DEGRADED" in codes
    assert rep.assessment == "REVIEW_REQUIRED"


# ===========================================================================
# 9. Confidence basis warnings
# ===========================================================================

def test_confidence_basis_warnings_surfaced():
    prior = _series_priors(8, state=STATE_WATCH)
    current = _snap(
        state=STATE_WATCH,
        basis_warnings=[
            "stability: last_30 trend INSUFFICIENT (insufficient history)",
            "edge_trend: insufficient impact-weighted history",
        ],
    )
    rep = build_weekly_report(
        snapshot=current, prior_snapshots=prior,
        approvals_for_snapshot=[],
    )
    codes = {f.code for f in rep.red_flags}
    assert "CONFIDENCE_BASIS_WARNINGS" in codes
    flag = next(f for f in rep.red_flags if f.code == "CONFIDENCE_BASIS_WARNINGS")
    assert flag.severity == "INFO"


# ===========================================================================
# 10. Bundle schema downgrade
# ===========================================================================

def test_bundle_schema_downgrade_flagged():
    prior = _series_priors(8, state=STATE_WATCH)
    current = _snap(
        state=STATE_WATCH,
        schema_version=LATEST_KNOWN_BUNDLE_SCHEMA - 1,
    )
    rep = build_weekly_report(
        snapshot=current, prior_snapshots=prior,
        approvals_for_snapshot=[],
    )
    codes = {f.code for f in rep.red_flags}
    assert "BUNDLE_SCHEMA_DOWNGRADE" in codes


# ===========================================================================
# 11. Recommended action rollup
# ===========================================================================

def test_recommended_action_do_not_approve_when_strong_with_review():
    """STRONG_CANDIDATE + REVIEW-severity flag → DO_NOT_APPROVE."""
    prior = _series_priors(8, state=STATE_STRONG_CANDIDATE,
                           comparison_fetch_ok=False)
    current = _snap(
        state=STATE_STRONG_CANDIDATE, confidence=0.85,
        verdict_streak=5, readiness_streak=3,
        comparison_fetch_ok=False,
    )
    rep = build_weekly_report(
        snapshot=current, prior_snapshots=prior,
        approvals_for_snapshot=[],
    )
    has_review = any(f.severity == "REVIEW" for f in rep.red_flags)
    assert has_review
    assert rep.recommended_action == "DO_NOT_APPROVE"


def test_assessment_rollup_review_dominates_watch():
    """One REVIEW + multiple WATCH → REVIEW_REQUIRED."""
    base = dt.date(2026, 1, 5)
    prior = []
    # Build streak resets for WATCH-flag + comparison fetch failures for REVIEW
    for i, ok in enumerate([True, False, True, False, True, False, True]):
        prior.append(_snap(
            snapshot_id=100 + i,
            as_of_date=base + dt.timedelta(weeks=i),
            state=STATE_WATCH, verdict_streak=(i % 2),
            comparison_fetch_ok=ok,
        ))
    current = _snap(
        as_of_date=base + dt.timedelta(weeks=7),
        state=STATE_WATCH, verdict_streak=0,
        comparison_fetch_ok=False,
    )
    rep = build_weekly_report(
        snapshot=current, prior_snapshots=prior,
        approvals_for_snapshot=[],
    )
    severities = {f.severity for f in rep.red_flags}
    assert "REVIEW" in severities
    assert rep.assessment == "REVIEW_REQUIRED"


def test_recommended_action_never_approve():
    """Recommended action enum is bounded — never APPROVE / EXECUTE."""
    valid = {"NONE", "REVIEW", "INVESTIGATE", "DO_NOT_APPROVE"}
    # Smoke through several scenarios
    scenarios = [
        (STATE_NOT_READY, []),
        (STATE_WATCH, []),
        (STATE_STRONG_CANDIDATE, []),
        (STATE_APPROVED, []),
    ]
    for state, _ in scenarios:
        prior = _series_priors(8, state=state)
        current = _snap(state=state)
        rep = build_weekly_report(
            snapshot=current, prior_snapshots=prior,
            approvals_for_snapshot=[],
        )
        assert rep.recommended_action in valid


# ===========================================================================
# 12. Trend INSUFFICIENT + history depth
# ===========================================================================

def test_insufficient_history_does_not_red_flag():
    """Only 2 prior snapshots → trend=INSUFFICIENT, no red flags from history."""
    prior = _series_priors(2, state=STATE_WATCH)
    current = _snap(state=STATE_WATCH, edge_bps=5.0)
    rep = build_weekly_report(
        snapshot=current, prior_snapshots=prior,
        approvals_for_snapshot=[],
    )
    assert rep.edge.trend == "INSUFFICIENT"
    assert rep.edge.last_4w_avg_edge_bps is None
    # No red flags purely from history depth
    history_codes = {"STREAK_RESET_FREQUENT", "RAPID_ASCENT",
                      "REPEATED_SUSPENDED", "INSUFFICIENT_SAMPLE_PERSIST",
                      "COMPARISON_HEALTH_DEGRADED"}
    actual = {f.code for f in rep.red_flags}
    assert actual.isdisjoint(history_codes)


def test_edge_trend_up():
    prior = []
    base = dt.date(2026, 1, 5)
    # 4 prior weeks edge_bps=5, then 4 weeks edge_bps=15 → UP
    for i in range(4):
        prior.append(_snap(
            snapshot_id=100 + i, as_of_date=base + dt.timedelta(weeks=i),
            state=STATE_WATCH, edge_bps=5.0,
        ))
    for i in range(4, 8):
        prior.append(_snap(
            snapshot_id=100 + i, as_of_date=base + dt.timedelta(weeks=i),
            state=STATE_WATCH, edge_bps=15.0,
        ))
    current = _snap(state=STATE_WATCH, edge_bps=15.0)
    rep = build_weekly_report(
        snapshot=current, prior_snapshots=prior,
        approvals_for_snapshot=[],
    )
    assert rep.edge.trend == "UP"
    assert rep.edge.slope_bps_per_week is not None
    assert rep.edge.slope_bps_per_week > 0


def test_edge_trend_down():
    prior = []
    base = dt.date(2026, 1, 5)
    for i in range(4):
        prior.append(_snap(
            snapshot_id=100 + i, as_of_date=base + dt.timedelta(weeks=i),
            state=STATE_WATCH, edge_bps=15.0,
        ))
    for i in range(4, 8):
        prior.append(_snap(
            snapshot_id=100 + i, as_of_date=base + dt.timedelta(weeks=i),
            state=STATE_WATCH, edge_bps=5.0,
        ))
    current = _snap(state=STATE_WATCH, edge_bps=5.0)
    rep = build_weekly_report(
        snapshot=current, prior_snapshots=prior,
        approvals_for_snapshot=[],
    )
    assert rep.edge.trend == "DOWN"


def test_edge_trend_flat_within_dead_zone():
    prior = _series_priors(8, edge_bps=5.0)
    current = _snap(state=STATE_WATCH, edge_bps=5.2)
    rep = build_weekly_report(
        snapshot=current, prior_snapshots=prior,
        approvals_for_snapshot=[],
    )
    assert rep.edge.trend == "FLAT"


# ===========================================================================
# 13. Source of truth + determinism
# ===========================================================================

def test_no_recompute_uses_stored_state_field_verbatim():
    """Manually crafted snapshot.state="WATCH" with bundle implying STRONG →
    report says WATCH (no recomputation)."""
    prior = _series_priors(8, state=STATE_STRONG_CANDIDATE)
    current = _snap(
        state=STATE_WATCH,
        confidence=0.95,
        verdict_streak=99,
        readiness_streak=99,
        edge_bps=100.0,
    )
    rep = build_weekly_report(
        snapshot=current, prior_snapshots=prior,
        approvals_for_snapshot=[],
    )
    assert rep.state == STATE_WATCH
    assert rep.confidence == 0.95
    assert rep.streaks.verdict_streak == 99


def test_report_is_deterministic():
    prior = _series_priors(8, state=STATE_STRONG_CANDIDATE)
    current = _snap(state=STATE_STRONG_CANDIDATE)
    r1 = build_weekly_report(
        snapshot=current, prior_snapshots=prior,
        approvals_for_snapshot=[],
    )
    r2 = build_weekly_report(
        snapshot=current, prior_snapshots=prior,
        approvals_for_snapshot=[],
    )
    assert r1 == r2


def test_report_to_jsonable_serializable():
    prior = _series_priors(8, state=STATE_WATCH)
    current = _snap(state=STATE_WATCH)
    rep = build_weekly_report(
        snapshot=current, prior_snapshots=prior,
        approvals_for_snapshot=[],
    )
    out = to_jsonable(rep)
    json.dumps(out)   # round-trip via stdlib json
    assert out["schema_version"] == REPORT_SCHEMA_VERSION
    assert out["recommended_action"] in ("NONE", "REVIEW", "INVESTIGATE",
                                           "DO_NOT_APPROVE")


def test_week_string_format():
    prior = _series_priors(8, state=STATE_WATCH)
    current = _snap(as_of_date=dt.date(2026, 5, 18), state=STATE_WATCH)
    rep = build_weekly_report(
        snapshot=current, prior_snapshots=prior,
        approvals_for_snapshot=[],
    )
    assert re.match(r"^\d{4}-W\d{2}$", rep.week)
    assert rep.week == "2026-W21"


# ===========================================================================
# 14. Hard boundary: no execution / governance imports
# ===========================================================================

_FORBIDDEN_PATTERNS = [
    r"\bv2_promotion_state\b",
    r"\bv2_promotion_gates\b",
    r"\bengine_b\w*",
    r"\bshadow_strategy\w*",
    r"\bpaper_trade_log\b",
    r"\bdecision_log\b",
    r"\brun_v2_promotion_snapshot\b",
    r"\btick_loop\b",
    r"\bregistry\b",
    r"\bml_\w+",
    r"\btensorflow\b", r"\bsklearn\b", r"\btorch\b", r"\bxgboost\b",
    r"\bevaluate_gate\w*",
    r"\badvance_or_rollback\b",
    r"\bupdate_streaks\b",
    r"\bcompute_promotion_confidence\b",
    r"\brequests\b", r"\bhttpx\b", r"\baiohttp\b",
]


def _module_source() -> str:
    here = Path(__file__).resolve()
    src = (
        here.parent.parent.parent
        / "src" / "research" / "v2_oos_monitoring.py"
    )
    return src.read_text(encoding="utf-8")


def test_no_forbidden_imports_in_module():
    src = _module_source()
    import_lines = [
        ln for ln in src.splitlines()
        if ln.strip().startswith(("import ", "from "))
    ]
    joined = "\n".join(import_lines)
    for pat in _FORBIDDEN_PATTERNS:
        assert not re.search(pat, joined, re.IGNORECASE), (
            f"forbidden pattern {pat!r} in imports:\n{joined}"
        )


def test_no_mutating_sql_in_module():
    src = _module_source()
    for pattern in (r"\bINSERT\b", r"\bUPDATE\s+\w+\s+SET\b",
                     r"\bDELETE\s+FROM\b", r"session\.add\b",
                     r"session\.commit\b", r"session\.delete\b",
                     r"session\.merge\b", r"session\.flush\b"):
        # Allow comments / docstrings to mention these words; check code
        for line in src.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith('"""'):
                continue
            assert not re.search(pattern, line), (
                f"forbidden mutating pattern {pattern!r} in code line:\n{line}"
            )


def test_module_does_not_import_run_v2_promotion_snapshot():
    src = _module_source()
    assert "run_v2_promotion_snapshot" not in src
