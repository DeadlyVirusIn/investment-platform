"""Rule executor — safe auto-apply + explicit apply/rollback.

Hard constraints enforced by `is_auto_applicable()`:
  * risk_level == "low"
  * confidence >= 0.80
  * sample_size >= 100
  * expected_impact == "positive"
  * suggestion type ∈ ALLOWED_AUTO_TYPES

Any attempt to auto-apply outside these constraints is rejected with a
clear reason. Manual apply via API still requires the suggestion to exist
in `alpha_rule_suggestion` with status='pending'.
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

from apps.api.src.alpha.rule_suggestions import (
    AUTO_MIN_CONF, AUTO_MIN_SAMPLE, Suggestion,
)


# Types that can be auto-applied (all reduce exposure / add guardrails)
ALLOWED_AUTO_TYPES = {
    "reduce_weight",
    "tighten_filters",
    "execution_guardrail",
    "restrict_concentrated_trades",
    "tighten_threshold",
}

# Types NEVER auto-applied (expose more risk)
FORBIDDEN_AUTO_TYPES = {
    "increase_weight",
    "remove_guardrail",
    "increase_position_size",
    "disable_filter",
}


@dataclass
class ApplyResult:
    ok: bool
    rule_id: str
    reason: str = ""
    history_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "rule_id": self.rule_id,
            "reason": self.reason,
            "history_id": self.history_id,
        }


# ---------------------------------------------------------------------------
# Gating
# ---------------------------------------------------------------------------

def is_auto_applicable(sug: Suggestion) -> tuple[bool, str]:
    if sug.type in FORBIDDEN_AUTO_TYPES:
        return False, f"type '{sug.type}' is in FORBIDDEN_AUTO_TYPES"
    if sug.type not in ALLOWED_AUTO_TYPES:
        return False, f"type '{sug.type}' not in ALLOWED_AUTO_TYPES"
    if sug.risk_level != "low":
        return False, f"risk_level='{sug.risk_level}' (require low)"
    if sug.confidence < AUTO_MIN_CONF:
        return False, f"confidence {sug.confidence:.2f} < {AUTO_MIN_CONF}"
    if sug.sample_size < AUTO_MIN_SAMPLE:
        return False, f"sample_size {sug.sample_size} < {AUTO_MIN_SAMPLE}"
    if sug.expected_impact != "positive":
        return False, f"expected_impact='{sug.expected_impact}'"
    return True, "ok"


# ---------------------------------------------------------------------------
# Persist suggestions
# ---------------------------------------------------------------------------

def persist_suggestions(
    session: Session, suggestions: list[Suggestion],
    *, dry_run: bool = False,
) -> int:
    """INSERT suggestions with status='pending'. Skips duplicates on
    (rule_id, created_at) thanks to unique constraint."""
    written = 0
    for s in suggestions:
        if dry_run:
            written += 1
            continue
        try:
            session.execute(text("""
                INSERT INTO alpha_rule_suggestion
                  (rule_id, rule_type, target, description,
                   confidence, sample_size, expected_impact,
                   risk_level, auto_applicable, parameters, details,
                   status)
                VALUES
                  (:rid, :rt, :t, :desc, :conf, :n, :imp,
                   :risk, :auto, CAST(:p AS jsonb), CAST(:d AS jsonb),
                   'pending')
                ON CONFLICT ON CONSTRAINT
                  ux_rule_suggestion_ruleid_created
                DO NOTHING
            """), {
                "rid":  s.rule_id, "rt": s.type, "t": s.target,
                "desc": s.description, "conf": s.confidence,
                "n":    s.sample_size, "imp": s.expected_impact,
                "risk": s.risk_level, "auto": s.auto_applicable,
                "p":    json.dumps(s.parameters, default=str),
                "d":    json.dumps(s.details, default=str),
            })
            written += 1
        except Exception as e:
            logger.warning("persist suggestion {} failed: {}",
                            s.rule_id, e)
    if not dry_run:
        session.commit()
    return written


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------

def apply_rule(
    session: Session,
    suggestion_id: str,
    *,
    applied_by: str = "operator",
    force_manual: bool = False,
) -> ApplyResult:
    """Apply a pending suggestion. `force_manual=True` allows applying
    medium-risk suggestions (still rejects high-risk or forbidden types).
    """
    row = session.execute(text("""
        SELECT id::text AS id, rule_id, rule_type, target, description,
               confidence, sample_size, expected_impact, risk_level,
               auto_applicable, parameters, details, status
        FROM alpha_rule_suggestion
        WHERE id = :id AND status = 'pending'
    """), {"id": suggestion_id}).mappings().first()
    if row is None:
        return ApplyResult(
            ok=False, rule_id="",
            reason=f"suggestion {suggestion_id} not pending",
        )

    # Reconstruct lean Suggestion for gate check
    sug = Suggestion(
        id=row["id"], rule_id=row["rule_id"],
        type=row["rule_type"], target=row["target"] or "",
        description=row["description"],
        confidence=float(row["confidence"]),
        sample_size=int(row["sample_size"]),
        expected_impact=row["expected_impact"],
        risk_level=row["risk_level"],
        auto_applicable=bool(row["auto_applicable"]),
        parameters=dict(row["parameters"] or {}),
        details=dict(row["details"] or {}),
    )

    if sug.type in FORBIDDEN_AUTO_TYPES:
        return ApplyResult(
            ok=False, rule_id=sug.rule_id,
            reason=f"type '{sug.type}' is FORBIDDEN",
        )
    if sug.risk_level == "high":
        return ApplyResult(
            ok=False, rule_id=sug.rule_id,
            reason="high-risk suggestions never applied via API",
        )
    if not force_manual:
        ok, reason = is_auto_applicable(sug)
        if not ok:
            return ApplyResult(
                ok=False, rule_id=sug.rule_id,
                reason=f"auto-apply rejected: {reason}",
            )

    # Previous parameters (if rule already live)
    prev_row = session.execute(text("""
        SELECT parameters FROM alpha_rule_active WHERE rule_id = :r
    """), {"r": sug.rule_id}).mappings().first()
    previous = dict(prev_row["parameters"] or {}) if prev_row else None

    # UPSERT active
    session.execute(text("""
        INSERT INTO alpha_rule_active
          (rule_id, rule_type, parameters, previous_parameters,
           applied_by, suggestion_id, status)
        VALUES
          (:r, :rt, CAST(:p AS jsonb), CAST(:pp AS jsonb),
           :ab, :sid, 'active')
        ON CONFLICT (rule_id) DO UPDATE SET
          parameters = EXCLUDED.parameters,
          previous_parameters = alpha_rule_active.parameters,
          applied_at = NOW(),
          applied_by = EXCLUDED.applied_by,
          suggestion_id = EXCLUDED.suggestion_id,
          status = 'active'
    """), {
        "r":  sug.rule_id, "rt": sug.type,
        "p":  json.dumps(sug.parameters, default=str),
        "pp": json.dumps(previous or {}),
        "ab": applied_by, "sid": sug.id,
    })

    # Append history
    history_id = str(uuid.uuid4())
    session.execute(text("""
        INSERT INTO alpha_rule_history
          (id, rule_id, action, parameters, previous_parameters,
           applied_by, reason, status)
        VALUES
          (:id, :r, 'apply', CAST(:p AS jsonb),
           CAST(:pp AS jsonb), :ab, :rea, 'active')
    """), {
        "id": history_id, "r": sug.rule_id,
        "p":  json.dumps(sug.parameters, default=str),
        "pp": json.dumps(previous or {}),
        "ab": applied_by,
        "rea": sug.description,
    })

    # Mark suggestion decided
    session.execute(text("""
        UPDATE alpha_rule_suggestion
           SET status = 'applied', decided_at = NOW()
         WHERE id = :id
    """), {"id": sug.id})
    session.commit()

    return ApplyResult(ok=True, rule_id=sug.rule_id, history_id=history_id,
                         reason="applied")


def ignore_suggestion(
    session: Session, suggestion_id: str,
    *, applied_by: str = "operator",
    reason: str = "",
) -> ApplyResult:
    session.execute(text("""
        UPDATE alpha_rule_suggestion
           SET status = 'ignored', decided_at = NOW()
         WHERE id = :id AND status = 'pending'
    """), {"id": suggestion_id})
    session.commit()
    return ApplyResult(ok=True, rule_id=suggestion_id,
                         reason=reason or "ignored")


# ---------------------------------------------------------------------------
# Rollback
# ---------------------------------------------------------------------------

def rollback_rule(
    session: Session, rule_id: str,
    *, applied_by: str = "operator", reason: str = "",
) -> ApplyResult:
    active = session.execute(text("""
        SELECT rule_id, rule_type, parameters, previous_parameters
        FROM alpha_rule_active
        WHERE rule_id = :r AND status = 'active'
    """), {"r": rule_id}).mappings().first()
    if active is None:
        return ApplyResult(
            ok=False, rule_id=rule_id,
            reason=f"rule {rule_id} not active",
        )
    prev = dict(active["previous_parameters"] or {})
    session.execute(text("""
        UPDATE alpha_rule_active
           SET parameters = CAST(:pp AS jsonb),
               previous_parameters = parameters,
               status = 'rolled_back',
               applied_at = NOW(),
               applied_by = :ab
         WHERE rule_id = :r
    """), {
        "r": rule_id, "pp": json.dumps(prev),
        "ab": applied_by,
    })
    history_id = str(uuid.uuid4())
    session.execute(text("""
        INSERT INTO alpha_rule_history
          (id, rule_id, action, parameters, previous_parameters,
           applied_by, reason, status)
        VALUES
          (:id, :r, 'rollback', CAST(:p AS jsonb),
           CAST(:pp AS jsonb), :ab, :rea, 'rolled_back')
    """), {
        "id": history_id, "r": rule_id,
        "p":  json.dumps(prev),
        "pp": json.dumps(dict(active["parameters"] or {})),
        "ab": applied_by,
        "rea": reason or "manual rollback",
    })
    session.commit()
    return ApplyResult(ok=True, rule_id=rule_id, history_id=history_id,
                         reason="rolled_back")
