"""ML-5 — paper-side runtime loader for shadow predictions.

Fail-soft: any DB/parse error returns `available=False`. Never raises
into the paper pipeline. Never mutates state. Read-only.

Selects the latest `ml_shadow_prediction` for (symbol, as_of_date)
joined to its `ml_model_run` to expose calibration + baseline health.
A stale, uncalibrated, or below-baseline model still returns a payload,
but `available=False` — the policy layer decides what to do.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session


# Only these statuses are eligible to contribute a multiplier.
ELIGIBLE_STATUSES = {"SHADOW_OUTPERFORMING", "TRAINED_SHADOW"}

# Advisory mode tolerates TRAINED_SHADOW (baseline not yet beaten).
ADVISORY_ELIGIBLE_STATUSES = {
    "SHADOW_OUTPERFORMING", "TRAINED_SHADOW",
}

# paper_reduce requires beating baseline unless overridden.
PAPER_REDUCE_ELIGIBLE_STATUSES = {"SHADOW_OUTPERFORMING"}


def load_latest_shadow_signal(
    session: Session, *,
    symbol: str,
    as_of_date: dt.date | str | None,
    engine: str,
    decision_context: dict[str, Any] | None = None,
    max_stale_days: int = 7,
) -> dict[str, Any]:
    """Return dict with `available` + ML signal + run health.

    `available=True` means downstream policy may apply a non-1.0 multiplier.
    `available=False` always forces multiplier 1.0 at the policy layer.
    """
    out: dict[str, Any] = _blank(reason="not_loaded")
    try:
        asof = _as_date(as_of_date)
        row = _load_latest_prediction(session, symbol=symbol, asof=asof)
        if row is None:
            out["reason_codes"] = ["no_prediction"]
            return out
        run = _load_model_run(session, run_id=str(row["model_run_id"]))
        if run is None:
            out["reason_codes"] = ["no_model_run"]
            return out

        # --- staleness (by model_run creation date) ---
        created_at = run.get("created_at")
        stale_days = _days_since(created_at)
        out["model_age_days"] = stale_days
        out["model_run_id"] = str(run.get("id"))
        out["status"] = str(run.get("status") or "")

        # --- calibration payload ---
        cal = run.get("calibration") or {}
        cal_poor = bool(cal.get("poor_calibration", False))
        out["calibration_ok"] = not cal_poor
        out["calibration"] = dict(cal) if isinstance(cal, dict) else None

        # --- baseline comparison ---
        cmp = run.get("baseline_comparison") or {}
        winner = str(cmp.get("winner") or "").lower()
        delta = cmp.get("delta_sharpe")
        out["baseline_winner"] = winner
        out["baseline_delta"] = (
            float(delta) if isinstance(delta, (int, float)) else None
        )
        out["beats_baseline"] = winner == "ml"

        # --- prediction details ---
        ml_action = str(row.get("ml_action") or "").lower() or None
        out["ml_score"] = _num(row.get("ml_score"))
        out["ml_confidence"] = _num(row.get("ml_confidence"))
        out["ml_action"] = ml_action
        rc = row.get("ml_reason_codes") or []
        out["reason_codes"] = (
            list(rc) if isinstance(rc, (list, tuple)) else []
        )
        out["engine"] = engine
        out["symbol"] = symbol
        out["as_of_date"] = asof.isoformat() if asof else None

        # --- eligibility roll-up ---
        status_ok = out["status"] in ELIGIBLE_STATUSES
        fresh_ok = (
            stale_days is not None and stale_days <= int(max_stale_days)
        )
        out["stale"] = not fresh_ok if stale_days is not None else True
        out["available"] = bool(
            status_ok and fresh_ok and ml_action in {
                "accept", "reduce", "avoid", "needs_more_data",
            },
        )
        return out
    except Exception as e:
        logger.warning("ml_runtime: shadow load failed: {}", e)
        return _blank(reason=f"load_error:{type(e).__name__}")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _blank(*, reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "ml_score": None,
        "ml_confidence": None,
        "ml_action": None,
        "model_run_id": None,
        "status": None,
        "calibration_ok": False,
        "baseline_delta": None,
        "baseline_winner": None,
        "beats_baseline": False,
        "stale": None,
        "model_age_days": None,
        "reason_codes": [reason],
        "source": "ml_shadow_prediction",
    }


def _as_date(v: Any) -> dt.date | None:
    if v is None:
        return None
    if isinstance(v, dt.date) and not isinstance(v, dt.datetime):
        return v
    if isinstance(v, dt.datetime):
        return v.date()
    try:
        return dt.date.fromisoformat(str(v))
    except ValueError:
        return None


def _num(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _days_since(created_at: Any) -> int | None:
    if created_at is None:
        return None
    try:
        now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
        if isinstance(created_at, dt.datetime):
            d = created_at
        else:
            d = dt.datetime.fromisoformat(str(created_at))
        if d.tzinfo is not None:
            d = d.replace(tzinfo=None)
        delta = now - d
        return int(delta.days)
    except Exception:
        return None


def _load_latest_prediction(
    session: Session, *, symbol: str, asof: dt.date | None,
) -> dict[str, Any] | None:
    """Newest prediction for this symbol. If `asof` given, prefer same date;
    fall back to most-recent regardless of date. Read-only."""
    if asof is not None:
        row = session.execute(text("""
            SELECT id::text                 AS id,
                   model_run_id::text       AS model_run_id,
                   symbol, as_of_date, decision_ts, source_type,
                   engine, original_decision, engine_confidence,
                   ml_score, ml_confidence, ml_action,
                   ml_reason_codes
            FROM ml_shadow_prediction
            WHERE symbol = :sym AND as_of_date = :d
            ORDER BY created_at DESC
            LIMIT 1
        """), {"sym": symbol, "d": asof}).mappings().first()
        if row is not None:
            return dict(row)
    row = session.execute(text("""
        SELECT id::text                 AS id,
               model_run_id::text       AS model_run_id,
               symbol, as_of_date, decision_ts, source_type,
               engine, original_decision, engine_confidence,
               ml_score, ml_confidence, ml_action,
               ml_reason_codes
        FROM ml_shadow_prediction
        WHERE symbol = :sym
        ORDER BY created_at DESC
        LIMIT 1
    """), {"sym": symbol}).mappings().first()
    return dict(row) if row else None


def _load_model_run(
    session: Session, *, run_id: str,
) -> dict[str, Any] | None:
    row = session.execute(text("""
        SELECT id::text AS id, created_at, model_type, status,
               row_count, labeled_row_count,
               metrics, baseline_comparison, calibration,
               leakage_report, feature_health, blockers
        FROM ml_model_run
        WHERE id = :id
    """), {"id": run_id}).mappings().first()
    return dict(row) if row else None
