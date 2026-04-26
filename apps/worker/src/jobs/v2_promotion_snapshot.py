"""V2 promotion-trigger weekly snapshot job — Phase 4.

Runs once per ISO week. Reads:
  * paper_shadow_log (via the comparison-framework analytics)
  * v2_promotion_snapshot (prior weeks)
  * v2_promotion_approval (operator approvals against prior snapshots)
  * settings.ENGINE_B_MODE (governance context)

Writes:
  * v2_promotion_snapshot (one new row per ISO week, idempotent)

Never updates anything. Never writes to paper_trade_log, decision_log,
paper_shadow_log, engine_b_router, or any execution surface.

Cron target: Monday 00:15 UTC (per design §Weekly Snapshot Logic).
"""

from __future__ import annotations

import dataclasses
import datetime as dt
from decimal import Decimal
from typing import Any

from loguru import logger
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from apps.api.src.config import settings
from apps.api.src.db import SessionLocal
from apps.api.src.db.models import (
    V2PromotionApproval,
    V2PromotionSnapshot,
)
from apps.api.src.research.b2_v2_comparison import compute_all
from apps.api.src.research.shadow_strategy import (
    SOURCE_STRATEGY as B2_SOURCE_STRATEGY,
)
from apps.api.src.research.shadow_strategy_v2 import SOURCE_STRATEGY_V2
from apps.api.src.research.v2_promotion_gates import (
    GateResult,
    evaluate_all_gates,
)
from apps.api.src.research.v2_promotion_state import (
    NOT_READY,
    advance_or_rollback,
    compute_promotion_confidence,
    update_streaks,
)


# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------

DEFAULT_LOOKBACK_DAYS = 365
DEFAULT_INSTRUMENT = "SPY"
PRIOR_SNAPSHOT_WINDOW = 8        # last N snapshots fed into gates / state
APPROVAL_LOOKBACK_DAYS = 30      # search window for approvals against priors


# ---------------------------------------------------------------------------
# Comparison-bundle fetcher
# ---------------------------------------------------------------------------

_JOIN_SQL = text(
    """
    SELECT
      b2.as_of_date,
      b2.instrument,
      b2.signal           AS b2_signal,
      v2.signal           AS v2_signal,
      b2.regime_label     AS b2_regime,
      v2.regime_label     AS v2_regime,
      b2.fwd_return_1d    AS fwd_return_1d,
      b2.fwd_return_5d    AS fwd_return_5d,
      b2.trend_score      AS b2_trend,
      v2.trend_score      AS v2_trend
    FROM paper_shadow_log b2
    INNER JOIN paper_shadow_log v2
      ON  b2.as_of_date  = v2.as_of_date
      AND b2.instrument  = v2.instrument
    WHERE b2.source_strategy = :b2_src
      AND v2.source_strategy = :v2_src
      AND b2.instrument      = :instrument
      AND b2.as_of_date     >= :cutoff
    ORDER BY b2.as_of_date ASC
    """
)


def fetch_comparison_bundle(
    session: Session,
    *,
    instrument: str = DEFAULT_INSTRUMENT,
    days: int = DEFAULT_LOOKBACK_DAYS,
    today: dt.date | None = None,
) -> dict:
    """Read paper_shadow_log + run pure-fn compute_all. SELECT only."""
    cutoff = (today or dt.date.today()) - dt.timedelta(days=days + 7)
    rs = session.execute(
        _JOIN_SQL,
        {
            "b2_src": B2_SOURCE_STRATEGY,
            "v2_src": SOURCE_STRATEGY_V2,
            "instrument": instrument,
            "cutoff": cutoff,
        },
    ).mappings().all()
    rows: list[dict] = []
    for r in rs:
        d = dict(r)
        for k in ("fwd_return_1d", "fwd_return_5d", "b2_trend", "v2_trend"):
            v = d.get(k)
            d[k] = float(v) if v is not None else None
        rows.append(d)
    return compute_all(rows)


# ---------------------------------------------------------------------------
# Snapshot row → dict (for prior-snapshot inputs)
# ---------------------------------------------------------------------------

def _snapshot_to_dict(snap: V2PromotionSnapshot) -> dict:
    """Shape consumed by gates + state machine + streaks."""
    bundle = snap.comparison_bundle_json or {}
    verdict_block = (bundle.get("verdict") or {}) if isinstance(bundle, dict) else {}
    return {
        "id": snap.id,
        "as_of_date": snap.as_of_date,
        "iso_year": snap.iso_year,
        "iso_week": snap.iso_week,
        "state": snap.state,
        "verdict_streak": int(snap.verdict_streak or 0),
        "readiness_streak": int(snap.readiness_streak or 0),
        "comparison_fetch_ok": bool(
            (snap.gates_json or {}).get("comparison_fetch_ok", True)
        ),
        "tail_guard_triggered": bool(verdict_block.get("tail_guard_triggered")),
        "verdict": {
            "verdict": verdict_block.get("verdict"),
            "readiness": verdict_block.get("readiness"),
            "tail_guard_triggered": bool(verdict_block.get("tail_guard_triggered")),
        },
        "metrics": (bundle.get("metrics") or {}),
    }


def load_prior_snapshots(
    session: Session,
    *,
    limit: int = PRIOR_SNAPSHOT_WINDOW,
) -> list[dict]:
    rows = session.scalars(
        select(V2PromotionSnapshot)
        .order_by(V2PromotionSnapshot.as_of_date.desc())
        .limit(limit)
    ).all()
    rows = list(reversed(rows))   # oldest-first
    return [_snapshot_to_dict(r) for r in rows]


def load_approvals_for_priors(
    session: Session,
    prior_snapshots: list[dict],
    *,
    snapshot_as_of_date: dt.date,
    lookback_days: int = APPROVAL_LOOKBACK_DAYS,
) -> tuple[list[dict], int | None]:
    """Find APPROVE rows for any of the recent prior snapshots.

    Returns (approval_records, target_snapshot_id_for_gate8).

    The target snapshot id is the prior snapshot id referenced by the
    most-recent fresh approval, OR (if none) the most-recent prior
    snapshot id (so Gate 8 can record `n_records=0` against a known id).
    """
    if not prior_snapshots:
        return [], None
    prior_ids = [s["id"] for s in prior_snapshots]
    rows = session.scalars(
        select(V2PromotionApproval)
        .where(V2PromotionApproval.snapshot_id.in_(prior_ids))
        .order_by(V2PromotionApproval.approved_at.asc())
    ).all()
    records = [
        {
            "decision": r.decision,
            "approver": r.approver,
            "rationale": r.rationale,
            "approved_at": r.approved_at,
            "snapshot_id": r.snapshot_id,
        }
        for r in rows
    ]
    # Pick target snapshot id
    target_id: int | None = prior_snapshots[-1]["id"]
    cutoff = dt.datetime(
        snapshot_as_of_date.year,
        snapshot_as_of_date.month,
        snapshot_as_of_date.day,
        tzinfo=dt.timezone.utc,
    ) - dt.timedelta(days=14)
    fresh_approves = sorted(
        [
            r for r in records
            if r["decision"] == "APPROVE"
            and r["approved_at"] >= cutoff
        ],
        key=lambda r: r["approved_at"],
    )
    if fresh_approves:
        target_id = fresh_approves[-1]["snapshot_id"]
    return records, target_id


# ---------------------------------------------------------------------------
# Governance state lookup (caller-supplied per Phase 2 contract)
# ---------------------------------------------------------------------------

def build_governance_state(
    *,
    comparison_fetch_ok: bool,
    engine_b_mode: str | None = None,
) -> dict:
    """Construct the dict that Gate 7 consumes.

    Reads `settings.ENGINE_B_MODE` (config layer — not an execution
    module). ML status hard-coded True per design (this framework
    must abstain if ML is ever promoted; see design §Hard Rules).
    """
    mode = engine_b_mode or getattr(settings, "ENGINE_B_MODE", "LEGACY")
    return {
        "engine_b_mode": str(mode),
        "ml_advisory_only": True,
        "comparison_framework_healthy": bool(comparison_fetch_ok),
        "b2_promotion_paused": False,   # informational only; not surfaced here
    }


# ---------------------------------------------------------------------------
# Serialization helpers for gates_json column
# ---------------------------------------------------------------------------

def _gate_to_jsonable(g: GateResult) -> dict:
    return {
        "name": g.name,
        "passed": bool(g.passed),
        "reason": g.reason,
        "details": _to_jsonable(g.details),
    }


def _to_jsonable(obj: Any) -> Any:
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, (dt.date, dt.datetime)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, dict):
        return {str(k): _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(v) for v in obj]
    if dataclasses.is_dataclass(obj):
        return _to_jsonable(dataclasses.asdict(obj))
    return str(obj)


def serialize_gates_json(
    gates: dict[str, GateResult],
    *,
    confidence,
    decision,
    streaks,
    comparison_fetch_ok: bool,
) -> dict:
    return {
        "gates": {name: _gate_to_jsonable(g) for name, g in gates.items()},
        "confidence_breakdown": _to_jsonable(confidence),
        "decision": _to_jsonable(decision),
        "streaks": _to_jsonable(streaks),
        "comparison_fetch_ok": bool(comparison_fetch_ok),
    }


# ---------------------------------------------------------------------------
# Main job
# ---------------------------------------------------------------------------

def run_v2_promotion_snapshot(
    *,
    as_of: dt.date | None = None,
    instrument: str = DEFAULT_INSTRUMENT,
    days: int = DEFAULT_LOOKBACK_DAYS,
    session_factory=SessionLocal,
) -> dict:
    """Execute one snapshot for the ISO-week containing `as_of`.

    Idempotent on `(iso_year, iso_week)`. Returns a status dict for the
    caller / scheduler.
    """
    target_date = as_of or dt.date.today()
    iso_year, iso_week, _ = target_date.isocalendar()

    with session_factory() as session:
        # Idempotency check FIRST — never compute or fetch if a row exists
        existing = session.scalar(
            select(V2PromotionSnapshot).where(
                V2PromotionSnapshot.iso_year == iso_year,
                V2PromotionSnapshot.iso_week == iso_week,
            )
        )
        if existing is not None:
            logger.info(
                "v2_promotion_snapshot exists for ISO {}-W{:02d} "
                "→ no-op (snapshot_id={})",
                iso_year, iso_week, existing.id,
            )
            return {
                "status": "noop_existing",
                "snapshot_id": existing.id,
                "iso_year": iso_year,
                "iso_week": iso_week,
            }

        # ----- 1. Fetch comparison bundle (READ-ONLY) -----
        try:
            bundle = fetch_comparison_bundle(
                session, instrument=instrument, days=days,
                today=target_date,
            )
            comparison_fetch_ok = True
        except Exception as exc:  # noqa: BLE001 — fail open into NOT_READY
            logger.error(
                "v2_promotion_snapshot: comparison fetch failed: {}", exc,
            )
            bundle = _empty_bundle()
            comparison_fetch_ok = False

        # ----- 2. Load prior snapshots (READ-ONLY) -----
        prior_snapshots = load_prior_snapshots(
            session, limit=PRIOR_SNAPSHOT_WINDOW,
        )
        prior_snapshot = prior_snapshots[-1] if prior_snapshots else None
        prior_state = (
            prior_snapshot["state"] if prior_snapshot else NOT_READY
        )

        # ----- 6. Operator approval lookup (READ-ONLY; Gate 8 input) -----
        approval_records, target_snapshot_id = load_approvals_for_priors(
            session, prior_snapshots, snapshot_as_of_date=target_date,
        )

        # Governance state
        governance_state = build_governance_state(
            comparison_fetch_ok=comparison_fetch_ok,
        )

        # ----- 3. Evaluate all 8 gates -----
        gates = evaluate_all_gates(
            bundle,
            snapshot_as_of_date=target_date,
            snapshot_id=target_snapshot_id,
            prior_snapshots=prior_snapshots,
            governance_state=governance_state,
            approval_records=approval_records,
        )
        approval_present = bool(
            gates["gate_8_operator_approval"].passed
        )

        # ----- 4. Update streaks -----
        verdict_block = (bundle.get("verdict") or {})
        streaks = update_streaks(
            prior_snapshot,
            current_verdict_label=verdict_block.get("verdict"),
            current_readiness_label=verdict_block.get("readiness"),
        )

        # ----- 5. Compute promotion confidence -----
        confidence = compute_promotion_confidence(
            gates, streaks=streaks, bundle=bundle,
        )

        # ----- 7+8. State machine (advance_or_rollback handles tail
        # emergency override internally as its first step) -----
        decision = advance_or_rollback(
            prior_state=prior_state,
            gates=gates,
            streaks=streaks,
            confidence=confidence.total,
            bundle=bundle,
            prior_snapshot=prior_snapshot,
            approval_present=approval_present,
        )

        # ----- 9. Insert -----
        row = V2PromotionSnapshot(
            as_of_date=target_date,
            iso_year=iso_year,
            iso_week=iso_week,
            comparison_bundle_json=_to_jsonable(bundle),
            state=decision.new_state,
            prior_state=(prior_snapshot["state"] if prior_snapshot else None),
            promotion_confidence=Decimal(str(confidence.total)),
            gates_json=serialize_gates_json(
                gates,
                confidence=confidence,
                decision=decision,
                streaks=streaks,
                comparison_fetch_ok=comparison_fetch_ok,
            ),
            verdict_streak=int(streaks.verdict_streak),
            readiness_streak=int(streaks.readiness_streak),
            rollback_reason=decision.rollback_reason,
        )
        try:
            session.add(row)
            session.commit()
            logger.info(
                "v2_promotion_snapshot inserted ISO {}-W{:02d} "
                "state={} confidence={:.4f}",
                iso_year, iso_week, decision.new_state, confidence.total,
            )
            return {
                "status": "inserted",
                "snapshot_id": row.id,
                "iso_year": iso_year,
                "iso_week": iso_week,
                "state": decision.new_state,
                "rollback_reason": decision.rollback_reason,
                "promotion_confidence": float(confidence.total),
            }
        except IntegrityError:
            # Race: another runner won the insert for this ISO week
            session.rollback()
            existing = session.scalar(
                select(V2PromotionSnapshot).where(
                    V2PromotionSnapshot.iso_year == iso_year,
                    V2PromotionSnapshot.iso_week == iso_week,
                )
            )
            logger.warning(
                "v2_promotion_snapshot ISO {}-W{:02d} race → no-op "
                "(snapshot_id={})",
                iso_year, iso_week, existing.id if existing else None,
            )
            return {
                "status": "noop_race",
                "snapshot_id": existing.id if existing else None,
                "iso_year": iso_year,
                "iso_week": iso_week,
            }


# ---------------------------------------------------------------------------
# Helper: empty bundle for fail-open behavior
# ---------------------------------------------------------------------------

def _empty_bundle() -> dict:
    return compute_all([])


# ---------------------------------------------------------------------------
# Async wrapper for the worker registry (Phase 8)
# ---------------------------------------------------------------------------

async def run_v2_promotion_snapshot_job() -> None:
    """No-arg async wrapper for `run_v2_promotion_snapshot`.

    Designed for the DB-backed scheduler (apps/worker/src/scheduler/tick_loop.py).
    The scheduler invokes this with no arguments; the underlying sync
    function uses today's date and default instrument / lookback.

    Idempotency: the underlying job is idempotent on (iso_year, iso_week).
    If this wrapper fires more than once per ISO week (e.g., due to
    scheduler timezone configuration drift, manual re-runs, or scheduler
    restart), the second + later invocations return `noop_existing`
    without computing or inserting anything.

    Logging: `run_v2_promotion_snapshot` already emits one of:
      INFO  v2_promotion_snapshot exists for ISO YYYY-Www → no-op (snapshot_id=...)
      INFO  v2_promotion_snapshot inserted ISO YYYY-Www state=<S> confidence=<C>
      WARN  v2_promotion_snapshot ISO YYYY-Www race → no-op (snapshot_id=...)
    plus, on insert, the rollback_reason column is set whenever the
    state machine downgraded the state — operators inspect via the
    /api/v2-promotion/state endpoint.

    Schedule target: Monday 00:15 UTC (cron `15 0 * * 1` evaluated in
    SCHEDULER_TZ). The scheduler's default timezone is America/New_York;
    if SCHEDULER_TZ is left at default, the cron fires at 00:15 ET on
    Mondays — still satisfies the "single execution per ISO week"
    requirement because of the idempotency guarantee. To match the
    design spec literally (Monday 00:15 UTC), set SCHEDULER_TZ=UTC in
    the worker's environment.
    """
    out = run_v2_promotion_snapshot()
    # Surface the result fields explicitly per Phase 8 logging requirement
    if out.get("status") == "inserted":
        logger.info(
            "v2_promotion_snapshot job → status=inserted snapshot_id={} "
            "iso={}-W{:02d} state={} confidence={:.4f} rollback_reason={}",
            out.get("snapshot_id"),
            out.get("iso_year"), out.get("iso_week"),
            out.get("state"),
            float(out.get("promotion_confidence") or 0.0),
            out.get("rollback_reason"),
        )
    else:
        logger.info(
            "v2_promotion_snapshot job → status={} snapshot_id={} "
            "iso={}-W{:02d}",
            out.get("status"),
            out.get("snapshot_id"),
            out.get("iso_year"), out.get("iso_week"),
        )
