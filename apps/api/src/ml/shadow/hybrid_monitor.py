"""ML-6 — Hybrid Performance Monitor.

Computes rolling-window metrics over closed paper trades. Joins
`paper_trade_log` → `ml_shadow_prediction` (when present) to estimate
whether ML advice would have improved paper outcomes.

Pure read + pure math. Never mutates decisions or engine state.

Definitions:
  • ml_advice_count        — trades where ML returned a valid action
  • ml_reduce_count        — subset with ml_action in {reduce}
  • ml_avoid_count         — subset with ml_action in {avoid}
  • avoided_loss_estimate  — sum of |net_ret| over ML-warned trades that
                              closed negative (what ML would have saved)
  • missed_winner_estimate — sum of net_ret over ML-warned trades that
                              closed positive (what ML would have missed)
  • false_avoid_rate       — missed_winners / ml_warnings
  • good_warning_rate      — avoided_losses / ml_warnings
  • missed_winner_rate     — missed_winners / ml_warnings
  • avg_return_when_agreed    — mean net_ret when ML action = 'accept'
  • avg_return_when_warned    — mean net_ret when ML action ∈ {reduce, avoid}
  • avg_return_when_unavail   — mean net_ret when ML unavailable/gated
  • delta_sharpe_vs_deterministic — Sharpe(no ML reduction) − Sharpe(with
                                    ML reduction applied counterfactually)
"""

from __future__ import annotations

import datetime as dt
import math
import statistics
from dataclasses import dataclass, field
from typing import Any

from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session


WARN_ACTIONS = {"reduce", "avoid", "reduce_size", "would_block"}
AGREE_ACTIONS = {"accept", "none"}


@dataclass
class HybridWindowResult:
    window_days: int
    as_of_date: dt.date
    mode: str
    ml_advice_count: int = 0
    ml_reduce_count: int = 0
    ml_avoid_count: int = 0
    ml_eligible_count: int = 0
    ml_gated_count: int = 0
    deterministic_trades: int = 0
    ml_agreement_count: int = 0
    ml_disagreement_count: int = 0
    avoided_loss_estimate: float | None = None
    missed_winner_estimate: float | None = None
    false_avoid_rate: float | None = None
    missed_winner_rate: float | None = None
    good_warning_rate: float | None = None
    avg_return_when_ml_agreed: float | None = None
    avg_return_when_ml_warned: float | None = None
    avg_return_when_ml_unavailable: float | None = None
    delta_sharpe_vs_deterministic: float | None = None
    calibration_ece: float | None = None
    brier_score: float | None = None
    model_status: str | None = None
    blockers: list[str] = field(default_factory=list)
    recommendation: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        def _r(v: float | None, n: int = 4) -> float | None:
            return None if v is None else round(float(v), n)
        return {
            "window_days": self.window_days,
            "as_of_date":  self.as_of_date.isoformat(),
            "mode":        self.mode,
            "ml_advice_count":      self.ml_advice_count,
            "ml_reduce_count":      self.ml_reduce_count,
            "ml_avoid_count":       self.ml_avoid_count,
            "ml_eligible_count":    self.ml_eligible_count,
            "ml_gated_count":       self.ml_gated_count,
            "deterministic_trades": self.deterministic_trades,
            "ml_agreement_count":    self.ml_agreement_count,
            "ml_disagreement_count": self.ml_disagreement_count,
            "avoided_loss_estimate":       _r(self.avoided_loss_estimate),
            "missed_winner_estimate":      _r(self.missed_winner_estimate),
            "false_avoid_rate":            _r(self.false_avoid_rate),
            "missed_winner_rate":          _r(self.missed_winner_rate),
            "good_warning_rate":           _r(self.good_warning_rate),
            "avg_return_when_ml_agreed":   _r(self.avg_return_when_ml_agreed),
            "avg_return_when_ml_warned":   _r(self.avg_return_when_ml_warned),
            "avg_return_when_ml_unavailable":
                _r(self.avg_return_when_ml_unavailable),
            "delta_sharpe_vs_deterministic":
                _r(self.delta_sharpe_vs_deterministic),
            "calibration_ece":  _r(self.calibration_ece, 6),
            "brier_score":      _r(self.brier_score, 6),
            "model_status":     self.model_status,
            "blockers":         list(self.blockers),
            "recommendation":   self.recommendation,
            "metrics":          dict(self.metrics),
        }


# ---------------------------------------------------------------------------
# Row loader
# ---------------------------------------------------------------------------

@dataclass
class _TradeRow:
    entry_date: dt.date
    exit_date: dt.date | None
    status: str
    engine: str
    instrument: str
    position_size_pct: float
    net_ret_pct: float | None
    exploratory: bool
    # From alpha_rule_snapshot jsonb
    ml_available: bool
    ml_action: str | None
    ml_multiplier: float
    # Effective paper multiplier actually used at entry
    paper_size_multiplier: float


def _load_trades(
    session: Session, *,
    as_of: dt.date, window_days: int,
) -> list[_TradeRow]:
    start = as_of - dt.timedelta(days=int(window_days))
    rows = session.execute(text("""
        SELECT entry_date, exit_date, status, engine, instrument,
               position_size_pct, net_ret_pct, exploratory_paper,
               (alpha_rule_snapshot->>'ml_shadow_available')  AS ml_avail,
               (alpha_rule_snapshot->>'ml_hybrid_action')     AS ml_action,
               (alpha_rule_snapshot->>'ml_shadow_multiplier') AS ml_mult,
               (alpha_rule_snapshot->>'paper_size_multiplier') AS psize
        FROM paper_trade_log
        WHERE entry_date >= :start AND entry_date <= :asof
    """), {"start": start, "asof": as_of}).mappings().all()

    out: list[_TradeRow] = []
    for r in rows:
        try:
            ml_mult = float(r.get("ml_mult") or 1.0)
        except (TypeError, ValueError):
            ml_mult = 1.0
        try:
            psize = float(r.get("psize") or 1.0)
        except (TypeError, ValueError):
            psize = 1.0
        out.append(_TradeRow(
            entry_date=r["entry_date"], exit_date=r.get("exit_date"),
            status=str(r.get("status") or ""),
            engine=str(r.get("engine") or ""),
            instrument=str(r.get("instrument") or ""),
            position_size_pct=float(r.get("position_size_pct") or 0.0),
            net_ret_pct=(
                float(r["net_ret_pct"])
                if r.get("net_ret_pct") is not None else None
            ),
            exploratory=bool(r.get("exploratory_paper")),
            ml_available=(
                str(r.get("ml_avail") or "").lower() == "true"
            ),
            ml_action=(r.get("ml_action") or "").lower() or None,
            ml_multiplier=ml_mult,
            paper_size_multiplier=psize,
        ))
    return out


def _latest_model_health(session: Session) -> dict[str, Any]:
    row = session.execute(text("""
        SELECT id::text AS id, created_at, status,
               calibration, baseline_comparison, metrics
        FROM ml_model_run
        ORDER BY created_at DESC LIMIT 1
    """)).mappings().first()
    if row is None:
        return {"present": False}
    cal = row.get("calibration") or {}
    cmp = row.get("baseline_comparison") or {}
    return {
        "present": True,
        "id": row.get("id"),
        "status": row.get("status"),
        "ece": (float(cal.get("ece"))
                 if isinstance(cal.get("ece"), (int, float)) else None),
        "brier": (float(cal.get("brier"))
                   if isinstance(cal.get("brier"), (int, float)) else None),
        "poor_calibration": bool(cal.get("poor_calibration", False)),
        "baseline_winner": cmp.get("winner"),
        "delta_sharpe": (
            float(cmp.get("delta_sharpe"))
            if isinstance(cmp.get("delta_sharpe"), (int, float)) else None
        ),
    }


# ---------------------------------------------------------------------------
# Math
# ---------------------------------------------------------------------------

def _safe_mean(xs: list[float]) -> float | None:
    return (sum(xs) / len(xs)) if xs else None


def _safe_sharpe(xs: list[float]) -> float | None:
    """Sharpe-proxy: mean / stdev (no annualization, same unit as inputs)."""
    if len(xs) < 2:
        return None
    mu = _safe_mean(xs) or 0.0
    try:
        sd = statistics.stdev(xs)
    except statistics.StatisticsError:
        return None
    if sd == 0 or not math.isfinite(sd):
        return None
    return mu / sd


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

def compute_window_performance(
    session: Session, *,
    as_of: dt.date, window_days: int, mode: str,
) -> HybridWindowResult:
    """Compute hybrid performance over a rolling window ending `as_of`."""
    trades = _load_trades(session, as_of=as_of, window_days=window_days)
    model = _latest_model_health(session)

    # Classify
    closed_with_ret = [
        t for t in trades
        if t.status == "closed" and t.net_ret_pct is not None
    ]
    with_ml = [t for t in closed_with_ret if t.ml_available
                and t.ml_action is not None]
    ml_warned = [t for t in with_ml if t.ml_action in WARN_ACTIONS]
    ml_agreed = [t for t in with_ml if t.ml_action in AGREE_ACTIONS]
    ml_reduce = [t for t in with_ml if t.ml_action in {"reduce", "reduce_size"}]
    ml_avoid  = [t for t in with_ml if t.ml_action in {"avoid", "would_block"}]
    ml_gated  = [t for t in closed_with_ret if not t.ml_available]

    # Warnings-hit analysis
    warned_losses = [t for t in ml_warned
                      if (t.net_ret_pct or 0.0) < 0]
    warned_wins   = [t for t in ml_warned
                      if (t.net_ret_pct or 0.0) > 0]

    avoided_loss = sum(abs(t.net_ret_pct or 0.0) for t in warned_losses)
    missed_wins  = sum(max(0.0, t.net_ret_pct or 0.0) for t in warned_wins)

    n_warn = len(ml_warned)
    fa_rate = (len(warned_wins) / n_warn) if n_warn else None
    gw_rate = (len(warned_losses) / n_warn) if n_warn else None
    mw_rate = fa_rate   # alias per spec

    avg_agreed = _safe_mean(
        [t.net_ret_pct for t in ml_agreed if t.net_ret_pct is not None],
    )
    avg_warned = _safe_mean(
        [t.net_ret_pct for t in ml_warned if t.net_ret_pct is not None],
    )
    avg_unavail = _safe_mean(
        [t.net_ret_pct for t in ml_gated if t.net_ret_pct is not None],
    )

    # Sharpe proxy: det stack (all trades) vs ML-applied counterfactual.
    det_returns = [t.net_ret_pct for t in closed_with_ret
                    if t.net_ret_pct is not None]
    # Counterfactual: apply ML multiplier to each trade's return scaled by
    # its advice. If ML warned → scale return by multiplier; else keep.
    cf_returns: list[float] = []
    for t in closed_with_ret:
        r = t.net_ret_pct or 0.0
        if t.ml_available and t.ml_action in WARN_ACTIONS:
            cf_returns.append(r * float(t.ml_multiplier or 1.0))
        else:
            cf_returns.append(r)
    det_sh = _safe_sharpe(det_returns)
    cf_sh  = _safe_sharpe(cf_returns)
    delta_sh = (
        (cf_sh or 0.0) - (det_sh or 0.0)
        if det_sh is not None and cf_sh is not None else None
    )

    # Agreement: engine fired (either directly or via paper_size>0) AND ML
    # accepted → agreement; engine fired AND ML warned → disagreement.
    agreements = sum(
        1 for t in with_ml
        if t.paper_size_multiplier > 0 and t.ml_action in AGREE_ACTIONS
    )
    disagreements = sum(
        1 for t in with_ml
        if t.paper_size_multiplier > 0 and t.ml_action in WARN_ACTIONS
    )

    # Small-sample rules
    blockers: list[str] = []
    if len(with_ml) < 20:
        blockers.append("insufficient_advice")
    if len(closed_with_ret) < 20:
        blockers.append("insufficient_outcomes")
    if model.get("poor_calibration"):
        blockers.append("poor_calibration")
    if model.get("baseline_winner") != "ml":
        blockers.append("below_baseline")
    if model.get("status") not in {
        "SHADOW_OUTPERFORMING", "TRAINED_SHADOW"
    }:
        blockers.append(f"bad_model_status:{model.get('status')}")

    res = HybridWindowResult(
        window_days=window_days,
        as_of_date=as_of,
        mode=mode,
        ml_advice_count=len(with_ml),
        ml_reduce_count=len(ml_reduce),
        ml_avoid_count=len(ml_avoid),
        ml_eligible_count=len(with_ml),
        ml_gated_count=len(ml_gated),
        deterministic_trades=len(closed_with_ret),
        ml_agreement_count=agreements,
        ml_disagreement_count=disagreements,
        avoided_loss_estimate=(avoided_loss if n_warn else None),
        missed_winner_estimate=(missed_wins if n_warn else None),
        false_avoid_rate=fa_rate,
        missed_winner_rate=mw_rate,
        good_warning_rate=gw_rate,
        avg_return_when_ml_agreed=avg_agreed,
        avg_return_when_ml_warned=avg_warned,
        avg_return_when_ml_unavailable=avg_unavail,
        delta_sharpe_vs_deterministic=delta_sh,
        calibration_ece=model.get("ece"),
        brier_score=model.get("brier"),
        model_status=model.get("status"),
        blockers=blockers,
        metrics={
            "warned_losses": len(warned_losses),
            "warned_wins":   len(warned_wins),
            "det_sharpe_proxy": det_sh,
            "cf_sharpe_proxy":  cf_sh,
            "model_id":     model.get("id"),
            "baseline_winner": model.get("baseline_winner"),
            "delta_sharpe_model": model.get("delta_sharpe"),
        },
    )
    res.recommendation = _recommendation(res, mode)
    return res


def _recommendation(r: HybridWindowResult, mode: str) -> str:
    if "insufficient_advice" in r.blockers:
        return ("Advisory needs more ML predictions before any claim can be "
                 "made. Keep advisory mode.")
    if "insufficient_outcomes" in r.blockers:
        return ("Not enough closed outcomes yet. Keep advisory mode until "
                 "at least 20 closed trades accumulate.")
    if "poor_calibration" in r.blockers:
        return "Model calibration is poor. Keep advisory mode; do not reduce."
    if "below_baseline" in r.blockers:
        return "Model is below baseline. Keep advisory mode."
    if any(b.startswith("bad_model_status") for b in r.blockers):
        return "Model not eligible. Keep advisory mode."
    if (r.false_avoid_rate or 0.0) > 0.5:
        return ("ML warns too often on winners. Keep advisory mode; review "
                 "feature quality.")
    if mode == "advisory":
        if (r.delta_sharpe_vs_deterministic or 0.0) > 0:
            return ("Advisory healthy. Consider paper_reduce trial after 7+ "
                     "healthy days with operator approval.")
        return "Advisory healthy but ML-applied Sharpe delta non-positive."
    if mode == "paper_reduce":
        if (r.delta_sharpe_vs_deterministic or 0.0) >= 0:
            return "paper_reduce running cleanly. Keep monitoring."
        return ("paper_reduce showing negative Sharpe delta. Revert to "
                 "advisory and investigate.")
    return "Insufficient evidence."


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def persist_snapshot(
    session: Session, *, result: HybridWindowResult, promotion_status: str,
) -> str:
    """Insert a row into ml_hybrid_performance_snapshot. Returns UUID."""
    import json
    row = session.execute(text("""
        INSERT INTO ml_hybrid_performance_snapshot
          (as_of_date, window_days, mode,
           ml_advice_count, ml_reduce_count, ml_avoid_count,
           ml_eligible_count, ml_gated_count, deterministic_trades,
           ml_agreement_count, ml_disagreement_count,
           avoided_loss_estimate, missed_winner_estimate,
           false_avoid_rate, missed_winner_rate, good_warning_rate,
           avg_return_when_ml_agreed, avg_return_when_ml_warned,
           avg_return_when_ml_unavailable,
           delta_sharpe_vs_deterministic,
           calibration_ece, brier_score, model_status,
           promotion_status, blockers, recommendation, metrics)
        VALUES
          (:asof, :wd, :mode,
           :ac, :rc, :vc,
           :elg, :gt, :det,
           :ag, :dis,
           :al, :mw,
           :fa, :mwr, :gw,
           :aag, :awn, :auv,
           :dsh,
           :ece, :br, :st,
           :prom, CAST(:blk AS jsonb), :rec, CAST(:met AS jsonb))
        RETURNING id
    """), {
        "asof": result.as_of_date, "wd": int(result.window_days),
        "mode": result.mode,
        "ac": int(result.ml_advice_count),
        "rc": int(result.ml_reduce_count),
        "vc": int(result.ml_avoid_count),
        "elg": int(result.ml_eligible_count),
        "gt": int(result.ml_gated_count),
        "det": int(result.deterministic_trades),
        "ag": int(result.ml_agreement_count),
        "dis": int(result.ml_disagreement_count),
        "al": result.avoided_loss_estimate,
        "mw": result.missed_winner_estimate,
        "fa": result.false_avoid_rate,
        "mwr": result.missed_winner_rate,
        "gw": result.good_warning_rate,
        "aag": result.avg_return_when_ml_agreed,
        "awn": result.avg_return_when_ml_warned,
        "auv": result.avg_return_when_ml_unavailable,
        "dsh": result.delta_sharpe_vs_deterministic,
        "ece": result.calibration_ece,
        "br": result.brier_score,
        "st": result.model_status,
        "prom": promotion_status,
        "blk": json.dumps(result.blockers),
        "rec": result.recommendation,
        "met": json.dumps(result.metrics, default=str),
    }).fetchone()
    session.commit()
    return str(row[0])


def load_latest_snapshot(
    session: Session, *, window_days: int | None = None,
) -> dict[str, Any] | None:
    try:
        if window_days is None:
            row = session.execute(text("""
                SELECT * FROM ml_hybrid_performance_snapshot
                ORDER BY created_at DESC LIMIT 1
            """)).mappings().first()
        else:
            row = session.execute(text("""
                SELECT * FROM ml_hybrid_performance_snapshot
                WHERE window_days = :w
                ORDER BY created_at DESC LIMIT 1
            """), {"w": int(window_days)}).mappings().first()
    except Exception as e:
        logger.warning("hybrid_monitor: latest snapshot read failed: {}", e)
        return None
    return dict(row) if row else None
