"""One-shot dashboard summary aggregator — read-only."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from apps.api.src.db.models import (
    Asset,
    CandidateIdea,
    FactorSnapshot,
    PaperTrade,
    RegimeSnapshot,
)
from apps.api.src.domain.pnl.engine import portfolio_pnl, resolve_portfolio
from apps.api.src.domain.stock_engine.portfolio.portfolio_sizer import (
    MAX_SECTOR_PCT,
)

SECTOR_NEAR_CAP_PCT = Decimal("0.45")    # 90% of 0.50 max
HIGH_SLIPPAGE_THRESHOLD_BPS = Decimal("50")
DEFAULT_BUY_THRESHOLD = Decimal("0.25")


@dataclass
class DashboardAlert:
    code: str
    severity: str                 # info | warning | critical
    message: str


def _d(v: object) -> Decimal:
    if v is None:
        return Decimal("0")
    return v if isinstance(v, Decimal) else Decimal(str(v))


def _latest_candidate_date(session: Session) -> dt.date | None:
    row = session.execute(
        select(func.max(CandidateIdea.as_of_date))
    ).first()
    return row[0] if row and row[0] else None


def _regime_payload(regime: RegimeSnapshot | None) -> dict[str, Any] | None:
    if regime is None:
        return None
    return {
        "as_of_date": regime.as_of_date.isoformat(),
        "benchmark_symbol": regime.benchmark_symbol,
        "market_trend": regime.market_trend,
        "vol_regime": regime.vol_regime,
        "breadth_regime": regime.breadth_regime,
        "sma50_over_sma200": regime.sma50_over_sma200,
        "realized_vol_20d": str(regime.realized_vol_20d),
        "atr_pctile_1y": str(regime.atr_pctile_1y),
    }


def _candidate_summary(
    session: Session, as_of: dt.date,
) -> dict[str, Any]:
    stmt = (
        select(
            CandidateIdea.status,
            CandidateIdea.action,
            CandidateIdea.rejection_reason,
            func.count().label("n"),
        )
        .where(CandidateIdea.as_of_date == as_of)
        .group_by(
            CandidateIdea.status,
            CandidateIdea.action,
            CandidateIdea.rejection_reason,
        )
    )
    total = 0
    accepted = 0
    accepted_buys = 0
    rejected = 0
    reasons: dict[str, int] = {}
    for status, action, reason, n in session.execute(stmt).all():
        n = int(n)
        total += n
        if status == "accepted":
            accepted += n
            if action == "Buy" and reason is None:
                accepted_buys += n
        elif status == "rejected":
            rejected += n
        if reason is not None:
            reasons[reason] = reasons.get(reason, 0) + n
    return {
        "total_evaluated": total,
        "accepted_total": accepted,
        "accepted_buys": accepted_buys,
        "rejected_total": rejected,
        "reasons": reasons,
    }


def _blocked_alpha_summary(
    session: Session, as_of: dt.date,
    min_score: Decimal = DEFAULT_BUY_THRESHOLD,
) -> dict[str, Any]:
    stmt = (
        select(CandidateIdea, Asset.symbol)
        .join(Asset, Asset.id == CandidateIdea.asset_id)
        .where(
            CandidateIdea.as_of_date == as_of,
            CandidateIdea.status == "rejected",
            CandidateIdea.composite_score.is_not(None),
            CandidateIdea.composite_score >= min_score,
        )
        .order_by(desc(CandidateIdea.composite_score))
    )
    rows = list(session.execute(stmt).all())
    top = [
        {
            "symbol": sym,
            "composite_score": str(c.composite_score) if c.composite_score is not None else None,
            "rejection_reason": c.rejection_reason,
        }
        for c, sym in rows[:3]
    ]
    return {
        "min_score": str(min_score),
        "count": len(rows),
        "top": top,
    }


def _top_accepted_buys(
    session: Session, as_of: dt.date, n: int = 5,
) -> list[dict[str, Any]]:
    stmt = (
        select(
            CandidateIdea, Asset.symbol,
            func.coalesce(Asset.sector, Asset.asset_class).label("sector"),
        )
        .join(Asset, Asset.id == CandidateIdea.asset_id)
        .where(
            CandidateIdea.as_of_date == as_of,
            CandidateIdea.status == "accepted",
            CandidateIdea.action == "Buy",
            CandidateIdea.rejection_reason.is_(None),
        )
        .order_by(desc(CandidateIdea.composite_score))
        .limit(n)
    )
    out: list[dict[str, Any]] = []
    for c, sym, sector in session.execute(stmt).all():
        out.append({
            "symbol": sym,
            "sector": sector,
            "composite_score": str(c.composite_score) if c.composite_score is not None else None,
            "confidence": str(c.confidence) if c.confidence is not None else None,
        })
    return out


def _portfolio_block(
    session: Session, portfolio, now: dt.datetime,
) -> dict[str, Any]:
    pnl = portfolio_pnl(session, portfolio, now=now)
    positions_sorted = sorted(
        pnl.positions, key=lambda p: p.market_value, reverse=True,
    )
    top = []
    for pm in positions_sorted[:5]:
        weight = (pm.market_value / pnl.nav) if pnl.nav > 0 else Decimal("0")
        top.append({
            "symbol": pm.symbol,
            "quantity": str(pm.quantity),
            "avg_cost": str(pm.avg_cost),
            "mark": str(pm.mark) if pm.mark is not None else None,
            "market_value": str(pm.market_value),
            "weight": str(weight),
            "unrealized_pnl": str(pm.unrealized_pnl),
            "unrealized_pct": str(pm.unrealized_pct) if pm.unrealized_pct is not None else None,
        })

    # Sector exposure
    sector_mv: dict[str, Decimal] = {}
    if pnl.positions:
        asset_ids = [p.asset_id for p in pnl.positions]
        sect_map = {
            aid: sector
            for aid, sector in session.execute(
                select(
                    Asset.id,
                    func.coalesce(Asset.sector, Asset.asset_class),
                ).where(Asset.id.in_(asset_ids))
            ).all()
        }
        for pm in pnl.positions:
            s = sect_map.get(pm.asset_id, "unknown")
            sector_mv[s] = sector_mv.get(s, Decimal("0")) + pm.market_value

    sector_weights = {
        s: str(mv / pnl.nav if pnl.nav > 0 else Decimal("0"))
        for s, mv in sector_mv.items()
    }

    return {
        "portfolio_id": pnl.portfolio_id,
        "nav": str(pnl.nav),
        "cash": str(pnl.cash),
        "invested": str(pnl.invested),
        "open_positions_count": pnl.open_positions_count,
        "top_positions": top,
        "sector_exposure": sector_weights,
    }


def _alerts(
    *,
    session: Session,
    as_of: dt.date,
    regime: RegimeSnapshot | None,
    candidates: dict[str, Any],
    portfolio_block: dict[str, Any] | None,
) -> list[DashboardAlert]:
    out: list[DashboardAlert] = []

    if regime is None:
        out.append(DashboardAlert(
            code="regime_missing", severity="warning",
            message=f"No regime snapshot for {as_of.isoformat()}",
        ))

    factor_exists = session.scalar(
        select(func.count()).select_from(FactorSnapshot)
        .where(FactorSnapshot.as_of_date == as_of)
    ) or 0
    if factor_exists == 0:
        out.append(DashboardAlert(
            code="factors_missing", severity="warning",
            message=f"No factor snapshots for {as_of.isoformat()}",
        ))

    if candidates["accepted_buys"] == 0 and candidates["total_evaluated"] > 0:
        out.append(DashboardAlert(
            code="no_buys_today", severity="warning",
            message="No accepted Buy candidates today",
        ))

    if candidates["rejected_total"] > 0 and candidates["reasons"]:
        top_reason, top_count = max(
            candidates["reasons"].items(), key=lambda kv: kv[1]
        )
        ratio = top_count / candidates["total_evaluated"] if candidates["total_evaluated"] else 0
        if ratio >= 0.8:
            out.append(DashboardAlert(
                code="all_blocked_one_reason", severity="warning",
                message=f"{int(ratio*100)}% of rows blocked by {top_reason}",
            ))

    # High slippage day
    hi_slip = session.scalar(
        select(func.count()).select_from(PaperTrade)
        .where(
            PaperTrade.fill_ts >= dt.datetime.combine(
                as_of, dt.time(0, 0, 0, tzinfo=dt.timezone.utc),
            ),
            PaperTrade.fill_ts < dt.datetime.combine(
                as_of + dt.timedelta(days=1),
                dt.time(0, 0, 0, tzinfo=dt.timezone.utc),
            ),
            PaperTrade.slippage_bps > HIGH_SLIPPAGE_THRESHOLD_BPS,
        )
    ) or 0
    if hi_slip > 0:
        out.append(DashboardAlert(
            code="high_slippage_day", severity="info",
            message=f"{hi_slip} trades with slippage > {HIGH_SLIPPAGE_THRESHOLD_BPS} bps",
        ))

    # Sector near cap
    if portfolio_block:
        for sector, w in portfolio_block.get("sector_exposure", {}).items():
            if Decimal(w) >= SECTOR_NEAR_CAP_PCT:
                out.append(DashboardAlert(
                    code="sector_near_cap", severity="warning",
                    message=(
                        f"Sector '{sector}' at {float(Decimal(w))*100:.1f}%"
                        f" (cap {int(MAX_SECTOR_PCT*100)}%)"
                    ),
                ))

    return out


def build_summary(
    session: Session,
    *,
    portfolio_id: str | None = None,
    as_of: dt.date | None = None,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    when = now or dt.datetime.now(dt.timezone.utc)
    effective = as_of or _latest_candidate_date(session)

    regime = session.get(RegimeSnapshot, effective) if effective else None

    candidates = {
        "total_evaluated": 0, "accepted_total": 0,
        "accepted_buys": 0, "rejected_total": 0, "reasons": {},
    }
    blocked: dict[str, Any] = {
        "min_score": str(DEFAULT_BUY_THRESHOLD),
        "count": 0, "top": [],
    }
    top_buys: list[dict[str, Any]] = []
    if effective:
        candidates = _candidate_summary(session, effective)
        blocked = _blocked_alpha_summary(session, effective)
        top_buys = _top_accepted_buys(session, effective)

    portfolio = resolve_portfolio(session, portfolio_id)
    portfolio_block = (
        _portfolio_block(session, portfolio, when)
        if portfolio is not None else None
    )

    alerts = _alerts(
        session=session, as_of=effective or when.date(),
        regime=regime, candidates=candidates,
        portfolio_block=portfolio_block,
    )

    return {
        "as_of_date": effective.isoformat() if effective else None,
        "regime": _regime_payload(regime),
        "candidates": candidates,
        "blocked_alpha": blocked,
        "top_buys": top_buys,
        "portfolio": portfolio_block,
        "alerts": [
            {"code": a.code, "severity": a.severity, "message": a.message}
            for a in alerts
        ],
    }
