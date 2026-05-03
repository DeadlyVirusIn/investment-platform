"""Engine B → B2 transition status API.

Read-only. Exposes:
  GET /api/engine-b/transition         current mode + metrics + verdict
  GET /api/engine-b/transition/timeline last N days of routed signals

NEVER changes mode. Mode flip is via env var only (operator-controlled).
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.config import settings
from apps.api.src.db import SessionLocal
from apps.api.src.research.engine_b_analytics import compute_all
from apps.api.src.research.engine_b_decision import (
    DEFAULT_THRESHOLDS_BY_FROM,
    evaluate as eval_decision,
)
from apps.api.src.research.engine_b_decision_writer import (
    upsert_decision_snapshot,
)
from apps.api.src.research.engine_b_promotion import (
    STATE_ORDER, evaluate as eval_promotion,
)


router = APIRouter(prefix="/engine-b", tags=["engine-b-transition"])


def _s() -> Session:
    return SessionLocal()


def _rows_for_strategy(s: Session, strategy: str,
                          since: date | None = None) -> list[dict]:
    sql = """
        SELECT as_of_date, signal,
               engine_b_signal, b2_signal, routed_signal,
               divergence_flag, divergence_outcome,
               fwd_return_1d, fwd_return_5d,
               regime_label, mode_at_decision
          FROM paper_shadow_log
         WHERE source_strategy = :s
    """
    params = {"s": strategy}
    if since is not None:
        sql += " AND as_of_date >= :since"
        params["since"] = since
    sql += " ORDER BY as_of_date ASC"
    return [dict(r) for r in
            s.execute(text(sql), params).mappings().all()]


def _engine_returns(rows: list[dict], who: str) -> list[float]:
    """Realized fwd_return_1d if `who` was LONG, else 0."""
    out: list[float] = []
    for r in rows:
        sig = r.get(f"{who}_signal")
        ret = r.get("fwd_return_1d")
        if ret is None:
            continue
        if sig == "LONG":
            out.append(float(ret))
        else:
            out.append(0.0)
    return out


def _routed_returns(rows: list[dict]) -> list[float]:
    out: list[float] = []
    for r in rows:
        sig = r.get("routed_signal")
        ret = r.get("fwd_return_1d")
        if ret is None:
            continue
        out.append(float(ret) if sig == "LONG" else 0.0)
    return out


def _divergence_outcomes(rows: list[dict]) -> list[float]:
    return [float(r["divergence_outcome"])
            for r in rows
            if r.get("divergence_flag") and
                r.get("divergence_outcome") is not None]


@router.get("/transition")
async def transition_status(
    strategy: str = "tsmom_60_no_stress",
    days: int = 365,
) -> dict[str, Any]:
    cutoff = date.today() - timedelta(days=days + 7)
    with _s() as s:
        rows = _rows_for_strategy(s, strategy, since=cutoff)

    mode = (settings.ENGINE_B_MODE or "LEGACY").upper()
    n_total = len(rows)

    # Counts
    n_div = sum(1 for r in rows if r.get("divergence_flag"))
    n_b2 = sum(1 for r in rows if r.get("routed_signal") == "LONG")

    b_rets = _engine_returns(rows, "engine_b")
    b2_rets = _engine_returns(rows, "b2")
    routed_rets = _routed_returns(rows)
    div_outs = _divergence_outcomes(rows)

    verdict = eval_promotion(
        current_state=mode,
        n_observations=n_total,
        b_returns=b_rets,
        b2_returns=b2_rets,
        routed_returns=routed_rets,
        divergence_outcomes=div_outs,
        min_shadow_days=int(settings.ENGINE_B_MIN_SHADOW_DAYS),
        sharpe_floor=float(settings.ENGINE_B_KILL_SHARPE),
        dd_floor_pct=float(settings.ENGINE_B_KILL_DD_PCT),
        operator_approval=bool(settings.ENGINE_B_OPERATOR_APPROVAL),
    )

    # Quick metrics for display
    def _summarize(label, rets):
        if not rets:
            return {"label": label, "n": 0, "sharpe": None,
                    "cumulative_pct": None}
        eq = 1.0
        for r in rets: eq *= 1 + r
        return {
            "label": label, "n": len(rets),
            "cumulative_pct": round((eq - 1) * 100, 4),
            "mean_bps": round((sum(rets) / len(rets)) * 1e4, 2),
        }

    metrics = {
        "engine_b": _summarize("engine_b", b_rets),
        "b2":       _summarize("b2", b2_rets),
        "routed":   _summarize("routed", routed_rets),
    }

    # Divergence stats: mean B2-advantage, hit rate, count
    div_stats = None
    if div_outs:
        # divergence_outcome is "B - B2"; we want B2 advantage = negate
        adv = [-d for d in div_outs]
        eq = 1.0
        for a in adv: eq *= 1 + a
        div_stats = {
            "n_divergent_days": int(len(div_outs)),
            "b2_won_days": int(sum(1 for a in adv if a > 0)),
            "b2_lost_days": int(sum(1 for a in adv if a < 0)),
            "tied_days": int(sum(1 for a in adv if a == 0)),
            "mean_b2_advantage_bps": round((sum(adv) / len(adv)) * 1e4, 2),
            "cumulative_b2_advantage_pct":
                round((eq - 1) * 100, 4),
        }

    return {
        "current_mode": mode,
        "state_order": list(STATE_ORDER),
        "operator_approval": bool(settings.ENGINE_B_OPERATOR_APPROVAL),
        "n_total_days": n_total,
        "n_divergent_days": n_div,
        "n_b2_routed_long_days": n_b2,
        "metrics": metrics,
        "divergence_stats": div_stats,
        "verdict": verdict.to_dict(),
        "advisory_only": True,
        "auto_promote": False,
        "execution_changed_under_current_mode":
            mode in ("PARTIAL_B2_25", "PARTIAL_B2_50",
                       "PARTIAL_B2_75", "FULL_B2"),
    }


@router.get("/analytics")
async def analytics(
    strategy: str = "tsmom_60_no_stress",
    days: int = 365,
) -> dict[str, Any]:
    """Full analytics block: divergence, tail risk, transition zones,
    regime consistency, stability split, readiness score."""
    cutoff = date.today() - timedelta(days=days + 7)
    with _s() as s:
        rows = _rows_for_strategy(s, strategy, since=cutoff)
    return {"strategy": strategy, **compute_all(rows)}


@router.get("/decision")
async def decision(
    strategy: str = "tsmom_60_no_stress",
    days: int = 365,
    persist: bool = True,
) -> dict[str, Any]:
    """End-to-end decision evaluation under current ENGINE_B_MODE.

    Returns 9 hard gates, confidence score (0-100), 3-window stability,
    kill switch state, and recommendation. If `persist=true`, an
    idempotent snapshot row is written to engine_b_decision_snapshot
    keyed on (as_of_date, current_state).
    """
    cutoff = date.today() - timedelta(days=days + 7)
    mode = (settings.ENGINE_B_MODE or "LEGACY").upper()
    op_approval = bool(settings.ENGINE_B_OPERATOR_APPROVAL)
    with _s() as s:
        rows = _rows_for_strategy(s, strategy, since=cutoff)
        # Load previous pause states (chronological, oldest -> newest)
        prior_states = s.execute(text("""
            SELECT as_of_date,
                   COALESCE(
                       (promotion_pause ->> 'active')::boolean, FALSE
                   ) AS pause_active
              FROM engine_b_decision_snapshot
             WHERE current_state = :mode
               AND as_of_date < CURRENT_DATE
             ORDER BY as_of_date ASC
             LIMIT 10
        """), {"mode": mode}).mappings().all()
        previous_pause_states = [bool(r["pause_active"]) for r in prior_states]
        verdict = eval_decision(
            rows=rows,
            current_state=mode,
            operator_approval=op_approval,
            previous_pause_states=previous_pause_states,
        )
        if persist and rows:
            try:
                last = rows[-1]["as_of_date"]
                # Convert string/date to date if needed
                if hasattr(last, "isoformat") and not isinstance(last, date):
                    last = date.fromisoformat(last.isoformat()[:10])
                upsert_decision_snapshot(
                    s, as_of_date=last, decision=verdict,
                )
                s.commit()
            except Exception as e:
                # Don't fail the API on snapshot persistence error
                s.rollback()
                _ = e
    payload = verdict.to_dict()
    payload["strategy"] = strategy
    payload["thresholds_used"] = DEFAULT_THRESHOLDS_BY_FROM.get(
        mode, DEFAULT_THRESHOLDS_BY_FROM["LEGACY"])
    payload["execution_changed_under_current_mode"] = mode in (
        "PARTIAL_B2_25", "PARTIAL_B2_50", "PARTIAL_B2_75", "FULL_B2")
    return payload


@router.get("/decision/history")
async def decision_history(days: int = 90) -> dict[str, Any]:
    """Recent decision snapshots from engine_b_decision_snapshot."""
    cutoff = date.today() - timedelta(days=days + 7)
    with _s() as s:
        rows = s.execute(text("""
            SELECT as_of_date, current_state, recommended_state, action,
                   label, score, operator_approval, kill_switch_triggered,
                   kill_switch_reason, n_observations, failed_gates, note,
                   created_at
              FROM engine_b_decision_snapshot
             WHERE as_of_date >= :cutoff
             ORDER BY as_of_date DESC
        """), {"cutoff": cutoff}).mappings().all()
    return {
        "n": len(rows),
        "snapshots": [
            {
                "as_of_date": (r["as_of_date"].isoformat()
                                  if hasattr(r["as_of_date"], "isoformat")
                                  else str(r["as_of_date"])),
                "current_state": r["current_state"],
                "recommended_state": r["recommended_state"],
                "action": r["action"], "label": r["label"],
                "score": int(r["score"]),
                "operator_approval": bool(r["operator_approval"]),
                "kill_switch_triggered":
                    bool(r["kill_switch_triggered"]),
                "kill_switch_reason": r["kill_switch_reason"],
                "n_observations": int(r["n_observations"]),
                "failed_gates": r["failed_gates"],
                "note": r["note"],
            } for r in rows
        ],
    }


@router.get("/transition/timeline")
async def timeline(
    strategy: str = "tsmom_60_no_stress",
    days: int = 60,
) -> dict[str, Any]:
    cutoff = date.today() - timedelta(days=days + 7)
    with _s() as s:
        rows = _rows_for_strategy(s, strategy, since=cutoff)
    out = [
        {
            "date": (r["as_of_date"].isoformat()
                       if hasattr(r["as_of_date"], "isoformat")
                       else str(r["as_of_date"])),
            "engine_b_signal": r.get("engine_b_signal"),
            "b2_signal": r.get("b2_signal"),
            "routed_signal": r.get("routed_signal"),
            "divergence_flag": bool(r.get("divergence_flag")),
            "regime_label": r.get("regime_label"),
            "fwd_return_1d": (float(r["fwd_return_1d"])
                                  if r.get("fwd_return_1d") is not None
                                  else None),
            "divergence_outcome": (float(r["divergence_outcome"])
                                       if r.get("divergence_outcome") is not None
                                       else None),
            "mode": r.get("mode_at_decision"),
        }
        for r in rows
    ]
    return {"strategy": strategy, "n": len(out), "timeline": out}
