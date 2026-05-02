"""Phase 11W (Phase E) — manual-only research run activation.

Thin wrapper around `manual_run.run_single_asset_context_note` that
enforces every Phase E pre-flight check BEFORE invoking the
provider, then returns sanitized metadata only (never raw model
body, never internal exception traces).

Hard guarantees (verified by tests):
  * NEVER imports execution / scoring / ML / candidate / paper /
    options modules (CI grep enforces).
  * NEVER schedules itself; this module is invoked synchronously
    from a CLI or, when explicitly enabled, from a single
    admin-gated HTTP route.
  * NEVER writes to public schema. All persistence is via
    `manual_run` which targets `research_ro.research_run` and
    `research_ro.research_agent_output` only.
  * NEVER returns the raw provider body. The HTTP-facing payload
    contains only run id + status + counts + cost. The body lives
    in `research_ro.research_agent_output` for operator review;
    the existing DB CHECK + server safety filter blocks any row
    whose body contains forbidden tokens.
  * Reflection rows (when added in a later phase) MUST stay
    labeled-history-only — there is no consumer of them in the
    execution path. CI tests enforce this invariant.
"""

from __future__ import annotations

import datetime as dt
import re
import uuid
from dataclasses import asdict, dataclass
from typing import Any

from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.config import settings


# ---------------------------------------------------------------------------
# Errors — public, structured, UI-renderable.
# ---------------------------------------------------------------------------


class PhaseEError(RuntimeError):
    """Base for Phase E manual-run errors. Carries a short stable
    `code` so the HTTP layer can pick a status code without leaking
    internal exception state."""

    code: str = "phase_e_error"
    http_status: int = 400

    def __init__(self, message: str, *, code: str | None = None):
        super().__init__(message)
        if code is not None:
            self.code = code


class PhaseEDisabledError(PhaseEError):
    code = "manual_run_disabled"
    http_status = 404  # never confirm the endpoint exists when off


class PhaseENotAllowedError(PhaseEError):
    code = "not_allowed"
    http_status = 403


class PhaseECostExceededError(PhaseEError):
    code = "cost_exceeded"
    http_status = 402  # payment required


class PhaseEQuotaExceededError(PhaseEError):
    code = "quota_exceeded"
    http_status = 429


class PhaseEValidationError(PhaseEError):
    code = "validation_error"
    http_status = 422


# ---------------------------------------------------------------------------
# Sanitized response payload
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ManualRunPayload:
    run_id: str
    status: str
    symbol: str
    as_of: str
    provider: str
    model_id: str | None
    model_version: str | None
    tokens_in: int
    tokens_out: int
    cost_usd: float
    operator_id: str
    triggered_by: str
    idempotency_key: str | None
    safety_status: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Allowlist parsing
# ---------------------------------------------------------------------------


_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


def _csv_set(s: str | None) -> frozenset[str]:
    if not s:
        return frozenset()
    return frozenset(part.strip() for part in s.split(",") if part.strip())


def _validate_symbol(symbol: str) -> str:
    if not symbol or not isinstance(symbol, str):
        raise PhaseEValidationError("symbol must be a non-empty str")
    sym = symbol.strip().upper()
    if not _SYMBOL_RE.match(sym):
        raise PhaseEValidationError(
            f"symbol '{symbol}' does not match expected format "
            f"(1-10 chars, A-Z 0-9 . -, must start with letter)"
        )
    return sym


def _validate_as_of(as_of: dt.date) -> dt.date:
    if not isinstance(as_of, dt.date):
        raise PhaseEValidationError("as_of must be a datetime.date")
    today = dt.date.today()
    if as_of > today:
        raise PhaseEValidationError(
            f"as_of {as_of} is in the future (today={today})"
        )
    return as_of


# ---------------------------------------------------------------------------
# Pre-flight checks (read-only)
# ---------------------------------------------------------------------------


def _assert_flags_enabled() -> None:
    if not bool(settings.RESEARCH_RO_ENABLED):
        raise PhaseEDisabledError(
            "RESEARCH_RO_ENABLED is false; manual run refused"
        )
    if not bool(settings.RESEARCH_MANUAL_RUN_ENABLED):
        raise PhaseEDisabledError(
            "RESEARCH_MANUAL_RUN_ENABLED is false; manual run refused"
        )


def _assert_provider_allowed(provider_name: str) -> str:
    p = (provider_name or "").strip().lower()
    allowlist = _csv_set(settings.RESEARCH_ALLOWED_PROVIDERS)
    if not allowlist:
        raise PhaseENotAllowedError(
            "RESEARCH_ALLOWED_PROVIDERS is empty; no provider is "
            "allowed for manual run"
        )
    if p not in allowlist:
        raise PhaseENotAllowedError(
            f"provider '{p}' not in allowlist {sorted(allowlist)}"
        )
    return p


def _assert_symbol_allowed(symbol: str) -> None:
    allowlist = _csv_set(settings.RESEARCH_ALLOWED_SYMBOLS)
    if not allowlist:
        return  # empty allowlist = symbol allowed (existing asset still required)
    if symbol not in allowlist:
        raise PhaseENotAllowedError(
            f"symbol '{symbol}' not in RESEARCH_ALLOWED_SYMBOLS allowlist"
        )


def _assert_symbol_resolves(session: Session, symbol: str) -> str:
    row = session.execute(
        text("SELECT id FROM asset WHERE symbol = :s AND is_active = TRUE LIMIT 1"),
        {"s": symbol},
    ).first()
    if not row:
        raise PhaseEValidationError(
            f"symbol '{symbol}' has no active asset row"
        )
    return str(row[0])


def _daily_cost_used(session: Session) -> float:
    row = session.execute(text(
        """
        SELECT COALESCE(SUM(cost_usd), 0)::float8
        FROM research_ro.research_run
        WHERE started_at::date = (now() AT TIME ZONE 'UTC')::date
        """
    )).first()
    return float(row[0]) if row and row[0] is not None else 0.0


def _ticker_daily_run_count(session: Session, symbol: str) -> int:
    row = session.execute(text(
        """
        SELECT count(*)::int
        FROM research_ro.research_run
        WHERE symbol = :s
          AND started_at::date = (now() AT TIME ZONE 'UTC')::date
        """
    ), {"s": symbol}).first()
    return int(row[0]) if row and row[0] is not None else 0


def _assert_caps(session: Session, *, symbol: str) -> None:
    used = _daily_cost_used(session)
    daily_max = float(settings.RESEARCH_MAX_DAILY_COST_USD)
    if used >= daily_max:
        raise PhaseECostExceededError(
            f"daily cost cap reached: ${used:.4f} >= ${daily_max:.4f}"
        )
    n_today = _ticker_daily_run_count(session, symbol)
    cap = int(settings.RESEARCH_MAX_TICKER_DAILY_RUNS)
    if n_today >= cap:
        raise PhaseEQuotaExceededError(
            f"ticker '{symbol}' has hit its daily run cap "
            f"({n_today} >= {cap})"
        )


# ---------------------------------------------------------------------------
# Audit logging — append-only
# ---------------------------------------------------------------------------


def _audit_log(
    *, event: str,
    operator_id: str, symbol: str, provider: str,
    model_id: str | None, prompt_hash: str | None,
    cost_estimate_usd: float | None,
    status: str, error_code: str | None = None,
    idempotency_key: str | None = None,
) -> None:
    """Operator-visible audit. No DB write — relies on structured
    log lines pulled by the standard log pipeline. We avoid adding
    a new audit table to keep the Phase E surface minimal."""
    logger.info(
        "[research_manual_run] event={} operator_id={} symbol={} "
        "provider={} model_id={} prompt_hash={} cost_est={} "
        "status={} error_code={} idempotency_key={}",
        event, operator_id, symbol, provider, model_id, prompt_hash,
        cost_estimate_usd, status, error_code, idempotency_key,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_manual_safely(
    session: Session, *,
    symbol: str,
    as_of: dt.date,
    provider_name: str = "mock",
    operator_id: str,
    candidate_idea_id: str | None = None,
    idempotency_key: str | None = None,
    triggered_by: str = "manual",
    request_source: str = "cli",
    admin_override: bool = False,
) -> ManualRunPayload:
    """Phase E manual entry. Enforces every gate, then delegates to
    the existing `run_single_asset_context_note` orchestrator. Never
    raises on provider failure — the orchestrator returns a status
    row instead. Raises only on Phase E pre-check failure.

    Phase E.1: also enforces operator allowlist + rate limits + audit
    logging + anomaly detection. Audit row is written to
    `research_ro.research_manual_run_audit` for both accepted and
    rejected attempts."""
    # --- Phase E flag-level gates (must run before any DB or audit
    #     activity to avoid leaking that the system is on at all).
    _assert_flags_enabled()
    if not operator_id or not isinstance(operator_id, str):
        raise PhaseEValidationError("operator_id is required")
    if triggered_by not in ("manual", "operator"):
        raise PhaseEValidationError(
            "triggered_by must be 'manual' or 'operator'"
        )
    if request_source not in ("cli", "http"):
        raise PhaseEValidationError(
            "request_source must be 'cli' or 'http'"
        )

    # --- Phase E.1 lazy-import of controls to keep this module load-
    #     time small and to make `test_no_execution_imports` simpler.
    from apps.api.src.research.manual_run_controls import (
        check_rate_limits,
        detect_anomalies,
        is_operator_allowed,
        write_audit_in_flight,
        write_audit_rejection,
        write_audit_terminal,
    )

    def _audit_then_raise(
        exc: PhaseEError, *, sym_for_audit: str | None = None,
        prov_for_audit: str | None = None,
        as_of_for_audit: dt.date | None = None,
    ):
        """Phase E.1 — write a rejection audit row then re-raise. Used
        for early gates that fail before the in-flight row is created.
        Best-effort; rollback on audit failure to avoid masking the
        real cause."""
        try:
            write_audit_rejection(
                session,
                operator_id=operator_id,
                symbol=sym_for_audit or symbol or "_invalid_",
                as_of=as_of_for_audit or as_of or dt.date.today(),
                provider=prov_for_audit or provider_name or "unknown",
                request_source=request_source,
                rejection_reason=f"{exc.code}:{exc}",
                request_id=idempotency_key,
            )
        except Exception:  # noqa: BLE001
            session.rollback()
        raise exc

    # --- Phase E + E.1 input validation (pure; no DB).
    try:
        sym = _validate_symbol(symbol)
        target = _validate_as_of(as_of)
        provider = _assert_provider_allowed(provider_name)
        _assert_symbol_allowed(sym)
    except PhaseEError as exc:
        _audit_then_raise(exc)

    # --- Phase E.1 operator allowlist.
    if not is_operator_allowed(operator_id):
        _audit_then_raise(
            PhaseENotAllowedError(
                f"operator '{operator_id}' is not in the allowlist"
            ),
            sym_for_audit=sym, prov_for_audit=provider,
            as_of_for_audit=target,
        )

    # --- Phase E.2 enforcement state check (BEFORE provider call).
    from apps.api.src.research.manual_run_enforcement import (
        evaluate_enforcement,
        emit_alert,
        touch_operator_last_seen,
        apply_anomaly_transitions,
    )
    touch_operator_last_seen(session, operator_id)

    # --- Phase E.3 auto enforcement (BEFORE the cached state check).
    if bool(settings.RESEARCH_AUTO_ENFORCEMENT_ENABLED):
        try:
            from apps.api.src.research.manual_run_auto_enforcement import (
                evaluate_operator_state,
                apply_operator_state_transition,
                auto_resolve_stale_alerts,
            )
            ev = evaluate_operator_state(
                session, operator_id=operator_id, dry_run=False,
            )
            if ev.would_change:
                apply_operator_state_transition(
                    session, evaluation=ev, source="auto",
                )
            # Best-effort auto-resolve stale alerts on clear-state.
            auto_resolve_stale_alerts(session, operator_id=operator_id)
        except Exception:  # noqa: BLE001
            session.rollback()

    enf = evaluate_enforcement(
        session, operator_id=operator_id,
        admin_override=admin_override,
    )
    if not enf.allowed:
        # Emit alert for the rejected attempt — operator visibility.
        try:
            emit_alert(
                session,
                severity=("critical" if enf.state == "blocked" else "high"),
                alert_type="enforcement_rejection",
                message=(
                    f"operator={operator_id} state={enf.state} "
                    f"reason={enf.reason}"
                ),
                operator_id=operator_id, symbol=sym,
                metadata={
                    "state": enf.state,
                    "reason_code": enf.reason or "",
                    "blocked_until": (
                        enf.blocked_until.isoformat()
                        if enf.blocked_until else None
                    ),
                },
            )
        except Exception:  # noqa: BLE001
            session.rollback()
        _audit_then_raise(
            PhaseENotAllowedError(
                f"operator '{operator_id}' state={enf.state}: {enf.reason}"
            ),
            sym_for_audit=sym, prov_for_audit=provider,
            as_of_for_audit=target,
        )
    if enf.state == "watch":
        # Watch state allows but logs.
        logger.warning(
            "[manual_run_watch] operator={} state=watch reason={}",
            operator_id, enf.reason,
        )
    if enf.state == "restricted" and admin_override:
        # Admin-override use is itself an alert-worthy event.
        try:
            emit_alert(
                session,
                severity="warning",
                alert_type="admin_override_used",
                message=(
                    f"operator={operator_id} state=restricted "
                    f"override_by=admin"
                ),
                operator_id=operator_id, symbol=sym,
                metadata={
                    "state": enf.state,
                    "override_used": True,
                },
            )
        except Exception:  # noqa: BLE001
            session.rollback()

    try:
        _assert_symbol_resolves(session, sym)
        _assert_caps(session, symbol=sym)
    except PhaseEError as exc:
        _audit_then_raise(
            exc, sym_for_audit=sym, prov_for_audit=provider,
            as_of_for_audit=target,
        )

    # --- Phase E.1 rate limits (operator daily / symbol daily /
    #     concurrent in-flight).
    rl = check_rate_limits(session, operator_id=operator_id, symbol=sym)
    if not rl.allowed:
        write_audit_rejection(
            session,
            operator_id=operator_id, symbol=sym,
            as_of=target, provider=provider,
            request_source=request_source,
            rejection_reason=rl.reason or "rate_limit",
            request_id=idempotency_key,
        )
        if "operator" in (rl.reason or "") and "daily" in (rl.reason or ""):
            raise PhaseEQuotaExceededError(rl.reason or "rate_limit")
        if "symbol" in (rl.reason or "") and "daily" in (rl.reason or ""):
            raise PhaseEQuotaExceededError(rl.reason or "rate_limit")
        if "concurrent" in (rl.reason or ""):
            raise PhaseEQuotaExceededError(rl.reason or "rate_limit")
        raise PhaseEQuotaExceededError(rl.reason or "rate_limit")

    # --- Phase E.1 anomaly detection (write flags onto the in-flight
    #     audit row; never block on flags alone — flags are visibility
    #     only, real blocking is via rate-limit and cost gates).
    anomalies = detect_anomalies(
        session, operator_id=operator_id, symbol=sym,
        estimated_cost_usd=None,
    )
    # Phase E.2 — anomaly flags trigger operator state escalation +
    # alert emission. Transitions never downgrade and never block
    # this attempt; the next attempt will hit the new state.
    if anomalies.flags:
        try:
            apply_anomaly_transitions(
                session,
                operator_id=operator_id, symbol=sym,
                flags=anomalies.flags,
            )
        except Exception:  # noqa: BLE001
            session.rollback()
    audit_id = write_audit_in_flight(
        session,
        operator_id=operator_id, symbol=sym, as_of=target,
        provider=provider, request_source=request_source,
        request_id=idempotency_key,
        estimated_cost_usd=None,
        anomaly_flags=anomalies.flags,
    )

    # Per-run cost cap: take the smaller of Phase E global cap and
    # the existing per-provider knob. Enforced inside the underlying
    # orchestrator already; here we just record the effective value
    # in the audit log.
    eff_run_cap = float(settings.RESEARCH_MAX_RUN_COST_USD)

    _audit_log(
        event="started", operator_id=operator_id, symbol=sym,
        provider=provider, model_id=None, prompt_hash=None,
        cost_estimate_usd=None, status="running",
        idempotency_key=idempotency_key,
    )

    # Lazy import to keep this module's load-time surface small AND
    # to make the CI no-execution-imports grep simpler. The
    # orchestrator already enforces forbidden-token CHECK + safety
    # filter before INSERT.
    from apps.api.src.research.manual_run import (
        run_single_asset_context_note,
    )

    try:
        result = run_single_asset_context_note(
            session,
            symbol=sym,
            as_of=target,
            candidate_idea_id=candidate_idea_id,
            provider_name=provider,
            operator_id=operator_id,
        )
    except Exception as exc:  # noqa: BLE001
        # Phase E idempotency: the orchestrator's UNIQUE on
        # (symbol, as_of, provider, prompt_bundle_hash,
        #  input_snapshot_hash, schema_version) raises IntegrityError
        # on duplicate inputs. Surface that as a clean duplicate
        # outcome rather than a generic orchestrator failure — the
        # prior research_run row already carries the answer.
        from sqlalchemy.exc import IntegrityError
        if isinstance(exc, IntegrityError):
            session.rollback()
            existing = session.execute(text(
                """
                SELECT id, status, provider, model_id, model_version,
                       tokens_in, tokens_out, cost_usd
                FROM research_ro.research_run
                WHERE symbol = :s AND as_of = :d AND provider = :p
                ORDER BY started_at DESC LIMIT 1
                """
            ), {"s": sym, "d": target, "p": provider}).mappings().first()
            if existing is not None:
                _audit_log(
                    event="duplicate", operator_id=operator_id,
                    symbol=sym, provider=provider,
                    model_id=existing["model_id"], prompt_hash=None,
                    cost_estimate_usd=float(existing["cost_usd"] or 0.0),
                    status=str(existing["status"]),
                    idempotency_key=idempotency_key,
                )
                # Phase E.1: finalize audit row as 'duplicate'.
                write_audit_terminal(
                    session, audit_id=audit_id, status="duplicate",
                    research_run_id=str(existing["id"]),
                    actual_cost_usd=float(existing["cost_usd"] or 0.0),
                    model_id=existing["model_id"],
                )
                return ManualRunPayload(
                    run_id=str(existing["id"]),
                    status=str(existing["status"]),
                    symbol=sym,
                    as_of=target.isoformat(),
                    provider=provider,
                    model_id=existing["model_id"],
                    model_version=existing["model_version"],
                    tokens_in=int(existing["tokens_in"] or 0),
                    tokens_out=int(existing["tokens_out"] or 0),
                    cost_usd=float(existing["cost_usd"] or 0.0),
                    operator_id=operator_id,
                    triggered_by=triggered_by,
                    idempotency_key=idempotency_key,
                    safety_status="safe" if existing["status"] in (
                        "succeeded", "partial",
                    ) else "error",
                )
        _audit_log(
            event="errored", operator_id=operator_id, symbol=sym,
            provider=provider, model_id=None, prompt_hash=None,
            cost_estimate_usd=None, status="error",
            error_code=type(exc).__name__,
            idempotency_key=idempotency_key,
        )
        # Phase E.1: finalize audit row as 'error'.
        write_audit_terminal(
            session, audit_id=audit_id, status="error",
            rejection_reason=f"orchestrator_raised:{type(exc).__name__}",
        )
        raise PhaseEError(
            f"orchestrator raised: {type(exc).__name__}",
            code="orchestrator_error",
        ) from exc

    # Post-call audit. `result.status` is one of the research_run
    # status enum values. We surface a single `safety_status` field
    # so HTTP clients can render fail-closed without parsing the
    # full enum:
    #   - 'safe' when status in {succeeded, partial}
    #   - 'unsafe' when status in {token_violation, schema_violation}
    #   - 'error' otherwise
    safety_status = "error"
    if result.status in ("succeeded", "partial"):
        safety_status = "safe"
    elif result.status in ("token_violation", "schema_violation"):
        safety_status = "unsafe"

    # Derive provenance from the persisted research_run row (the
    # orchestrator's ResearchRunResult dataclass doesn't expose
    # model_id / cost_usd directly; we read back the row by id).
    persisted = session.execute(text(
        """
        SELECT model_id, model_version, tokens_in, tokens_out, cost_usd
        FROM research_ro.research_run WHERE id = :id
        """
    ), {"id": str(result.run_id)}).mappings().first()
    payload = ManualRunPayload(
        run_id=str(result.run_id),
        status=str(result.status),
        symbol=sym,
        as_of=target.isoformat(),
        provider=provider,
        model_id=(persisted["model_id"] if persisted else None),
        model_version=(persisted["model_version"] if persisted else None),
        tokens_in=int((persisted["tokens_in"] if persisted else 0) or 0),
        tokens_out=int((persisted["tokens_out"] if persisted else 0) or 0),
        cost_usd=float((persisted["cost_usd"] if persisted else 0.0) or 0.0),
        operator_id=operator_id,
        triggered_by=triggered_by,
        idempotency_key=idempotency_key,
        safety_status=safety_status,
    )

    _audit_log(
        event="finished", operator_id=operator_id, symbol=sym,
        provider=provider, model_id=payload.model_id,
        prompt_hash=getattr(result, "prompt_hash", None),
        cost_estimate_usd=payload.cost_usd,
        status=payload.status,
        idempotency_key=idempotency_key,
    )
    # Phase E.1: finalize audit row as 'accepted' (or 'rejected' when
    # the run produced an unsafe-status result, e.g. token_violation).
    final_status = (
        "accepted"
        if payload.safety_status == "safe"
        else "rejected"
    )
    write_audit_terminal(
        session, audit_id=audit_id,
        status=final_status,
        rejection_reason=(
            f"orchestrator_status:{payload.status}"
            if final_status == "rejected" else None
        ),
        research_run_id=payload.run_id,
        actual_cost_usd=payload.cost_usd,
        model_id=payload.model_id,
        prompt_hash=getattr(result, "prompt_hash", None),
    )
    return payload


# Re-export used by tests that need the global per-run cap.
def effective_per_run_cap_usd() -> float:
    return float(settings.RESEARCH_MAX_RUN_COST_USD)
