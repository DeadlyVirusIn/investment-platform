"""Weekly rebalance orchestrator.

Pipeline per portfolio:

  1. Load regime_snapshot(as_of) + latest factor snapshots.
  2. Load open positions + latest prices + universe membership.
  3. Apply exit_rules → sell trades (always first).
  4. Load top accepted Buy candidates from candidate_idea.
  5. Size them via portfolio_sizer.
  6. Diff current weights vs target → buy trades for new entries.
  7. Route every trade through ``submit_trade`` with cost_model slippage.
  8. Snapshot equity at end.

Returns a ``RebalanceReport`` summarising the session. Deterministic.
Safe to re-run on the same day (idempotency is enforced by submit_trade
cash/position state, not here).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Sequence

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from apps.api.src.db.models import (
    Asset,
    CandidateIdea,
    PaperPortfolio,
    PaperPosition,
    PriceBar,
    RegimeSnapshot,
    UniverseMembership,
)
from apps.api.src.domain.paper_trading.paper_execution import (
    PaperTradeRejected,
    submit_trade,
)
from apps.api.src.domain.paper_trading.paper_service import snapshot_equity_now
from apps.api.src.domain.stock_engine.portfolio.cost_model import (
    DEFAULT_COMMISSION,
    CostResult,
    cost_for_trade,
)
from apps.api.src.domain.stock_engine.portfolio.exit_rules import (
    PositionView,
    RegimeView,
    evaluate_exits,
)
from apps.api.src.domain.stock_engine.portfolio.portfolio_sizer import (
    MAX_POSITIONS,
    SizingInput,
    size_positions,
)
from apps.api.src.domain.stock_engine.scoring import MODEL_VERSION

DEFAULT_UNIVERSE = "stock_swing_v1"


# ---------------------------------------------------------------------------
# Reporting shapes
# ---------------------------------------------------------------------------


@dataclass
class TradeOutcome:
    asset_id: str
    symbol: str | None
    side: str
    reason: str
    intent: str                       # 'enter' | 'exit'
    status: str                       # 'executed' | 'skipped' | 'failed'
    quantity: Decimal | None = None
    fill_price: Decimal | None = None
    slippage_bps: Decimal | None = None
    commission: Decimal | None = None
    error: str | None = None


@dataclass
class RebalanceReport:
    portfolio_id: str
    as_of_date: dt.date
    regime_snapshot_present: bool
    market_trend: str | None
    vol_regime: str | None
    target_weights: dict[str, Decimal]
    sector_totals: dict[str, Decimal]
    exits: list[TradeOutcome] = field(default_factory=list)
    entries: list[TradeOutcome] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Loading helpers
# ---------------------------------------------------------------------------


def _universe_ids(
    session: Session, universe_name: str, as_of: dt.date,
) -> set[str]:
    stmt = select(UniverseMembership.asset_id).where(
        UniverseMembership.universe_name == universe_name,
        UniverseMembership.start_date <= as_of,
        or_(
            UniverseMembership.end_date.is_(None),
            UniverseMembership.end_date >= as_of,
        ),
    )
    return {row[0] for row in session.execute(stmt).all()}


def _open_positions(
    session: Session, portfolio_id: str,
) -> list[PaperPosition]:
    stmt = (
        select(PaperPosition)
        .where(
            PaperPosition.portfolio_id == portfolio_id,
            PaperPosition.is_open.is_(True),
            PaperPosition.quantity > 0,
        )
    )
    return list(session.scalars(stmt))


def _latest_bar_for_asset(
    session: Session, asset_id: str, as_of: dt.date,
) -> PriceBar | None:
    upper = dt.datetime.combine(
        as_of, dt.time(23, 59, 59, 999999), tzinfo=dt.timezone.utc,
    )
    stmt = (
        select(PriceBar)
        .where(
            PriceBar.asset_id == asset_id,
            PriceBar.timeframe == "1d",
            PriceBar.ts <= upper,
        )
        .order_by(PriceBar.ts.desc())
        .limit(1)
    )
    return session.scalars(stmt).first()


def _symbol_and_sector_map(
    session: Session, asset_ids: list[str],
) -> dict[str, tuple[str, str]]:
    if not asset_ids:
        return {}
    stmt = select(Asset.id, Asset.symbol, Asset.sector, Asset.asset_class).where(
        Asset.id.in_(asset_ids)
    )
    out: dict[str, tuple[str, str]] = {}
    for aid, sym, sector, asset_class in session.execute(stmt).all():
        out[aid] = (sym, sector or asset_class)
    return out


def _top_buy_candidates(
    session: Session, as_of: dt.date, limit: int,
    model_version: str = MODEL_VERSION,
) -> list[CandidateIdea]:
    stmt = (
        select(CandidateIdea)
        .where(
            CandidateIdea.as_of_date == as_of,
            CandidateIdea.status == "accepted",
            CandidateIdea.action == "Buy",
            CandidateIdea.rejection_reason.is_(None),
            CandidateIdea.model_version == model_version,
        )
        .order_by(CandidateIdea.composite_score.desc())
        .limit(limit)
    )
    return list(session.scalars(stmt))


def _adv_from_factor(session: Session, asset_id: str, as_of: dt.date) -> Decimal | None:
    """Pull avg_dollar_volume_20d from the latest factor_snapshot on/before as_of."""
    from apps.api.src.db.models import FactorSnapshot

    stmt = (
        select(FactorSnapshot.avg_dollar_volume_20d)
        .where(
            FactorSnapshot.asset_id == asset_id,
            FactorSnapshot.as_of_date <= as_of,
        )
        .order_by(FactorSnapshot.as_of_date.desc())
        .limit(1)
    )
    row = session.execute(stmt).first()
    if not row or row[0] is None:
        return None
    return row[0] if isinstance(row[0], Decimal) else Decimal(str(row[0]))


# ---------------------------------------------------------------------------
# Execution helpers
# ---------------------------------------------------------------------------


def _cost_from_bar(
    bar: PriceBar | None,
    side: str,
    trade_notional: Decimal,
    adv20: Decimal | None,
) -> CostResult | None:
    if bar is None or bar.close is None or bar.high is None or bar.low is None:
        return None
    return cost_for_trade(
        side=side,
        quote_price=bar.close,
        high=bar.high,
        low=bar.low,
        trade_notional=trade_notional,
        avg_dollar_volume=adv20,
        commission=DEFAULT_COMMISSION,
    )


def _execute_exit(
    session: Session,
    *,
    portfolio_id: str,
    pos: PaperPosition,
    reason: str,
    as_of: dt.date,
    symbols: dict[str, tuple[str, str]],
    submitted_at: dt.datetime,
) -> TradeOutcome:
    sym, _sector = symbols.get(pos.asset_id, (None, "unknown"))
    bar = _latest_bar_for_asset(session, pos.asset_id, as_of)
    adv = _adv_from_factor(session, pos.asset_id, as_of)
    qty = pos.quantity if isinstance(pos.quantity, Decimal) else Decimal(str(pos.quantity))

    if bar is None:
        return TradeOutcome(
            asset_id=pos.asset_id, symbol=sym, side="sell", reason=reason,
            intent="exit", status="skipped",
            error="no price bar available",
        )

    trade_notional = qty * (bar.close or Decimal("0"))
    cost = _cost_from_bar(bar, "sell", trade_notional, adv)
    try:
        result = submit_trade(
            session,
            portfolio_id=portfolio_id, asset_id=pos.asset_id, side="sell",
            quantity=qty, submitted_at=submitted_at,
            reason=f"exit:{reason}",
            fill_price_override=cost.fill_price if cost else None,
            slippage_bps=cost.slippage_bps if cost else None,
            commission=cost.commission if cost else Decimal("0"),
        )
    except PaperTradeRejected as exc:
        return TradeOutcome(
            asset_id=pos.asset_id, symbol=sym, side="sell", reason=reason,
            intent="exit", status="failed", error=str(exc),
        )
    return TradeOutcome(
        asset_id=pos.asset_id, symbol=sym, side="sell", reason=reason,
        intent="exit", status="executed",
        quantity=result.quantity, fill_price=result.fill_price,
        slippage_bps=cost.slippage_bps if cost else None,
        commission=cost.commission if cost else Decimal("0"),
    )


def _execute_entry(
    session: Session,
    *,
    portfolio_id: str,
    asset_id: str,
    usd_amount: Decimal,
    as_of: dt.date,
    symbols: dict[str, tuple[str, str]],
    submitted_at: dt.datetime,
    candidate_id: str | None,
) -> TradeOutcome:
    sym, _sector = symbols.get(asset_id, (None, "unknown"))
    bar = _latest_bar_for_asset(session, asset_id, as_of)
    adv = _adv_from_factor(session, asset_id, as_of)

    if bar is None or bar.close is None or bar.close <= 0:
        return TradeOutcome(
            asset_id=asset_id, symbol=sym, side="buy", reason="rebalance_entry",
            intent="enter", status="skipped",
            error="no price bar available",
        )

    cost = _cost_from_bar(bar, "buy", usd_amount, adv)
    # Recompute qty from cost-adjusted price so cash math ties out.
    fill_px = cost.fill_price if cost else bar.close
    qty = (usd_amount / fill_px).quantize(Decimal("0.0001"))
    if qty <= 0:
        return TradeOutcome(
            asset_id=asset_id, symbol=sym, side="buy", reason="rebalance_entry",
            intent="enter", status="skipped",
            error="zero quantity after sizing",
        )

    try:
        result = submit_trade(
            session,
            portfolio_id=portfolio_id, asset_id=asset_id, side="buy",
            quantity=qty, submitted_at=submitted_at,
            reason="rebalance_entry",
            fill_price_override=fill_px,
            slippage_bps=cost.slippage_bps if cost else None,
            commission=cost.commission if cost else Decimal("0"),
        )
    except PaperTradeRejected as exc:
        return TradeOutcome(
            asset_id=asset_id, symbol=sym, side="buy", reason="rebalance_entry",
            intent="enter", status="failed", error=str(exc),
        )
    _ = candidate_id  # reserved for future linkage
    return TradeOutcome(
        asset_id=asset_id, symbol=sym, side="buy", reason="rebalance_entry",
        intent="enter", status="executed",
        quantity=result.quantity, fill_price=result.fill_price,
        slippage_bps=cost.slippage_bps if cost else None,
        commission=cost.commission if cost else Decimal("0"),
    )


# ---------------------------------------------------------------------------
# Core orchestrator
# ---------------------------------------------------------------------------


def run_rebalance(
    session: Session,
    portfolio: PaperPortfolio,
    *,
    as_of: dt.date,
    now: dt.datetime | None = None,
    universe_name: str = DEFAULT_UNIVERSE,
    max_positions: int = MAX_POSITIONS,
) -> RebalanceReport:
    submitted_at = now or dt.datetime.combine(
        as_of, dt.time(13, 30), tzinfo=dt.timezone.utc,
    )

    # Context
    regime = session.get(RegimeSnapshot, as_of)
    universe_ids = _universe_ids(session, universe_name, as_of)
    positions = _open_positions(session, portfolio.id)

    # Prices for held assets
    price_map: dict[str, Decimal | None] = {}
    for pos in positions:
        bar = _latest_bar_for_asset(session, pos.asset_id, as_of)
        price_map[pos.asset_id] = bar.close if bar is not None else None

    regime_view = RegimeView(
        market_trend=regime.market_trend if regime is not None else None,
    )

    # 1. Exits (always evaluated first)
    position_views = [
        PositionView(
            asset_id=p.asset_id,
            quantity=(p.quantity if isinstance(p.quantity, Decimal) else Decimal(str(p.quantity))),
            avg_cost=(p.avg_cost if isinstance(p.avg_cost, Decimal) else Decimal(str(p.avg_cost))),
            opened_at=p.opened_at,
        )
        for p in positions
    ]
    exit_decisions = evaluate_exits(
        positions=position_views,
        prices_by_asset=price_map,
        regime=regime_view,
        universe_asset_ids=universe_ids,
        now=submitted_at,
    )
    exit_asset_ids = {e.asset_id for e in exit_decisions}

    held_symbols = _symbol_and_sector_map(session, [p.asset_id for p in positions])

    exit_outcomes: list[TradeOutcome] = []
    exits_by_asset = {e.asset_id: e for e in exit_decisions}
    for pos in positions:
        if pos.asset_id not in exit_asset_ids:
            continue
        reason = exits_by_asset[pos.asset_id].reason
        exit_outcomes.append(
            _execute_exit(
                session,
                portfolio_id=portfolio.id, pos=pos, reason=reason,
                as_of=as_of, symbols=held_symbols, submitted_at=submitted_at,
            )
        )

    # Downtrend or missing regime → no new entries.
    notes: list[str] = []
    if regime is None:
        notes.append("regime_missing_no_entries")
        sizing_inputs: Sequence[SizingInput] = ()
    elif regime.market_trend == "downtrend":
        notes.append("downtrend_no_entries")
        sizing_inputs = ()
    else:
        candidates = _top_buy_candidates(session, as_of, limit=max_positions)
        sym_sect = _symbol_and_sector_map(session, [c.asset_id for c in candidates])
        sizing_inputs = [
            SizingInput(
                asset_id=c.asset_id,
                composite_score=c.composite_score if c.composite_score is not None else Decimal("0"),
                confidence=c.confidence if c.confidence is not None else Decimal("0"),
                sector=sym_sect.get(c.asset_id, ("", "unknown"))[1],
            )
            for c in candidates
        ]

    # 2. Size
    sizing = size_positions(sizing_inputs, max_positions=max_positions)

    # 3. Diff vs current (skip assets we just exited; skip assets already held)
    held_after_exit_ids = {
        p.asset_id for p in positions if p.asset_id not in exit_asset_ids
    }
    entry_weights: dict[str, Decimal] = {
        aid: w for aid, w in sizing.target_weights.items()
        if aid not in held_after_exit_ids
    }

    # Compute NAV snapshot (pre-entry) to size USD — base on cash + current
    # position market value.
    cash = portfolio.cash if isinstance(portfolio.cash, Decimal) else Decimal(str(portfolio.cash))
    position_mv = Decimal("0")
    for pos in positions:
        if pos.asset_id in exit_asset_ids:
            continue
        px = price_map.get(pos.asset_id) or Decimal("0")
        qty = pos.quantity if isinstance(pos.quantity, Decimal) else Decimal(str(pos.quantity))
        position_mv += qty * px
    nav = cash + position_mv

    # Also refresh cash post-exit for entry budgeting. After exits run,
    # portfolio.cash is updated by submit_trade; re-read.
    session.flush()
    cash_after_exits = portfolio.cash if isinstance(portfolio.cash, Decimal) else Decimal(str(portfolio.cash))

    entries: list[TradeOutcome] = []
    entry_symbols = _symbol_and_sector_map(
        session, list(entry_weights.keys()),
    )
    for asset_id, weight in sorted(
        entry_weights.items(),
        key=lambda kv: (-float(kv[1]), kv[0]),
    ):
        usd = (weight * nav).quantize(Decimal("0.01"))
        if usd <= 0:
            continue
        if usd > cash_after_exits:
            entries.append(TradeOutcome(
                asset_id=asset_id, symbol=entry_symbols.get(asset_id, (None, ""))[0],
                side="buy", reason="rebalance_entry", intent="enter",
                status="skipped",
                error=f"insufficient_cash (need {usd}, have {cash_after_exits})",
            ))
            continue
        outcome = _execute_entry(
            session,
            portfolio_id=portfolio.id, asset_id=asset_id,
            usd_amount=usd, as_of=as_of, symbols=entry_symbols,
            submitted_at=submitted_at, candidate_id=None,
        )
        if outcome.status == "executed" and outcome.fill_price is not None and outcome.quantity is not None:
            cash_after_exits -= outcome.quantity * outcome.fill_price
        entries.append(outcome)

    # 4. End-of-run equity snapshot
    # P6a (M079): snapshot_equity_now now requires an explicit source.
    # The live rebalance path writes a live snapshot. (Deployed image
    # still calls this without source — latent TypeError if reached;
    # this compatibility update fixes it under the required-source API.)
    snapshot_equity_now(session, portfolio, as_of=submitted_at, source="live")

    return RebalanceReport(
        portfolio_id=portfolio.id,
        as_of_date=as_of,
        regime_snapshot_present=regime is not None,
        market_trend=regime.market_trend if regime is not None else None,
        vol_regime=regime.vol_regime if regime is not None else None,
        target_weights=sizing.target_weights,
        sector_totals=sizing.sector_totals,
        exits=exit_outcomes,
        entries=entries,
        notes=notes,
    )
