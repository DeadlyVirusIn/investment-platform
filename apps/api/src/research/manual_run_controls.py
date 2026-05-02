"""Phase 11W (Phase E.1) — enterprise-safe controls for manual runs.

Adds operator allowlist, rate limiting, audit logging, usage
tracking, and rule-based anomaly detection on top of Phase E. ALL
checks run **before** the provider is invoked. Audit rows are
written for both accepted and rejected attempts.

NEVER imports execution / scoring / ML / candidate / paper / options
modules. NEVER schedules itself. NEVER returns raw provider body.
NEVER feeds research output back into trading decisions. CI grep
tests enforce these invariants.
"""

from __future__ import annotations

import datetime as dt
import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterable

from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.config import settings


# ---------------------------------------------------------------------------
# Allowlist parsing
# ---------------------------------------------------------------------------


def _csv_set(s: str | None) -> frozenset[str]:
    if not s:
        return frozenset()
    return frozenset(part.strip() for part in s.split(",") if part.strip())


def is_operator_allowed(operator_id: str) -> bool:
    """Returns True iff:
      * operator_id appears in RESEARCH_ALLOWED_OPERATORS CSV, OR
      * RESEARCH_LOCAL_TEST_MODE is True AND the allowlist is empty.

    Never raises. Returns False on empty/None operator_id."""
    if not operator_id:
        return False
    allow = _csv_set(settings.RESEARCH_ALLOWED_OPERATORS)
    if allow:
        return operator_id in allow
    # No allowlist configured — production refuses; local-test allows any.
    return bool(settings.RESEARCH_LOCAL_TEST_MODE)


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------


def write_audit_in_flight(
    session: Session, *,
    operator_id: str, symbol: str, as_of: dt.date,
    provider: str, request_source: str,
    request_id: str | None = None,
    estimated_cost_usd: float | None = None,
    anomaly_flags: Iterable[str] | None = None,
) -> str:
    """Insert an audit row with status='in_flight' BEFORE the
    provider is invoked. Returns the new audit row id (uuid str).

    Uses ON CONFLICT DO NOTHING when request_id is set so
    idempotent retries don't double-log."""
    audit_id = str(uuid.uuid4())
    flags_json = json.dumps(list(anomaly_flags or []))
    if request_id:
        # Idempotent path — a duplicate request_id collapses to the
        # original audit row id.
        existing = session.execute(text(
            "SELECT id::text FROM research_ro.research_manual_run_audit "
            "WHERE request_id = :rid"
        ), {"rid": request_id}).first()
        if existing:
            return str(existing[0])
    session.execute(text(
        """
        INSERT INTO research_ro.research_manual_run_audit
          (id, operator_id, symbol, as_of, provider, request_source,
           estimated_cost_usd, status, anomaly_flags, request_id)
        VALUES
          (CAST(:id AS uuid), :op, :sym, :asof, :prov, :src,
           :est_cost, 'in_flight', CAST(:flags AS jsonb), :rid)
        """
    ), {
        "id": audit_id, "op": operator_id, "sym": symbol,
        "asof": as_of, "prov": provider, "src": request_source,
        "est_cost": estimated_cost_usd, "flags": flags_json,
        "rid": request_id,
    })
    session.commit()
    return audit_id


def write_audit_terminal(
    session: Session, *,
    audit_id: str, status: str,
    rejection_reason: str | None = None,
    research_run_id: str | None = None,
    actual_cost_usd: float | None = None,
    model_id: str | None = None,
    prompt_hash: str | None = None,
    extra_anomaly_flags: Iterable[str] | None = None,
) -> None:
    """Update an existing audit row to its terminal status. Append
    any newly-detected anomaly flags onto the existing array."""
    session.execute(text(
        """
        UPDATE research_ro.research_manual_run_audit
        SET status            = :status,
            rejection_reason  = :reason,
            research_run_id   = CAST(:rid AS uuid),
            actual_cost_usd   = COALESCE(:cost, actual_cost_usd),
            model_id          = COALESCE(:mid, model_id),
            prompt_hash       = COALESCE(:phash, prompt_hash),
            anomaly_flags     = anomaly_flags || CAST(:extra AS jsonb)
        WHERE id = CAST(:id AS uuid)
        """
    ), {
        "id": audit_id, "status": status,
        "reason": rejection_reason, "rid": research_run_id,
        "cost": actual_cost_usd, "mid": model_id, "phash": prompt_hash,
        "extra": json.dumps(list(extra_anomaly_flags or [])),
    })
    session.commit()


def write_audit_rejection(
    session: Session, *,
    operator_id: str, symbol: str, as_of: dt.date,
    provider: str, request_source: str,
    rejection_reason: str,
    estimated_cost_usd: float | None = None,
    request_id: str | None = None,
    anomaly_flags: Iterable[str] | None = None,
) -> str:
    """Direct one-shot insert of a rejection. Used when the request
    is refused before any provider call is even attempted."""
    audit_id = str(uuid.uuid4())
    flags_json = json.dumps(list(anomaly_flags or []))
    session.execute(text(
        """
        INSERT INTO research_ro.research_manual_run_audit
          (id, operator_id, symbol, as_of, provider, request_source,
           estimated_cost_usd, status, rejection_reason,
           anomaly_flags, request_id)
        VALUES
          (CAST(:id AS uuid), :op, :sym, :asof, :prov, :src,
           :est_cost, 'rejected', :reason,
           CAST(:flags AS jsonb), :rid)
        """
    ), {
        "id": audit_id, "op": operator_id, "sym": symbol,
        "asof": as_of, "prov": provider, "src": request_source,
        "est_cost": estimated_cost_usd, "reason": rejection_reason,
        "flags": flags_json, "rid": request_id,
    })
    session.commit()
    return audit_id


# ---------------------------------------------------------------------------
# Usage tracking — read-only
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UsageSummary:
    operator_id: str
    runs_today_by_operator: int
    runs_today_by_symbol_for_operator: dict[str, int]
    rejected_today_by_operator: int
    total_cost_today_usd: float
    last_successful_run_at: dt.datetime | None
    last_rejection_reason: str | None


def usage_summary(
    session: Session, *, operator_id: str,
) -> UsageSummary:
    """Read-only operator-scoped usage summary. Counts derived from
    research_manual_run_audit only (single-source-of-truth for
    rejections too)."""
    today_filter = (
        "(created_at AT TIME ZONE 'UTC')::date "
        "= (now() AT TIME ZONE 'UTC')::date"
    )
    n_runs_op = int(session.execute(text(
        f"""
        SELECT count(*) FROM research_ro.research_manual_run_audit
        WHERE operator_id = :op
          AND status IN ('accepted', 'duplicate')
          AND {today_filter}
        """
    ), {"op": operator_id}).scalar() or 0)
    n_rejected_op = int(session.execute(text(
        f"""
        SELECT count(*) FROM research_ro.research_manual_run_audit
        WHERE operator_id = :op AND status = 'rejected'
          AND {today_filter}
        """
    ), {"op": operator_id}).scalar() or 0)
    by_symbol_rows = session.execute(text(
        f"""
        SELECT symbol, count(*)::int AS n
        FROM research_ro.research_manual_run_audit
        WHERE operator_id = :op
          AND status IN ('accepted', 'duplicate')
          AND {today_filter}
        GROUP BY symbol
        """
    ), {"op": operator_id}).mappings().all()
    by_symbol = {r["symbol"]: int(r["n"]) for r in by_symbol_rows}
    total_cost = float(session.execute(text(
        f"""
        SELECT COALESCE(SUM(actual_cost_usd), 0)::float8
        FROM research_ro.research_manual_run_audit
        WHERE operator_id = :op
          AND status IN ('accepted', 'duplicate')
          AND {today_filter}
        """
    ), {"op": operator_id}).scalar() or 0.0)
    last_success = session.execute(text(
        """
        SELECT created_at FROM research_ro.research_manual_run_audit
        WHERE operator_id = :op AND status = 'accepted'
        ORDER BY created_at DESC LIMIT 1
        """
    ), {"op": operator_id}).first()
    last_reject = session.execute(text(
        """
        SELECT rejection_reason FROM research_ro.research_manual_run_audit
        WHERE operator_id = :op AND status = 'rejected'
        ORDER BY created_at DESC LIMIT 1
        """
    ), {"op": operator_id}).first()
    return UsageSummary(
        operator_id=operator_id,
        runs_today_by_operator=n_runs_op,
        runs_today_by_symbol_for_operator=by_symbol,
        rejected_today_by_operator=n_rejected_op,
        total_cost_today_usd=total_cost,
        last_successful_run_at=last_success[0] if last_success else None,
        last_rejection_reason=(
            last_reject[0] if last_reject and last_reject[0] else None
        ),
    )


# ---------------------------------------------------------------------------
# Rate-limit helpers — enforce before provider call
# ---------------------------------------------------------------------------


def _audit_today_count(
    session: Session, *,
    operator_id: str | None = None,
    symbol: str | None = None,
    statuses: Iterable[str] = ("accepted", "duplicate", "in_flight"),
) -> int:
    where = ["(created_at AT TIME ZONE 'UTC')::date = (now() AT TIME ZONE 'UTC')::date"]
    params: dict[str, Any] = {}
    if operator_id is not None:
        where.append("operator_id = :op")
        params["op"] = operator_id
    if symbol is not None:
        where.append("symbol = :sym")
        params["sym"] = symbol
    where.append("status = ANY(:st)")
    params["st"] = list(statuses)
    sql = (
        "SELECT count(*) FROM research_ro.research_manual_run_audit "
        "WHERE " + " AND ".join(where)
    )
    return int(session.execute(text(sql), params).scalar() or 0)


def _concurrent_in_flight(session: Session) -> int:
    """Count audit rows whose status='in_flight' and created within
    the last 5 minutes. Stale in_flight rows older than that are
    treated as failed-but-not-finalized and not counted (see
    `cleanup_stale_in_flight` below)."""
    return int(session.execute(text(
        """
        SELECT count(*) FROM research_ro.research_manual_run_audit
        WHERE status = 'in_flight'
          AND created_at > now() - interval '5 minutes'
        """
    )).scalar() or 0)


def cleanup_stale_in_flight(session: Session) -> int:
    """Mark stale in_flight rows as 'error' so concurrency bookkeeping
    doesn't deadlock on crashed processes. Idempotent."""
    n = int(session.execute(text(
        """
        UPDATE research_ro.research_manual_run_audit
        SET status = 'error',
            rejection_reason = COALESCE(rejection_reason, 'stale_in_flight')
        WHERE status = 'in_flight'
          AND created_at <= now() - interval '5 minutes'
        """
    )).rowcount or 0)
    session.commit()
    return n


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    reason: str | None
    operator_runs_today: int
    symbol_runs_today: int
    concurrent_in_flight: int


def check_rate_limits(
    session: Session, *,
    operator_id: str, symbol: str,
) -> RateLimitDecision:
    cleanup_stale_in_flight(session)
    op_count = _audit_today_count(session, operator_id=operator_id)
    sym_count = _audit_today_count(session, symbol=symbol)
    in_flight = _concurrent_in_flight(session)

    op_cap = int(settings.RESEARCH_MAX_RUNS_PER_OPERATOR_DAILY)
    sym_cap = int(settings.RESEARCH_MAX_RUNS_PER_SYMBOL_DAILY)
    cc_cap = int(settings.RESEARCH_MAX_CONCURRENT_MANUAL_RUNS)

    if op_count >= op_cap:
        return RateLimitDecision(
            allowed=False,
            reason=(
                f"operator '{operator_id}' has hit daily cap "
                f"({op_count} >= {op_cap})"
            ),
            operator_runs_today=op_count,
            symbol_runs_today=sym_count,
            concurrent_in_flight=in_flight,
        )
    if sym_count >= sym_cap:
        return RateLimitDecision(
            allowed=False,
            reason=(
                f"symbol '{symbol}' has hit daily cap "
                f"({sym_count} >= {sym_cap})"
            ),
            operator_runs_today=op_count,
            symbol_runs_today=sym_count,
            concurrent_in_flight=in_flight,
        )
    if in_flight >= cc_cap:
        return RateLimitDecision(
            allowed=False,
            reason=(
                f"concurrent in-flight limit reached "
                f"({in_flight} >= {cc_cap})"
            ),
            operator_runs_today=op_count,
            symbol_runs_today=sym_count,
            concurrent_in_flight=in_flight,
        )
    return RateLimitDecision(
        allowed=True, reason=None,
        operator_runs_today=op_count,
        symbol_runs_today=sym_count,
        concurrent_in_flight=in_flight,
    )


# ---------------------------------------------------------------------------
# Anomaly detection — rule-based, deterministic
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AnomalyReport:
    flags: list[str] = field(default_factory=list)


def detect_anomalies(
    session: Session, *,
    operator_id: str, symbol: str,
    estimated_cost_usd: float | None = None,
) -> AnomalyReport:
    """Compute rule-based anomaly flags for a *prospective* attempt.
    Pure-fn over the audit log — no model, no LLM, no scoring."""
    flags: list[str] = []
    win_min = int(settings.RESEARCH_ANOMALY_REJECTED_WINDOW_MIN)
    rejected_thr = int(settings.RESEARCH_ANOMALY_REJECTED_THRESHOLD)
    token_thr = int(settings.RESEARCH_ANOMALY_TOKEN_VIOLATION_THRESHOLD)
    dup_thr = int(settings.RESEARCH_ANOMALY_DUPLICATE_THRESHOLD)

    rejected_n = int(session.execute(text(
        f"""
        SELECT count(*) FROM research_ro.research_manual_run_audit
        WHERE operator_id = :op AND status = 'rejected'
          AND created_at > now() - interval '{win_min} minutes'
        """
    ), {"op": operator_id}).scalar() or 0)
    if rejected_n >= rejected_thr:
        flags.append(
            f"operator_repeated_rejections:{rejected_n}>={rejected_thr}"
        )

    token_n = int(session.execute(text(
        f"""
        SELECT count(*) FROM research_ro.research_manual_run_audit
        WHERE operator_id = :op
          AND rejection_reason ILIKE '%token%'
          AND created_at > now() - interval '{win_min} minutes'
        """
    ), {"op": operator_id}).scalar() or 0)
    if token_n >= token_thr:
        flags.append(
            f"operator_repeated_token_violations:{token_n}>={token_thr}"
        )

    dup_n = int(session.execute(text(
        f"""
        SELECT count(*) FROM research_ro.research_manual_run_audit
        WHERE operator_id = :op
          AND symbol = :sym
          AND status = 'duplicate'
          AND created_at > now() - interval '{win_min} minutes'
        """
    ), {"op": operator_id, "sym": symbol}).scalar() or 0)
    if dup_n >= dup_thr:
        flags.append(
            f"operator_symbol_duplicate_spam:{dup_n}>={dup_thr}"
        )

    per_run_cap = float(settings.RESEARCH_MAX_RUN_COST_USD)
    spike_mult = float(settings.RESEARCH_ANOMALY_COST_SPIKE_MULTIPLIER)
    if (
        estimated_cost_usd is not None
        and per_run_cap > 0
        and estimated_cost_usd >= spike_mult * per_run_cap
    ):
        flags.append(
            f"cost_spike:est=${estimated_cost_usd:.4f}"
            f">={spike_mult:.1f}x_run_cap"
        )

    if flags:
        logger.warning(
            "[manual_run_anomaly] operator={} symbol={} flags={}",
            operator_id, symbol, flags,
        )
    return AnomalyReport(flags=flags)
