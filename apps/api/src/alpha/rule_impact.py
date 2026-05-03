"""Rule impact tracker — computes before/after metrics per active rule.

Populates rule_performance_log. Never auto-rolls back by default. Returns
recommendation ∈ {keep, monitor, suggest_rollback, insufficient_data}.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session


MIN_APPLIED = 20
WINDOWS = (7, 14, 30)


@dataclass
class ImpactMetrics:
    rule_id: str
    window_days: int
    n_applied: int
    n_control: int
    mean_return_applied:  float | None
    mean_return_control:  float | None
    hit_rate_applied:     float | None
    hit_rate_control:     float | None
    mean_return_change:   float | None
    hit_rate_change:      float | None
    trade_count_change:   float | None
    recommendation:       str
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "window_days": self.window_days,
            "n_applied": self.n_applied,
            "n_control": self.n_control,
            "mean_return_applied":
                _r(self.mean_return_applied, 6),
            "mean_return_control":
                _r(self.mean_return_control, 6),
            "hit_rate_applied":
                _r(self.hit_rate_applied),
            "hit_rate_control":
                _r(self.hit_rate_control),
            "mean_return_change":
                _r(self.mean_return_change, 6),
            "hit_rate_change":
                _r(self.hit_rate_change),
            "trade_count_change":
                _r(self.trade_count_change),
            "recommendation": self.recommendation,
            "warnings": list(self.warnings),
        }


def compute_rule_impact(
    session: Session,
    *,
    windows: tuple[int, ...] = WINDOWS,
    min_applied: int = MIN_APPLIED,
    return_col_candidates: tuple[str, ...] = (
        "fwd_ret_5d", "realized_net_ret",
    ),
    rollback_hit_rate_drop: float = 0.10,
    rollback_return_drop: float = -0.01,
    rollback_trade_drop: float = 0.50,
    persist: bool = True,
) -> list[ImpactMetrics]:
    """One row per (rule_id, window). Persists to rule_performance_log."""
    today = dt.date.today()
    # Pull active rules
    rules = session.execute(text("""
        SELECT rule_id FROM alpha_rule_active WHERE status = 'active'
    """)).mappings().all()
    if not rules:
        return []

    out: list[ImpactMetrics] = []
    for rule_row in rules:
        rule_id = str(rule_row["rule_id"])
        for window in windows:
            m = _metrics_for_rule(
                session, rule_id=rule_id, window_days=window,
                min_applied=min_applied,
                return_cols=return_col_candidates,
                rollback_hit_rate_drop=rollback_hit_rate_drop,
                rollback_return_drop=rollback_return_drop,
                rollback_trade_drop=rollback_trade_drop,
            )
            out.append(m)
            if persist:
                _persist_metrics(session, today, window, m)
    if persist:
        session.commit()
    return out


# ---------------------------------------------------------------------------

def _metrics_for_rule(
    session: Session, *,
    rule_id: str, window_days: int, min_applied: int,
    return_cols: tuple[str, ...],
    rollback_hit_rate_drop: float,
    rollback_return_drop: float,
    rollback_trade_drop: float,
) -> ImpactMetrics:
    since = dt.date.today() - dt.timedelta(days=window_days)
    try:
        applied_rows = session.execute(text("""
            SELECT instrument AS symbol,
                   alpha_rule_adjustment,
                   inputs_used,
                   factor_attribution,
                   as_of_date
            FROM decision_log
            WHERE as_of_date >= :since
              AND alpha_rules_applied IS NOT NULL
              AND alpha_rule_adjustment IS NOT NULL
              AND alpha_rule_adjustment ->> 'applied_rules' LIKE :pat
        """), {
            "since": since,
            "pat": f'%{rule_id}%',
        }).mappings().all()
    except Exception as e:
        logger.warning("impact: applied query failed: {}", e)
        applied_rows = []

    # Control = same-window decisions without this rule applied
    try:
        control_rows = session.execute(text("""
            SELECT instrument AS symbol, as_of_date
            FROM decision_log
            WHERE as_of_date >= :since
              AND (alpha_rule_adjustment IS NULL
                OR alpha_rule_adjustment ->> 'applied_rules'
                   NOT LIKE :pat)
        """), {
            "since": since,
            "pat": f'%{rule_id}%',
        }).mappings().all()
    except Exception as e:
        logger.warning("impact: control query failed: {}", e)
        control_rows = []

    # Pull outcomes from paper_trade_log entry_date → net_ret_pct
    applied_metrics = _match_outcomes(session, applied_rows, since)
    control_metrics = _match_outcomes(session, control_rows, since)

    n_app = len(applied_metrics)
    n_ctl = len(control_metrics)

    if n_app < min_applied:
        return ImpactMetrics(
            rule_id=rule_id, window_days=window_days,
            n_applied=n_app, n_control=n_ctl,
            mean_return_applied=None, mean_return_control=None,
            hit_rate_applied=None, hit_rate_control=None,
            mean_return_change=None, hit_rate_change=None,
            trade_count_change=None,
            recommendation="insufficient_data",
            warnings=[
                f"n_applied {n_app} < {min_applied} — no recommendation",
            ],
        )

    mean_app = float(np.mean(applied_metrics))
    mean_ctl = float(np.mean(control_metrics)) if n_ctl > 0 else 0.0
    hit_app  = float((np.array(applied_metrics) > 0).mean())
    hit_ctl  = (
        float((np.array(control_metrics) > 0).mean())
        if n_ctl > 0 else 0.0
    )
    ret_change = mean_app - mean_ctl
    hit_change = hit_app - hit_ctl
    trade_change = (
        (n_app - n_ctl) / max(1, n_ctl) if n_ctl > 0 else 0.0
    )

    # Recommendation
    warnings: list[str] = []
    reason_flags = []
    if ret_change <= rollback_return_drop:
        reason_flags.append("return_drop")
    if hit_change <= -rollback_hit_rate_drop:
        reason_flags.append("hit_rate_drop")
    if trade_change <= -rollback_trade_drop:
        reason_flags.append("trade_count_collapse")

    if reason_flags:
        rec = "suggest_rollback"
        warnings.append(f"negative evidence: {reason_flags}")
    elif ret_change >= 0 and hit_change >= 0:
        rec = "keep"
    else:
        rec = "monitor"

    return ImpactMetrics(
        rule_id=rule_id, window_days=window_days,
        n_applied=n_app, n_control=n_ctl,
        mean_return_applied=mean_app,
        mean_return_control=mean_ctl,
        hit_rate_applied=hit_app,
        hit_rate_control=hit_ctl,
        mean_return_change=ret_change,
        hit_rate_change=hit_change,
        trade_count_change=trade_change,
        recommendation=rec,
        warnings=warnings,
    )


def _match_outcomes(
    session: Session, rows, since: dt.date,
) -> list[float]:
    if not rows:
        return []
    # Collapse to (symbol, date) tuples and look up paper outcomes
    keys = {(str(r["symbol"]), r["as_of_date"]) for r in rows}
    if not keys:
        return []
    symbols = list({k[0] for k in keys})
    dates   = list({k[1] for k in keys})
    try:
        trade_rows = session.execute(text("""
            SELECT instrument AS symbol, entry_date, net_ret_pct
            FROM paper_trade_log
            WHERE status = 'closed'
              AND instrument = ANY(:syms)
              AND entry_date = ANY(:dates)
              AND net_ret_pct IS NOT NULL
        """), {"syms": symbols, "dates": dates}).mappings().all()
    except Exception as e:
        logger.warning("impact: outcome lookup failed: {}", e)
        return []
    by_key = {
        (str(t["symbol"]), t["entry_date"]):
        float(t["net_ret_pct"]) for t in trade_rows
    }
    out: list[float] = []
    for s, d in keys:
        v = by_key.get((s, d))
        if v is not None:
            out.append(v)
    return out


def _persist_metrics(
    session: Session, as_of: dt.date, window_days: int,
    m: ImpactMetrics,
) -> None:
    session.execute(text("""
        INSERT INTO rule_performance_log
          (rule_id, window_start, window_end, before, after, delta)
        VALUES
          (:r, :ws, :we, CAST(:b AS jsonb),
           CAST(:a AS jsonb), CAST(:d AS jsonb))
    """), {
        "r":  m.rule_id,
        "ws": as_of - dt.timedelta(days=window_days),
        "we": as_of,
        "b":  json.dumps({
            "mean_return": m.mean_return_control,
            "hit_rate":    m.hit_rate_control,
            "n":           m.n_control,
        }),
        "a":  json.dumps({
            "mean_return": m.mean_return_applied,
            "hit_rate":    m.hit_rate_applied,
            "n":           m.n_applied,
        }),
        "d":  json.dumps({
            "mean_return_change": m.mean_return_change,
            "hit_rate_change":    m.hit_rate_change,
            "trade_count_change": m.trade_count_change,
            "recommendation":     m.recommendation,
            "warnings":           m.warnings,
            "window_days":        m.window_days,
        }, default=str),
    })


def _r(x: float | None, digits: int = 4) -> float | None:
    if x is None:
        return None
    try:
        return round(float(x), digits)
    except (TypeError, ValueError):
        return None
