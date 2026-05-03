"""ActionItem repository — list, get, act, dismiss.

All functions operate on a single Session; caller owns the commit boundary.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.src.db.models import (
    ActionItem,
    PaperPortfolio,
    PaperPosition,
)
from apps.api.src.domain.paper_trading.paper_execution import (
    DEFAULT_SIZING_PCT,
    PaperTradeRejected,
    submit_trade,
)


@dataclass
class ActResult:
    ok: bool
    reason: str | None = None
    payload: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def _dec_str(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return str(v)
    return str(v)


def serialize(a: ActionItem) -> dict[str, Any]:
    return {
        "id": a.id,
        "as_of_date": a.as_of_date.isoformat() if a.as_of_date else None,
        "kind": a.kind,
        "symbol": a.symbol,
        "sector": a.sector,
        "asset_id": a.asset_id,
        "candidate_id": a.candidate_id,
        "priority": _dec_str(a.priority),
        "priority_tier": a.priority_tier,
        "urgency": a.urgency,
        "confidence": _dec_str(a.confidence),
        "composite_score": _dec_str(a.composite_score),
        "rationale_short": a.rationale_short,
        "factor_top": a.factor_top,
        "impact_estimate": a.impact_estimate,
        "decay_at": a.decay_at.isoformat() if a.decay_at else None,
        "dependencies": a.dependencies,
        "origin": a.origin,
        "status": a.status,
        "acted_trade_id": a.acted_trade_id,
        "acted_at": a.acted_at.isoformat() if a.acted_at else None,
        "dismissed_at": a.dismissed_at.isoformat() if a.dismissed_at else None,
        "dismiss_reason": a.dismiss_reason,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


def list_pending(
    session: Session, *, status: str = "pending", limit: int = 50,
) -> list[dict[str, Any]]:
    stmt = (
        select(ActionItem)
        .where(ActionItem.status == status)
        .order_by(ActionItem.priority.desc(), ActionItem.created_at.desc())
        .limit(limit)
    )
    return [serialize(a) for a in session.scalars(stmt)]


def get(session: Session, action_id: str) -> dict[str, Any] | None:
    a = session.get(ActionItem, action_id)
    return serialize(a) if a is not None else None


# ---------------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------------


def _active_portfolio(session: Session) -> PaperPortfolio | None:
    return session.scalars(
        select(PaperPortfolio).where(PaperPortfolio.is_active.is_(True)).limit(1)
    ).first()


def _get_position(
    session: Session, portfolio_id: str, asset_id: str,
) -> PaperPosition | None:
    return session.scalars(
        select(PaperPosition).where(
            PaperPosition.portfolio_id == portfolio_id,
            PaperPosition.asset_id == asset_id,
            PaperPosition.is_open.is_(True),
        )
    ).first()


def _compute_buy_usd(
    session: Session, portfolio: PaperPortfolio,
) -> Decimal:
    import json
    cfg: dict = {}
    try:
        cfg = json.loads(portfolio.config_json or "{}")
    except (json.JSONDecodeError, TypeError):
        cfg = {}
    sizing_pct = Decimal(str(cfg.get("sizing_pct_of_equity", DEFAULT_SIZING_PCT)))

    cash = Decimal(portfolio.cash)
    open_positions = list(session.scalars(
        select(PaperPosition).where(
            PaperPosition.portfolio_id == portfolio.id,
            PaperPosition.is_open.is_(True),
        )
    ))
    positions_value = sum(
        (Decimal(p.quantity) * Decimal(p.avg_cost) for p in open_positions),
        Decimal("0"),
    )
    equity = cash + positions_value
    return (sizing_pct * equity).quantize(Decimal("0.01"))


def act_on(session: Session, action_id: str) -> ActResult:
    action = session.get(ActionItem, action_id)
    if action is None:
        return ActResult(ok=False, reason="action_not_found")
    if action.status != "pending":
        return ActResult(
            ok=False,
            reason=f"action_not_actionable status={action.status}",
        )

    portfolio = _active_portfolio(session)
    if portfolio is None:
        return ActResult(ok=False, reason="no_active_portfolio")

    now = dt.datetime.now(dt.timezone.utc)

    try:
        if action.kind == "BUY":
            usd = _compute_buy_usd(session, portfolio)
            if usd <= 0:
                return ActResult(ok=False, reason="sizing_below_threshold")
            result = submit_trade(
                session,
                portfolio_id=portfolio.id, asset_id=action.asset_id,
                side="buy", usd_amount=usd,
                submitted_at=now,
                reason=f"action_item:{action.id}",
            )
        elif action.kind in ("EXIT", "TRIM"):
            pos = _get_position(session, portfolio.id, action.asset_id)
            if pos is None:
                return ActResult(ok=False, reason="position_not_open")
            qty_total = Decimal(pos.quantity)
            qty = qty_total if action.kind == "EXIT" else qty_total / Decimal("2")
            if qty <= 0:
                return ActResult(ok=False, reason="zero_quantity")
            result = submit_trade(
                session,
                portfolio_id=portfolio.id, asset_id=action.asset_id,
                side="sell", quantity=qty,
                submitted_at=now,
                reason=f"action_item:{action.id}",
            )
        else:
            return ActResult(
                ok=False,
                reason=f"kind_not_directly_actionable kind={action.kind}",
            )
    except PaperTradeRejected as exc:
        return ActResult(ok=False, reason=f"exec_rejected: {exc}")

    action.status = "acted"
    action.acted_trade_id = result.trade_id
    action.acted_at = now

    # Auto-dismiss conflicting pending actions
    for conflict_id in (action.dependencies or {}).get("conflicts_with", []) or []:
        conflict = session.get(ActionItem, conflict_id)
        if conflict is not None and conflict.status == "pending":
            conflict.status = "dismissed"
            conflict.dismiss_reason = "superseded_by_inverse"
            conflict.dismissed_at = now

    return ActResult(
        ok=True,
        payload={
            "trade_id": result.trade_id,
            "action_id": action.id,
            "fill_price": str(result.fill_price),
            "fill_ts": result.fill_ts.isoformat(),
            "cash_after": str(result.cash_after),
        },
    )


def dismiss(
    session: Session, action_id: str, *, reason: str = "user_dismiss",
) -> ActResult:
    action = session.get(ActionItem, action_id)
    if action is None:
        return ActResult(ok=False, reason="action_not_found")
    if action.status != "pending":
        return ActResult(
            ok=False,
            reason=f"action_not_dismissable status={action.status}",
        )
    action.status = "dismissed"
    action.dismiss_reason = reason[:64]
    action.dismissed_at = dt.datetime.now(dt.timezone.utc)
    return ActResult(ok=True, payload={"action_id": action_id})
