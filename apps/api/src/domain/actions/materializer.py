"""Materialize action_item rows from candidate_idea + portfolio state.

Called after generate_stock_candidates writes candidate_idea for a given
as_of. Kinds derive from (action, is_held) combination:

    candidate.action   is_held   → action kind
    Buy                  False   → BUY
    Buy                  True    → (skip; reaffirm not actionable)
    Trim                 True    → TRIM
    Trim                 False   → (skip; can't trim what you don't own)
    Sell                 True    → EXIT
    Sell                 False   → (skip)
    Hold                 any     → (skip)

Exit-rule events (max_holding_days, stop_loss, regime=downtrend) also emit
EXIT actions with origin="exit_rules".

Dedup: unique index on (as_of_date, asset_id, kind, origin). Upsert pattern.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from apps.api.src.db import SessionLocal
from apps.api.src.db.models import (
    ActionItem,
    Asset,
    CandidateIdea,
    PaperPortfolio,
    PaperPosition,
    RegimeSnapshot,
)
from apps.api.src.domain.actions.priority import (
    compute_priority,
    priority_tier,
)
from apps.api.src.domain.confidence_calibration.integrator import (
    BatchResult,
    calibrate_batch,
)
from apps.api.src.domain.confidence_calibration.loader import (
    load_calibration_inputs,
)
from apps.api.src.domain.confidence_calibration.policy import derive_factors
from apps.api.src.domain.stock_engine.scoring import MODEL_VERSION as ENGINE_MODEL_VERSION

URGENCY_BY_KIND: dict[str, str] = {
    "BUY": "today",
    "TRIM": "today",
    "EXIT": "today",
    "RESOLVE_ALERT": "now",
}

# Default economic impact when we can't derive it from sizing
DEFAULT_IMPACT_PCT = 0.05
DEFAULT_SIZING_PCT = Decimal("0.10")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _kind_from(action: str | None, is_held: bool) -> str | None:
    if action is None:
        return None
    if action == "Buy" and not is_held:
        return "BUY"
    if action == "Trim" and is_held:
        return "TRIM"
    if action == "Sell" and is_held:
        return "EXIT"
    return None


def _urgency_for(kind: str, exit_reason: str | None = None) -> str:
    if kind == "EXIT" and exit_reason == "stop_loss":
        return "now"
    return URGENCY_BY_KIND.get(kind, "today")


def _regime_aligned(regime: RegimeSnapshot | None, kind: str) -> bool:
    if regime is None:
        return False
    trend = (regime.market_trend or "").lower()
    vol = (regime.vol_regime or "").lower()
    if kind == "BUY":
        return trend != "downtrend" and vol != "high"
    if kind in ("EXIT", "TRIM"):
        return trend == "downtrend" or vol == "high"
    return False


def _deps_resolved_frac_for_buy(
    portfolio: PaperPortfolio, required_cash: Decimal,
) -> float:
    cash = Decimal(portfolio.cash) if portfolio is not None else Decimal("0")
    if required_cash <= 0:
        return 1.0
    return 1.0 if cash >= required_cash else float(cash / required_cash)


def _extract_top_factors(
    factor_breakdown: dict | None, n: int = 3,
) -> list[dict[str, Any]]:
    if not factor_breakdown:
        return []
    contrib = factor_breakdown.get("contributions") or {}
    values  = factor_breakdown.get("values") or {}
    rows: list[dict[str, Any]] = []
    for key, c_raw in contrib.items():
        try:
            c = float(c_raw) if c_raw is not None else 0.0
        except (TypeError, ValueError):
            c = 0.0
        v_raw = values.get(_factor_value_key(key)) if values else None
        try:
            v = float(v_raw) if v_raw is not None else None
        except (TypeError, ValueError):
            v = None
        rows.append({"key": key, "contribution": round(c, 4), "value": v})
    rows.sort(key=lambda r: abs(r["contribution"]), reverse=True)
    return rows[:n]


def _factor_value_key(contrib_key: str) -> str:
    """Map scoring.py contribution key → factor_breakdown values key."""
    mapping = {
        "rm60": "residual_momentum_60d",
        "rm20": "residual_momentum_20d",
        "sector": "sector_relative_rank",
        "trend": "trend_strength_20d",
        "vol": "atr_percent_14",
    }
    return mapping.get(contrib_key, contrib_key)


def _build_rationale(
    cand: CandidateIdea, kind: str, top_factors: list[dict[str, Any]],
) -> str:
    conf_str = f"{float(cand.confidence):.0f}" if cand.confidence is not None else "?"
    lead = f"{kind} {cand.action} conf={conf_str}"
    if top_factors:
        parts = [
            f"{f['key']}{'+' if f['contribution'] >= 0 else ''}{f['contribution']:.2f}"
            for f in top_factors[:2]
        ]
        lead = f"{lead} | {', '.join(parts)}"
    return lead[:200]


def _impact_estimate_for_buy(portfolio: PaperPortfolio | None) -> dict[str, Any]:
    sizing_pct = DEFAULT_SIZING_PCT
    if portfolio is not None and portfolio.config_json:
        import json
        try:
            cfg = json.loads(portfolio.config_json or "{}")
            sizing_pct = Decimal(str(cfg.get("sizing_pct_of_equity", DEFAULT_SIZING_PCT)))
        except (json.JSONDecodeError, TypeError):
            pass
    return {
        "position_delta_pct": float(sizing_pct) * 100.0,
        "portfolio_weight_after": float(sizing_pct),
    }


def _impact_estimate_for_exit(pos: PaperPosition) -> dict[str, Any]:
    value = float(Decimal(pos.quantity) * Decimal(pos.avg_cost))
    return {"position_delta_pct": -100.0, "notional_usd": round(value, 2)}


def _impact_estimate_for_trim(pos: PaperPosition) -> dict[str, Any]:
    return {"position_delta_pct": -50.0}


def _decay_for(kind: str, as_of: dt.date) -> dt.datetime | None:
    # Market-close-of-next-trading-day style decay
    base = dt.datetime.combine(as_of, dt.time(21, 0), tzinfo=dt.timezone.utc)
    if kind == "BUY":
        return base + dt.timedelta(days=1)
    if kind in ("TRIM", "EXIT"):
        return base + dt.timedelta(hours=6)
    return None


# ---------------------------------------------------------------------------
# Upsert
# ---------------------------------------------------------------------------


def _upsert_action(session: Session, row: dict[str, Any]) -> None:
    stmt = pg_insert(ActionItem).values(**row)
    stmt = stmt.on_conflict_do_update(
        index_elements=["as_of_date", "asset_id", "kind", "origin"],
        set_={
            k: v for k, v in row.items()
            if k not in ("id", "created_at", "updated_at", "status",
                         "acted_trade_id", "acted_at",
                         "dismissed_at", "dismiss_reason")
        },
    )
    session.execute(stmt)


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


def materialize_actions_for_day(
    session: Session, as_of: dt.date,
) -> int:
    """Materialize action_item rows for `as_of`. Idempotent via unique index."""
    regime = session.get(RegimeSnapshot, as_of)

    portfolio = session.scalars(
        select(PaperPortfolio).where(PaperPortfolio.is_active.is_(True)).limit(1)
    ).first()
    open_positions: dict[str, PaperPosition] = {}
    if portfolio is not None:
        for p in session.scalars(
            select(PaperPosition).where(
                PaperPosition.portfolio_id == portfolio.id,
                PaperPosition.is_open.is_(True),
            )
        ):
            open_positions[p.asset_id] = p
    held_ids = set(open_positions.keys())

    candidates = list(session.scalars(
        select(CandidateIdea).where(
            CandidateIdea.as_of_date == as_of,
            CandidateIdea.status == "accepted",
        )
    ))

    # --- Phase 4 calibration: derive factors + compute batch once per run ---
    # Flag-gated in config; when disabled, identity behavior preserved.
    cal30, cal7 = load_calibration_inputs(
        session, model_name=ENGINE_MODEL_VERSION,
    )
    factors = derive_factors(cal30, cal7)
    batch_input = [
        {"signal_id": c.id, "confidence": c.confidence}
        for c in candidates if c.confidence is not None
    ]
    calibration_batch: BatchResult = calibrate_batch(batch_input, factors)

    assets = {
        a.id: a for a in session.scalars(
            select(Asset).where(
                Asset.id.in_([c.asset_id for c in candidates] + list(held_ids))
            )
        )
    }

    written = 0

    for cand in candidates:
        is_held = cand.asset_id in held_ids
        kind = _kind_from(cand.action, is_held)
        if kind is None:
            continue

        asset = assets.get(cand.asset_id)
        if asset is None:
            continue

        top_factors = _extract_top_factors(cand.factor_breakdown, n=3)
        urgency = _urgency_for(kind)
        aligned = _regime_aligned(regime, kind)

        if kind == "BUY":
            impact = _impact_estimate_for_buy(portfolio)
            required_cash = (
                Decimal(str(impact.get("portfolio_weight_after", 0.10)))
                * (Decimal(portfolio.cash) if portfolio else Decimal("0"))
            )
            deps_frac = _deps_resolved_frac_for_buy(portfolio, required_cash)
        elif kind == "TRIM":
            impact = _impact_estimate_for_trim(open_positions[cand.asset_id])
            deps_frac = 1.0
        elif kind == "EXIT":
            impact = _impact_estimate_for_exit(open_positions[cand.asset_id])
            deps_frac = 1.0
        else:
            impact = {}
            deps_frac = 1.0

        economic_impact = min(1.0, abs(float(impact.get("position_delta_pct", 0))) / 100.0)

        # Phase 4: calibration — use effective_confidence when flag on and
        # shadow_mode off; otherwise original confidence (identity).
        effective_conf = calibration_batch.effective_confidence(
            cand.id, fallback=float(cand.confidence) if cand.confidence is not None else 0.0,
        )
        priority = compute_priority(
            confidence=effective_conf,
            regime_aligned=aligned,
            urgency=urgency,
            dependencies_resolved_frac=deps_frac,
            economic_impact_pct=economic_impact,
        )
        tier = priority_tier(priority)

        # Status: blocked if deps unresolved on a BUY
        status = "pending"
        if kind == "BUY" and deps_frac < 1.0:
            status = "blocked"

        row = {
            "id": str(uuid.uuid4()),
            "as_of_date": as_of,
            "kind": kind,
            "asset_id": cand.asset_id,
            "symbol": asset.symbol,
            "sector": asset.sector,
            "candidate_id": cand.id,
            "priority": priority,
            "priority_tier": tier,
            "urgency": urgency,
            "confidence": cand.confidence,
            "composite_score": cand.composite_score,
            "rationale_short": _build_rationale(cand, kind, top_factors),
            "factor_top": top_factors,
            "impact_estimate": impact,
            "decay_at": _decay_for(kind, as_of),
            "dependencies": {
                "requires_cash": float(required_cash) if kind == "BUY" else None,
                "conflicts_with": [],
                "blocks_on": [] if deps_frac >= 1.0 else ["cash"],
            } if kind == "BUY" else {
                "conflicts_with": [],
                "blocks_on": [],
            },
            "origin": "engine",
            "status": status,
        }
        _upsert_action(session, row)
        written += 1

    # Exit-rule-driven actions (age >= 10d or regime=downtrend)
    max_age = 10
    now_dt = dt.datetime.combine(as_of, dt.time.min, tzinfo=dt.timezone.utc)
    for pos in open_positions.values():
        opened_at = pos.opened_at
        if opened_at.tzinfo is None:
            opened_at = opened_at.replace(tzinfo=dt.timezone.utc)
        age_days = max(0, (as_of - opened_at.date()).days)
        reason: str | None = None
        if age_days >= max_age:
            reason = "horizon_exit"
        elif regime is not None and regime.market_trend == "downtrend":
            reason = "regime_exit"
        if reason is None:
            continue

        asset = assets.get(pos.asset_id)
        if asset is None:
            continue
        impact = _impact_estimate_for_exit(pos)
        priority = compute_priority(
            confidence=Decimal("80"),   # system-initiated exits are high-conviction
            regime_aligned=True,
            urgency=_urgency_for("EXIT"),
            dependencies_resolved_frac=1.0,
            economic_impact_pct=1.0,
        )
        row = {
            "id": str(uuid.uuid4()),
            "as_of_date": as_of,
            "kind": "EXIT",
            "asset_id": pos.asset_id,
            "symbol": asset.symbol,
            "sector": asset.sector,
            "candidate_id": None,
            "priority": priority,
            "priority_tier": priority_tier(priority),
            "urgency": _urgency_for("EXIT"),
            "confidence": Decimal("80"),
            "composite_score": None,
            "rationale_short": f"EXIT {asset.symbol} {reason} age={age_days}d",
            "factor_top": [],
            "impact_estimate": impact,
            "decay_at": _decay_for("EXIT", as_of),
            "dependencies": {"conflicts_with": [], "blocks_on": []},
            "origin": "exit_rules",
            "status": "pending",
        }
        _upsert_action(session, row)
        written += 1

    session.commit()
    logger.info(
        "[actions] materialized as_of={} rows={} held={} candidates={}",
        as_of, written, len(held_ids), len(candidates),
    )
    return written


def materialize_today() -> int:
    today = dt.date.today()
    with SessionLocal() as session:
        return materialize_actions_for_day(session, today)
