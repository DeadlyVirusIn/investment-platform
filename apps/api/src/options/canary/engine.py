"""Canary-1 engine — operational shell.

Gate 4 deliverable. Interface-contract compliant; no business logic.

Two write gateways are real and importable (telemetry + lifecycle event)
so that callers can use them on the flag-off path. Logic stubs return
no-op placeholders. Master flag gates in the worker wrappers ensure no
stub is ever reached under current configuration.

See:
  docs/research/OPTIONS_CANARY_1_EXECUTION_PLAN.md
  docs/research/OPTIONS_CANARY_1_GATE_3_MODULE_SKELETONS.md

Contracts implemented:
  - PreflightResult dataclass
  - preflight(now) -> PreflightResult                  [STUB]
  - run_proposal_cycle(now) -> WrapperResult           [STUB]
  - run_lifecycle_cycle(now) -> WrapperResult          [STUB]
  - _select_candidate_contract(...)                    [STUB]
  - _execute_fill(...)                                 [STUB]
  - _evaluate_exit_triggers(...)                       [STUB]
  - _reconcile_close_accounting(...)                   [STUB]
  - _append_lifecycle_event(...)                       [REAL gateway]
  - _write_canary_telemetry(...)                       [REAL gateway]

Append-only invariant: this module contains NO UPDATE / DELETE
statements against options_trade_lifecycle_event or
options_canary_lifecycle_run. CI lint (canary_gateway_lint.py)
enforces this across the repo.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib as _hashlib
import json as _json
from typing import Any, Literal

from loguru import logger
from sqlalchemy import text as _sql_text

from apps.api.src.db import SessionLocal


# ---------------------------------------------------------------------------
# Closed enums (string literals; mirror Gate 2 DB CHECK constraints).
# ---------------------------------------------------------------------------

CANARY_PORTFOLIO_ID = "canary-spy-v1"
CANARY_UNIVERSE = ("SPY",)

LifecycleEvent = Literal[
    "PROPOSED",
    "PROPOSAL_EXPIRED",
    "OPENED",
    "MONITORED",
    "CLOSED",
    "MANUAL_OPERATOR_PAUSE",
    "MANUAL_OPERATOR_CLOSE",
]

JobName = Literal["canary_proposal", "canary_lifecycle"]

Classification = Literal[
    "success", "no_op", "paused", "error", "operator_action",
]

FailureCode = Literal[
    "F1_stale_chain",
    "F2_no_fill",
    "F3_pricing_invalid",
    "F4_lifecycle_stall",
    "F5_expiry_edge",
    "F6_deployment_drift",
    "F7_telemetry_mismatch",
]

MONITOR_MIN_INTERVAL_SECONDS = 60


# ---------------------------------------------------------------------------
# Pre-flight contract
# ---------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class PreflightResult:
    """Outcome of the canary pre-flight sequence.

    See OPTIONS_CANARY_1_GATE_3_MODULE_SKELETONS.md §3.
    Caller maps `kind` to wrapper-RC reason + telemetry failure_code.
    """

    ok: bool
    kind: Literal[
        "ok", "drift", "schema_drift", "chain_stale",
        "portfolio_paused", "exception",
    ]
    failed_check: str | None = None
    details: dict | None = None


# Gate 5 EXCEPTION: anchor freshness on actual actionable chain data
# (MAX(snapshot_at_utc) for SPY) rather than ingest_run.started_at, and
# allow a 240-minute window to accommodate after-hours dry-run timing.
# Tightening at Gate 6+:
#   - revert threshold to 90 minutes (or market-session-aware)
#   - reject stale after-hours quotes
#   - no relaxation of quote-validity gates
# See: OPTIONS_CANARY_1_GATE_5_BLAST_RADIUS.md §6 "Gate 5 freshness
# exception" note.
CHAIN_FRESHNESS_MAX_AGE_MINUTES = 240


def preflight(now: dt.datetime) -> PreflightResult:
    """Run the canary pre-flight check sequence (in-container scope).

    Performs the two DB-readable checks that can be done from inside a
    worker container:
      3. canary portfolio active flag
      4. chain freshness via options_chain_ingest_run

    Checks 1 (md5 parity) and 2 (alembic head equality) are performed
    out-of-band by scripts/canary_preflight.py, which runs on the host
    with docker exec access to each worker container. The operator MUST
    run that script with --strict before flipping OPTIONS_CANARY_ENABLED.

    Fail-fast order: portfolio_paused before chain_stale (no point
    checking freshness if the portfolio is dormant by design).
    """
    # Check 3: canary portfolio active
    try:
        with SessionLocal() as session:
            row = session.execute(
                _sql_text(
                    "SELECT active FROM options_paper_portfolio "
                    "WHERE name = :name"
                ),
                {"name": CANARY_PORTFOLIO_ID},
            ).first()
    except Exception as exc:  # noqa: BLE001
        return PreflightResult(
            ok=False, kind="exception",
            failed_check="portfolio_active_query",
            details={"error": f"{type(exc).__name__}: {str(exc)[:200]}"},
        )
    if row is None:
        return PreflightResult(
            ok=False, kind="portfolio_paused",
            failed_check="portfolio_missing",
            details={"portfolio": CANARY_PORTFOLIO_ID},
        )
    if not bool(row[0]):
        return PreflightResult(
            ok=False, kind="portfolio_paused",
            failed_check="portfolio_active=false",
            details={"portfolio": CANARY_PORTFOLIO_ID},
        )

    # Check 4: chain freshness via MAX(snapshot_at_utc) on the actual
    # SPY chain table (Gate 5 exception — see CHAIN_FRESHNESS_MAX_AGE_MINUTES
    # comment above). The selector will act on rows from this snapshot,
    # so anchoring freshness on the data is more truthful than on the
    # ingest_run telemetry.
    try:
        with SessionLocal() as session:
            row = session.execute(
                _sql_text(
                    "SELECT MAX(snapshot_at_utc) "
                    "FROM options_chain_snapshot "
                    "WHERE underlying = 'SPY'"
                ),
            ).first()
    except Exception as exc:  # noqa: BLE001
        return PreflightResult(
            ok=False, kind="exception",
            failed_check="chain_freshness_query",
            details={"error": f"{type(exc).__name__}: {str(exc)[:200]}"},
        )
    if row is None or row[0] is None:
        return PreflightResult(
            ok=False, kind="chain_stale",
            failed_check="no_spy_chain_rows",
            details={"max_age_minutes": CHAIN_FRESHNESS_MAX_AGE_MINUTES},
        )
    latest_snapshot_at = row[0]
    age_min = (now - latest_snapshot_at).total_seconds() / 60.0
    if age_min > CHAIN_FRESHNESS_MAX_AGE_MINUTES:
        return PreflightResult(
            ok=False, kind="chain_stale",
            failed_check=f"spy_chain_age={age_min:.1f}min",
            details={"latest_snapshot_at": latest_snapshot_at.isoformat(),
                     "age_minutes": age_min,
                     "max_age_minutes": CHAIN_FRESHNESS_MAX_AGE_MINUTES},
        )

    return PreflightResult(
        ok=True, kind="ok",
        failed_check=None,
        details={
            "portfolio_active": True,
            "latest_spy_snapshot_at": latest_snapshot_at.isoformat(),
            "chain_age_minutes": round(age_min, 2),
        },
    )


# ---------------------------------------------------------------------------
# Cycle entrypoints (STUBS)
# ---------------------------------------------------------------------------

async def run_proposal_cycle(now: dt.datetime) -> dict[str, Any]:
    """Generate at-most-one canary proposal for the given moment.

    Order:
      1. preflight (portfolio active + chain freshness)
      2. one-shot guard (any CLOSED canary trade → canary_complete)
      3. capacity guard (any PROPOSED/OPEN canary trade → canary_at_capacity)
      4. candidate selection (SPY ATM call ~30 DTE; deterministic)
      5. quote-validity gates
      6. INSERT options_paper_trade (status=PROPOSED, idempotent on
         proposal_hash)
      7. _append_lifecycle_event(PROPOSED)
      8. _write_canary_telemetry(success)

    Returns wrapper-RC dict per Gate 3 §5.2. Telemetry written on every
    path (including failure paths) so the per-invocation invariant holds.
    """
    started_at = now

    def _finish_skip(reason: str, classification: str,
                    failure_code: FailureCode | None = None,
                    error_summary: dict | None = None,
                    detail: dict | None = None) -> dict[str, Any]:
        _write_canary_telemetry(
            started_at=started_at,
            finished_at=dt.datetime.now(dt.timezone.utc),
            job_name="canary_proposal",
            classification=classification,
            failure_code=failure_code,
            counts={},
            error_summary=error_summary,
        )
        result: dict[str, Any] = {"skipped": True, "reason": reason}
        if detail is not None:
            result["detail"] = detail
        return result

    def _finish_error(reason: str, failure_code: FailureCode,
                      error_summary: dict) -> dict[str, Any]:
        _write_canary_telemetry(
            started_at=started_at,
            finished_at=dt.datetime.now(dt.timezone.utc),
            job_name="canary_proposal",
            classification="error",
            failure_code=failure_code,
            counts={},
            error_summary=error_summary,
        )
        return {"return_code": 1, "reason": reason}

    # ---- 1. preflight --------------------------------------------------
    pf = preflight(now)
    if not pf.ok:
        if pf.kind == "portfolio_paused":
            return _finish_skip(
                reason="canary_paused", classification="paused",
                error_summary={"preflight": dataclasses.asdict(pf)},
            )
        if pf.kind == "chain_stale":
            return _finish_error(
                reason="preflight_failed:chain_stale",
                failure_code="F1_stale_chain",
                error_summary={"preflight": dataclasses.asdict(pf)},
            )
        return _finish_error(
            reason=f"preflight_failed:{pf.kind}",
            failure_code="F6_deployment_drift",
            error_summary={"preflight": dataclasses.asdict(pf)},
        )

    # ---- 2. one-shot + capacity guards ---------------------------------
    try:
        with SessionLocal() as session:
            existing = session.execute(
                _sql_text(
                    "SELECT status FROM options_paper_trade "
                    "WHERE underlying = 'SPY' "
                    "AND strategy_name = 'LONG_CALL' "
                    "ORDER BY created_at DESC LIMIT 1"
                ),
            ).first()
    except Exception as exc:  # noqa: BLE001
        return _finish_error(
            reason=f"exception:{type(exc).__name__}",
            failure_code="F6_deployment_drift",
            error_summary={"phase": "capacity_query",
                           "error": f"{type(exc).__name__}: {str(exc)[:200]}"},
        )

    if existing is not None:
        existing_status = existing[0]
        if existing_status in ("CLOSED", "EXPIRED", "ASSIGNED"):
            return _finish_skip(
                reason="canary_complete", classification="no_op",
                detail={"prior_trade_status": existing_status},
            )
        if existing_status in ("PROPOSED", "OPEN", "EXPIRING"):
            return _finish_skip(
                reason="canary_at_capacity", classification="no_op",
                detail={"prior_trade_status": existing_status},
            )

    # ---- 3. candidate selection ----------------------------------------
    try:
        cand = _select_spy_atm_30dte_call(now)
    except Exception as exc:  # noqa: BLE001
        return _finish_error(
            reason=f"exception:{type(exc).__name__}",
            failure_code="F6_deployment_drift",
            error_summary={"phase": "select_candidate",
                           "error": f"{type(exc).__name__}: {str(exc)[:200]}"},
        )

    if cand is None:
        return _finish_skip(
            reason="no_signal_today", classification="no_op",
            detail={"phase": "select_candidate", "matched": 0},
        )

    # ---- 4. quote-validity gates ---------------------------------------
    gate_failure = _validate_candidate_gates(cand)
    if gate_failure is not None:
        return _finish_error(
            reason=f"pricing_invalid:{gate_failure}",
            failure_code="F3_pricing_invalid",
            error_summary={"phase": "quote_gates",
                           "sub_reason": gate_failure,
                           "candidate": cand},
        )

    # ---- 5. INSERT trade (idempotent on proposal_hash) -----------------
    proposal_hash = _proposal_hash(cand)
    try:
        with SessionLocal() as session:
            row = session.execute(
                _sql_text(
                    "INSERT INTO options_paper_trade "
                    "  (underlying, strategy_name, strategy_version, status, "
                    "   fees_total_dollars, max_loss_dollars, max_profit_dollars, "
                    "   breakeven_upper, fill_model_version, paper_only, "
                    "   proposal_hash) "
                    "VALUES "
                    "  ('SPY', 'LONG_CALL', 'canary-1-v1', 'PROPOSED', "
                    "   0, :max_loss, :max_profit, "
                    "   :breakeven, 'canary-1-gate5-noop', TRUE, "
                    "   :proposal_hash) "
                    "ON CONFLICT (proposal_hash) DO NOTHING "
                    "RETURNING id"
                ),
                {
                    "max_loss": float(cand["mid"]) * 100,
                    "max_profit": float(cand["mid"]) * 100 * 10,  # 10x cap
                    "breakeven": float(cand["strike"]) + float(cand["mid"]),
                    "proposal_hash": proposal_hash,
                },
            ).first()
            session.commit()
    except Exception as exc:  # noqa: BLE001
        return _finish_error(
            reason=f"exception:{type(exc).__name__}",
            failure_code="F6_deployment_drift",
            error_summary={"phase": "insert_trade",
                           "error": f"{type(exc).__name__}: {str(exc)[:200]}"},
        )

    if row is None:
        # Hash collision = exact same proposal already exists. Treat as
        # idempotent no-op.
        return _finish_skip(
            reason="proposal_exists_today", classification="no_op",
            detail={"proposal_hash": proposal_hash},
        )

    trade_id = int(row[0])

    # ---- 6. PROPOSED lifecycle event -----------------------------------
    try:
        event_id = _append_lifecycle_event(
            trade_id=trade_id,
            event="PROPOSED",
            event_at_utc=now,
            triggered_by="canary_proposal_job",
            payload={
                "candidate": cand,
                "proposal_hash": proposal_hash,
                "strategy_id": "LONG_CALL_ATM_30DTE",
            },
        )
    except Exception as exc:  # noqa: BLE001
        return _finish_error(
            reason=f"exception:{type(exc).__name__}",
            failure_code="F6_deployment_drift",
            error_summary={"phase": "append_event",
                           "trade_id": trade_id,
                           "error": f"{type(exc).__name__}: {str(exc)[:200]}"},
        )

    # ---- 7. telemetry --------------------------------------------------
    _write_canary_telemetry(
        started_at=started_at,
        finished_at=dt.datetime.now(dt.timezone.utc),
        job_name="canary_proposal",
        classification="success",
        counts={"n_proposals_generated": 1},
    )
    return {
        "return_code": 0,
        "inserted": 1,
        "classification": "success",
        "detail": {
            "trade_id": trade_id,
            "event_id": event_id,
            "proposal_hash": proposal_hash,
            "candidate_summary": {
                "expiry": cand["expiry"],
                "strike": cand["strike"],
                "mid": cand["mid"],
                "dte": cand["dte"],
            },
        },
    }


async def run_lifecycle_cycle(now: dt.datetime) -> dict[str, Any]:
    """Run one lifecycle pass: fill if pending, monitor if open, close if
    triggered.

    Gate 4 STUB. Returns no-op. Telemetry is still written.
    """
    started_at = now
    finished_at = dt.datetime.now(dt.timezone.utc)
    _write_canary_telemetry(
        started_at=started_at,
        finished_at=finished_at,
        job_name="canary_lifecycle",
        classification="paused",
        counts={},
        error_summary={"stub": "gate_4_no_logic_yet"},
    )
    return {"skipped": True, "reason": "gate_4_stub"}


# ---------------------------------------------------------------------------
# Logic stubs — signatures only. Bodies return safe no-op values.
# ---------------------------------------------------------------------------

def _select_candidate_contract(
    now: dt.datetime,
    underlying_spot: Any,
) -> None:
    """Legacy stub kept for Gate 3 contract surface compatibility.

    The real selection function used by run_proposal_cycle is
    `_select_spy_atm_30dte_call`. This wrapper is preserved so the
    Gate 3 module skeleton table remains a true description of the
    engine's named surfaces.
    """
    return None


# Strategy constants — see OPTIONS_CANARY_1_EXECUTION_PLAN.md §2.
DTE_WINDOW_MIN = 25
DTE_WINDOW_MAX = 45
MIN_OPEN_INTEREST = 100
MIN_VOLUME = 10
MAX_SPREAD_PCT = 0.05


def _select_spy_atm_30dte_call(now: dt.datetime) -> dict | None:
    """Deterministic SPY ATM call selector.

    Picks from the most recent SPY chain snapshot:
      - option_type = 'CALL'
      - expiry in [now + 25d, now + 45d]
      - bid > 0, ask > 0
      - open_interest >= 100
      - volume >= 10
    Orders by:
      - earliest expiry first
      - then |delta - 0.50| ascending (closest to ATM)

    Returns dict or None if no row matches. The strike-distance tie-break
    via delta means we never need an external underlying-spot lookup.
    """
    with SessionLocal() as session:
        row = session.execute(
            _sql_text(
                "WITH latest AS ("
                "  SELECT MAX(snapshot_at_utc) AS s "
                "  FROM options_chain_snapshot "
                "  WHERE underlying = 'SPY'"
                ") "
                "SELECT id, snapshot_at_utc, expiry, strike, option_type, "
                "       option_symbol, bid, ask, mid, last, "
                "       open_interest, volume, delta, gamma, theta, vega, "
                "       iv, quote_age_seconds, provider, "
                "       (expiry - CURRENT_DATE) AS dte "
                "FROM options_chain_snapshot "
                "WHERE underlying = 'SPY' "
                "  AND option_type = 'CALL' "
                "  AND snapshot_at_utc = (SELECT s FROM latest) "
                "  AND (expiry - CURRENT_DATE) BETWEEN :dte_min AND :dte_max "
                "  AND bid IS NOT NULL AND ask IS NOT NULL "
                "  AND bid > 0 AND ask > 0 "
                "  AND open_interest IS NOT NULL "
                "  AND open_interest >= :min_oi "
                "  AND volume IS NOT NULL AND volume >= :min_vol "
                "ORDER BY "
                "  expiry ASC, "
                "  ABS(COALESCE(delta, 0.5) - 0.5) ASC "
                "LIMIT 1"
            ),
            {
                "dte_min": DTE_WINDOW_MIN,
                "dte_max": DTE_WINDOW_MAX,
                "min_oi": MIN_OPEN_INTEREST,
                "min_vol": MIN_VOLUME,
            },
        ).first()
    if row is None:
        return None
    return {
        "chain_id": int(row[0]),
        "snapshot_at_utc": row[1].isoformat(),
        "expiry": row[2].isoformat(),
        "strike": float(row[3]),
        "option_type": row[4],
        "option_symbol": row[5],
        "bid": float(row[6]),
        "ask": float(row[7]),
        "mid": float(row[8]) if row[8] is not None else (float(row[6]) + float(row[7])) / 2.0,
        "last": float(row[9]) if row[9] is not None else None,
        "open_interest": int(row[10]),
        "volume": int(row[11]),
        "delta": float(row[12]) if row[12] is not None else None,
        "gamma": float(row[13]) if row[13] is not None else None,
        "theta": float(row[14]) if row[14] is not None else None,
        "vega": float(row[15]) if row[15] is not None else None,
        "iv": float(row[16]) if row[16] is not None else None,
        "quote_age_seconds": int(row[17]),
        "provider": row[18],
        "dte": int(row[19]),
    }


def _validate_candidate_gates(cand: dict) -> str | None:
    """Run all quote-validity gates from Plan §4. Returns None if all
    pass; otherwise the sub-reason string for `pricing_invalid:<sub>`."""
    bid = cand.get("bid")
    ask = cand.get("ask")
    mid = cand.get("mid")
    if bid is None or bid <= 0:
        return "bid_zero"
    if ask is None or ask <= 0:
        return "ask_zero"
    if ask < bid:
        return "crossed"
    if mid is None or mid <= 0:
        return "mid_zero"
    spread_pct = (ask - bid) / mid
    if spread_pct > MAX_SPREAD_PCT:
        return f"spread_wide:{spread_pct:.4f}"
    if (cand.get("open_interest") or 0) < MIN_OPEN_INTEREST:
        return "oi_thin"
    if (cand.get("volume") or 0) < MIN_VOLUME:
        return "vol_thin"
    return None


def _proposal_hash(cand: dict) -> str:
    """Deterministic hash for ON CONFLICT idempotency on
    options_paper_trade.proposal_hash (VARCHAR(32))."""
    key = (
        f"LONG_CALL_ATM_30DTE|SPY|{cand['expiry']}|"
        f"{cand['strike']:.4f}|{cand['option_type']}|"
        f"{cand['snapshot_at_utc'][:10]}"
    )
    return _hashlib.md5(key.encode("utf-8")).hexdigest()


def _execute_fill(
    trade_id: int,
    chain_row: Any,
    now: dt.datetime,
) -> None:
    """Validate quote gates, fill at mid, write OPENED event. Gate 4 STUB."""
    return None


def _evaluate_exit_triggers(
    position: Any,
    chain_row: Any,
    now: dt.datetime,
) -> None:
    """Evaluate TP/SL/max-hold/expiry triggers. Gate 4 STUB."""
    return None


def _reconcile_close_accounting(
    position: Any,
    exit_chain_row: Any,
    exit_reason: str,
    now: dt.datetime,
) -> None:
    """Compute exit credit, commission, realized P&L, write CLOSED event.
    Gate 4 STUB."""
    return None


# ---------------------------------------------------------------------------
# Write gateways — REAL. Sole legal write surfaces for the two audit tables.
# CI lint (canary_gateway_lint.py) enforces no other INSERT/UPDATE/DELETE
# against options_trade_lifecycle_event or options_canary_lifecycle_run.
# ---------------------------------------------------------------------------

def _append_lifecycle_event(
    *,
    trade_id: int,
    event: LifecycleEvent,
    event_at_utc: dt.datetime,
    triggered_by: str,
    payload: dict | None = None,
) -> int:
    """Append one row to options_trade_lifecycle_event. INSERT only.

    Returns the new event id. Raises on DB failure — lifecycle events
    are load-bearing; we want loud failure if persistence breaks.

    `triggered_by` examples: 'canary_proposal_job', 'canary_lifecycle_job',
    'operator:<operator_id>'.
    """
    payload = payload or {}
    with SessionLocal() as session:
        row = session.execute(
            _sql_text(
                "INSERT INTO options_trade_lifecycle_event "
                "  (trade_id, event_type, event_at_utc, triggered_by, payload_json) "
                "VALUES "
                "  (:trade_id, :event_type, :event_at_utc, :triggered_by, "
                "   CAST(:payload_json AS jsonb)) "
                "RETURNING id"
            ),
            {
                "trade_id": trade_id,
                "event_type": event,
                "event_at_utc": event_at_utc,
                "triggered_by": triggered_by,
                "payload_json": _json.dumps(payload),
            },
        ).first()
        session.commit()
    return int(row[0])


def _write_canary_telemetry(
    *,
    started_at: dt.datetime,
    finished_at: dt.datetime,
    job_name: JobName,
    classification: Classification,
    counts: dict | None = None,
    failure_code: FailureCode | None = None,
    error_summary: dict | None = None,
    operator_fields: dict | None = None,
) -> None:
    """Append one row to options_canary_lifecycle_run. INSERT only.

    Never raises — telemetry write failure is logged at WARN; the
    calling cycle still returns its real outcome. Mirror of
    options_chain_snapshot._write_telemetry pattern (M089).

    When the table is missing (e.g. migration 090 not yet applied),
    this gracefully degrades to a single WARN log line.
    """
    counts = counts or {}
    op_fields = operator_fields or {}
    payload = {
        "started_at": started_at,
        "finished_at": finished_at,
        "job_name": job_name,
        "portfolio_id": CANARY_PORTFOLIO_ID,
        "universe": list(CANARY_UNIVERSE),
        "n_proposals_generated": int(counts.get("n_proposals_generated", 0)),
        "n_fills_executed": int(counts.get("n_fills_executed", 0)),
        "n_monitors_written": int(counts.get("n_monitors_written", 0)),
        "n_exits_executed": int(counts.get("n_exits_executed", 0)),
        "classification": classification,
        "failure_code": failure_code,
        "error_summary": _json.dumps(error_summary) if error_summary else None,
        "operator_id": op_fields.get("operator_id"),
        "operator_reason": op_fields.get("operator_reason"),
        "incident_ref": op_fields.get("incident_ref"),
        "quote_gates_overridden": op_fields.get("quote_gates_overridden"),
        "referenced_event_id": op_fields.get("referenced_event_id"),
        "duration_sec": (finished_at - started_at).total_seconds(),
    }
    try:
        with SessionLocal() as session:
            session.execute(
                _sql_text(
                    "INSERT INTO options_canary_lifecycle_run "
                    "  (started_at, finished_at, job_name, portfolio_id, "
                    "   universe, n_proposals_generated, n_fills_executed, "
                    "   n_monitors_written, n_exits_executed, classification, "
                    "   failure_code, error_summary, operator_id, "
                    "   operator_reason, incident_ref, quote_gates_overridden, "
                    "   referenced_event_id, duration_sec) "
                    "VALUES "
                    "  (:started_at, :finished_at, :job_name, :portfolio_id, "
                    "   :universe, :n_proposals_generated, :n_fills_executed, "
                    "   :n_monitors_written, :n_exits_executed, :classification, "
                    "   :failure_code, CAST(:error_summary AS jsonb), "
                    "   :operator_id, :operator_reason, :incident_ref, "
                    "   :quote_gates_overridden, :referenced_event_id, "
                    "   :duration_sec)"
                ),
                payload,
            )
            session.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "options_canary_lifecycle_run telemetry write failed "
            "(table missing or constraint violation?): {}",
            exc,
        )
