"""Phase 4 integration tests for v2_promotion_snapshot job.

Covers:
  * Idempotency — running the job twice for the same ISO week produces 1 row.
  * Week boundary correctness via ISO calendar.
  * Full snapshot creation with seeded paper_shadow_log rows.
  * Tail-emergency override path.
  * Approval present vs absent → STRONG_CANDIDATE → APPROVED transition.

Marked `integration` — requires Docker / testcontainers (or TEST_DATABASE_URL).
"""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Iterator
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from apps.api.src.db.models import (
    V2PromotionApproval,
    V2PromotionSnapshot,
)
from apps.worker.src.jobs import v2_promotion_snapshot as job_module
from apps.worker.src.jobs.v2_promotion_snapshot import (
    run_v2_promotion_snapshot,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _factory(pg_engine):
    return sessionmaker(bind=pg_engine, class_=Session, expire_on_commit=False)


_PAPER_SHADOW_DDL = text("""
CREATE TABLE IF NOT EXISTS paper_shadow_log (
    id              TEXT PRIMARY KEY,
    as_of_date      DATE NOT NULL,
    instrument      TEXT NOT NULL,
    source_strategy TEXT NOT NULL,
    signal          TEXT NOT NULL CHECK (signal IN ('LONG', 'FLAT')),
    entry_price     NUMERIC(20, 6),
    exit_price      NUMERIC(20, 6),
    fwd_return_1d   NUMERIC(12, 8),
    fwd_return_5d   NUMERIC(12, 8),
    regime_label    TEXT,
    engine_a_active BOOLEAN NOT NULL DEFAULT FALSE,
    trend_score     NUMERIC(12, 6),
    note            TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (as_of_date, instrument, source_strategy)
)
""")


def _ensure_paper_shadow_table(session: Session) -> None:
    session.execute(_PAPER_SHADOW_DDL)
    session.commit()


def _seed_paper_shadow(session: Session, *,
                       start: dt.date,
                       n_days: int = 80,
                       b2_long_every: int = 3,
                       v2_long_every: int = 2,
                       fwd_return_pattern=None,
                       regime_label: str = "DIRECTIONAL") -> None:
    _ensure_paper_shadow_table(session)
    """Insert paper_shadow_log rows for B2 + V2 source_strategies.

    `b2_long_every` / `v2_long_every` control LONG cadence (others FLAT).
    `fwd_return_pattern` is a list of returns per day (cycled if shorter).
    Both source_strategies share the same fwd_return_1d and instrument.
    """
    if fwd_return_pattern is None:
        fwd_return_pattern = [0.005, 0.003, -0.001, 0.004, 0.002]
    sql = text(
        """
        INSERT INTO paper_shadow_log
          (id, as_of_date, instrument, source_strategy, signal,
           fwd_return_1d, fwd_return_5d, regime_label,
           engine_a_active, trend_score, note)
        VALUES
          (:id, :d, :instrument, :src, :sig, :ret, :ret5, :regime,
           true, 0.0, 'seed')
        """
    )
    rows = []
    for i in range(n_days):
        d = start + dt.timedelta(days=i)
        ret = fwd_return_pattern[i % len(fwd_return_pattern)]
        b2_sig = "LONG" if (i % b2_long_every == 0) else "FLAT"
        v2_sig = "LONG" if (i % v2_long_every == 0) else "FLAT"
        # Force divergence on enough days
        rows.append(("b2", i, d, "SPY", "tsmom_60_no_stress",
                     b2_sig, ret, ret * 5, regime_label))
        rows.append(("v2", i, d, "SPY", "tsmom_60_no_stress_v2_persist3",
                     v2_sig, ret, ret * 5, regime_label))
    for prefix, i, d, instr, src, sig, ret, ret5, regime in rows:
        session.execute(
            sql,
            {
                "id": f"{prefix}-{i:03d}-{d.isoformat()}",
                "d": d, "instrument": instr, "src": src,
                "sig": sig, "ret": ret, "ret5": ret5, "regime": regime,
            },
        )
    session.commit()


def _isoweek(d: dt.date) -> tuple[int, int]:
    iy, iw, _ = d.isocalendar()
    return iy, iw


# ---------------------------------------------------------------------------
# pytest plumbing
# ---------------------------------------------------------------------------

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _ensure_paper_shadow_log_exists(pg_engine):
    """paper_shadow_log isn't an ORM model — create it via raw DDL once
    per test so the snapshot job's SELECT does not error out.

    DROP+CREATE (not IF NOT EXISTS) so this fixture's full schema wins
    over any abbreviated schema left by other test files in the same
    pytest run."""
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS paper_shadow_log"))
        conn.execute(_PAPER_SHADOW_DDL)
    yield


@pytest.fixture
def pg_factory(pg_engine):
    return _factory(pg_engine)


# ===========================================================================
# Idempotency
# ===========================================================================

def test_idempotency_two_runs_same_iso_week_one_row(pg_factory, pg_session):
    target = dt.date(2026, 5, 4)  # Monday → ISO 2026-W19
    iy, iw = _isoweek(target)
    _seed_paper_shadow(pg_session, start=dt.date(2026, 1, 1), n_days=120)

    out1 = run_v2_promotion_snapshot(
        as_of=target, session_factory=pg_factory,
    )
    out2 = run_v2_promotion_snapshot(
        as_of=target, session_factory=pg_factory,
    )
    assert out1["status"] == "inserted"
    assert out2["status"] == "noop_existing"
    assert out1["snapshot_id"] == out2["snapshot_id"]

    n_rows = pg_session.scalar(
        text("SELECT COUNT(*) FROM v2_promotion_snapshot "
             "WHERE iso_year=:y AND iso_week=:w"),
        {"y": iy, "w": iw},
    )
    assert n_rows == 1


def test_idempotency_no_writes_when_existing_row(pg_factory, pg_session):
    target = dt.date(2026, 5, 4)
    _seed_paper_shadow(pg_session, start=dt.date(2026, 1, 1), n_days=120)

    out1 = run_v2_promotion_snapshot(
        as_of=target, session_factory=pg_factory,
    )
    snap_id_before = out1["snapshot_id"]
    n_paper_before = pg_session.scalar(
        text("SELECT COUNT(*) FROM paper_shadow_log")
    )

    out2 = run_v2_promotion_snapshot(
        as_of=target, session_factory=pg_factory,
    )
    assert out2["status"] == "noop_existing"
    assert out2["snapshot_id"] == snap_id_before

    n_paper_after = pg_session.scalar(
        text("SELECT COUNT(*) FROM paper_shadow_log")
    )
    assert n_paper_before == n_paper_after  # comparison source untouched


# ===========================================================================
# Week-boundary correctness
# ===========================================================================

@pytest.mark.parametrize("d, expected_year, expected_week", [
    (dt.date(2026, 1, 5), 2026, 2),     # Mon ISO 2026-W02
    (dt.date(2026, 4, 27), 2026, 18),   # Mon ISO 2026-W18
    (dt.date(2026, 12, 28), 2026, 53),  # ISO 2026-W53
    (dt.date(2027, 1, 4), 2027, 1),     # Mon ISO 2027-W01
])
def test_week_boundary_correctness(pg_factory, pg_session, d, expected_year,
                                    expected_week):
    _seed_paper_shadow(pg_session, start=d - dt.timedelta(days=120),
                       n_days=120)
    out = run_v2_promotion_snapshot(
        as_of=d, session_factory=pg_factory,
    )
    assert out["iso_year"] == expected_year
    assert out["iso_week"] == expected_week
    snap = pg_session.get(V2PromotionSnapshot, out["snapshot_id"])
    assert snap is not None
    assert snap.iso_year == expected_year
    assert snap.iso_week == expected_week


# ===========================================================================
# Full snapshot creation
# ===========================================================================

def test_full_snapshot_creation_with_seeded_inputs(pg_factory, pg_session):
    target = dt.date(2026, 5, 18)
    _seed_paper_shadow(pg_session,
                       start=dt.date(2026, 1, 1), n_days=120)
    out = run_v2_promotion_snapshot(
        as_of=target, session_factory=pg_factory,
    )
    assert out["status"] == "inserted"

    snap = pg_session.get(V2PromotionSnapshot, out["snapshot_id"])
    assert snap.as_of_date == target
    assert snap.iso_year, snap.iso_week == _isoweek(target)
    assert snap.state in (
        "NOT_READY", "WATCH", "READY_FOR_REVIEW",
        "STRONG_CANDIDATE", "APPROVED_FOR_SHADOW_REPLACEMENT",
    )
    assert isinstance(snap.comparison_bundle_json, dict)
    assert "metrics" in snap.comparison_bundle_json
    assert "verdict" in snap.comparison_bundle_json
    assert isinstance(snap.gates_json, dict)
    assert set(snap.gates_json["gates"].keys()) == {
        "gate_1_minimum_sample", "gate_2_verdict_stability",
        "gate_3_edge_quality", "gate_4_tail_risk",
        "gate_5_regime_validation", "gate_6_stability",
        "gate_7_governance", "gate_8_operator_approval",
    }
    assert isinstance(snap.promotion_confidence, Decimal)
    assert 0 <= float(snap.promotion_confidence) <= 1
    assert snap.verdict_streak >= 0
    assert snap.readiness_streak >= 0


def test_first_snapshot_prior_state_is_null(pg_factory, pg_session):
    target = dt.date(2026, 5, 18)
    _seed_paper_shadow(pg_session, start=dt.date(2026, 1, 1), n_days=120)
    out = run_v2_promotion_snapshot(
        as_of=target, session_factory=pg_factory,
    )
    snap = pg_session.get(V2PromotionSnapshot, out["snapshot_id"])
    assert snap.prior_state is None


# ===========================================================================
# Tail-emergency override scenario
# ===========================================================================

def test_tail_emergency_forces_not_ready(pg_factory, pg_session, monkeypatch):
    """Bundle with tail_delta_p99_bps deeply negative → state forced
    to SUSPENDED (Phase 9A; was NOT_READY)."""
    target = dt.date(2026, 5, 25)

    def _emergency_bundle(*args, **kwargs):
        b = job_module.compute_all([])
        b["n_input_rows"] = 200
        b["n_divergent_rows"] = 60
        b["metrics"]["n_b2_flat_v2_long"] = 30
        b["metrics"]["avg_return_diff_1d_bps"] = 12.0
        b["metrics"]["cumulative_return_diff_pct"] = 2.0
        b["metrics"]["impact_weighted_edge"] = 0.10
        b["tail"]["b2"] = {"p95_loss_bps": -100.0, "p99_loss_bps": -200.0,
                            "worst_5_losses_bps": [-200, -180, -150, -120, -100]}
        b["tail"]["v2"] = {"p95_loss_bps": -100.0, "p99_loss_bps": -250.0,
                            "worst_5_losses_bps": [-250, -200, -180, -150, -120]}
        b["tail"]["tail_delta_p95_bps"] = 0.0
        b["tail"]["tail_delta_p99_bps"] = -50.0  # deep breach
        b["verdict"] = {
            "verdict": "V2_BETTER", "confidence": 0.85,
            "tail_guard_triggered": False, "tail_guard_reason": None,
            "readiness": "STRONG_CANDIDATE",
            "base_verdict_before_guard": "V2_BETTER",
            "base_confidence_before_guard": 0.85,
        }
        return b

    monkeypatch.setattr(job_module, "fetch_comparison_bundle", _emergency_bundle)
    out = run_v2_promotion_snapshot(
        as_of=target, session_factory=pg_factory,
    )
    snap = pg_session.get(V2PromotionSnapshot, out["snapshot_id"])
    assert snap.state == "SUSPENDED"
    assert snap.rollback_reason and "emergency" in snap.rollback_reason


# ===========================================================================
# Approval present vs absent
# ===========================================================================

def test_approval_absent_no_advance_to_approved(pg_factory, pg_session,
                                                  monkeypatch):
    """Bundle that would justify STRONG_CANDIDATE but no approval row →
    state stays at STRONG_CANDIDATE (or below), NOT APPROVED."""
    monkeypatch.setattr(
        job_module, "fetch_comparison_bundle",
        lambda *a, **kw: _strong_candidate_bundle(),
    )
    target = dt.date(2026, 5, 25)
    out = run_v2_promotion_snapshot(
        as_of=target, session_factory=pg_factory,
    )
    snap = pg_session.get(V2PromotionSnapshot, out["snapshot_id"])
    assert snap.state != "APPROVED_FOR_SHADOW_REPLACEMENT"


def test_approval_present_advances_strong_to_approved(pg_factory, pg_session,
                                                        monkeypatch):
    """Two-snapshot dance:
       Week N: state advances forward; eventually a snapshot is
                STRONG_CANDIDATE.
       Operator writes approval row referencing that snapshot.
       Week N+1: state advances to APPROVED_FOR_SHADOW_REPLACEMENT.
    """
    monkeypatch.setattr(
        job_module, "fetch_comparison_bundle",
        lambda *a, **kw: _strong_candidate_bundle(),
    )
    # Walk forward four ISO weeks to build up streaks + state
    # Phase 9B.1: GATE1_MIN_OOS_DAYS raised to 60; start ≥ 60 days after
    # FRAMEWORK_IMPLEMENTATION_DATE (2026-04-25) so Gate 1 can pass.
    base = dt.date(2026, 6, 29)  # Mon ISO 2026-W27 (~65 days OOS)
    snapshot_ids: list[int] = []
    states: list[str] = []
    for w in range(6):
        target = base + dt.timedelta(weeks=w)
        out = run_v2_promotion_snapshot(
            as_of=target, session_factory=pg_factory,
        )
        snapshot_ids.append(out["snapshot_id"])
        snap = pg_session.get(V2PromotionSnapshot, out["snapshot_id"])
        states.append(snap.state)

    # Find LAST STRONG_CANDIDATE snapshot — operator approves the most-
    # recent one so that next snapshot's prior is the approved one.
    strong_indices = [i for i, s in enumerate(states)
                       if s == "STRONG_CANDIDATE"]
    assert strong_indices, f"expected STRONG_CANDIDATE in {states}"
    strong_idx = strong_indices[-1]

    strong_snap_id = snapshot_ids[strong_idx]
    approval_dt = dt.datetime(
        base.year, base.month, base.day,
        tzinfo=dt.timezone.utc,
    ) + dt.timedelta(weeks=strong_idx, days=1)
    pg_session.add(V2PromotionApproval(
        snapshot_id=strong_snap_id,
        decision="APPROVE",
        approver="ops@example.com",
        rationale="phase 4 integration test approval rationale text",
        approved_at=approval_dt,
    ))
    pg_session.commit()

    # Run the next-week snapshot — should now advance to APPROVED.
    # next_target = week immediately after the latest existing snapshot.
    next_target = base + dt.timedelta(weeks=len(states))

    out = run_v2_promotion_snapshot(
        as_of=next_target, session_factory=pg_factory,
    )
    snap = pg_session.get(V2PromotionSnapshot, out["snapshot_id"])
    assert snap.state == "APPROVED_FOR_SHADOW_REPLACEMENT"


# ===========================================================================
# Empty / error scenarios
# ===========================================================================

def test_empty_database_yields_not_ready(pg_factory, pg_session):
    """No paper_shadow_log rows → bundle empty → NOT_READY."""
    target = dt.date(2026, 5, 25)
    out = run_v2_promotion_snapshot(
        as_of=target, session_factory=pg_factory,
    )
    snap = pg_session.get(V2PromotionSnapshot, out["snapshot_id"])
    assert snap.state == "NOT_READY"


def test_comparison_fetch_failure_graceful_fallback(pg_factory, pg_session,
                                                     monkeypatch):
    """If fetch raises, job inserts a NOT_READY snapshot with
    comparison_fetch_ok=False rather than crashing."""
    def _boom(*a, **kw):
        raise RuntimeError("simulated fetch failure")
    monkeypatch.setattr(job_module, "fetch_comparison_bundle", _boom)
    target = dt.date(2026, 6, 1)
    out = run_v2_promotion_snapshot(
        as_of=target, session_factory=pg_factory,
    )
    assert out["status"] == "inserted"
    snap = pg_session.get(V2PromotionSnapshot, out["snapshot_id"])
    assert snap.gates_json["comparison_fetch_ok"] is False


# ---------------------------------------------------------------------------
# Bundle factory for STRONG_CANDIDATE happy-path
# ---------------------------------------------------------------------------

def _strong_candidate_bundle() -> dict:
    """A bundle that satisfies all 7 quantitative gates with margin."""
    base = job_module.compute_all([])
    base["n_input_rows"] = 300   # Phase 9B.1: bumped to satisfy Gate 4 floor
    base["n_divergent_rows"] = 80
    base["metrics"] = {
        "n_divergent_days": 80,
        "n_b2_flat_v2_long": 50,
        "n_b2_long_v2_flat": 30,
        "win_rate_v2_vs_b2_pct": 65.0,
        "avg_return_diff_1d_bps": 12.0,
        "avg_return_diff_5d_bps": 12.0,
        "cumulative_return_diff_pct": 2.5,
        "avoided_losses_count": 10,
        "avoided_losses_avg_bps": 80.0,
        "new_losses_count": 5,
        "new_losses_avg_bps": 30.0,
        "impact_weighted_edge": 0.10,
    }
    base["metrics_by_regime"] = {
        "stress": {
            "n_divergent_days": 20, "n_b2_flat_v2_long": 10,
            "n_b2_long_v2_flat": 10, "win_rate_v2_vs_b2_pct": 60.0,
            "avg_return_diff_1d_bps": 6.0, "avg_return_diff_5d_bps": 6.0,
            "cumulative_return_diff_pct": 0.5,
            "avoided_losses_count": 3, "avoided_losses_avg_bps": 50.0,
            "new_losses_count": 1, "new_losses_avg_bps": 20.0,
            "impact_weighted_edge": 0.07,
        },
        "directional": {
            "n_divergent_days": 50, "n_b2_flat_v2_long": 35,
            "n_b2_long_v2_flat": 15, "win_rate_v2_vs_b2_pct": 70.0,
            "avg_return_diff_1d_bps": 14.0, "avg_return_diff_5d_bps": 14.0,
            "cumulative_return_diff_pct": 1.5,
            "avoided_losses_count": 5, "avoided_losses_avg_bps": 80.0,
            "new_losses_count": 3, "new_losses_avg_bps": 30.0,
            "impact_weighted_edge": 0.12,
        },
        "neutral": {
            "n_divergent_days": 10, "n_b2_flat_v2_long": 5,
            "n_b2_long_v2_flat": 5, "win_rate_v2_vs_b2_pct": 50.0,
            "avg_return_diff_1d_bps": 0.0, "avg_return_diff_5d_bps": 0.0,
            "cumulative_return_diff_pct": 0.5,
            "avoided_losses_count": 2, "avoided_losses_avg_bps": 30.0,
            "new_losses_count": 1, "new_losses_avg_bps": 25.0,
            "impact_weighted_edge": 0.02,
        },
    }
    base["tail"] = {
        "b2": {"n": 300, "p95_loss_bps": -100.0, "p99_loss_bps": -200.0,
                "worst_5_losses_bps": [-200, -180, -150, -120, -100]},
        "v2": {"n": 300, "p95_loss_bps": -100.0, "p99_loss_bps": -200.0,
                "worst_5_losses_bps": [-200, -180, -150, -120, -100]},
        "tail_delta_p95_bps": 0.0,
        "tail_delta_p99_bps": 0.0,
    }
    base["stability"] = {
        "first_half_vs_second_half": {
            "first_half_edge_bps": 8.0, "second_half_edge_bps": 14.0,
            "n_first": 40, "n_second": 40, "trend": "STABLE",
        },
        "last_30_vs_prior_30": {
            "last_30_edge_bps": 12.0, "prior_30_edge_bps": 10.0,
            "n_last": 30, "n_prior": 30, "trend": "STABLE",
        },
    }
    base["verdict"] = {
        "verdict": "V2_BETTER", "confidence": 0.85,
        "tail_guard_triggered": False, "tail_guard_reason": None,
        "readiness": "STRONG_CANDIDATE",
        "base_verdict_before_guard": "V2_BETTER",
        "base_confidence_before_guard": 0.85,
    }
    return base
