"""Phase 11W (Phase E.3) — auto enforcement + cooldown engine.

Pure, deterministic, rule-based evaluator. Reads `research_alert`,
`research_manual_run_audit`, `research_operator_control` and
returns a desired state for an operator. Apply step writes to
`research_operator_control` and `research_operator_control_history`.

NEVER imports execution / scoring / ML / candidate / paper /
options modules. NEVER schedules itself. NEVER opens a research
run. NEVER returns raw provider body text. Sanitizes any metadata
dict by stripping body/raw/structured/evidence/reflection/prompt
keys before persistence.
"""

from __future__ import annotations

import datetime as dt
import json
import uuid
from dataclasses import dataclass, field
from typing import Any

from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.config import settings


# ---------------------------------------------------------------------------
# Sanitization
# ---------------------------------------------------------------------------


_FORBIDDEN_METADATA_KEYS: tuple[str, ...] = (
    "body", "raw_body", "raw_response",
    "structured_output", "agent_output",
    "evidence_refs", "reflection",
    "prompt", "prompt_text", "prompt_template",
)


def sanitize_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    """Strip raw-output / prompt keys recursively. Always returns a
    new dict; never mutates input."""
    if not metadata:
        return {}
    out: dict[str, Any] = {}
    for k, v in metadata.items():
        if k in _FORBIDDEN_METADATA_KEYS:
            continue
        if isinstance(v, dict):
            out[k] = sanitize_metadata(v)
        elif isinstance(v, list):
            out[k] = [
                sanitize_metadata(x) if isinstance(x, dict) else x
                for x in v
            ]
        else:
            out[k] = v
    return out


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OperatorSignalSummary:
    operator_id: str
    rejected_count: int
    token_violation_count: int
    duplicate_count: int
    override_count: int
    blocked_attempt_count: int
    cost_spike_count: int
    latest_alert_at: dt.datetime | None
    current_state: str
    restricted_until: dt.datetime | None
    blocked_until: dt.datetime | None


@dataclass(frozen=True)
class EnforcementEvaluation:
    operator_id: str
    current_state: str
    desired_state: str
    reason: str
    severity: str
    cooldown_until: dt.datetime | None
    source: str
    would_change: bool
    dry_run: bool
    sanitized_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OperatorControlResult:
    operator_id: str
    previous_state: str | None
    new_state: str
    changed: bool
    cooldown_until: dt.datetime | None
    alert_id: str | None
    history_id: str | None


@dataclass(frozen=True)
class AlertResult:
    alert_id: str
    deduped: bool


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------


def _now_utc(now: dt.datetime | None = None) -> dt.datetime:
    return now or dt.datetime.now(dt.timezone.utc)


def get_operator_signal_summary(
    session: Session, *, operator_id: str,
    now: dt.datetime | None = None,
) -> OperatorSignalSummary:
    """Aggregate operator-scoped signal counts within the
    configured lookback window."""
    cur_now = _now_utc(now)
    win_h = int(settings.RESEARCH_ENFORCEMENT_LOOKBACK_HOURS)

    audit_row = session.execute(text(
        f"""
        SELECT
          count(*) FILTER (WHERE status='rejected')                AS rejected,
          count(*) FILTER (WHERE rejection_reason ILIKE '%token%')
                                                                  AS tokens,
          count(*) FILTER (WHERE status='duplicate')               AS dup,
          count(*) FILTER (WHERE status='rejected'
                            AND rejection_reason ILIKE '%blocked%') AS blkatt
        FROM research_ro.research_manual_run_audit
        WHERE operator_id = :op
          AND created_at > now() - interval '{win_h} hours'
        """
    ), {"op": operator_id}).mappings().first() or {}

    alert_row = session.execute(text(
        f"""
        SELECT
          count(*) FILTER (WHERE alert_type='admin_override_used') AS overrides,
          count(*) FILTER (WHERE alert_type='cost_spike')          AS spikes,
          max(created_at)                                          AS latest
        FROM research_ro.research_alert
        WHERE operator_id = :op
          AND created_at > now() - interval '{win_h} hours'
        """
    ), {"op": operator_id}).mappings().first() or {}

    ctrl = session.execute(text(
        """
        SELECT state, restricted_until, blocked_until
        FROM research_ro.research_operator_control
        WHERE operator_id = :op
        """
    ), {"op": operator_id}).mappings().first() or {}

    return OperatorSignalSummary(
        operator_id=operator_id,
        rejected_count=int(audit_row.get("rejected") or 0),
        token_violation_count=int(audit_row.get("tokens") or 0),
        duplicate_count=int(audit_row.get("dup") or 0),
        override_count=int(alert_row.get("overrides") or 0),
        blocked_attempt_count=int(audit_row.get("blkatt") or 0),
        cost_spike_count=int(alert_row.get("spikes") or 0),
        latest_alert_at=alert_row.get("latest"),
        current_state=str(ctrl.get("state") or "clear"),
        restricted_until=ctrl.get("restricted_until"),
        blocked_until=ctrl.get("blocked_until"),
    )


# ---------------------------------------------------------------------------
# Pure rule evaluation
# ---------------------------------------------------------------------------


def _state_priority(state: str) -> int:
    return {"clear": 0, "watch": 1, "restricted": 2, "blocked": 3}.get(
        state, 0,
    )


def _cooldown_for(target_state: str, reason: str) -> int:
    """Return cooldown hours for a transition target+reason."""
    if target_state == "blocked":
        return int(settings.RESEARCH_BLOCKED_COOLDOWN_HOURS)
    if target_state == "restricted":
        if reason == "repeated_token_violations":
            return int(settings.RESEARCH_TOKEN_RESTRICTED_COOLDOWN_HOURS)
        return int(settings.RESEARCH_RESTRICTED_COOLDOWN_HOURS)
    if target_state == "watch":
        return int(settings.RESEARCH_WATCH_COOLDOWN_HOURS)
    return 0


def _propose_target(
    summary: OperatorSignalSummary,
) -> tuple[str, str, str] | None:
    """Pure-fn: given a signal summary, return (target_state,
    reason, severity) or None when no escalation is warranted.
    Worst-severity rule wins."""
    candidates: list[tuple[str, str, str, int]] = []  # (state, reason, sev, prio)
    if summary.token_violation_count >= int(
        settings.RESEARCH_ANOMALY_TOKEN_VIOLATION_THRESHOLD
    ):
        candidates.append((
            "restricted", "repeated_token_violations", "high",
            _state_priority("restricted"),
        ))
    if summary.duplicate_count >= int(
        settings.RESEARCH_ANOMALY_DUPLICATE_THRESHOLD
    ):
        candidates.append((
            "restricted", "duplicate_spam", "warning",
            _state_priority("restricted"),
        ))
    if summary.rejected_count >= int(
        settings.RESEARCH_ANOMALY_REJECTED_THRESHOLD
    ):
        candidates.append((
            "watch", "repeated_rejections", "warning",
            _state_priority("watch"),
        ))
    if summary.blocked_attempt_count >= 1:
        candidates.append((
            "blocked", "blocked_attempt_while_restricted", "critical",
            _state_priority("blocked"),
        ))
    if summary.override_count >= int(
        settings.RESEARCH_ADMIN_OVERRIDE_RESTRICT_THRESHOLD
    ):
        candidates.append((
            "restricted", "repeated_admin_override_usage", "high",
            _state_priority("restricted"),
        ))
    elif summary.override_count >= int(
        settings.RESEARCH_ADMIN_OVERRIDE_WATCH_THRESHOLD
    ):
        candidates.append((
            "watch", "repeated_admin_override_usage", "warning",
            _state_priority("watch"),
        ))
    if summary.cost_spike_count >= 1:
        candidates.append((
            "watch", "cost_spike", "warning",
            _state_priority("watch"),
        ))
    if not candidates:
        return None
    # Highest priority wins; ties broken by `reason` lex order for
    # deterministic output.
    candidates.sort(key=lambda c: (-c[3], c[1]))
    state, reason, sev, _ = candidates[0]
    return state, reason, sev


def _propose_demotion(
    summary: OperatorSignalSummary, *, now: dt.datetime,
) -> tuple[str, str, str] | None:
    """If the current cooldown has expired, return the next state
    based on demotion rules. Otherwise None."""
    cur = summary.current_state
    if cur == "blocked":
        if summary.blocked_until and summary.blocked_until > now:
            return None
        # blocked expired
        if summary.token_violation_count >= 1 or summary.cost_spike_count >= 1:
            return "restricted", "blocked_expired_high_signals", "high"
        return "clear", "blocked_expired_no_signals", "info"
    if cur == "restricted":
        # Cooldown end may be tracked in restricted_until; fallback
        # is "compare state_changed_at + cooldown hours" but we
        # don't read state_changed_at here — keep the rule simple.
        if summary.restricted_until and summary.restricted_until > now:
            return None
        if summary.token_violation_count >= 1:
            return "watch", "restricted_expired_token_signals", "warning"
        if summary.rejected_count >= 1 or summary.cost_spike_count >= 1:
            return "watch", "restricted_expired_recent_warnings", "warning"
        return "clear", "restricted_expired_no_signals", "info"
    if cur == "watch":
        # Watch has no per-row TTL field; we evaluate against the
        # rejected/duplicate/token counts in the lookback window.
        active_signals = (
            summary.rejected_count
            + summary.duplicate_count
            + summary.token_violation_count
            + summary.cost_spike_count
        )
        if active_signals == 0:
            return "clear", "watch_expired_no_signals", "info"
        # Stay on watch; no demotion proposal.
        return None
    return None  # clear stays clear


def evaluate_operator_state(
    session: Session, *,
    operator_id: str,
    now: dt.datetime | None = None,
    dry_run: bool = False,
) -> EnforcementEvaluation:
    """Read-only evaluation. Returns the desired state regardless of
    the auto-enforcement flag — caller decides whether to apply."""
    cur_now = _now_utc(now)
    summary = get_operator_signal_summary(
        session, operator_id=operator_id, now=cur_now,
    )
    cur_state = summary.current_state

    # Phase E.3: escalation first; if no escalation, check demotion.
    proposal = _propose_target(summary)
    if proposal:
        target, reason, severity = proposal
        if _state_priority(target) > _state_priority(cur_state):
            cooldown_h = _cooldown_for(target, reason)
            cooldown_until = (
                cur_now + dt.timedelta(hours=cooldown_h)
                if cooldown_h > 0 else None
            )
            return EnforcementEvaluation(
                operator_id=operator_id,
                current_state=cur_state,
                desired_state=target,
                reason=reason,
                severity=severity,
                cooldown_until=cooldown_until,
                source="auto",
                would_change=True,
                dry_run=dry_run,
                sanitized_metadata=sanitize_metadata({
                    "from_state": cur_state,
                    "to_state": target,
                    "reason": reason,
                    "summary": {
                        "rejected": summary.rejected_count,
                        "tokens": summary.token_violation_count,
                        "dup": summary.duplicate_count,
                        "overrides": summary.override_count,
                        "blkatt": summary.blocked_attempt_count,
                        "spikes": summary.cost_spike_count,
                    },
                }),
            )
    # No escalation. Check for demotion.
    demo = _propose_demotion(summary, now=cur_now)
    if demo:
        target, reason, severity = demo
        if _state_priority(target) < _state_priority(cur_state):
            cooldown_h = _cooldown_for(target, reason)
            cooldown_until = (
                cur_now + dt.timedelta(hours=cooldown_h)
                if cooldown_h > 0 else None
            )
            return EnforcementEvaluation(
                operator_id=operator_id,
                current_state=cur_state,
                desired_state=target,
                reason=reason,
                severity=severity,
                cooldown_until=cooldown_until,
                source="auto",
                would_change=True,
                dry_run=dry_run,
                sanitized_metadata=sanitize_metadata({
                    "from_state": cur_state,
                    "to_state": target,
                    "reason": reason,
                }),
            )
    # No change.
    return EnforcementEvaluation(
        operator_id=operator_id,
        current_state=cur_state,
        desired_state=cur_state,
        reason="no_change",
        severity="info",
        cooldown_until=None,
        source="auto",
        would_change=False,
        dry_run=dry_run,
        sanitized_metadata={},
    )


# ---------------------------------------------------------------------------
# Apply transitions
# ---------------------------------------------------------------------------


def _insert_history(
    session: Session, *,
    operator_id: str, previous_state: str | None,
    new_state: str, reason: str, source: str,
    cooldown_until: dt.datetime | None,
    alert_id: str | None,
    metadata: dict[str, Any],
) -> str:
    hid = str(uuid.uuid4())
    session.execute(text(
        """
        INSERT INTO research_ro.research_operator_control_history
          (id, operator_id, previous_state, new_state, reason,
           source, cooldown_until, alert_id, metadata)
        VALUES
          (CAST(:id AS uuid), :op, :ps, :ns, :reason,
           :src, :until, CAST(:aid AS uuid), CAST(:md AS jsonb))
        """
    ), {
        "id": hid, "op": operator_id,
        "ps": previous_state, "ns": new_state,
        "reason": reason, "src": source,
        "until": cooldown_until, "aid": alert_id,
        "md": json.dumps(sanitize_metadata(metadata), default=str),
    })
    session.commit()
    return hid


def apply_operator_state_transition(
    session: Session, *,
    evaluation: EnforcementEvaluation,
    source: str | None = None,
    alert_id: str | None = None,
) -> OperatorControlResult:
    """Apply the desired state when `evaluation.would_change` is
    True. Idempotent: re-applying when current==desired is a no-op
    that still touches updated_at."""
    src = source or evaluation.source
    if src not in ("auto", "manual", "override"):
        raise ValueError(f"invalid source: {src!r}")
    if evaluation.dry_run:
        return OperatorControlResult(
            operator_id=evaluation.operator_id,
            previous_state=evaluation.current_state,
            new_state=evaluation.desired_state,
            changed=False, cooldown_until=evaluation.cooldown_until,
            alert_id=alert_id, history_id=None,
        )
    if not evaluation.would_change:
        return OperatorControlResult(
            operator_id=evaluation.operator_id,
            previous_state=evaluation.current_state,
            new_state=evaluation.current_state,
            changed=False, cooldown_until=None,
            alert_id=None, history_id=None,
        )
    # Compute cooldown column splits per target state.
    blocked_until: dt.datetime | None = None
    restricted_until: dt.datetime | None = None
    if evaluation.desired_state == "blocked":
        blocked_until = evaluation.cooldown_until
    elif evaluation.desired_state == "restricted":
        restricted_until = evaluation.cooldown_until

    session.execute(text(
        """
        INSERT INTO research_ro.research_operator_control
          (operator_id, state, reason, blocked_until, restricted_until,
           cooldown_reason, cooldown_source, last_auto_evaluation_at,
           previous_state, state_changed_at,
           updated_by, updated_at, last_seen_at, first_seen_at)
        VALUES (:op, :st, :reason, :bu, :ru,
                :creason, :csrc, now(),
                :prev, now(),
                :ub, now(), now(), now())
        ON CONFLICT (operator_id) DO UPDATE
          SET previous_state          = research_ro.research_operator_control.state,
              state                   = EXCLUDED.state,
              reason                  = EXCLUDED.reason,
              blocked_until           = EXCLUDED.blocked_until,
              restricted_until        = EXCLUDED.restricted_until,
              cooldown_reason         = EXCLUDED.cooldown_reason,
              cooldown_source         = EXCLUDED.cooldown_source,
              last_auto_evaluation_at = EXCLUDED.last_auto_evaluation_at,
              state_changed_at        = CASE
                WHEN research_ro.research_operator_control.state IS DISTINCT FROM EXCLUDED.state
                  THEN now()
                ELSE research_ro.research_operator_control.state_changed_at
              END,
              updated_by              = EXCLUDED.updated_by,
              updated_at              = now(),
              last_seen_at            = now()
        """
    ), {
        "op": evaluation.operator_id,
        "st": evaluation.desired_state,
        "reason": evaluation.reason,
        "bu": blocked_until,
        "ru": restricted_until,
        "creason": evaluation.reason,
        "csrc": "auto" if src == "auto" else "manual",
        "prev": evaluation.current_state,
        "ub": "auto_enforcement" if src == "auto" else "manual",
    })
    session.commit()

    history_id = _insert_history(
        session,
        operator_id=evaluation.operator_id,
        previous_state=evaluation.current_state,
        new_state=evaluation.desired_state,
        reason=evaluation.reason,
        source=src,
        cooldown_until=evaluation.cooldown_until,
        alert_id=alert_id,
        metadata=evaluation.sanitized_metadata,
    )

    return OperatorControlResult(
        operator_id=evaluation.operator_id,
        previous_state=evaluation.current_state,
        new_state=evaluation.desired_state,
        changed=True,
        cooldown_until=evaluation.cooldown_until,
        alert_id=alert_id,
        history_id=history_id,
    )


# ---------------------------------------------------------------------------
# Alert dedup + auto-resolve
# ---------------------------------------------------------------------------


def dedupe_or_create_alert(
    session: Session, *,
    operator_id: str | None,
    alert_type: str, severity: str, message: str,
    symbol: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AlertResult:
    """Dedupe identical (operator_id, alert_type, severity) opens
    inside the configured window. When duplicate exists, returns
    its id and `deduped=True`. Otherwise inserts a new alert."""
    win_min = int(settings.RESEARCH_ALERT_DEDUP_WINDOW_MIN)
    existing = session.execute(text(
        f"""
        SELECT id::text FROM research_ro.research_alert
        WHERE COALESCE(operator_id, '') = COALESCE(:op, '')
          AND alert_type = :atype
          AND severity = :sev
          AND status = 'open'
          AND created_at > now() - interval '{win_min} minutes'
        ORDER BY created_at DESC LIMIT 1
        """
    ), {"op": operator_id, "atype": alert_type, "sev": severity}).first()
    if existing:
        return AlertResult(alert_id=str(existing[0]), deduped=True)

    aid = str(uuid.uuid4())
    md = sanitize_metadata(metadata or {})
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
    return AlertResult(alert_id=aid, deduped=False)


def auto_resolve_stale_alerts(
    session: Session, *,
    operator_id: str,
    now: dt.datetime | None = None,
) -> int:
    """Mark open alerts older than `RESEARCH_ALERT_AUTO_RESOLVE_HOURS`
    as `resolved` when the operator's current state is `clear`.
    Returns rows affected."""
    cur_now = _now_utc(now)
    state_row = session.execute(text(
        "SELECT state FROM research_ro.research_operator_control "
        "WHERE operator_id = :op"
    ), {"op": operator_id}).first()
    state = state_row[0] if state_row else "clear"
    if state != "clear":
        return 0
    auto_h = int(settings.RESEARCH_ALERT_AUTO_RESOLVE_HOURS)
    res = session.execute(text(
        f"""
        UPDATE research_ro.research_alert
        SET status = 'resolved',
            acknowledged_by = COALESCE(acknowledged_by, 'auto_resolve'),
            acknowledged_at = COALESCE(acknowledged_at, now())
        WHERE operator_id = :op
          AND status = 'open'
          AND created_at <= now() - interval '{auto_h} hours'
        """
    ), {"op": operator_id})
    session.commit()
    return int(res.rowcount or 0)


# ---------------------------------------------------------------------------
# Bulk evaluation
# ---------------------------------------------------------------------------


def evaluate_all_operators(
    session: Session, *, now: dt.datetime | None = None,
    dry_run: bool = True,
) -> list[EnforcementEvaluation]:
    """Evaluate every operator with an active control row OR with
    audit/alert activity in the lookback window. Returns the list
    of evaluations; caller decides whether to apply."""
    cur_now = _now_utc(now)
    win_h = int(settings.RESEARCH_ENFORCEMENT_LOOKBACK_HOURS)
    rows = session.execute(text(
        f"""
        SELECT operator_id FROM (
          SELECT operator_id FROM research_ro.research_operator_control
          UNION
          SELECT operator_id FROM research_ro.research_manual_run_audit
          WHERE created_at > now() - interval '{win_h} hours'
          UNION
          SELECT operator_id FROM research_ro.research_alert
          WHERE created_at > now() - interval '{win_h} hours'
            AND operator_id IS NOT NULL
        ) AS u
        WHERE operator_id IS NOT NULL
        """
    )).all()
    out: list[EnforcementEvaluation] = []
    for r in rows:
        ev = evaluate_operator_state(
            session, operator_id=r[0], now=cur_now, dry_run=dry_run,
        )
        out.append(ev)
        if not dry_run and ev.would_change:
            apply_operator_state_transition(
                session, evaluation=ev, source="auto",
            )
    if not dry_run:
        logger.info(
            "[auto_enforcement] evaluated={} changed={}",
            len(out), sum(1 for e in out if e.would_change),
        )
    return out
