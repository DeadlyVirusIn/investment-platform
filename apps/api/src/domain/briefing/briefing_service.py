"""Daily briefing synthesis. Template-based text, no LLM."""

from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from apps.api.src.db.models import Asset, Lot, PriceBar, Recommendation, Transaction
from apps.api.src.domain.ledger.pnl_calculator import compute_pnl_summary

STALENESS_DAYS = 2


def _decimal_or_none(v: object) -> Decimal | None:
    if v is None:
        return None
    try:
        return v if isinstance(v, Decimal) else Decimal(str(v))
    except (ValueError, TypeError):
        return None


def _latest_rec_per_asset_for_account(
    session: Session, account_id: str
) -> list[tuple[Recommendation, Asset]]:
    """Join: held assets × latest Recommendation per asset."""
    held_stmt = (
        select(Lot.asset_id)
        .join(Transaction, Lot.open_transaction_id == Transaction.id)
        .where(
            Transaction.account_id == account_id,
            Lot.quantity_remaining > 0,
        )
        .distinct()
    )
    held_asset_ids = [row[0] for row in session.execute(held_stmt).all()]
    if not held_asset_ids:
        return []

    latest_ts_stmt = (
        select(
            Recommendation.asset_id.label("asset_id"),
            func.max(Recommendation.generated_at).label("max_ts"),
        )
        .where(Recommendation.asset_id.in_(held_asset_ids))
        .group_by(Recommendation.asset_id)
        .subquery()
    )
    stmt = (
        select(Recommendation, Asset)
        .join(
            latest_ts_stmt,
            (Recommendation.asset_id == latest_ts_stmt.c.asset_id)
            & (Recommendation.generated_at == latest_ts_stmt.c.max_ts),
        )
        .join(Asset, Recommendation.asset_id == Asset.id)
    )
    return list(session.execute(stmt).all())


def _rationale(rec: Recommendation) -> dict[str, Any]:
    try:
        return json.loads(rec.rationale or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}


def _check_staleness(
    session: Session, account_id: str, now: dt.datetime
) -> list[dict[str, Any]]:
    threshold = now - dt.timedelta(days=STALENESS_DAYS)
    held_stmt = (
        select(Asset.id, Asset.symbol)
        .join(Lot, Lot.asset_id == Asset.id)
        .join(Transaction, Lot.open_transaction_id == Transaction.id)
        .where(
            Transaction.account_id == account_id,
            Lot.quantity_remaining > 0,
        )
        .distinct()
    )
    stale: list[dict[str, Any]] = []
    for asset_id, symbol in session.execute(held_stmt).all():
        latest_bar_ts = session.scalar(
            select(func.max(PriceBar.ts)).where(PriceBar.asset_id == asset_id)
        )
        if latest_bar_ts is None:
            stale.append({
                "asset_id": asset_id,
                "symbol": symbol,
                "reason": "no price data",
                "latest_bar_ts": None,
            })
        elif latest_bar_ts < threshold:
            stale.append({
                "asset_id": asset_id,
                "symbol": symbol,
                "reason": "price data stale",
                "latest_bar_ts": latest_bar_ts.isoformat(),
            })
    return stale


def build_briefing(session: Session, account_id: str) -> dict[str, Any]:
    """Assemble the daily briefing payload for `account_id`."""
    now = dt.datetime.now(dt.timezone.utc)

    summary = compute_pnl_summary(session, account_id)

    rec_rows = _latest_rec_per_asset_for_account(session, account_id)
    actionable: list[dict[str, Any]] = []
    for rec, asset in rec_rows:
        if rec.action not in ("Buy", "Trim", "Sell"):
            continue
        rationale = _rationale(rec)
        actionable.append({
            "recommendation_id": rec.id,
            "asset_id": rec.asset_id,
            "symbol": asset.symbol,
            "action": rec.action,
            "confidence": _decimal_or_none(rec.conviction),
            "thesis": rationale.get("thesis"),
            "generated_at": rec.generated_at.isoformat() if rec.generated_at else None,
        })
    actionable.sort(key=lambda r: r["confidence"] or Decimal("0"), reverse=True)
    top_3 = actionable[:3]

    stale = _check_staleness(session, account_id, now)

    # Template text summary — deterministic, no LLM.
    realized = _decimal_or_none(summary.get("realized_pnl")) or Decimal("0")
    unrealized = _decimal_or_none(summary.get("unrealized_pnl"))
    pnl_line = f"Realized P&L: {realized}."
    if unrealized is not None:
        pnl_line += f" Unrealized P&L: {unrealized}."
    else:
        pnl_line += " Unrealized P&L: unavailable (missing prices)."
    actions_line = (
        f"{len(top_3)} actionable recommendation(s) to review."
        if top_3
        else "No Buy/Trim/Sell recommendations pending."
    )
    stale_line = (
        f"{len(stale)} asset(s) with stale or missing price data."
        if stale
        else "All held assets have fresh price data."
    )
    text_summary = f"{pnl_line} {actions_line} {stale_line}"

    # JSON-safe output (Decimals → strings).
    def _js(v: object) -> object:
        if isinstance(v, Decimal):
            return str(v)
        if isinstance(v, dict):
            return {k: _js(val) for k, val in v.items()}
        if isinstance(v, list):
            return [_js(x) for x in v]
        return v

    return _js({
        "account_id": account_id,
        "date": now.date().isoformat(),
        "generated_at": now.isoformat(),
        "portfolio_summary": summary,
        "top_actions": top_3,
        "stale_data": stale,
        "text_summary": text_summary,
    })
