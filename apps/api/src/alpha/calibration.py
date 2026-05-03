"""Deterministic auto-calibration — recommends safe, risk-reducing only.

Pure rules, no ML. Reads paper_trade_log + alpha_param_active. Emits list
of CalibrationRec; caller decides apply vs recommend via auto-apply gates.

Parameters calibrated:
  * paper_exploratory_size_multiplier
  * paper_exploratory_min_gates
  * min_data_confidence
  * max_event_risk
  * engine_size_multiplier_A / engine_size_multiplier_B
  * min_entry_quality
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from typing import Any

from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session


# --- auto-apply gates ---
AUTO_MIN_CONFIDENCE = 0.85
AUTO_MIN_SAMPLE = 50


# --- Known calibratable parameters with bounds.
# min_value / max_value ensure no rule ever crosses safety floor.
PARAM_BOUNDS: dict[str, dict[str, float]] = {
    "paper_exploratory_size_multiplier": {"min": 0.05, "max": 0.25,
                                            "default": 0.25},
    "paper_exploratory_min_gates":       {"min": 2.0,  "max": 4.0,
                                            "default": 2.0},
    "min_data_confidence":               {"min": 0.3,  "max": 0.9,
                                            "default": 0.5},
    "max_event_risk":                    {"min": 0.3,  "max": 0.9,
                                            "default": 0.7},
    "engine_size_multiplier_A":          {"min": 0.25, "max": 1.0,
                                            "default": 1.0},
    "engine_size_multiplier_B":          {"min": 0.25, "max": 1.0,
                                            "default": 1.0},
    "min_entry_quality":                 {"min": 0.3,  "max": 0.8,
                                            "default": 0.5},
}


@dataclass
class CalibrationRec:
    parameter_key: str
    old_value: float
    new_value: float
    reason: str
    confidence: float
    sample_size: int
    metrics: dict[str, Any] = field(default_factory=dict)
    risk_reducing: bool = True

    @property
    def auto_applicable(self) -> bool:
        return (
            self.risk_reducing
            and self.confidence >= AUTO_MIN_CONFIDENCE
            and self.sample_size >= AUTO_MIN_SAMPLE
            and self.new_value <= self.old_value   # never increase
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "parameter_key": self.parameter_key,
            "old_value": round(self.old_value, 6),
            "new_value": round(self.new_value, 6),
            "reason":    self.reason,
            "confidence": round(self.confidence, 4),
            "sample_size": self.sample_size,
            "metrics":   dict(self.metrics),
            "risk_reducing": self.risk_reducing,
            "auto_applicable": self.auto_applicable,
        }


# ---------------------------------------------------------------------------
# rule evaluators
# ---------------------------------------------------------------------------

def evaluate_calibration(
    session: Session,
    *,
    lookback_days: int = 30,
) -> list[CalibrationRec]:
    recs: list[CalibrationRec] = []
    active = _load_active_params(session)

    # Aggregate paper_trade stats
    closed = _load_closed_trades(session, lookback_days)
    exploratory = [t for t in closed if t.get("exploratory_paper")]
    strict = [t for t in closed if not t.get("exploratory_paper")]
    eng_a = [t for t in closed if (t.get("engine") or "").upper() == "A"]
    eng_b = [t for t in closed if (t.get("engine") or "").upper() == "B"]

    # Rule 1: exploratory reduction
    r1 = _rule_reduce_exploratory(exploratory, active)
    if r1 is not None: recs.append(r1)

    # Rule 2: engine B underperformance
    r2 = _rule_engine_underperf("B", eng_b, active)
    if r2 is not None: recs.append(r2)
    # Same rule applies symmetrically to A
    r2a = _rule_engine_underperf("A", eng_a, active)
    if r2a is not None: recs.append(r2a)

    # Rule 3: low win-rate → raise min_data_confidence
    r3 = _rule_raise_data_confidence(closed, active)
    if r3 is not None: recs.append(r3)

    # Rule 4: stable strong — mark only, no size change
    # (We don't return a rec; recorded as metric when applicable.)
    return recs


def _rule_reduce_exploratory(
    rows: list[dict[str, Any]],
    active: dict[str, float],
) -> CalibrationRec | None:
    n = len(rows)
    if n < 20:
        return None
    returns = [float(t["net_ret_pct"] or 0) for t in rows
               if t.get("net_ret_pct") is not None]
    if not returns:
        return None
    avg_return = sum(returns) / len(returns)
    if avg_return >= 0:
        return None
    current = active.get(
        "paper_exploratory_size_multiplier",
        PARAM_BOUNDS["paper_exploratory_size_multiplier"]["default"],
    )
    # Reduce by 30%, bounded to floor
    proposed = max(
        PARAM_BOUNDS["paper_exploratory_size_multiplier"]["min"],
        round(current * 0.7, 4),
    )
    if proposed >= current:
        return None
    # Confidence scales with how negative the avg return is and n
    conf = min(1.0, 0.6 + (abs(avg_return) * 0.05) + (n / 200.0))
    return CalibrationRec(
        parameter_key="paper_exploratory_size_multiplier",
        old_value=current, new_value=proposed,
        reason=(f"{n} exploratory trades avg_return "
                f"{avg_return:.2f}% — reduce size"),
        confidence=conf, sample_size=n,
        metrics={"avg_return": avg_return, "n": n},
        risk_reducing=True,
    )


def _rule_engine_underperf(
    engine: str, rows: list[dict[str, Any]],
    active: dict[str, float],
) -> CalibrationRec | None:
    n = len(rows)
    if n < 30:
        return None
    rets = [float(t["net_ret_pct"] or 0) for t in rows
            if t.get("net_ret_pct") is not None]
    if not rets:
        return None
    avg = sum(rets) / len(rets)
    wins = sum(1 for r in rets if r > 0)
    win_rate = wins / len(rets)
    sd = _std(rets)
    sharpe = (avg / sd) if sd > 1e-9 else 0.0
    # Negative sharpe AND negative avg → tighten
    if sharpe >= 0 or avg >= 0:
        return None
    key = f"engine_size_multiplier_{engine}"
    bounds = PARAM_BOUNDS[key]
    current = active.get(key, bounds["default"])
    proposed = max(bounds["min"], 0.5)
    if proposed >= current:
        return None
    conf = min(1.0, 0.7 + (n / 300.0))
    return CalibrationRec(
        parameter_key=key,
        old_value=current, new_value=proposed,
        reason=(f"Engine {engine}: sharpe {sharpe:.2f} avg {avg:.2f}% "
                f"win {win_rate:.0%} over {n} trades — halve size"),
        confidence=conf, sample_size=n,
        metrics={
            "avg_return": avg, "sharpe": sharpe,
            "win_rate": win_rate, "n": n,
        },
        risk_reducing=True,
    )


def _rule_raise_data_confidence(
    rows: list[dict[str, Any]], active: dict[str, float],
) -> CalibrationRec | None:
    # Separate by data_confidence (if present on paper_trade_log via
    # snapshot). Fall back: low-win rate across all trades.
    n = len(rows)
    if n < 40:
        return None
    wins = 0
    total_with_ret = 0
    for t in rows:
        r = t.get("net_ret_pct")
        if r is None:
            continue
        total_with_ret += 1
        if float(r) > 0:
            wins += 1
    if total_with_ret < 30:
        return None
    wr = wins / total_with_ret
    if wr >= 0.45:
        return None
    current = active.get(
        "min_data_confidence",
        PARAM_BOUNDS["min_data_confidence"]["default"],
    )
    proposed = min(
        PARAM_BOUNDS["min_data_confidence"]["max"],
        round(current + 0.1, 3),
    )
    if proposed <= current:
        return None
    conf = min(1.0, 0.7 + (total_with_ret / 300.0))
    # This rule TIGHTENS the filter; it increases a threshold but that
    # reduces trade frequency / risk overall. Mark risk_reducing=True.
    return CalibrationRec(
        parameter_key="min_data_confidence",
        old_value=current, new_value=proposed,
        reason=(f"Recent win_rate {wr:.0%} over {total_with_ret} trades — "
                f"tighten min_data_confidence"),
        confidence=conf, sample_size=total_with_ret,
        metrics={"win_rate": wr, "n": total_with_ret},
        risk_reducing=True,
    )


# ---------------------------------------------------------------------------
# persistence
# ---------------------------------------------------------------------------

def persist_recommendations(
    session: Session, recs: list[CalibrationRec],
    *, auto_apply: bool = False,
) -> dict[str, Any]:
    applied = 0
    recommended = 0
    for r in recs:
        # Always log recommendation
        session.execute(text("""
            INSERT INTO alpha_calibration_log
              (parameter_key, action, old_value, new_value, reason,
               confidence, sample_size, applied_by, auto_applied,
               status, metrics)
            VALUES
              (:k, 'recommend', :ov, :nv, :rea,
               :c, :n, 'system', false, 'pending',
               CAST(:m AS jsonb))
        """), {
            "k": r.parameter_key, "ov": r.old_value, "nv": r.new_value,
            "rea": r.reason, "c": r.confidence, "n": r.sample_size,
            "m": json.dumps(r.metrics, default=str),
        })
        recommended += 1
        if auto_apply and r.auto_applicable:
            apply_recommendation(session, r, applied_by="system",
                                   mark_auto=True)
            applied += 1
    session.commit()
    return {"recommended": recommended, "auto_applied": applied}


def apply_recommendation(
    session: Session, r: CalibrationRec,
    *, applied_by: str = "operator", mark_auto: bool = False,
) -> None:
    session.execute(text("""
        INSERT INTO alpha_param_active
          (parameter_key, value, previous_value, reason,
           confidence, sample_size, applied_by, status)
        VALUES
          (:k, :nv, :ov, :rea, :c, :n, :ab, 'active')
        ON CONFLICT (parameter_key) DO UPDATE SET
          previous_value = alpha_param_active.value,
          value       = EXCLUDED.value,
          reason      = EXCLUDED.reason,
          confidence  = EXCLUDED.confidence,
          sample_size = EXCLUDED.sample_size,
          applied_by  = EXCLUDED.applied_by,
          applied_at  = NOW(),
          status      = 'active'
    """), {
        "k": r.parameter_key, "nv": r.new_value, "ov": r.old_value,
        "rea": r.reason, "c": r.confidence, "n": r.sample_size,
        "ab": applied_by,
    })
    session.execute(text("""
        INSERT INTO alpha_calibration_log
          (parameter_key, action, old_value, new_value, reason,
           confidence, sample_size, applied_by, auto_applied,
           status, metrics)
        VALUES
          (:k, 'apply', :ov, :nv, :rea,
           :c, :n, :ab, :auto, 'applied',
           CAST(:m AS jsonb))
    """), {
        "k": r.parameter_key, "ov": r.old_value, "nv": r.new_value,
        "rea": r.reason, "c": r.confidence, "n": r.sample_size,
        "ab": applied_by, "auto": mark_auto,
        "m": json.dumps(r.metrics, default=str),
    })


def revert_parameter(
    session: Session, parameter_key: str, *,
    applied_by: str = "operator", reason: str = "",
) -> bool:
    row = session.execute(text("""
        SELECT value, previous_value FROM alpha_param_active
        WHERE parameter_key = :k AND status = 'active'
    """), {"k": parameter_key}).mappings().first()
    if row is None:
        return False
    prev = row.get("previous_value")
    if prev is None:
        # Revert to default
        prev = PARAM_BOUNDS.get(parameter_key, {}).get("default")
        if prev is None:
            return False
    session.execute(text("""
        UPDATE alpha_param_active
           SET previous_value = value,
               value = :pv,
               reason = :rea,
               applied_by = :ab,
               applied_at = NOW()
         WHERE parameter_key = :k
    """), {"k": parameter_key, "pv": prev, "rea": reason or "manual revert",
            "ab": applied_by})
    session.execute(text("""
        INSERT INTO alpha_calibration_log
          (parameter_key, action, old_value, new_value, reason,
           confidence, sample_size, applied_by, auto_applied,
           status, metrics)
        VALUES
          (:k, 'revert', :ov, :nv, :rea, 0, 0, :ab, false,
           'reverted', CAST('{}' AS jsonb))
    """), {
        "k": parameter_key, "ov": row["value"], "nv": prev,
        "rea": reason or "manual revert", "ab": applied_by,
    })
    session.commit()
    return True


def load_active_params(session: Session) -> dict[str, float]:
    return _load_active_params(session)


def _load_active_params(session: Session) -> dict[str, float]:
    try:
        rows = session.execute(text("""
            SELECT parameter_key, value FROM alpha_param_active
            WHERE status = 'active'
        """)).mappings().all()
    except Exception as e:
        logger.warning("calibration: active params read failed: {}", e)
        return {}
    return {r["parameter_key"]: float(r["value"]) for r in rows}


def _load_closed_trades(
    session: Session, lookback_days: int,
) -> list[dict[str, Any]]:
    try:
        rows = session.execute(text("""
            SELECT engine, instrument, entry_date, exit_date,
                   net_ret_pct, exploratory_paper
            FROM paper_trade_log
            WHERE status = 'closed'
              AND entry_date >= CURRENT_DATE - :lb
        """), {"lb": int(lookback_days)}).mappings().all()
    except Exception as e:
        logger.warning("calibration: closed-trades read failed: {}", e)
        return []
    return [dict(r) for r in rows]


def _std(xs: list[float]) -> float:
    if not xs:
        return 0.0
    m = sum(xs) / len(xs)
    return (sum((x - m) ** 2 for x in xs) / len(xs)) ** 0.5
