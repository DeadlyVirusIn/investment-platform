"""Signal Validation Agent (shadow).

Read-only validation pass over recent rows of the `signal` table.
Produces a per-row alignment / warning summary AND a roll-up.
Shadow only: NEVER writes back to any table, NEVER changes signal
strength, NEVER influences execution.

Validation rules (deterministic, all pure):

  R1 confidence_floor          confidence >= 0.5 (configurable)
  R2 strength_direction_align  signal_strength sign matches
                               signal_direction (long > 0,
                               short < 0). Strength 0 always
                               flags as "ambiguous".
  R3 holding_period_positive   holding_period_bars >= 1
  R4 regime_tag_present        regime_tag is non-empty
  R5 freshness                 generated_at within `max_age_days`
                               (default 30) of `as_of_date`

Each row emits a structured `signal_check` with the rule names
that fired. The roll-up reports counts per rule and a global
`alignment_rate` = signals_with_zero_warnings / total.
"""

from __future__ import annotations

import datetime as _dt
from collections import Counter
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.src.db.models import Signal

from ..base import Agent, AgentOutput


def _to_float(v: Any) -> float | None:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _check_signal(
    row: Signal,
    *,
    confidence_floor: float,
    max_age_days: int,
) -> list[str]:
    """Return list of warning codes that fired for this row.
    Empty list = aligned."""
    warnings: list[str] = []

    conf = _to_float(row.confidence) or 0.0
    if conf < confidence_floor:
        warnings.append(
            f"low_confidence:{conf:.3f}<{confidence_floor:.3f}",
        )

    strength = _to_float(row.signal_strength) or 0.0
    direction = (row.signal_direction or "").lower()
    if strength == 0.0:
        warnings.append("ambiguous_strength_zero")
    elif direction in ("long", "buy"):
        if strength <= 0:
            warnings.append("strength_direction_mismatch:long_negative")
    elif direction in ("short", "sell"):
        if strength >= 0:
            warnings.append("strength_direction_mismatch:short_positive")

    if (row.holding_period_bars or 0) < 1:
        warnings.append("holding_period_nonpositive")

    if not (row.regime_tag or "").strip():
        warnings.append("regime_tag_missing")

    # Freshness — generated_at must not be more than `max_age_days`
    # past `as_of_date`. Use UTC-safe comparison.
    try:
        gen = row.generated_at
        ref = row.as_of_date
        if gen and ref:
            gen_d = gen.date() if hasattr(gen, "date") else gen
            delta = (gen_d - ref).days if isinstance(gen_d, _dt.date) else 0
            if abs(delta) > max_age_days:
                warnings.append(
                    f"stale:abs_delta_days={abs(delta)}",
                )
    except Exception:  # noqa: BLE001 — defensive boundary
        warnings.append("freshness_check_failed")

    return warnings


class SignalValidationAgent(Agent):
    name = "signal_validation"
    description = (
        "Shadow validator: per-signal alignment + warning checks "
        "and a roll-up alignment_rate. Read-only — never affects "
        "signal scoring or execution."
    )

    def inputs(self) -> dict[str, str]:
        return {
            "signal": (
                "recent rows from the signal table — direction, "
                "strength, confidence, holding_period_bars, "
                "regime_tag, generated_at"
            ),
        }

    def run(
        self,
        *,
        db: Session,
        limit: int = 500,
        confidence_floor: float = 0.5,
        max_age_days: int = 30,
        **_: Any,
    ) -> AgentOutput:
        confidence_floor = max(0.0, min(1.0, float(confidence_floor)))
        max_age_days = max(0, int(max_age_days))
        limit = max(1, min(int(limit), 2000))

        rows = (
            db.execute(
                select(Signal)
                .order_by(Signal.generated_at.desc())
                .limit(limit),
            )
            .scalars()
            .all()
        )

        per_signal: list[dict[str, Any]] = []
        rule_counter: Counter[str] = Counter()
        aligned = 0
        for r in rows:
            warns = _check_signal(
                r,
                confidence_floor=confidence_floor,
                max_age_days=max_age_days,
            )
            for w in warns:
                # Bucket by leading rule name (before the colon).
                rule_counter[w.split(":", 1)[0]] += 1
            if not warns:
                aligned += 1
            per_signal.append({
                "signal_id": r.signal_id,
                "as_of_date": r.as_of_date.isoformat()
                if r.as_of_date else None,
                "symbol": r.symbol,
                "strategy_id": r.strategy_id,
                "direction": r.signal_direction,
                "strength": _to_float(r.signal_strength),
                "confidence": _to_float(r.confidence),
                "warnings": warns,
                "aligned": len(warns) == 0,
            })

        n = len(per_signal)
        alignment_rate = (aligned / n) if n else None

        rollup_warnings: list[str] = []
        if n == 0:
            rollup_warnings.append("no_signals_in_window")
        elif n < 20:
            rollup_warnings.append(
                f"small_sample:n={n} — alignment_rate is "
                "directional only",
            )

        return self.envelope(
            output={
                "n_signals": n,
                "aligned_count": aligned,
                "alignment_rate": alignment_rate,
                "rule_counts": dict(rule_counter),
                "per_signal": per_signal,
                "params": {
                    "confidence_floor": confidence_floor,
                    "max_age_days": max_age_days,
                    "limit": limit,
                },
            },
            inputs_summary={
                "limit": limit,
                "confidence_floor": confidence_floor,
                "max_age_days": max_age_days,
                "n_signals": n,
            },
            warnings=rollup_warnings,
        )
