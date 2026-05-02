"""Phase 11W (Phase E.2) — operator enforcement + alert helpers.

Read+write helpers over `research_operator_control` and
`research_alert` tables. NEVER imports execution / scoring / ML /
candidate / paper / options modules. NEVER schedules itself.
NEVER emits raw model body content into alerts (CHECK enforces a
forbidden-token regex on `message`).

Used by `manual_run_safe.run_manual_safely` to:
  * fetch the operator's enforcement state BEFORE provider call;
  * raise `PhaseENotAllowedError` for blocked / restricted-without-
    override operators;
  * flip the operator into watch/restricted/blocked when anomaly
    flags trip; and
  * record alert rows for operator review.
"""

from __future__ import annotations

import datetime as dt
import json
import uuid
from dataclasses import dataclass
from typing import Any, Iterable

from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


_ALLOWED_STATES = ("clear", "watch", "restricted", "blocked")
_ALLOWED_SEVERITY = ("info", "warning", "high", "critical")
_ALLOWED_ALERT_STATUS = ("open", "acknowledged", "resolved")


@dataclass(frozen=True)
class OperatorControl:
    operator_id: str
    state: str
    reason: str | None
    blocked_until: dt.datetime | None
    updated_by: str
    updated_at: dt.datetime
    notes: str | None


@dataclass(frozen=True)
class EnforcementDecision:
    """Per-attempt decision returned by `evaluate_enforcement`."""
    operator_id: str
    state: str
    allowed: bool
    requires_override: bool
    reason: str | None
    blocked_until: dt.datetime | None


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------


def get_operator_control(
    session: Session, operator_id: str,
) -> OperatorControl | None:
    row = session.execute(text(
        """
        SELECT operator_id, state, reason, blocked_until,
               updated_by, updated_at, notes
        FROM research_ro.research_operator_control
        WHERE operator_id = :op
        """
    ), {"op": operator_id}).mappings().first()
    if row is None:
        return None
    return OperatorControl(
        operator_id=row["operator_id"],
        state=row["state"],
        reason=row["reason"],
        blocked_until=row["blocked_until"],
        updated_by=row["updated_by"],
        updated_at=row["updated_at"],
        notes=row["notes"],
    )


def evaluate_enforcement(
    session: Session, *, operator_id: str,
    admin_override: bool = False,
) -> EnforcementDecision:
    """Read-only enforcement check. Treats missing row as 'clear'."""
    ctrl = get_operator_control(session, operator_id)
    if ctrl is None:
        return EnforcementDecision(
            operator_id=operator_id, state="clear",
            allowed=True, requires_override=False,
            reason=None, blocked_until=None,
        )
    # Auto-expire blocked_until.
    if (
        ctrl.state == "blocked"
        and ctrl.blocked_until is not None
        and ctrl.blocked_until <= dt.datetime.now(dt.timezone.utc)
    ):
        return EnforcementDecision(
            operator_id=operator_id, state="watch",
            allowed=True, requires_override=False,
            reason="block_expired",
            blocked_until=ctrl.blocked_until,
        )
    if ctrl.state == "blocked":
        return EnforcementDecision(
            operator_id=operator_id, state="blocked",
            allowed=False, requires_override=False,
            reason=ctrl.reason or "operator_blocked",
            blocked_until=ctrl.blocked_until,
        )
    if ctrl.state == "restricted":
        if admin_override:
            return EnforcementDecision(
                operator_id=operator_id, state="restricted",
                allowed=True, requires_override=True,
                reason=ctrl.reason, blocked_until=None,
            )
        return EnforcementDecision(
            operator_id=operator_id, state="restricted",
            allowed=False, requires_override=True,
            reason=ctrl.reason or "operator_restricted",
            blocked_until=None,
        )
    # 'watch' / 'clear' both allow.
    return EnforcementDecision(
        operator_id=operator_id, state=ctrl.state,
        allowed=True, requires_override=False,
        reason=ctrl.reason, blocked_until=None,
    )


# ---------------------------------------------------------------------------
# Write helpers — operator state transitions
# ---------------------------------------------------------------------------


def set_operator_state(
    session: Session, *,
    operator_id: str, state: str, updated_by: str,
    reason: str | None = None,
    blocked_until: dt.datetime | None = None,
    notes: str | None = None,
) -> OperatorControl:
    """Upsert the operator's control row. Idempotent on PK."""
    if state not in _ALLOWED_STATES:
        raise ValueError(f"invalid state: {state!r}")
    if not operator_id or not updated_by:
        raise ValueError("operator_id and updated_by are required")
    session.execute(text(
        """
        INSERT INTO research_ro.research_operator_control
          (operator_id, state, reason, blocked_until,
           updated_by, updated_at, notes,
           first_seen_at, last_seen_at)
        VALUES (:op, :st, :reason, :blocked_until,
                :ub, now(), :notes, now(), now())
        ON CONFLICT (operator_id) DO UPDATE
          SET state         = EXCLUDED.state,
              reason        = EXCLUDED.reason,
              blocked_until = EXCLUDED.blocked_until,
              updated_by    = EXCLUDED.updated_by,
              updated_at    = now(),
              notes         = COALESCE(EXCLUDED.notes,
                                       research_ro.research_operator_control.notes),
              last_seen_at  = now()
        """
    ), {
        "op": operator_id, "st": state, "reason": reason,
        "blocked_until": blocked_until, "ub": updated_by, "notes": notes,
    })
    session.commit()
    out = get_operator_control(session, operator_id)
    assert out is not None
    return out


def touch_operator_last_seen(
    session: Session, operator_id: str,
) -> None:
    """Cheap upsert that records every attempt's last_seen_at and
    creates a 'clear' row on first contact. Idempotent."""
    session.execute(text(
        """
        INSERT INTO research_ro.research_operator_control
          (operator_id, state, updated_by, last_seen_at, first_seen_at)
        VALUES (:op, 'clear', 'system', now(), now())
        ON CONFLICT (operator_id) DO UPDATE
          SET last_seen_at = now()
        """
    ), {"op": operator_id})
    session.commit()


# ---------------------------------------------------------------------------
# Alert writes
# ---------------------------------------------------------------------------


def emit_alert(
    session: Session, *,
    severity: str, alert_type: str, message: str,
    operator_id: str | None = None,
    symbol: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    """Insert an alert row. The DB CHECK on `message` blocks any
    forbidden-token text. Caller MUST NOT pass raw model body in
    `message` or `metadata`."""
    if severity not in _ALLOWED_SEVERITY:
        raise ValueError(f"invalid severity: {severity!r}")
    aid = str(uuid.uuid4())
    md = dict(metadata or {})
    # Defense in depth — strip any field that looks like a raw body.
    for forbidden_key in (
        "body", "raw_body", "raw_response", "structured_output",
        "agent_output", "evidence_refs", "reflection",
    ):
        md.pop(forbidden_key, None)
    session.execute(text(
        """
        INSERT INTO research_ro.research_alert
          (id, severity, alert_type, operator_id, symbol,
           message, metadata)
        VALUES (CAST(:id AS uuid), :sev, :atype, :op, :sym,
                :msg, CAST(:md AS jsonb))
        """
    ), {
        "id": aid, "sev": severity, "atype": alert_type,
        "op": operator_id, "sym": symbol, "msg": message,
        "md": json.dumps(md, default=str),
    })
    session.commit()
    logger.info(
        "[research_alert] sev={} type={} op={} sym={}",
        severity, alert_type, operator_id, symbol,
    )
    return aid


# ---------------------------------------------------------------------------
# Anomaly → state transition rules (deterministic)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StateTransition:
    target_state: str
    reason: str
    severity: str
    alert_type: str
    blocked_until: dt.datetime | None = None


def map_flag_to_transition(flag: str) -> StateTransition | None:
    """Pure-fn mapping from anomaly flag → operator-state change +
    alert spec. Order matters: more-severe rules win when multiple
    flags fire at once."""
    if flag.startswith("operator_repeated_token_violations"):
        return StateTransition(
            target_state="restricted",
            reason="repeated_token_violations",
            severity="high",
            alert_type="forbidden_token_threshold_exceeded",
        )
    if flag.startswith("operator_repeated_rejections"):
        return StateTransition(
            target_state="watch",
            reason="repeated_rejections",
            severity="warning",
            alert_type="repeated_rejections",
        )
    if flag.startswith("operator_symbol_duplicate_spam"):
        return StateTransition(
            target_state="restricted",
            reason="duplicate_spam",
            severity="warning",
            alert_type="duplicate_spam",
        )
    if flag.startswith("cost_spike"):
        return StateTransition(
            target_state="watch",
            reason="cost_spike",
            severity="warning",
            alert_type="cost_spike",
        )
    return None


def apply_anomaly_transitions(
    session: Session, *,
    operator_id: str, symbol: str,
    flags: Iterable[str],
) -> list[str]:
    """For each anomaly flag, possibly transition the operator's
    state (escalating only — never downgrades) and emit an alert.
    Returns the list of alert ids created. Pure rule-based; no ML."""
    severity_priority = {
        "clear": 0, "watch": 1, "restricted": 2, "blocked": 3,
    }
    alert_ids: list[str] = []
    transitions = [t for t in (map_flag_to_transition(f) for f in flags) if t]
    if not transitions:
        return alert_ids

    current = get_operator_control(session, operator_id)
    cur_state = current.state if current else "clear"
    # Escalate to the worst suggested state but NEVER downgrade.
    target = max(
        transitions, key=lambda t: severity_priority[t.target_state],
    )
    if severity_priority[target.target_state] > severity_priority[cur_state]:
        set_operator_state(
            session,
            operator_id=operator_id,
            state=target.target_state,
            reason=target.reason,
            updated_by="anomaly_rule",
            blocked_until=target.blocked_until,
            notes=f"escalated_from={cur_state} flags={list(flags)}",
        )

    # Emit one alert per matched transition (operators can ack
    # individually).
    for t in transitions:
        msg = (
            f"operator={operator_id} flag={t.reason} "
            f"target_state={t.target_state}"
        )
        alert_ids.append(emit_alert(
            session,
            severity=t.severity, alert_type=t.alert_type,
            message=msg,
            operator_id=operator_id,
            symbol=symbol,
            metadata={
                "from_state": cur_state,
                "to_state": t.target_state,
                "reason": t.reason,
            },
        ))
    return alert_ids
