"""Alert engine. Threshold evaluation + 24h cooldown. Decimal math only."""

from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.src.db.models import Alert, Asset, PriceBar, Recommendation

AlertType = Literal[
    "price_above",
    "price_below",
    "concentration",
    "recommendation_changed",
]

COOLDOWN_HOURS = 24


class AlertCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alert_type: AlertType
    asset_id: str | None = None          # required for price/rec alerts
    account_id: str | None = None        # required for concentration alerts
    threshold: Decimal | None = None     # price threshold or concentration pct
    is_active: bool = True


class AlertOut(BaseModel):
    id: str
    alert_type: str
    asset_id: str | None
    condition: dict[str, Any]
    is_active: bool
    triggered_at: dt.datetime | None
    created_at: dt.datetime


def _condition_to_dict(text: str | None) -> dict[str, Any]:
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _d(v: object) -> Decimal | None:
    if v is None:
        return None
    try:
        return v if isinstance(v, Decimal) else Decimal(str(v))
    except (ValueError, TypeError):
        return None


def _to_out(row: Alert) -> AlertOut:
    return AlertOut(
        id=row.id,
        alert_type=row.alert_type,
        asset_id=row.asset_id,
        condition=_condition_to_dict(row.condition),
        is_active=row.is_active,
        triggered_at=row.triggered_at,
        created_at=row.created_at,
    )


def create_alert(session: Session, payload: AlertCreate) -> AlertOut:
    condition: dict[str, Any] = {"alert_type": payload.alert_type}
    if payload.threshold is not None:
        condition["threshold"] = str(payload.threshold)
    if payload.asset_id is not None:
        condition["asset_id"] = payload.asset_id
    if payload.account_id is not None:
        condition["account_id"] = payload.account_id

    if payload.alert_type in ("price_above", "price_below"):
        if payload.asset_id is None or payload.threshold is None:
            raise ValueError(
                f"alert_type={payload.alert_type} requires asset_id + threshold"
            )
    elif payload.alert_type == "concentration":
        if payload.account_id is None or payload.threshold is None:
            raise ValueError(
                "alert_type=concentration requires account_id + threshold"
            )
    elif payload.alert_type == "recommendation_changed":
        if payload.asset_id is None:
            raise ValueError(
                "alert_type=recommendation_changed requires asset_id"
            )

    row = Alert(
        asset_id=payload.asset_id,
        alert_type=payload.alert_type,
        condition=json.dumps(condition),
        is_active=payload.is_active,
    )
    session.add(row)
    session.flush()
    return _to_out(row)


def list_alerts(session: Session) -> list[AlertOut]:
    stmt = select(Alert).order_by(Alert.created_at.asc(), Alert.id.asc())
    return [_to_out(a) for a in session.execute(stmt).scalars()]


# ---------------------------------------------------------------------------
# Evaluation helpers
# ---------------------------------------------------------------------------


def _latest_price(session: Session, asset_id: str) -> Decimal | None:
    stmt = (
        select(PriceBar.adjusted_close, PriceBar.close)
        .where(PriceBar.asset_id == asset_id)
        .order_by(PriceBar.ts.desc())
        .limit(1)
    )
    row = session.execute(stmt).first()
    if row is None:
        return None
    return _d(row[0] if row[0] is not None else row[1])


def _latest_rec(session: Session, asset_id: str) -> Recommendation | None:
    stmt = (
        select(Recommendation)
        .where(Recommendation.asset_id == asset_id)
        .order_by(Recommendation.generated_at.desc())
        .limit(1)
    )
    return session.execute(stmt).scalars().first()


def _prior_rec(session: Session, asset_id: str) -> Recommendation | None:
    stmt = (
        select(Recommendation)
        .where(Recommendation.asset_id == asset_id)
        .order_by(Recommendation.generated_at.desc())
        .offset(1)
        .limit(1)
    )
    return session.execute(stmt).scalars().first()


def _concentration_pct(session: Session, account_id: str) -> Decimal:
    from apps.api.src.domain.ledger.pnl_calculator import compute_positions

    positions = compute_positions(session, account_id)
    total = Decimal("0")
    max_value = Decimal("0")
    for p in positions:
        mv = p["market_value"] if p["market_value"] is not None else p["total_cost_basis"]
        total += mv
        if mv > max_value:
            max_value = mv
    if total <= 0:
        return Decimal("0")
    return (max_value / total) * Decimal("100")


def _within_cooldown(triggered_at: dt.datetime | None, now: dt.datetime) -> bool:
    if triggered_at is None:
        return False
    delta = now - triggered_at
    return delta < dt.timedelta(hours=COOLDOWN_HOURS)


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------


def evaluate_alerts(
    session: Session, now: dt.datetime | None = None
) -> list[dict[str, Any]]:
    """Walk active alerts, fire any that match (respecting 24h cooldown)."""
    now = now or dt.datetime.now(dt.timezone.utc)
    fired: list[dict[str, Any]] = []

    active = session.execute(
        select(Alert).where(Alert.is_active == True)  # noqa: E712
    ).scalars().all()

    for alert in active:
        if _within_cooldown(alert.triggered_at, now):
            continue

        cond = _condition_to_dict(alert.condition)
        threshold = _d(cond.get("threshold"))
        kind = alert.alert_type

        matched = False
        detail: dict[str, Any] = {}

        if kind == "price_above" and alert.asset_id and threshold is not None:
            price = _latest_price(session, alert.asset_id)
            if price is not None and price > threshold:
                matched = True
                detail = {"price": str(price), "threshold": str(threshold)}

        elif kind == "price_below" and alert.asset_id and threshold is not None:
            price = _latest_price(session, alert.asset_id)
            if price is not None and price < threshold:
                matched = True
                detail = {"price": str(price), "threshold": str(threshold)}

        elif kind == "concentration" and threshold is not None:
            account_id = cond.get("account_id")
            if account_id:
                pct = _concentration_pct(session, account_id)
                if pct > threshold:
                    matched = True
                    detail = {"concentration_pct": str(pct), "threshold": str(threshold)}

        elif kind == "recommendation_changed" and alert.asset_id:
            latest = _latest_rec(session, alert.asset_id)
            prior = _prior_rec(session, alert.asset_id)
            if latest is not None and prior is not None and latest.action != prior.action:
                matched = True
                detail = {
                    "prior_action": prior.action,
                    "latest_action": latest.action,
                    "recommendation_id": latest.id,
                }

        if matched:
            alert.triggered_at = now
            fired.append({
                "alert_id": alert.id,
                "alert_type": kind,
                "asset_id": alert.asset_id,
                "fired_at": now.isoformat(),
                "detail": detail,
            })

    if fired:
        session.flush()

    return fired
