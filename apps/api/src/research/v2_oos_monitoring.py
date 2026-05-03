"""V2 OOS monitoring report layer (Phase 10B.2).

Pure-function weekly assessment over existing v2_promotion_snapshot data.
Read-only DB wrapper; SELECT only. NEVER recomputes gates / state /
confidence. NEVER imports v2_promotion_gates or v2_promotion_state. NEVER
imports any execution / routing / risk / ML / scheduler module. Stored
snapshot fields are the source of truth.

Spec: docs/research/V2_OOS_MONITORING_DESIGN.md
"""

from __future__ import annotations

import dataclasses
import datetime as dt
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from apps.api.src.db.models import (
    V2PromotionApproval,
    V2PromotionSnapshot,
)


# ---------------------------------------------------------------------------
# Frozen module constants — design-doc-locked, no operator tuning
# ---------------------------------------------------------------------------

REPORT_SCHEMA_VERSION = 1

TREND_LOOKBACK_WEEKS = 4
TREND_PRIOR_WEEKS = 4
EDGE_TREND_DEAD_ZONE_BPS = 0.5
RAPID_ASCENT_MAX_WEEKS = 5
APPROVAL_EXPIRY_WARN_DAYS = 4
APPROVAL_STALENESS_DAYS = 14         # mirrors API constant; documented
INSUFFICIENT_SAMPLE_PERSIST_WEEKS = 3
SUSPENDED_REPEAT_WINDOW_WEEKS = 12
SUSPENDED_REPEAT_THRESHOLD = 2
STREAK_RESET_FREQUENT_THRESHOLD = 3
COMPARISON_HEALTH_FAILURE_TOLERANCE = 1   # > this in trailing 7 → degraded
LATEST_KNOWN_BUNDLE_SCHEMA = 2

# Locally-defined state-name constants. NOT imported from v2_promotion_state
# to keep the dependency graph clean (per design § Hard Boundaries). Strings
# match the state machine's stored values byte-for-byte.
STATE_NOT_READY = "NOT_READY"
STATE_SUSPENDED = "SUSPENDED"
STATE_WATCH = "WATCH"
STATE_READY_FOR_REVIEW = "READY_FOR_REVIEW"
STATE_STRONG_CANDIDATE = "STRONG_CANDIDATE"
STATE_APPROVED = "APPROVED_FOR_SHADOW_REPLACEMENT"


# ---------------------------------------------------------------------------
# Result dataclasses (frozen + JSON-serializable)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EdgeReport:
    edge_bps: float | None
    impact_weighted_edge: float | None
    trend: str
    last_4w_avg_edge_bps: float | None
    prior_4w_avg_edge_bps: float | None
    slope_bps_per_week: float | None


@dataclass(frozen=True)
class TailReport:
    tail_guard_triggered: bool
    tail_delta_p99_bps: float | None
    tail_delta_p95_bps: float | None
    tail_by_regime_present: bool


@dataclass(frozen=True)
class StreaksReport:
    verdict_streak: int
    readiness_streak: int
    streak_reset_count_last_8w: int


@dataclass(frozen=True)
class GovernanceReport:
    approval_status: str       # NONE | ACTIVE | EXPIRING_SOON | EXPIRED | RESCINDED
    days_until_expiry: int | None
    is_stale: bool
    snapshot_content_hash_match: bool
    code_version: str | None
    timezone: str | None
    schema_version: int | None


@dataclass(frozen=True)
class RedFlag:
    code: str
    severity: str   # INFO | WATCH | REVIEW
    message: str


@dataclass(frozen=True)
class WeeklyOOSReport:
    schema_version: int
    week: str
    as_of_date: str
    snapshot_id: int
    state: str
    confidence: float
    confidence_basis: tuple[str, ...]
    edge: EdgeReport
    tail: TailReport
    streaks: StreaksReport
    governance: GovernanceReport
    assessment: str
    red_flags: tuple[RedFlag, ...]
    notes: tuple[str, ...]
    recommended_action: str    # NONE | REVIEW | INVESTIGATE | DO_NOT_APPROVE


# ---------------------------------------------------------------------------
# Snapshot accessors (helpers; NEVER mutate)
# ---------------------------------------------------------------------------

def _bundle(snap: V2PromotionSnapshot) -> dict:
    return snap.comparison_bundle_json or {}


def _gates_block(snap: V2PromotionSnapshot) -> dict:
    return (snap.gates_json or {})


def _gates(snap: V2PromotionSnapshot) -> dict[str, dict]:
    return (_gates_block(snap).get("gates") or {})


def _verdict_block(snap: V2PromotionSnapshot) -> dict:
    return (_bundle(snap).get("verdict") or {})


def _metrics_block(snap: V2PromotionSnapshot) -> dict:
    return (_bundle(snap).get("metrics") or {})


def _tail_block(snap: V2PromotionSnapshot) -> dict:
    return (_bundle(snap).get("tail") or {})


def _confidence_basis(snap: V2PromotionSnapshot) -> tuple[str, ...]:
    cb = (_gates_block(snap).get("confidence_breakdown") or {})
    warnings = cb.get("basis_warnings") or []
    return tuple(str(w) for w in warnings)


# ---------------------------------------------------------------------------
# Edge / trend / streaks computation (pure)
# ---------------------------------------------------------------------------

def _edge_report(
    current: V2PromotionSnapshot,
    prior: list[V2PromotionSnapshot],
) -> EdgeReport:
    metrics = _metrics_block(current)
    edge_bps = metrics.get("avg_return_diff_1d_bps")
    iwe = metrics.get("impact_weighted_edge")

    # Use trailing prior snapshots only (not the current one) for trend.
    prior_edges = [
        _metrics_block(s).get("avg_return_diff_1d_bps") for s in prior
    ]
    finite = [float(e) for e in prior_edges if e is not None]
    needed = TREND_LOOKBACK_WEEKS + TREND_PRIOR_WEEKS
    if len(finite) < needed:
        return EdgeReport(
            edge_bps=float(edge_bps) if edge_bps is not None else None,
            impact_weighted_edge=float(iwe) if iwe is not None else None,
            trend="INSUFFICIENT",
            last_4w_avg_edge_bps=None,
            prior_4w_avg_edge_bps=None,
            slope_bps_per_week=None,
        )
    last_4 = finite[-TREND_LOOKBACK_WEEKS:]
    prior_4 = finite[-(TREND_LOOKBACK_WEEKS + TREND_PRIOR_WEEKS):
                       -TREND_LOOKBACK_WEEKS]
    last_avg = sum(last_4) / len(last_4)
    prior_avg = sum(prior_4) / len(prior_4)
    delta = last_avg - prior_avg
    if delta > EDGE_TREND_DEAD_ZONE_BPS:
        trend = "UP"
    elif delta < -EDGE_TREND_DEAD_ZONE_BPS:
        trend = "DOWN"
    else:
        trend = "FLAT"
    return EdgeReport(
        edge_bps=float(edge_bps) if edge_bps is not None else None,
        impact_weighted_edge=float(iwe) if iwe is not None else None,
        trend=trend,
        last_4w_avg_edge_bps=round(last_avg, 4),
        prior_4w_avg_edge_bps=round(prior_avg, 4),
        slope_bps_per_week=round(delta / TREND_LOOKBACK_WEEKS, 4),
    )


def _tail_report(current: V2PromotionSnapshot) -> TailReport:
    verdict = _verdict_block(current)
    tail = _tail_block(current)
    return TailReport(
        tail_guard_triggered=bool(verdict.get("tail_guard_triggered")),
        tail_delta_p99_bps=(
            float(tail["tail_delta_p99_bps"])
            if tail.get("tail_delta_p99_bps") is not None else None
        ),
        tail_delta_p95_bps=(
            float(tail["tail_delta_p95_bps"])
            if tail.get("tail_delta_p95_bps") is not None else None
        ),
        tail_by_regime_present=bool(_bundle(current).get("tail_by_regime")),
    )


def _streak_reset_count(prior: list[V2PromotionSnapshot]) -> int:
    """Count week-over-week verdict_streak DECREASES across last 8 priors."""
    last_8 = prior[-8:]
    if len(last_8) < 2:
        return 0
    count = 0
    for prev, cur in zip(last_8[:-1], last_8[1:]):
        if int(cur.verdict_streak or 0) < int(prev.verdict_streak or 0):
            count += 1
    return count


def _streaks_report(
    current: V2PromotionSnapshot,
    prior: list[V2PromotionSnapshot],
) -> StreaksReport:
    return StreaksReport(
        verdict_streak=int(current.verdict_streak or 0),
        readiness_streak=int(current.readiness_streak or 0),
        streak_reset_count_last_8w=_streak_reset_count(prior),
    )


# ---------------------------------------------------------------------------
# Governance / approval analysis
# ---------------------------------------------------------------------------

def _classify_approvals(
    current: V2PromotionSnapshot,
    approvals: list[V2PromotionApproval],
) -> tuple[str, int | None, bool, bool]:
    """Returns (approval_status, days_until_expiry, is_stale, hash_match)."""
    if not approvals:
        return ("NONE", None, False, True)

    # Most-recent decision wins for status
    sorted_apps = sorted(approvals, key=lambda a: a.approved_at)
    rescinded = any(a.decision == "RESCIND" for a in sorted_apps)
    if rescinded:
        return ("RESCINDED", None, False, True)

    fresh_approve = next(
        (a for a in reversed(sorted_apps) if a.decision == "APPROVE"),
        None,
    )
    if fresh_approve is None:
        return ("NONE", None, False, True)

    snap_dt = dt.datetime(
        current.as_of_date.year, current.as_of_date.month,
        current.as_of_date.day, tzinfo=dt.timezone.utc,
    )
    age_days = (
        snap_dt - fresh_approve.approved_at.astimezone(dt.timezone.utc)
    ).days
    days_until_expiry = APPROVAL_STALENESS_DAYS - age_days

    if days_until_expiry > APPROVAL_EXPIRY_WARN_DAYS:
        status = "ACTIVE"
        is_stale = False
    elif days_until_expiry > 0:
        status = "EXPIRING_SOON"
        is_stale = False
    else:
        status = "EXPIRED"
        is_stale = True

    hash_match = (
        fresh_approve.snapshot_content_hash_at_approval is None
        or current.snapshot_content_hash is None
        or fresh_approve.snapshot_content_hash_at_approval
            == current.snapshot_content_hash
    )
    return (status, int(days_until_expiry), bool(is_stale), bool(hash_match))


def _governance_report(
    current: V2PromotionSnapshot,
    approvals: list[V2PromotionApproval],
) -> GovernanceReport:
    status, days_until, is_stale, hash_match = _classify_approvals(
        current, approvals,
    )
    return GovernanceReport(
        approval_status=status,
        days_until_expiry=days_until,
        is_stale=is_stale,
        snapshot_content_hash_match=hash_match,
        code_version=current.code_version,
        timezone=current.timezone,
        schema_version=int(current.schema_version) if current.schema_version is not None else None,
    )


# ---------------------------------------------------------------------------
# Red flags
# ---------------------------------------------------------------------------

def _flag_tail_emergency(current: V2PromotionSnapshot) -> RedFlag | None:
    if current.state != STATE_SUSPENDED:
        return None
    reason = current.rollback_reason or ""
    if "emergency" not in reason:
        return None
    return RedFlag(
        code="TAIL_EMERGENCY",
        severity="REVIEW",
        message=(
            f"Tail emergency triggered SUSPENDED on "
            f"{current.as_of_date.isoformat()}: {reason}"
        ),
    )


def _flag_repeated_suspended(
    current: V2PromotionSnapshot,
    prior: list[V2PromotionSnapshot],
) -> RedFlag | None:
    window = prior[-SUSPENDED_REPEAT_WINDOW_WEEKS:] + [current]
    suspended_count = sum(
        1 for s in window if s.state == STATE_SUSPENDED
    )
    if suspended_count < SUSPENDED_REPEAT_THRESHOLD:
        return None
    return RedFlag(
        code="REPEATED_SUSPENDED",
        severity="REVIEW",
        message=(
            f"{suspended_count} SUSPENDED events in last "
            f"{SUSPENDED_REPEAT_WINDOW_WEEKS}w — investigate underlying tail risk"
        ),
    )


def _flag_high_conf_failing_gates(
    current: V2PromotionSnapshot,
) -> RedFlag | None:
    conf = float(current.promotion_confidence or 0.0)
    if conf < 0.70:
        return None
    gates = _gates(current)
    failing = [
        g.get("name", k) for k, g in gates.items()
        if k != "gate_8_operator_approval" and not g.get("passed", True)
    ]
    if not failing:
        return None
    return RedFlag(
        code="HIGH_CONF_FAILING_GATES",
        severity="REVIEW",
        message=(
            f"Confidence {conf:.2f} ≥ 0.70 but {len(failing)} gate(s) "
            f"failing: {', '.join(failing)}"
        ),
    )


def _flag_rapid_ascent(
    current: V2PromotionSnapshot,
    prior: list[V2PromotionSnapshot],
) -> RedFlag | None:
    if current.state != STATE_STRONG_CANDIDATE:
        return None
    chain = prior + [current]
    # Find earliest STRONG_CANDIDATE entry in the trailing chain
    first_strong_idx = next(
        (i for i, s in enumerate(chain) if s.state == STATE_STRONG_CANDIDATE),
        None,
    )
    if first_strong_idx is None:
        return None
    # Find last NOT_READY before that
    last_not_ready_idx = None
    for i in range(first_strong_idx - 1, -1, -1):
        if chain[i].state == STATE_NOT_READY:
            last_not_ready_idx = i
            break
    if last_not_ready_idx is None:
        return None
    weeks = first_strong_idx - last_not_ready_idx
    if weeks > RAPID_ASCENT_MAX_WEEKS:
        return None
    return RedFlag(
        code="RAPID_ASCENT",
        severity="WATCH",
        message=(
            f"STRONG_CANDIDATE reached in {weeks} weeks (rapid); "
            f"double-check OOS depth"
        ),
    )


def _flag_approval_expiring(gov: GovernanceReport) -> RedFlag | None:
    if gov.days_until_expiry is None:
        return None
    if gov.days_until_expiry <= 0 or gov.days_until_expiry > APPROVAL_EXPIRY_WARN_DAYS:
        return None
    return RedFlag(
        code="APPROVAL_EXPIRING_SOON",
        severity="WATCH",
        message=(
            f"Approval expires in {gov.days_until_expiry} day(s); "
            f"operator action required to retain APPROVED state"
        ),
    )


def _flag_approval_expired(gov: GovernanceReport) -> RedFlag | None:
    if gov.approval_status != "EXPIRED":
        return None
    return RedFlag(
        code="APPROVAL_EXPIRED",
        severity="WATCH",
        message=(
            "Approval staleness window passed; state will degrade on "
            "next snapshot"
        ),
    )


def _flag_approval_hash_mismatch(gov: GovernanceReport) -> RedFlag | None:
    if gov.approval_status not in ("ACTIVE", "EXPIRING_SOON"):
        return None
    if gov.snapshot_content_hash_match:
        return None
    return RedFlag(
        code="APPROVAL_HASH_MISMATCH",
        severity="REVIEW",
        message=(
            "Active approval references stale snapshot hash; evidence "
            "has changed since approval"
        ),
    )


def _flag_comparison_health_degraded(
    current: V2PromotionSnapshot,
    prior: list[V2PromotionSnapshot],
) -> RedFlag | None:
    chain = prior[-6:] + [current]   # 7 total
    failures = sum(
        1 for s in chain
        if not bool((_gates_block(s)).get("comparison_fetch_ok", True))
    )
    if failures <= COMPARISON_HEALTH_FAILURE_TOLERANCE:
        return None
    return RedFlag(
        code="COMPARISON_HEALTH_DEGRADED",
        severity="REVIEW",
        message=(
            f"Comparison framework health degraded ({failures}/7 "
            f"fetches failed)"
        ),
    )


def _flag_insufficient_sample_persist(
    current: V2PromotionSnapshot,
    prior: list[V2PromotionSnapshot],
) -> RedFlag | None:
    chain = prior[-(INSUFFICIENT_SAMPLE_PERSIST_WEEKS - 1):] + [current]
    if len(chain) < INSUFFICIENT_SAMPLE_PERSIST_WEEKS:
        return None

    def _has_insufficient(s: V2PromotionSnapshot) -> bool:
        for g in _gates(s).values():
            reason = str(g.get("reason") or "")
            if "INSUFFICIENT" in reason:
                return True
        return False

    if not all(_has_insufficient(s) for s in chain):
        return None
    return RedFlag(
        code="INSUFFICIENT_SAMPLE_PERSIST",
        severity="WATCH",
        message=(
            f"Insufficient sample persists for "
            f"{INSUFFICIENT_SAMPLE_PERSIST_WEEKS}w; data accumulation "
            f"slower than expected"
        ),
    )


def _flag_streak_reset_frequent(streaks: StreaksReport) -> RedFlag | None:
    if streaks.streak_reset_count_last_8w < STREAK_RESET_FREQUENT_THRESHOLD:
        return None
    return RedFlag(
        code="STREAK_RESET_FREQUENT",
        severity="WATCH",
        message=(
            f"Verdict streak reset {streaks.streak_reset_count_last_8w} "
            f"times in last 8w; underlying signal is noisy"
        ),
    )


def _flag_confidence_basis_warnings(
    basis: tuple[str, ...],
) -> RedFlag | None:
    if not basis:
        return None
    summary = "; ".join(basis[:3])
    if len(basis) > 3:
        summary += f" (+ {len(basis) - 3} more)"
    return RedFlag(
        code="CONFIDENCE_BASIS_WARNINGS",
        severity="INFO",
        message=(
            f"Confidence components flagged as vacuously high: {summary}"
        ),
    )


def _flag_bundle_schema_downgrade(
    schema_version: int | None,
) -> RedFlag | None:
    if schema_version is None:
        return None
    if schema_version >= LATEST_KNOWN_BUNDLE_SCHEMA:
        return None
    return RedFlag(
        code="BUNDLE_SCHEMA_DOWNGRADE",
        severity="INFO",
        message=(
            f"Snapshot bundle schema {schema_version} behind latest known "
            f"({LATEST_KNOWN_BUNDLE_SCHEMA}); expected fields may be missing"
        ),
    )


def _evaluate_red_flags(
    current: V2PromotionSnapshot,
    prior: list[V2PromotionSnapshot],
    gov: GovernanceReport,
    streaks: StreaksReport,
    basis: tuple[str, ...],
) -> tuple[RedFlag, ...]:
    flags: list[RedFlag] = []
    for fn, args in (
        (_flag_tail_emergency, (current,)),
        (_flag_repeated_suspended, (current, prior)),
        (_flag_high_conf_failing_gates, (current,)),
        (_flag_rapid_ascent, (current, prior)),
        (_flag_approval_expiring, (gov,)),
        (_flag_approval_expired, (gov,)),
        (_flag_approval_hash_mismatch, (gov,)),
        (_flag_comparison_health_degraded, (current, prior)),
        (_flag_insufficient_sample_persist, (current, prior)),
        (_flag_streak_reset_frequent, (streaks,)),
        (_flag_confidence_basis_warnings, (basis,)),
        (_flag_bundle_schema_downgrade, (current.schema_version,)),
    ):
        result = fn(*args)
        if result is not None:
            flags.append(result)
    return tuple(flags)


# ---------------------------------------------------------------------------
# Assessment + recommended action rollup
# ---------------------------------------------------------------------------

def _assess(red_flags: tuple[RedFlag, ...]) -> str:
    severities = {f.severity for f in red_flags}
    if "REVIEW" in severities:
        return "REVIEW_REQUIRED"
    if "WATCH" in severities:
        return "WATCH"
    return "NORMAL"


def _recommended_action(
    state: str, assessment: str, red_flags: tuple[RedFlag, ...],
) -> str:
    """Bounded enum: NONE | REVIEW | INVESTIGATE | DO_NOT_APPROVE.
    NEVER returns APPROVE or EXECUTE."""
    has_review = any(f.severity == "REVIEW" for f in red_flags)
    if state == STATE_STRONG_CANDIDATE and has_review:
        return "DO_NOT_APPROVE"
    if assessment == "REVIEW_REQUIRED":
        return "INVESTIGATE"
    if assessment == "WATCH":
        return "REVIEW"
    return "NONE"


# ---------------------------------------------------------------------------
# Public: build_weekly_report (PURE)
# ---------------------------------------------------------------------------

def _iso_week_str(d: dt.date) -> str:
    iy, iw, _ = d.isocalendar()
    return f"{iy}-W{iw:02d}"


def build_weekly_report(
    *,
    snapshot: V2PromotionSnapshot,
    prior_snapshots: list[V2PromotionSnapshot],
    approvals_for_snapshot: list[V2PromotionApproval],
) -> WeeklyOOSReport:
    """Pure function. No DB access. No side effects.

    `prior_snapshots` should be ordered oldest-first and exclude the
    current snapshot. `approvals_for_snapshot` are the approval rows
    referencing `snapshot.id`.
    """
    edge = _edge_report(snapshot, prior_snapshots)
    tail = _tail_report(snapshot)
    streaks = _streaks_report(snapshot, prior_snapshots)
    governance = _governance_report(snapshot, approvals_for_snapshot)
    basis = _confidence_basis(snapshot)
    red_flags = _evaluate_red_flags(
        snapshot, prior_snapshots, governance, streaks, basis,
    )
    assessment = _assess(red_flags)
    recommended = _recommended_action(snapshot.state, assessment, red_flags)

    notes: list[str] = []
    if edge.trend == "INSUFFICIENT":
        notes.append(
            "Insufficient prior history for edge trend "
            f"(need ≥ {TREND_LOOKBACK_WEEKS + TREND_PRIOR_WEEKS} prior snapshots)"
        )
    if not tail.tail_by_regime_present:
        notes.append(
            "tail_by_regime missing from comparison bundle "
            "(pre-Phase-9B.3 snapshot)"
        )

    return WeeklyOOSReport(
        schema_version=REPORT_SCHEMA_VERSION,
        week=_iso_week_str(snapshot.as_of_date),
        as_of_date=snapshot.as_of_date.isoformat(),
        snapshot_id=int(snapshot.id),
        state=str(snapshot.state),
        confidence=float(snapshot.promotion_confidence),
        confidence_basis=basis,
        edge=edge,
        tail=tail,
        streaks=streaks,
        governance=governance,
        assessment=assessment,
        red_flags=red_flags,
        notes=tuple(notes),
        recommended_action=recommended,
    )


# ---------------------------------------------------------------------------
# Public: read-only DB wrapper
# ---------------------------------------------------------------------------

def fetch_and_build_weekly_report(
    session: Session,
    *,
    snapshot_id: int | None = None,
    history_window_weeks: int = 16,
) -> WeeklyOOSReport | None:
    """Read-only DB access. Performs SELECT queries only; never writes.

    Returns None if no snapshot exists (or supplied id not found).
    """
    if snapshot_id is None:
        snapshot = session.scalar(
            select(V2PromotionSnapshot)
            .order_by(desc(V2PromotionSnapshot.as_of_date),
                       desc(V2PromotionSnapshot.id))
            .limit(1)
        )
    else:
        snapshot = session.get(V2PromotionSnapshot, snapshot_id)
    if snapshot is None:
        return None

    prior_rows = list(session.scalars(
        select(V2PromotionSnapshot)
        .where(V2PromotionSnapshot.as_of_date < snapshot.as_of_date)
        .order_by(desc(V2PromotionSnapshot.as_of_date),
                   desc(V2PromotionSnapshot.id))
        .limit(history_window_weeks)
    ).all())
    prior_rows.reverse()   # oldest-first

    approvals = list(session.scalars(
        select(V2PromotionApproval)
        .where(V2PromotionApproval.snapshot_id == snapshot.id)
        .order_by(V2PromotionApproval.approved_at.asc())
    ).all())

    return build_weekly_report(
        snapshot=snapshot,
        prior_snapshots=prior_rows,
        approvals_for_snapshot=approvals,
    )


# ---------------------------------------------------------------------------
# JSON serialization
# ---------------------------------------------------------------------------

def to_jsonable(report: WeeklyOOSReport) -> dict[str, Any]:
    out = dataclasses.asdict(report)
    # Convert tuples → lists for JSON
    def _walk(v: Any) -> Any:
        if isinstance(v, tuple):
            return [_walk(x) for x in v]
        if isinstance(v, list):
            return [_walk(x) for x in v]
        if isinstance(v, dict):
            return {k: _walk(x) for k, x in v.items()}
        return v
    return _walk(out)
