"""ML-5 — Hybrid Advisor admin + status API.

Read-only inspection + safe toggle of `ML_HYBRID_ENABLED`. Mode changes
are allowed between "advisory" and "paper_reduce". This endpoint does
NOT enable real-money execution; it cannot flip `ML_CAN_AFFECT_TRADES`.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.config import settings
from apps.api.src.db import SessionLocal
from apps.api.src.ml.shadow.hybrid_monitor import (
    compute_window_performance, load_latest_snapshot, persist_snapshot,
)
from apps.api.src.ml.shadow.hybrid_policy import HybridConfig
from apps.api.src.ml.shadow.promotion_guard import (
    PromotionThresholds, evaluate_promotion,
)
from apps.api.src.ml.shadow.runtime import load_latest_shadow_signal

router = APIRouter(prefix="/ml/hybrid", tags=["ml-hybrid"])

ALLOWED_MODES = {"advisory", "paper_reduce"}


def _s() -> Session:
    return SessionLocal()


@router.get("/status")
async def status() -> dict[str, Any]:
    """Return current config + latest model run health + recent activity."""
    cfg = HybridConfig.from_settings(settings)
    latest_run: dict[str, Any] | None = None
    recent: list[dict[str, Any]] = []
    with _s() as s:
        mr = s.execute(text("""
            SELECT id::text AS id, created_at, status,
                   calibration, baseline_comparison, metrics,
                   row_count, labeled_row_count, model_type
            FROM ml_model_run
            ORDER BY created_at DESC
            LIMIT 1
        """)).mappings().first()
        if mr is not None:
            latest_run = dict(mr)
        recs = s.execute(text("""
            SELECT id::text AS trade_id, entry_date, instrument, engine,
                   (alpha_rule_snapshot->>'ml_shadow_multiplier') AS mult,
                   (alpha_rule_snapshot->>'ml_hybrid_action')     AS action,
                   (alpha_rule_snapshot->>'ml_shadow_available')  AS avail,
                   (alpha_rule_snapshot->'ml_hybrid'->>'ml_hybrid_reason') AS reason
            FROM paper_trade_log
            WHERE alpha_rule_snapshot ? 'ml_hybrid'
            ORDER BY entry_date DESC, id DESC
            LIMIT 20
        """)).mappings().all()
        for r in recs:
            try:
                m = float(r.get("mult") or 1.0)
            except (TypeError, ValueError):
                m = 1.0
            recent.append({
                "trade_id":   r["trade_id"],
                "entry_date": str(r.get("entry_date")),
                "instrument": r.get("instrument"),
                "engine":     r.get("engine"),
                "multiplier": m,
                "action":     r.get("action"),
                "available":  (
                    str(r.get("avail") or "").lower() == "true"
                ),
                "reason":     r.get("reason"),
            })

    return {
        "config": {
            "enabled": cfg.enabled,
            "mode": cfg.mode,
            "min_confidence": cfg.min_confidence,
            "require_calibration": cfg.require_calibration,
            "require_baseline_beat": cfg.require_baseline_beat,
            "max_stale_days": cfg.max_stale_days,
            "min_data_confidence": cfg.min_data_confidence,
            "allow_block": cfg.allow_block,
            "min_multiplier": cfg.min_multiplier,
        },
        "ml_can_affect_trades": bool(
            getattr(settings, "ML_CAN_AFFECT_TRADES", False),
        ),
        "latest_model_run": latest_run,
        "recent_activity": recent,
    }


@router.post("/preview")
async def preview(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Preview hybrid evaluation for an ad-hoc candidate context."""
    from apps.api.src.ml.shadow.hybrid_policy import evaluate_hybrid

    symbol = str(body.get("symbol") or "SPY")
    engine = str(body.get("engine") or "B")
    as_of = body.get("as_of_date")
    data_quality = body.get("data_quality") or {}
    catalyst = body.get("catalyst") or {}
    similarity = body.get("similarity") or None
    context = body.get("context") or None
    cfg = HybridConfig.from_settings(settings)
    with _s() as s:
        sig = load_latest_shadow_signal(
            s, symbol=symbol, as_of_date=as_of, engine=engine,
            decision_context=context,
            max_stale_days=int(cfg.max_stale_days),
        )
    res = evaluate_hybrid(
        ml_signal=sig, cfg=cfg,
        current_paper_mult=1.0,
        data_quality=data_quality, catalyst=catalyst,
        similarity=similarity, context=context,
    )
    return {"signal": sig, **res.to_dict()}


@router.post("/toggle")
async def toggle(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Flip `ML_HYBRID_ENABLED` in-process. Restart resets to env value.

    Does NOT enable execution. Real-money gate is untouched.
    """
    val = body.get("enabled")
    if val is None:
        raise HTTPException(400, "enabled flag required")
    enabled = bool(val)
    setattr(settings, "ML_HYBRID_ENABLED", enabled)
    return {"ok": True, "enabled": enabled,
            "warning": "in-memory only; set ML_HYBRID_ENABLED in env for "
                        "permanent change"}


@router.post("/mode")
async def set_mode(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Switch advisory ↔ paper_reduce. Does not enable execution."""
    mode = str(body.get("mode") or "").lower()
    if mode not in ALLOWED_MODES:
        raise HTTPException(400,
                              f"mode must be one of {sorted(ALLOWED_MODES)}")
    setattr(settings, "ML_HYBRID_MODE", mode)
    return {"ok": True, "mode": mode,
            "warning": "in-memory only; set ML_HYBRID_MODE in env for "
                        "permanent change"}


# ---------------------------------------------------------------------------
# ML-6 — Performance monitor + promotion guard endpoints
# ---------------------------------------------------------------------------

@router.get("/performance/latest")
async def performance_latest() -> dict[str, Any]:
    """Return the most recent persisted snapshot across all windows."""
    with _s() as s:
        rows: dict[int, dict[str, Any]] = {}
        for w in (7, 14, 30):
            r = load_latest_snapshot(s, window_days=w)
            if r:
                rows[w] = r
    return {"present": bool(rows), "snapshots": rows}


@router.get("/performance")
async def performance(window_days: int = 14) -> dict[str, Any]:
    """Compute current-on-the-fly window performance. Read-only."""
    import datetime as dt
    w = int(window_days)
    if w not in (7, 14, 30):
        raise HTTPException(400, "window_days must be 7, 14, or 30")
    mode = str(getattr(settings, "ML_HYBRID_MODE", "advisory"))
    as_of = dt.date.today()
    with _s() as s:
        r = compute_window_performance(
            s, as_of=as_of, window_days=w, mode=mode,
        )
    return r.to_dict()


@router.get("/promotion-status")
async def promotion_status() -> dict[str, Any]:
    """Evaluate promotion guard against current windows + history."""
    import datetime as dt
    mode = str(getattr(settings, "ML_HYBRID_MODE", "advisory"))
    th = PromotionThresholds.from_settings(settings)
    as_of = dt.date.today()
    with _s() as s:
        results: dict[int, dict[str, Any]] = {}
        has_preds = False
        for w in (7, 14, 30):
            r = compute_window_performance(
                s, as_of=as_of, window_days=w, mode=mode,
            )
            results[w] = r.to_dict()
            if r.ml_advice_count > 0:
                has_preds = True
        # History for healthy-day count (7d window snapshots)
        from sqlalchemy import text
        recent = s.execute(text("""
            SELECT as_of_date, window_days, calibration_ece,
                   delta_sharpe_vs_deterministic, false_avoid_rate,
                   missed_winner_rate, ml_advice_count,
                   deterministic_trades, model_status
            FROM ml_hybrid_performance_snapshot
            WHERE window_days = 7
            ORDER BY as_of_date DESC
            LIMIT :l
        """), {"l": int(th.required_healthy_days * 2)}).mappings().all()
        decision = evaluate_promotion(
            current_mode=mode,
            window_results=results,
            recent_snapshots=[dict(r) for r in recent],
            thresholds=th,
            has_ml_predictions=has_preds,
        )
    return {
        "as_of": as_of.isoformat(),
        "current_mode": mode,
        "promotion": decision.to_dict(),
        "windows": results,
        "thresholds": {
            "min_advice": th.min_advice,
            "min_outcomes": th.min_outcomes,
            "max_ece": th.max_ece,
            "min_delta_sharpe": th.min_delta_sharpe,
            "max_false_avoid_rate": th.max_false_avoid_rate,
            "required_healthy_days": th.required_healthy_days,
        },
    }


@router.post("/performance/capture")
async def performance_capture(
    body: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    """Compute + persist snapshot for the specified window (or 7/14/30)."""
    import datetime as dt
    windows = body.get("window_days")
    ws = (
        [int(x) for x in windows] if isinstance(windows, (list, tuple))
        else [7, 14, 30]
    )
    as_of = dt.date.today()
    mode = str(getattr(settings, "ML_HYBRID_MODE", "advisory"))
    th = PromotionThresholds.from_settings(settings)

    persisted: list[str] = []
    results: dict[int, dict[str, Any]] = {}
    with _s() as s:
        has_preds = False
        for w in ws:
            r = compute_window_performance(
                s, as_of=as_of, window_days=w, mode=mode,
            )
            results[w] = r.to_dict()
            if r.ml_advice_count > 0:
                has_preds = True
        from sqlalchemy import text
        recent = s.execute(text("""
            SELECT as_of_date, window_days, calibration_ece,
                   delta_sharpe_vs_deterministic, false_avoid_rate,
                   missed_winner_rate, ml_advice_count,
                   deterministic_trades, model_status
            FROM ml_hybrid_performance_snapshot
            WHERE window_days = 7
            ORDER BY as_of_date DESC
            LIMIT :l
        """), {"l": int(th.required_healthy_days * 2)}).mappings().all()
        decision = evaluate_promotion(
            current_mode=mode,
            window_results=results,
            recent_snapshots=[dict(r) for r in recent],
            thresholds=th,
            has_ml_predictions=has_preds,
        )
        for w in ws:
            r_obj_dict = results[w]
            # Re-hydrate a minimal HybridWindowResult for persistence
            from apps.api.src.ml.shadow.hybrid_monitor import (
                HybridWindowResult,
            )
            hr = HybridWindowResult(
                window_days=int(r_obj_dict["window_days"]),
                as_of_date=dt.date.fromisoformat(r_obj_dict["as_of_date"]),
                mode=str(r_obj_dict["mode"]),
                ml_advice_count=int(r_obj_dict["ml_advice_count"]),
                ml_reduce_count=int(r_obj_dict["ml_reduce_count"]),
                ml_avoid_count=int(r_obj_dict["ml_avoid_count"]),
                ml_eligible_count=int(r_obj_dict["ml_eligible_count"]),
                ml_gated_count=int(r_obj_dict["ml_gated_count"]),
                deterministic_trades=int(r_obj_dict["deterministic_trades"]),
                ml_agreement_count=int(r_obj_dict["ml_agreement_count"]),
                ml_disagreement_count=int(
                    r_obj_dict["ml_disagreement_count"],
                ),
                avoided_loss_estimate=r_obj_dict["avoided_loss_estimate"],
                missed_winner_estimate=r_obj_dict["missed_winner_estimate"],
                false_avoid_rate=r_obj_dict["false_avoid_rate"],
                missed_winner_rate=r_obj_dict["missed_winner_rate"],
                good_warning_rate=r_obj_dict["good_warning_rate"],
                avg_return_when_ml_agreed=(
                    r_obj_dict["avg_return_when_ml_agreed"]
                ),
                avg_return_when_ml_warned=(
                    r_obj_dict["avg_return_when_ml_warned"]
                ),
                avg_return_when_ml_unavailable=(
                    r_obj_dict["avg_return_when_ml_unavailable"]
                ),
                delta_sharpe_vs_deterministic=(
                    r_obj_dict["delta_sharpe_vs_deterministic"]
                ),
                calibration_ece=r_obj_dict["calibration_ece"],
                brier_score=r_obj_dict["brier_score"],
                model_status=r_obj_dict["model_status"],
                blockers=list(r_obj_dict["blockers"] or []),
                recommendation=r_obj_dict["recommendation"] or "",
                metrics=dict(r_obj_dict["metrics"] or {}),
            )
            try:
                pid = persist_snapshot(
                    s, result=hr, promotion_status=decision.state,
                )
                persisted.append(pid)
            except Exception as e:
                from loguru import logger as _log
                _log.warning("persist failed w={}: {}", w, e)
    return {
        "persisted_ids": persisted,
        "promotion": decision.to_dict(),
        "windows": results,
    }
