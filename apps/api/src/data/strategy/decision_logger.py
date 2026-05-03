"""Decision Logger — append-only writes to decision_log.

Phase reliability/catalyst extension — every decision now carries:
  data_quality:     provenance + confidence + missing/stale fields
  catalyst:         CatalystSummary snapshot at decision time
  feature_confidence: roll-up 0..1 for fast filtering / ML pipelines
  skip_reason:      plain-text reason when engine opts out
  missing_features: redundant list for fast SQL "WHERE X IS IN"

All new fields optional — existing call sites keep working.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.data.strategy.selector import SelectorOutput


@dataclass(frozen=True)
class LoggedDecision:
    as_of_date: dt.date
    engine: str
    action: str
    instrument: str
    inputs_used: dict
    context_values: dict
    decision_version: str
    reason: str
    blocked_by: str | None = None
    diagnostic_snapshot: dict | None = None
    # --- Phase reliability / catalyst additions (all optional) ---
    data_quality: dict | None = None
    catalyst: dict | None = None
    feature_confidence: float | None = None
    skip_reason: str | None = None
    missing_features: list[str] | None = None
    # --- Phase ML-2 advisory annotations (never affects execution) ---
    ml_advisory: dict | None = None
    baseline_advisory: dict | None = None
    pattern_flags: dict | None = None
    # --- Phase SYSTEM-ALPHA-4 rule adjustment audit ---
    alpha_rule_adjustment: dict | None = None
    alpha_rules_applied: list | dict | None = None
    alpha_rules_mode: str | None = None
    alpha_rule_size_multiplier: float | None = None
    alpha_rule_blocked: bool | None = None
    alpha_rule_block_reason: str | None = None
    # --- Phase SYSTEM-ALPHA-5 paper exploratory ---
    gate_mode: str | None = None
    exploratory_paper: bool | None = None
    exploratory_reason: str | None = None
    gates_passed: int | None = None
    gates_total: int | None = None
    gates_failed: list | None = None
    strict_would_block: bool | None = None
    exploratory_size_multiplier: float | None = None


def write_decision(
    session: Session, logged: LoggedDecision,
) -> str:
    """Insert row into decision_log. Returns new row id as UUID string."""
    row = session.execute(text("""
        INSERT INTO decision_log
          (as_of_date, engine, action, instrument, inputs_used,
           context_values, decision_version, reason, blocked_by,
           diagnostic_snapshot,
           data_quality, catalyst, feature_confidence, skip_reason,
           missing_features,
           ml_advisory, baseline_advisory, pattern_flags,
           alpha_rule_adjustment, alpha_rules_applied,
           alpha_rules_mode, alpha_rule_size_multiplier,
           alpha_rule_blocked, alpha_rule_block_reason,
           gate_mode, exploratory_paper, exploratory_reason,
           gates_passed, gates_total, gates_failed,
           strict_would_block, exploratory_size_multiplier)
        VALUES
          (:asof, :eng, :act, :inst, CAST(:inp AS jsonb),
           CAST(:ctx AS jsonb), :ver, :reason, :blocked,
           CAST(:diag AS jsonb),
           CAST(:dq AS jsonb), CAST(:cat AS jsonb), :fconf, :skip,
           CAST(:miss AS jsonb),
           CAST(:mla AS jsonb), CAST(:bla AS jsonb), CAST(:pfl AS jsonb),
           CAST(:ara AS jsonb), CAST(:arap AS jsonb),
           :armode, :arsize, :arblk, :arblkr,
           :gmode, :expar, :expreason,
           :gp, :gt, CAST(:gf AS jsonb),
           :swb, :esm)
        RETURNING id
    """), {
        "asof": logged.as_of_date,
        "eng": logged.engine,
        "act": logged.action,
        "inst": logged.instrument,
        "inp": json.dumps(logged.inputs_used, default=str),
        "ctx": json.dumps(logged.context_values, default=str),
        "ver": logged.decision_version,
        "reason": logged.reason,
        "blocked": logged.blocked_by,
        "diag": json.dumps(logged.diagnostic_snapshot or {}, default=str),
        "dq":   _json_or_null(logged.data_quality),
        "cat":  _json_or_null(logged.catalyst),
        "fconf": logged.feature_confidence,
        "skip": logged.skip_reason,
        "miss": _json_or_null(logged.missing_features),
        "mla":  _json_or_null(logged.ml_advisory),
        "bla":  _json_or_null(logged.baseline_advisory),
        "pfl":  _json_or_null(logged.pattern_flags),
        "ara":  _json_or_null(logged.alpha_rule_adjustment),
        "arap": _json_or_null(logged.alpha_rules_applied),
        "armode": logged.alpha_rules_mode,
        "arsize": logged.alpha_rule_size_multiplier,
        "arblk":  logged.alpha_rule_blocked,
        "arblkr": logged.alpha_rule_block_reason,
        "gmode":    logged.gate_mode,
        "expar":    logged.exploratory_paper,
        "expreason": logged.exploratory_reason,
        "gp":       logged.gates_passed,
        "gt":       logged.gates_total,
        "gf":       _json_or_null(logged.gates_failed),
        "swb":      logged.strict_would_block,
        "esm":      logged.exploratory_size_multiplier,
    }).fetchone()
    session.commit()
    return str(row[0])


def _json_or_null(v: Any) -> str | None:
    if v is None:
        return None
    return json.dumps(v, default=str)


def decision_from_selector(
    output: SelectorOutput, *, as_of_date: dt.date, instrument: str,
    inputs_used: dict, context_values: dict,
    diagnostic_snapshot: dict | None = None,
    data_quality: dict | None = None,
    catalyst: dict | None = None,
    feature_confidence: float | None = None,
    skip_reason: str | None = None,
    missing_features: list[str] | None = None,
    # Phase SYSTEM-ALPHA-4 / 5 — optional, paper-only
    alpha_rule_adjustment: dict | None = None,
    alpha_rules_applied: list | dict | None = None,
    alpha_rules_mode: str | None = None,
    alpha_rule_size_multiplier: float | None = None,
    alpha_rule_blocked: bool | None = None,
    alpha_rule_block_reason: str | None = None,
    gate_mode: str | None = None,
    exploratory_paper: bool | None = None,
    exploratory_reason: str | None = None,
    gates_passed: int | None = None,
    gates_total: int | None = None,
    gates_failed: list | None = None,
    strict_would_block: bool | None = None,
    exploratory_size_multiplier: float | None = None,
) -> LoggedDecision:
    """Build a LoggedDecision from a SelectorOutput.

    Optional kwargs carry reliability + catalyst metadata through unchanged.
    """
    if output.fire:
        action = "enter_long"
    elif output.engine == "none":
        action = "skip"
    else:
        action = "no_fire"
    return LoggedDecision(
        as_of_date=as_of_date,
        engine=output.engine,
        action=action,
        instrument=instrument,
        inputs_used=inputs_used,
        context_values=context_values,
        decision_version=output.decision_version,
        reason=output.reason,
        blocked_by=None,
        diagnostic_snapshot=diagnostic_snapshot,
        data_quality=data_quality,
        catalyst=catalyst,
        feature_confidence=feature_confidence,
        skip_reason=skip_reason,
        missing_features=missing_features,
        alpha_rule_adjustment=alpha_rule_adjustment,
        alpha_rules_applied=alpha_rules_applied,
        alpha_rules_mode=alpha_rules_mode,
        alpha_rule_size_multiplier=alpha_rule_size_multiplier,
        alpha_rule_blocked=alpha_rule_blocked,
        alpha_rule_block_reason=alpha_rule_block_reason,
        gate_mode=gate_mode,
        exploratory_paper=exploratory_paper,
        exploratory_reason=exploratory_reason,
        gates_passed=gates_passed,
        gates_total=gates_total,
        gates_failed=gates_failed,
        strict_would_block=strict_would_block,
        exploratory_size_multiplier=exploratory_size_multiplier,
    )
