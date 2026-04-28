"""Phase 11P.3 - Exploratory paper-only runner.

Reads `context_daily` per as-of-date, applies a frozen exploratory
rule, and writes append-only rows to `decision_log` tagged
source='exploratory_paper'. NEVER writes to `paper_position` /
`paper_trade`. NEVER touches strict engine code or strict gate
constants. NEVER imports broker / live / execution modules.

Frozen rule (EXPLORATORY_RULE_v1.0.0):
  * fire when any 1 of the 4 production gates is True
  * record an observation (no fire) when all 4 gates are None
    (data-missing day) so the day is still ML-label-eligible
  * never short
  * size = 1 (deterministic; paper-only label generation only)

Operator opt-in via settings.EQUITY_EXPLORATORY_ENABLED. Refuses to
commit when False even if invoked manually with --commit.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from typing import Any, Sequence

from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.config import settings as default_settings
from apps.api.src.db import SessionLocal


EXPLORATORY_RULE_VERSION = "EXPLORATORY_RULE_v1.0.0"
SOURCE_TAG = "exploratory_paper"
PRODUCTION_GATES: tuple[str, ...] = (
    "rates_calm", "vrp_supportive", "credit_stable", "liquidity_expanding",
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class ExploratorySafetyError(RuntimeError):
    """Raised when EQUITY_EXPLORATORY_ENABLED is False or other
    invariant is violated."""


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ExploratoryConfig:
    date: dt.date
    underlyings: tuple[str, ...]
    backfill_from: dt.date | None
    dry_run: bool
    commit: bool

    def __post_init__(self) -> None:
        if self.dry_run == self.commit:
            raise ValueError("dry_run and commit are mutually exclusive")
        if not self.underlyings:
            raise ValueError("underlyings must be non-empty")
        if self.backfill_from is not None and self.backfill_from > self.date:
            raise ValueError("backfill_from must be <= date")


@dataclass(frozen=True)
class ExploratoryDecision:
    as_of_date: dt.date
    instrument: str
    fire: bool
    failed_gates: tuple[str, ...]
    strict_gates_passed: bool
    gate_snapshot: dict[str, Any]
    rule_id: str
    reason: str


@dataclass(frozen=True)
class ExploratorySummary:
    config: ExploratoryConfig
    n_days: int
    n_decisions: int
    n_fires: int
    n_committed: int
    rule_version: str


# ---------------------------------------------------------------------------
# Safety
# ---------------------------------------------------------------------------

def assert_exploratory_enabled(settings_obj=None) -> None:
    s = settings_obj if settings_obj is not None else default_settings
    if not getattr(s, "EQUITY_EXPLORATORY_ENABLED", False):
        raise ExploratorySafetyError(
            "EQUITY_EXPLORATORY_ENABLED must be True before exploratory "
            "paper observations may be committed"
        )


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def read_context_for_day(
    session: Session, *, as_of: dt.date,
) -> dict[str, bool | None]:
    rows = session.execute(text(
        """
        SELECT context_name, value_bool, status
        FROM context_daily
        WHERE as_of_date = :d
          AND context_name IN (
              'rates_calm','vrp_supportive',
              'credit_stable','liquidity_expanding'
          )
        """
    ), {"d": as_of}).all()
    out: dict[str, bool | None] = {n: None for n in PRODUCTION_GATES}
    for r in rows:
        if r.status == "missing_data":
            out[r.context_name] = None
        else:
            out[r.context_name] = bool(r.value_bool)
    return out


def evaluate_exploratory_rule(
    *,
    as_of: dt.date,
    instrument: str,
    gates: dict[str, bool | None],
) -> ExploratoryDecision:
    """Frozen rule. fire when any 1 of the 4 gates is True."""
    failed = tuple(
        g for g in PRODUCTION_GATES
        if gates.get(g) is not True
    )
    n_true = sum(1 for g in PRODUCTION_GATES if gates.get(g) is True)
    fire = n_true >= 1
    strict_pass = all(gates.get(g) is True for g in PRODUCTION_GATES)
    if fire:
        reason = (
            f"exploratory: {n_true}/4 gates true; record observation "
            f"for ML labeling"
        )
    else:
        reason = (
            "exploratory: 0/4 gates true; no fire; observation logged "
            "for ML labeling"
        )
    return ExploratoryDecision(
        as_of_date=as_of, instrument=instrument, fire=fire,
        failed_gates=failed, strict_gates_passed=strict_pass,
        gate_snapshot={k: gates.get(k) for k in PRODUCTION_GATES},
        rule_id=EXPLORATORY_RULE_VERSION,
        reason=reason,
    )


_INSERT_DECISION_SQL = text(
    """
    INSERT INTO decision_log
      (as_of_date, engine, action, instrument,
       inputs_used, context_values, decision_version, reason,
       diagnostic_snapshot,
       source, strict_gates_passed, failed_gates,
       ml_label_eligible,
       gate_mode, exploratory_paper, exploratory_reason,
       gates_passed, gates_total, gates_failed,
       strict_would_block, exploratory_size_multiplier,
       alpha_rule_blocked)
    VALUES
      (:as_of_date, 'exploratory', :action, :instrument,
       CAST(:inputs AS jsonb), CAST(:ctx AS jsonb),
       :decision_version, :reason,
       CAST(:diag AS jsonb),
       :source, :strict_pass, :failed_gates,
       :ml_eligible,
       'exploratory', TRUE, :exploratory_reason,
       :gates_passed, :gates_total, CAST(:gates_failed AS jsonb),
       :strict_would_block, :exp_size,
       FALSE)
    """
)


def persist_decision(
    session: Session,
    decision: ExploratoryDecision,
) -> None:
    n_pass = sum(
        1 for v in decision.gate_snapshot.values() if v is True
    )
    action = "enter_long" if decision.fire else "no_fire"
    session.execute(_INSERT_DECISION_SQL, {
        "as_of_date": decision.as_of_date,
        "action": action,
        "instrument": decision.instrument,
        "inputs": json.dumps({
            "rule": decision.rule_id,
            "size_paper_contracts": 1,
        }),
        "ctx": json.dumps(decision.gate_snapshot, default=str),
        "decision_version": decision.rule_id,
        "reason": decision.reason,
        "diag": json.dumps({
            "source": SOURCE_TAG,
            "n_gates_true": n_pass,
        }),
        "source": SOURCE_TAG,
        "strict_pass": decision.strict_gates_passed,
        "failed_gates": list(decision.failed_gates),
        "ml_eligible": True,
        "exploratory_reason": decision.reason,
        "gates_passed": n_pass,
        "gates_total": len(PRODUCTION_GATES),
        "gates_failed": json.dumps(list(decision.failed_gates)),
        "strict_would_block": not decision.strict_gates_passed,
        "exp_size": 1.0,
    })


def days_in_window(
    cfg: ExploratoryConfig,
) -> list[dt.date]:
    start = cfg.backfill_from or cfg.date
    end = cfg.date
    out: list[dt.date] = []
    d = start
    while d <= end:
        if d.weekday() < 5:  # Monday..Friday
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def run(
    cfg: ExploratoryConfig,
    *,
    settings_obj=None,
    session_factory=None,
) -> ExploratorySummary:
    if cfg.commit:
        assert_exploratory_enabled(settings_obj)

    sf = session_factory or SessionLocal
    days = days_in_window(cfg)

    n_decisions = 0
    n_fires = 0
    n_committed = 0
    with sf() as session:
        for d in days:
            gates = read_context_for_day(session, as_of=d)
            for inst in cfg.underlyings:
                decision = evaluate_exploratory_rule(
                    as_of=d, instrument=inst, gates=gates,
                )
                n_decisions += 1
                if decision.fire:
                    n_fires += 1
                if cfg.commit:
                    persist_decision(session, decision)
                    n_committed += 1
        if cfg.commit:
            session.commit()

    summary = ExploratorySummary(
        config=cfg,
        n_days=len(days),
        n_decisions=n_decisions,
        n_fires=n_fires,
        n_committed=n_committed,
        rule_version=EXPLORATORY_RULE_VERSION,
    )
    logger.info(
        "phase 11P exploratory complete: dry_run={} days={} "
        "decisions={} fires={} committed={}",
        cfg.dry_run, summary.n_days, summary.n_decisions,
        summary.n_fires, summary.n_committed,
    )
    return summary
