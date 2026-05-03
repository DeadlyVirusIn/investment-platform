"""Module B — Portfolio Intelligence Engine.

Explains what is driving NAV: concentration, sector mix, regime mix of
entries, capital utilization, slippage, and a flag list.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from apps.api.src.db.models import (
    Asset,
    PaperPortfolio,
    PaperTrade,
)
from apps.api.src.domain.pnl.attribution import entry_context_map
from apps.api.src.domain.pnl.engine import portfolio_pnl, resolve_portfolio


CONCENTRATION_FLAG = Decimal("0.50")      # top 2 weight
SECTOR_CAP_FLAG = Decimal("0.50")         # single-sector cap reference
IDLE_CASH_FLAG = Decimal("0.60")          # cash / NAV
HIGH_SLIPPAGE_FLAG = Decimal("30")        # bps


@dataclass
class TopPosition:
    symbol: str | None
    weight: Decimal
    unrealized_pnl: Decimal
    unrealized_pct: Decimal | None


@dataclass
class SectorSlice:
    sector: str
    weight: Decimal


@dataclass
class RegimeMix:
    market_trend: str
    vol_regime: str
    count: int


@dataclass
class PortfolioIntelligence:
    nav: Decimal
    cash: Decimal
    invested: Decimal
    cash_pct: Decimal | None
    invested_pct: Decimal | None
    open_positions: int
    top_positions: list[TopPosition] = field(default_factory=list)
    top1_weight: Decimal | None = None
    top2_weight_sum: Decimal | None = None
    sector_exposure: list[SectorSlice] = field(default_factory=list)
    regime_mix: list[RegimeMix] = field(default_factory=list)
    avg_slippage_bps: Decimal | None = None
    max_slippage_bps: Decimal | None = None
    flags: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _d(v: object) -> Decimal:
    if v is None:
        return Decimal("0")
    return v if isinstance(v, Decimal) else Decimal(str(v))


def analyze_portfolio(
    session: Session, portfolio_id: str | None = None,
) -> PortfolioIntelligence:
    portfolio = resolve_portfolio(session, portfolio_id)
    if portfolio is None:
        return PortfolioIntelligence(
            nav=Decimal("0"), cash=Decimal("0"), invested=Decimal("0"),
            cash_pct=None, invested_pct=None, open_positions=0,
            notes=["no_active_portfolio"],
        )

    pnl = portfolio_pnl(session, portfolio)

    cash_pct = pnl.cash / pnl.nav if pnl.nav > 0 else None
    invested_pct = pnl.invested / pnl.nav if pnl.nav > 0 else None

    # Top positions by market_value
    positions_sorted = sorted(
        pnl.positions, key=lambda p: p.market_value, reverse=True,
    )
    top_positions: list[TopPosition] = []
    for pm in positions_sorted[:5]:
        w = pm.market_value / pnl.nav if pnl.nav > 0 else Decimal("0")
        top_positions.append(TopPosition(
            symbol=pm.symbol,
            weight=w.quantize(Decimal("0.000001")),
            unrealized_pnl=pm.unrealized_pnl,
            unrealized_pct=pm.unrealized_pct,
        ))
    top1 = top_positions[0].weight if top_positions else None
    if len(top_positions) >= 2:
        top2_sum = top_positions[0].weight + top_positions[1].weight
    elif len(top_positions) == 1:
        top2_sum = top1
    else:
        top2_sum = None

    # Sector exposure
    sector_mv: dict[str, Decimal] = {}
    if pnl.positions:
        asset_ids = [p.asset_id for p in pnl.positions]
        sect_map = {
            aid: (sector or asset_class)
            for aid, sector, asset_class in session.execute(
                select(Asset.id, Asset.sector, Asset.asset_class).where(
                    Asset.id.in_(asset_ids)
                )
            ).all()
        }
        for pm in pnl.positions:
            s = sect_map.get(pm.asset_id, "unknown")
            sector_mv[s] = sector_mv.get(s, Decimal("0")) + pm.market_value
    sectors = [
        SectorSlice(
            sector=s,
            weight=(mv / pnl.nav if pnl.nav > 0 else Decimal("0")).quantize(
                Decimal("0.000001"),
            ),
        )
        for s, mv in sorted(sector_mv.items(), key=lambda kv: -kv[1])
    ]

    # Regime mix at entry
    ctx = entry_context_map(session, portfolio.id)
    regime_counter: Counter[tuple[str, str]] = Counter()
    for pm in pnl.positions:
        c = ctx.get(pm.asset_id)
        trend = (c or {}).get("market_trend") or "unknown"
        vol = (c or {}).get("vol_regime") or "unknown"
        regime_counter[(trend, vol)] += 1
    regime_mix = [
        RegimeMix(market_trend=t, vol_regime=v, count=n)
        for (t, v), n in regime_counter.most_common()
    ]

    # Slippage
    slip_stmt = (
        select(PaperTrade.slippage_bps)
        .where(
            PaperTrade.portfolio_id == portfolio.id,
            PaperTrade.slippage_bps.is_not(None),
        )
    )
    slips = [_d(v) for (v,) in session.execute(slip_stmt).all()]
    avg_slip = sum(slips, Decimal("0")) / Decimal(len(slips)) if slips else None
    max_slip = max(slips) if slips else None

    # Flags
    flags: list[str] = []
    if top1 is not None and top1 >= Decimal("0.30"):
        flags.append(f"high_single_position_weight:{float(top1):.1%}")
    if top2_sum is not None and top2_sum >= CONCENTRATION_FLAG:
        flags.append(f"high_top2_concentration:{float(top2_sum):.1%}")
    for s in sectors:
        if s.weight >= SECTOR_CAP_FLAG:
            flags.append(f"sector_cap_breached:{s.sector}:{float(s.weight):.1%}")
    if cash_pct is not None and cash_pct >= IDLE_CASH_FLAG:
        flags.append(f"idle_cash:{float(cash_pct):.1%}")
    if avg_slip is not None and avg_slip >= HIGH_SLIPPAGE_FLAG:
        flags.append(f"high_avg_slippage:{float(avg_slip):.1f}bps")
    if pnl.open_positions_count > 0 and pnl.open_positions_count < 3:
        flags.append("low_diversification")
    if pnl.cumulative_pnl < Decimal("-0.15") * pnl.starting_cash:
        flags.append("drawdown_exceeds_15pct")

    notes: list[str] = []
    if pnl.open_positions_count == 0:
        notes.append("no_open_positions")

    return PortfolioIntelligence(
        nav=pnl.nav,
        cash=pnl.cash,
        invested=pnl.invested,
        cash_pct=cash_pct,
        invested_pct=invested_pct,
        open_positions=pnl.open_positions_count,
        top_positions=top_positions,
        top1_weight=top1,
        top2_weight_sum=top2_sum,
        sector_exposure=sectors,
        regime_mix=regime_mix,
        avg_slippage_bps=avg_slip,
        max_slippage_bps=max_slip,
        flags=flags,
        notes=notes,
    )
