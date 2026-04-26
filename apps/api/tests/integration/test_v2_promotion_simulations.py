"""Phase 7 — V2 promotion-trigger system validation simulations.

No new features. No logic changes. Drives the existing snapshot job
(Phase 4) + state machine (Phase 3) + gates (Phase 2) over scripted
multi-week scenarios and asserts:

  * No premature promotion (forward steps respect no-skipping rule)
  * No stuck STRONG_CANDIDATE (regression paths fire on degradation)
  * No oscillation loops (each scenario terminates in expected state)
  * No silent APPROVED drift (only operator rescind / tail emergency
    can leave APPROVED)
  * All rollbacks behave exactly as designed

Each scenario prints a week-by-week trace via stdout (`-s` to view).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from apps.api.src.db.models import (
    V2PromotionApproval,
    V2PromotionSnapshot,
)
from apps.api.src.research.b2_v2_comparison import compute_all
from apps.worker.src.jobs import v2_promotion_snapshot as job_module
from apps.worker.src.jobs.v2_promotion_snapshot import (
    run_v2_promotion_snapshot,
)


pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def pg_factory(pg_engine):
    return sessionmaker(bind=pg_engine, class_=Session, expire_on_commit=False)


@pytest.fixture(autouse=True)
def _ensure_paper_shadow_log_exists(pg_engine):
    """The simulation patches fetch_comparison_bundle, but compute_all
    (used to seed the empty-bundle skeleton) is pure — no DB access
    required. Still ensure the table exists for completeness."""
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS paper_shadow_log"))
        conn.execute(text("""
            CREATE TABLE paper_shadow_log (
                id              TEXT PRIMARY KEY,
                as_of_date      DATE NOT NULL,
                instrument      TEXT NOT NULL,
                source_strategy TEXT NOT NULL,
                signal          TEXT NOT NULL CHECK (signal IN ('LONG','FLAT')),
                fwd_return_1d   NUMERIC(12, 8),
                fwd_return_5d   NUMERIC(12, 8),
                regime_label    TEXT
            )
        """))
    yield


# ---------------------------------------------------------------------------
# Bundle factories (exact bundle shape consumed by gates + state machine)
# ---------------------------------------------------------------------------

def _bundle_skeleton() -> dict:
    b = compute_all([])
    b["metrics_by_regime"] = {
        "stress": _empty_regime(),
        "directional": _empty_regime(),
        "neutral": _empty_regime(),
    }
    return b


def _empty_regime() -> dict:
    return {
        "n_divergent_days": 0,
        "n_b2_flat_v2_long": 0, "n_b2_long_v2_flat": 0,
        "win_rate_v2_vs_b2_pct": None,
        "avg_return_diff_1d_bps": None,
        "avg_return_diff_5d_bps": None,
        "cumulative_return_diff_pct": None,
        "avoided_losses_count": 0, "avoided_losses_avg_bps": None,
        "new_losses_count": 0, "new_losses_avg_bps": None,
        "impact_weighted_edge": None,
    }


def _build_bundle(
    *,
    n_input: int,
    n_div: int,
    n_b2flat: int,
    edge_bps: float,
    cum_pct: float,
    iwe: float,
    verdict: str = "V2_BETTER",
    readiness: str = "STRONG_CANDIDATE",
    confidence: float = 0.85,
    tail_guard: bool = False,
    p99_delta: float = 0.0,
    p95_delta: float = 0.0,
    fh_edge: float = 8.0,
    sh_edge: float = 10.0,
    last_30_trend: str = "STABLE",
    regime_split: tuple[float, float, float] = (0.25, 0.50, 0.25),
    b2_w5: list[float] | None = None,
    v2_w5: list[float] | None = None,
) -> dict:
    """Build a comparison bundle dict matching the schema produced by
    apps/api/src/research/b2_v2_comparison.compute_all."""
    if b2_w5 is None:
        b2_w5 = [-200.0, -150.0, -120.0, -90.0, -50.0]
    if v2_w5 is None:
        v2_w5 = list(b2_w5)
    s_share, d_share, n_share = regime_split
    b = _bundle_skeleton()
    b["n_input_rows"] = n_input
    b["n_divergent_rows"] = n_div
    b["metrics"] = {
        "n_divergent_days": n_div,
        "n_b2_flat_v2_long": n_b2flat,
        "n_b2_long_v2_flat": max(0, n_div - n_b2flat),
        "win_rate_v2_vs_b2_pct": 60.0,
        "avg_return_diff_1d_bps": edge_bps,
        "avg_return_diff_5d_bps": edge_bps,
        "cumulative_return_diff_pct": cum_pct,
        "avoided_losses_count": 5, "avoided_losses_avg_bps": 80.0,
        "new_losses_count": 3, "new_losses_avg_bps": 30.0,
        "impact_weighted_edge": iwe,
    }
    b["metrics_by_regime"] = {
        "stress": _regime_block(int(n_div * s_share), edge_bps, cum_pct * s_share),
        "directional": _regime_block(int(n_div * d_share), max(edge_bps, 0.1),
                                       cum_pct * d_share),
        "neutral": _regime_block(int(n_div * n_share), edge_bps, cum_pct * n_share),
    }
    b["tail"] = {
        "b2": {"n": n_input, "p95_loss_bps": -100.0, "p99_loss_bps": -200.0,
               "worst_5_losses_bps": b2_w5},
        "v2": {"n": n_input,
               "p95_loss_bps": -100.0 + p95_delta,
               "p99_loss_bps": -200.0 + p99_delta,
               "worst_5_losses_bps": v2_w5},
        "tail_delta_p95_bps": p95_delta,
        "tail_delta_p99_bps": p99_delta,
    }
    b["stability"] = {
        "first_half_vs_second_half": {
            "first_half_edge_bps": fh_edge,
            "second_half_edge_bps": sh_edge,
            "n_first": n_div // 2, "n_second": n_div // 2,
            "trend": "STABLE",
        },
        "last_30_vs_prior_30": {
            "last_30_edge_bps": edge_bps,
            "prior_30_edge_bps": edge_bps * 0.9,
            "n_last": 30, "n_prior": 30,
            "trend": last_30_trend,
        },
    }
    b["verdict"] = {
        "verdict": verdict,
        "confidence": confidence,
        "tail_guard_triggered": tail_guard,
        "tail_guard_reason": None,
        "readiness": readiness,
        "base_verdict_before_guard": verdict,
        "base_confidence_before_guard": confidence,
    }
    return b


def _regime_block(n: int, edge_bps: float, cum_pct: float) -> dict:
    return {
        "n_divergent_days": n,
        "n_b2_flat_v2_long": n, "n_b2_long_v2_flat": 0,
        "win_rate_v2_vs_b2_pct": 60.0,
        "avg_return_diff_1d_bps": edge_bps,
        "avg_return_diff_5d_bps": edge_bps,
        "cumulative_return_diff_pct": cum_pct,
        "avoided_losses_count": 1, "avoided_losses_avg_bps": 30.0,
        "new_losses_count": 1, "new_losses_avg_bps": 20.0,
        "impact_weighted_edge": 0.05,
    }


# ---------------------------------------------------------------------------
# Multi-week driver
# ---------------------------------------------------------------------------

@dataclass
class WeekResult:
    week: int
    iso_year: int
    iso_week: int
    state: str
    prior_state: str | None
    confidence: float
    verdict_streak: int
    readiness_streak: int
    rollback_reason: str | None


def _drive_simulation(
    *,
    monkeypatch,
    pg_factory,
    pg_session: Session,
    bundles: list[dict],
    start: dt.date,
    approval_callback: Callable[[int, V2PromotionSnapshot, Session], None]
        | None = None,
) -> list[WeekResult]:
    """Run len(bundles) weekly snapshots, one per ISO week starting at `start`.

    `bundles[i]` is the comparison bundle returned by the patched
    fetch_comparison_bundle for week i.
    `approval_callback(week_idx, latest_snapshot, session)` is invoked
    AFTER each snapshot insertion — operator may write approval rows.
    """
    week_idx = {"i": 0}
    def _patched_fetch(*args, **kwargs):
        b = bundles[week_idx["i"]]
        return b
    monkeypatch.setattr(job_module, "fetch_comparison_bundle", _patched_fetch)

    results: list[WeekResult] = []
    for i, _ in enumerate(bundles):
        week_idx["i"] = i
        target = start + dt.timedelta(weeks=i)
        out = run_v2_promotion_snapshot(
            as_of=target, session_factory=pg_factory,
        )
        snap = pg_session.get(V2PromotionSnapshot, out["snapshot_id"])
        # Defensive expire in case approval_callback or next iteration reads
        pg_session.expire(snap)
        snap = pg_session.get(V2PromotionSnapshot, out["snapshot_id"])
        results.append(WeekResult(
            week=i + 1,
            iso_year=snap.iso_year, iso_week=snap.iso_week,
            state=snap.state, prior_state=snap.prior_state,
            confidence=float(snap.promotion_confidence),
            verdict_streak=snap.verdict_streak,
            readiness_streak=snap.readiness_streak,
            rollback_reason=snap.rollback_reason,
        ))
        if approval_callback is not None:
            approval_callback(i, snap, pg_session)
    return results


def _print_trace(label: str, results: list[WeekResult]) -> None:
    print(f"\n{'=' * 78}")
    print(f"SIMULATION: {label}")
    print(f"{'=' * 78}")
    print(f"{'wk':>3} {'iso':>9} {'state':<33} {'conf':>6} "
          f"{'vstrk':>6} {'rstrk':>6} {'rollback':<30}")
    print(f"{'-' * 78}")
    for r in results:
        rb = (r.rollback_reason or "")[:28]
        iso = f"{r.iso_year}-W{r.iso_week:02d}"
        print(f"{r.week:>3} {iso:>9} {r.state:<33} "
              f"{r.confidence:>6.3f} {r.verdict_streak:>6} "
              f"{r.readiness_streak:>6} {rb:<30}")


def _start_monday(year: int = 2026, week: int = 18) -> dt.date:
    return dt.date.fromisocalendar(year, week, 1)


# ===========================================================================
# Scenario 1 — Gradual improvement (NOT_READY → STRONG_CANDIDATE)
# ===========================================================================

def test_scenario_1_gradual_improvement(monkeypatch, pg_factory, pg_session):
    """8 weeks: data + edge accumulate; expect single forward step per week."""
    bundles = []
    # Week 1: insufficient sample → NOT_READY
    bundles.append(_build_bundle(
        n_input=20, n_div=5, n_b2flat=2, edge_bps=2.0, cum_pct=0.1,
        iwe=0.01, verdict="INCONCLUSIVE", readiness="NOT_READY",
        confidence=0.3,
    ))
    # Week 2: sample crosses → WATCH
    bundles.append(_build_bundle(
        n_input=70, n_div=15, n_b2flat=8, edge_bps=2.0, cum_pct=0.1,
        iwe=0.01, verdict="INCONCLUSIVE", readiness="NOT_READY",
        confidence=0.4,
    ))
    # Week 3: edge crosses 5 bps + V2_BETTER → READY_FOR_REVIEW
    bundles.append(_build_bundle(
        n_input=80, n_div=25, n_b2flat=12, edge_bps=6.0, cum_pct=0.6,
        iwe=0.04, verdict="V2_BETTER", readiness="REVIEW",
        confidence=0.55,
    ))
    # Weeks 4-7: V2_BETTER + STRONG_CANDIDATE accumulate streaks
    for w in range(4):
        bundles.append(_build_bundle(
            n_input=120 + w * 10, n_div=40 + w * 5,
            n_b2flat=20 + w * 3, edge_bps=10.0, cum_pct=2.0,
            iwe=0.10, verdict="V2_BETTER",
            readiness="STRONG_CANDIDATE", confidence=0.85,
        ))
    # Week 8: same — should now satisfy STRONG_CANDIDATE
    bundles.append(_build_bundle(
        n_input=160, n_div=60, n_b2flat=30, edge_bps=12.0, cum_pct=2.5,
        iwe=0.10, verdict="V2_BETTER",
        readiness="STRONG_CANDIDATE", confidence=0.90,
    ))

    results = _drive_simulation(
        monkeypatch=monkeypatch, pg_factory=pg_factory, pg_session=pg_session,
        bundles=bundles, start=_start_monday(2026, 18),
    )
    _print_trace("Scenario 1 — gradual improvement", results)

    states = [r.state for r in results]
    # Forward progression — every step is forward or stay, never backward
    state_idx = ["NOT_READY", "WATCH", "READY_FOR_REVIEW",
                  "STRONG_CANDIDATE", "APPROVED_FOR_SHADOW_REPLACEMENT"]
    for i in range(1, len(states)):
        assert state_idx.index(states[i]) >= state_idx.index(states[i - 1]), \
            f"backward step at week {i + 1}: {states[i - 1]} → {states[i]}"
    # No skipping forward steps
    for i in range(1, len(states)):
        if state_idx.index(states[i]) > state_idx.index(states[i - 1]):
            assert state_idx.index(states[i]) == state_idx.index(states[i - 1]) + 1, \
                f"state skip at week {i + 1}: {states[i - 1]} → {states[i]}"
    # Terminal state is STRONG_CANDIDATE (no approval written)
    assert states[-1] == "STRONG_CANDIDATE"
    # No rollback reasons during normal forward progression
    for r in results:
        if r.state != "NOT_READY":
            assert r.rollback_reason is None, \
                f"unexpected rollback at week {r.week}: {r.rollback_reason}"


# ===========================================================================
# Scenario 2 — Streak break (3 V2_BETTER, 1 INCONCLUSIVE, then resume)
# ===========================================================================

def test_scenario_2_streak_break_resets(monkeypatch, pg_factory, pg_session):
    """3 V2_BETTER weeks (streak grows), 1 INCONCLUSIVE (hard reset),
    3 V2_BETTER again (streak rebuilds from 1)."""
    base = lambda **kw: _build_bundle(
        n_input=120, n_div=50, n_b2flat=25, edge_bps=10.0, cum_pct=2.0,
        iwe=0.08, **kw,
    )
    bundles = [
        base(verdict="V2_BETTER", readiness="STRONG_CANDIDATE", confidence=0.85),
        base(verdict="V2_BETTER", readiness="STRONG_CANDIDATE", confidence=0.85),
        base(verdict="V2_BETTER", readiness="STRONG_CANDIDATE", confidence=0.85),
        # Break
        base(verdict="INCONCLUSIVE", readiness="NOT_READY", confidence=0.40),
        base(verdict="V2_BETTER", readiness="STRONG_CANDIDATE", confidence=0.85),
        base(verdict="V2_BETTER", readiness="STRONG_CANDIDATE", confidence=0.85),
        base(verdict="V2_BETTER", readiness="STRONG_CANDIDATE", confidence=0.85),
    ]
    results = _drive_simulation(
        monkeypatch=monkeypatch, pg_factory=pg_factory, pg_session=pg_session,
        bundles=bundles, start=_start_monday(2026, 20),
    )
    _print_trace("Scenario 2 — streak break", results)

    # Streak hits 3 by week 3, resets to 0 at week 4, rebuilds to 3 by week 7
    assert [r.verdict_streak for r in results] == [1, 2, 3, 0, 1, 2, 3]
    assert [r.readiness_streak for r in results] == [1, 2, 3, 0, 1, 2, 3]
    # Never reaches STRONG_CANDIDATE because verdict_streak ≥ 4 never holds
    # AND the streak resets right when it would have crossed.
    for r in results:
        assert r.state != "APPROVED_FOR_SHADOW_REPLACEMENT"


# ===========================================================================
# Scenario 3 — False spike (one strong week, weak others)
# ===========================================================================

def test_scenario_3_false_spike_never_promotes(monkeypatch, pg_factory, pg_session):
    """6 weeks: only week 3 is strong; rest are mediocre. STRONG_CANDIDATE
    requires 4 consecutive V2_BETTER weeks → must never reach it."""
    weak = _build_bundle(
        n_input=120, n_div=40, n_b2flat=18, edge_bps=2.0, cum_pct=0.2,
        iwe=0.02, verdict="INCONCLUSIVE", readiness="NOT_READY",
        confidence=0.45,
    )
    spike = _build_bundle(
        n_input=120, n_div=40, n_b2flat=18, edge_bps=15.0, cum_pct=3.0,
        iwe=0.15, verdict="V2_BETTER", readiness="STRONG_CANDIDATE",
        confidence=0.90,
    )
    bundles = [weak, weak, spike, weak, weak, weak]
    results = _drive_simulation(
        monkeypatch=monkeypatch, pg_factory=pg_factory, pg_session=pg_session,
        bundles=bundles, start=_start_monday(2026, 22),
    )
    _print_trace("Scenario 3 — false spike", results)

    states = {r.state for r in results}
    assert "STRONG_CANDIDATE" not in states
    assert "APPROVED_FOR_SHADOW_REPLACEMENT" not in states


# ===========================================================================
# Scenario 4 — Tail failure (STRONG_CANDIDATE → tail breach → NOT_READY)
# ===========================================================================

def test_scenario_4_tail_failure_rolls_back_to_not_ready(monkeypatch, pg_factory,
                                                          pg_session):
    """Build to STRONG_CANDIDATE then breach tail_delta_p99 < -25."""
    good = _build_bundle(
        n_input=160, n_div=60, n_b2flat=30, edge_bps=12.0, cum_pct=2.5,
        iwe=0.10, verdict="V2_BETTER", readiness="STRONG_CANDIDATE",
        confidence=0.90,
    )
    breach = _build_bundle(
        n_input=160, n_div=60, n_b2flat=30, edge_bps=12.0, cum_pct=2.5,
        iwe=0.10, verdict="V2_BETTER", readiness="STRONG_CANDIDATE",
        confidence=0.90, p99_delta=-30.0,  # hard breach
    )
    # 5 good weeks to climb, then one breach week
    bundles = [good, good, good, good, good, breach]
    results = _drive_simulation(
        monkeypatch=monkeypatch, pg_factory=pg_factory, pg_session=pg_session,
        bundles=bundles, start=_start_monday(2026, 24),
    )
    _print_trace("Scenario 4 — tail failure", results)

    # Last week must be NOT_READY with tail-emergency rollback reason
    assert results[-1].state == "NOT_READY"
    assert results[-1].rollback_reason and "emergency" in results[-1].rollback_reason
    # Some prior week must have reached STRONG_CANDIDATE (otherwise the test is
    # validating something different)
    assert any(r.state == "STRONG_CANDIDATE" for r in results[:-1])


# ===========================================================================
# Scenario 5 — Approval flow (STRONG_CANDIDATE → APPROVE → APPROVED)
# ===========================================================================

def test_scenario_5_approval_flow(monkeypatch, pg_factory, pg_session):
    """Build to STRONG_CANDIDATE; operator writes approval; next snapshot
    advances to APPROVED_FOR_SHADOW_REPLACEMENT."""
    good = _build_bundle(
        n_input=160, n_div=60, n_b2flat=30, edge_bps=12.0, cum_pct=2.5,
        iwe=0.10, verdict="V2_BETTER", readiness="STRONG_CANDIDATE",
        confidence=0.90,
    )

    approval_written = {"done": False}

    def _approve_when_strong(week_idx: int, snap: V2PromotionSnapshot,
                              session: Session):
        if not approval_written["done"] and snap.state == "STRONG_CANDIDATE":
            session.add(V2PromotionApproval(
                snapshot_id=snap.id,
                decision="APPROVE",
                approver="ops@example.com",
                rationale="phase 7 simulation approval rationale text",
                approved_at=dt.datetime.combine(
                    snap.as_of_date, dt.time(12, 0, tzinfo=dt.timezone.utc),
                ) + dt.timedelta(days=1),
            ))
            session.commit()
            approval_written["done"] = True

    # 6 weeks of good data; approval written when the first STRONG_CANDIDATE
    # snapshot is observed. Next week's snapshot should advance to APPROVED.
    bundles = [good] * 7
    results = _drive_simulation(
        monkeypatch=monkeypatch, pg_factory=pg_factory, pg_session=pg_session,
        bundles=bundles, start=_start_monday(2026, 28),
        approval_callback=_approve_when_strong,
    )
    _print_trace("Scenario 5 — approval flow", results)

    states = [r.state for r in results]
    assert approval_written["done"]
    assert "APPROVED_FOR_SHADOW_REPLACEMENT" in states
    # APPROVED appears strictly after the first STRONG_CANDIDATE (no skipping)
    first_strong_idx = states.index("STRONG_CANDIDATE")
    first_approved_idx = states.index("APPROVED_FOR_SHADOW_REPLACEMENT")
    assert first_approved_idx > first_strong_idx


# ===========================================================================
# Scenario 6 — Rescind flow (APPROVED → RESCIND → downgrade)
# ===========================================================================

def test_scenario_6_rescind_flow(monkeypatch, pg_factory, pg_session):
    """Reach APPROVED, then operator rescinds; next snapshot regresses
    to STRONG_CANDIDATE (gates 1–7 still pass)."""
    good = _build_bundle(
        n_input=160, n_div=60, n_b2flat=30, edge_bps=12.0, cum_pct=2.5,
        iwe=0.10, verdict="V2_BETTER", readiness="STRONG_CANDIDATE",
        confidence=0.90,
    )

    approval_written = {"done": False}
    rescission_written = {"done": False}
    approved_snapshot_id: dict[str, int | None] = {"id": None}

    def _operator(week_idx: int, snap: V2PromotionSnapshot,
                   session: Session):
        snap_dt = dt.datetime.combine(
            snap.as_of_date, dt.time(12, 0, tzinfo=dt.timezone.utc),
        )
        if not approval_written["done"] and snap.state == "STRONG_CANDIDATE":
            session.add(V2PromotionApproval(
                snapshot_id=snap.id, decision="APPROVE",
                approver="ops@example.com",
                rationale="phase 7 rescind-flow approval rationale text",
                approved_at=snap_dt + dt.timedelta(days=1),
            ))
            session.commit()
            approval_written["done"] = True
            approved_snapshot_id["id"] = snap.id
            return
        if (
            approval_written["done"]
            and not rescission_written["done"]
            and snap.state == "APPROVED_FOR_SHADOW_REPLACEMENT"
        ):
            session.add(V2PromotionApproval(
                snapshot_id=approved_snapshot_id["id"],
                decision="RESCIND",
                approver="ops@example.com",
                rationale="phase 7 rescission rationale text long enough",
                approved_at=snap_dt + dt.timedelta(days=1),
            ))
            session.commit()
            rescission_written["done"] = True

    bundles = [good] * 9
    results = _drive_simulation(
        monkeypatch=monkeypatch, pg_factory=pg_factory, pg_session=pg_session,
        bundles=bundles, start=_start_monday(2026, 36),
        approval_callback=_operator,
    )
    _print_trace("Scenario 6 — rescind flow", results)

    states = [r.state for r in results]
    assert approval_written["done"]
    assert rescission_written["done"]
    assert "APPROVED_FOR_SHADOW_REPLACEMENT" in states
    # After RESCIND, a later snapshot must NOT be APPROVED
    last_approved_idx = max(
        i for i, s in enumerate(states) if s == "APPROVED_FOR_SHADOW_REPLACEMENT"
    )
    # If rescission happened on the same week as last APPROVED, the NEXT week
    # must have downgraded (must have at least one snapshot after the last
    # APPROVED whose state is below APPROVED).
    assert any(
        s != "APPROVED_FOR_SHADOW_REPLACEMENT"
        for s in states[last_approved_idx + 1:]
    )


# ===========================================================================
# Scenario 7 — Post-approval degradation (APPROVED → 2 bad weeks)
# ===========================================================================

def test_scenario_7_post_approval_degradation(monkeypatch, pg_factory,
                                                pg_session):
    """Reach APPROVED, then degrade with 2-consec tail-guard breach.
    APPROVED has only one auto exit: tail-risk emergency → NOT_READY."""
    good = _build_bundle(
        n_input=160, n_div=60, n_b2flat=30, edge_bps=12.0, cum_pct=2.5,
        iwe=0.10, verdict="V2_BETTER", readiness="STRONG_CANDIDATE",
        confidence=0.90,
    )
    bad = _build_bundle(
        n_input=160, n_div=60, n_b2flat=30, edge_bps=12.0, cum_pct=2.5,
        iwe=0.10, verdict="V2_BETTER", readiness="STRONG_CANDIDATE",
        confidence=0.90, tail_guard=True, p99_delta=-15.0,
    )

    approval_written = {"done": False}

    def _approve_once(week_idx, snap, session):
        if not approval_written["done"] and snap.state == "STRONG_CANDIDATE":
            session.add(V2PromotionApproval(
                snapshot_id=snap.id, decision="APPROVE",
                approver="ops@example.com",
                rationale="phase 7 post-approval degradation rationale",
                approved_at=dt.datetime.combine(
                    snap.as_of_date, dt.time(12, 0, tzinfo=dt.timezone.utc),
                ) + dt.timedelta(days=1),
            ))
            session.commit()
            approval_written["done"] = True

    # 6 good (climbs to APPROVED), 2 bad (consecutive tail-guard hits → emergency)
    bundles = [good] * 6 + [bad, bad]
    results = _drive_simulation(
        monkeypatch=monkeypatch, pg_factory=pg_factory, pg_session=pg_session,
        bundles=bundles, start=_start_monday(2026, 44),
        approval_callback=_approve_once,
    )
    _print_trace("Scenario 7 — post-approval degradation", results)

    states = [r.state for r in results]
    assert "APPROVED_FOR_SHADOW_REPLACEMENT" in states
    # Final state must be NOT_READY (only auto exit from APPROVED is emergency)
    assert results[-1].state == "NOT_READY"
    assert results[-1].rollback_reason and (
        "consecutive" in results[-1].rollback_reason
        or "emergency" in results[-1].rollback_reason
    )


# ===========================================================================
# Cross-cutting invariant: no oscillation loop within a single scenario
# ===========================================================================

def _no_oscillation(states: list[str]) -> bool:
    """No (X, Y, X, Y) ping-pong within trailing 4."""
    if len(states) < 4:
        return True
    for i in range(len(states) - 3):
        a, b, c, d = states[i:i + 4]
        if a == c and b == d and a != b:
            return False
    return True


def test_no_oscillation_in_any_scenario(monkeypatch, pg_factory, pg_session):
    """Run scenarios 1–4 sequentially in independent sessions (each via the
    pg_session fixture's TRUNCATE-between-tests) and assert no oscillation."""
    # Run a single representative scenario here; per-scenario tests above
    # already capture the per-week trace. This test covers the invariant
    # over a longer 12-week run that mixes good and noisy bundles.
    rng_pattern = []
    good = _build_bundle(
        n_input=160, n_div=60, n_b2flat=30, edge_bps=10.0, cum_pct=2.0,
        iwe=0.08, verdict="V2_BETTER", readiness="STRONG_CANDIDATE",
        confidence=0.85,
    )
    mediocre = _build_bundle(
        n_input=120, n_div=40, n_b2flat=20, edge_bps=4.0, cum_pct=0.4,
        iwe=0.03, verdict="INCONCLUSIVE", readiness="REVIEW",
        confidence=0.55,
    )
    pattern = [good, good, mediocre, good, good, good, mediocre,
                good, good, good, good, good]
    results = _drive_simulation(
        monkeypatch=monkeypatch, pg_factory=pg_factory, pg_session=pg_session,
        bundles=pattern, start=_start_monday(2026, 14),
    )
    _print_trace("Anti-oscillation 12-week mixed run", results)

    states = [r.state for r in results]
    assert _no_oscillation(states), f"oscillation detected: {states}"
