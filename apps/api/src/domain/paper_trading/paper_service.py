"""Paper-portfolio lifecycle + equity computation + trade log retrieval."""

from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from apps.api.src.db.models import (
    Asset,
    PaperEquitySnapshot,
    PaperPortfolio,
    PaperPosition,
    PaperTrade,
    PriceBar,
)
from apps.api.src.domain.paper_trading.paper_execution import (
    DEFAULT_MAX_OPEN_POSITIONS,
    DEFAULT_SIZING_PCT,
    _compute_current_equity,
    _d,
)

DEFAULT_STARTING_CASH = Decimal("1000.00")


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class PortfolioCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    starting_cash: Decimal = Field(default=DEFAULT_STARTING_CASH, gt=0)
    sizing_pct_of_equity: Decimal | None = Field(default=None, gt=0, le=1)
    max_open_positions: int | None = Field(default=None, gt=0, le=100)


class TradeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: str | None = None
    symbol: str | None = None
    side: Literal["buy", "sell"]
    quantity: Decimal | None = Field(default=None, gt=0)
    usd_amount: Decimal | None = Field(default=None, gt=0)
    submitted_at: dt.datetime | None = None
    reason: str | None = None
    recommendation_id: str | None = None


# ---------------------------------------------------------------------------
# Portfolio CRUD
# ---------------------------------------------------------------------------


def create_portfolio(session: Session, payload: PortfolioCreate) -> PaperPortfolio:
    existing = session.scalars(
        select(PaperPortfolio).where(PaperPortfolio.name == payload.name)
    ).first()
    if existing is not None:
        raise ValueError(f"portfolio name already in use: {payload.name!r}")

    config = {
        "sizing_pct_of_equity": str(payload.sizing_pct_of_equity or DEFAULT_SIZING_PCT),
        "max_open_positions": int(
            payload.max_open_positions or DEFAULT_MAX_OPEN_POSITIONS
        ),
    }
    portfolio = PaperPortfolio(
        name=payload.name,
        starting_cash=payload.starting_cash,
        cash=payload.starting_cash,
        config_json=json.dumps(config),
        is_active=True,
    )
    session.add(portfolio)
    session.flush()
    return portfolio


USER_STOCK_STARTING_CASH = Decimal("100000")


def user_stock_portfolio_name(user_id: str) -> str:
    """Canonical name of a user's own stock paper book."""
    return f"user:{user_id[:64]}:stock"


def resolve_user_stock_portfolio(session: Session, user_id: str) -> str:
    """Get-or-create the caller's OWN stock paper book (``user:<id>:stock``).

    SINGLE source of per-user portfolio resolution — used by BOTH the read
    endpoint (/paper/canonical/stock) and the write endpoints (add-to-paper,
    follow). They therefore can never diverge, and a cold device gets a fresh
    EMPTY personal book, never the shared demo/Replay-Recovery portfolio.
    Race-safe: a lost create (unique-name collision) re-selects.
    """
    name = user_stock_portfolio_name(user_id)
    pf = session.scalars(
        select(PaperPortfolio).where(PaperPortfolio.name == name)
    ).first()
    if pf is not None:
        return pf.id
    try:
        created = create_portfolio(
            session,
            PortfolioCreate(
                name=name,
                starting_cash=USER_STOCK_STARTING_CASH,
                max_open_positions=100,
            ),
        )
        return created.id
    except ValueError:
        # Lost a create race against a concurrent request — re-select.
        again = session.scalars(
            select(PaperPortfolio).where(PaperPortfolio.name == name)
        ).first()
        if again is None:
            raise
        return again.id


def list_portfolios(session: Session) -> list[PaperPortfolio]:
    stmt = select(PaperPortfolio).order_by(
        PaperPortfolio.created_at.asc(), PaperPortfolio.id.asc()
    )
    return list(session.scalars(stmt))


def get_portfolio(session: Session, portfolio_id: str) -> PaperPortfolio | None:
    return session.get(PaperPortfolio, portfolio_id)


def resolve_asset_id(
    session: Session, asset_id: str | None, symbol: str | None
) -> str:
    if asset_id:
        if session.get(Asset, asset_id) is None:
            raise ValueError(f"unknown asset_id: {asset_id}")
        return asset_id
    if symbol:
        asset = session.scalars(select(Asset).where(Asset.symbol == symbol)).first()
        if asset is None:
            raise ValueError(f"unknown symbol: {symbol}")
        return asset.id
    raise ValueError("asset_id or symbol required")


# ---------------------------------------------------------------------------
# Equity + snapshot
# ---------------------------------------------------------------------------


def compute_equity_breakdown(
    session: Session, portfolio: PaperPortfolio
) -> dict[str, Any]:
    """Return cash, positions_value, total_equity, unrealized_pnl,
    realized_pnl_cumulative."""
    cash = _d(portfolio.cash)
    open_positions = session.scalars(
        select(PaperPosition).where(
            PaperPosition.portfolio_id == portfolio.id,
            PaperPosition.is_open.is_(True),
        )
    ).all()

    positions_value = Decimal("0")
    unrealized = Decimal("0")
    for pos in open_positions:
        bar = session.scalars(
            select(PriceBar)
            .where(PriceBar.asset_id == pos.asset_id, PriceBar.timeframe == "1d")
            .order_by(PriceBar.ts.desc())
            .limit(1)
        ).first()
        last_price = (
            _d(bar.close if bar.close is not None else bar.open)
            if bar is not None else _d(pos.avg_cost)
        )
        qty = _d(pos.quantity)
        mv = qty * last_price
        positions_value += mv
        unrealized += qty * (last_price - _d(pos.avg_cost))

    realized = _d(
        session.execute(
            select(func.coalesce(func.sum(PaperTrade.realized_pnl), 0))
            .where(PaperTrade.portfolio_id == portfolio.id)
        ).scalar()
    )

    total_equity = cash + positions_value
    return {
        "cash": cash,
        "positions_value": positions_value,
        "total_equity": total_equity,
        "unrealized_pnl": unrealized,
        "realized_pnl_cumulative": realized,
    }


_ALLOWED_SNAPSHOT_SOURCES = frozenset(
    {"live", "replay", "backfill", "operator_manual"}
)


def snapshot_equity_now(
    session: Session,
    portfolio: PaperPortfolio,
    *,
    as_of: dt.datetime | None = None,
    source: str,
) -> PaperEquitySnapshot:
    """P6D.35C — UPSERT the equity snapshot (last writer wins).

    One row per (portfolio_id, snapshot_date, source) — PostgreSQL
    INSERT ... ON CONFLICT ON CONSTRAINT uq_paper_equity_snapshot
    DO UPDATE. A second write into the same (portfolio, calendar date,
    source) cell overwrites ALL value columns (cash, positions_value,
    total_equity, unrealized_pnl, realized_pnl_cumulative) and advances
    `recorded_at` to the new write time; the original row's `id` and
    `created_at` are preserved.

    Truth contract (Phase L M079, amended by P6D.35C):
      - every call MUST specify `source` explicitly (raises ValueError
        otherwise);
      - rows in OTHER (date, source) cells are never modified — replay
        writes (`source='replay'`) can never rewrite live history;
      - canonical user-facing readers MUST filter `source='live'` to
        honor presentation immutability
        (docs/research/M083_CANONICAL_SEMANTIC.md).
    """
    if source not in _ALLOWED_SNAPSHOT_SOURCES:
        raise ValueError(
            f"snapshot_equity_now: source must be one of "
            f"{sorted(_ALLOWED_SNAPSHOT_SOURCES)}, got {source!r}"
        )

    now = as_of or dt.datetime.now(dt.timezone.utc)
    snapshot_date = now.replace(hour=0, minute=0, second=0, microsecond=0)

    breakdown = compute_equity_breakdown(session, portfolio)

    stmt = pg_insert(PaperEquitySnapshot).values(
        portfolio_id=portfolio.id,
        snapshot_date=snapshot_date,
        cash=breakdown["cash"],
        positions_value=breakdown["positions_value"],
        total_equity=breakdown["total_equity"],
        unrealized_pnl=breakdown["unrealized_pnl"],
        realized_pnl_cumulative=breakdown["realized_pnl_cumulative"],
        recorded_at=dt.datetime.now(dt.timezone.utc),
        source=source,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_paper_equity_snapshot",
        set_={
            "cash": stmt.excluded.cash,
            "positions_value": stmt.excluded.positions_value,
            "total_equity": stmt.excluded.total_equity,
            "unrealized_pnl": stmt.excluded.unrealized_pnl,
            "realized_pnl_cumulative": stmt.excluded.realized_pnl_cumulative,
            "recorded_at": stmt.excluded.recorded_at,
        },
    ).returning(PaperEquitySnapshot.id)

    snapshot_id = session.execute(stmt).scalar_one()
    snap = session.get(PaperEquitySnapshot, snapshot_id)
    if snap is None:  # pragma: no cover — row was just upserted
        raise RuntimeError(
            f"snapshot_equity_now: upserted snapshot {snapshot_id} not found"
        )
    # The identity map may hold the pre-UPSERT state of an existing row;
    # refresh so callers observe the post-write values.
    session.refresh(snap)
    return snap


def get_equity_curve(
    session: Session,
    portfolio_id: str,
    limit: int = 365,
    *,
    source: str = "live",
) -> list[PaperEquitySnapshot]:
    """Canonical equity-curve reader.

    Phase L M079: defaults to `source='live'` (presentation immutability).
    Forensic / operator callers may pass another source explicitly.
    """
    stmt = (
        select(PaperEquitySnapshot)
        .where(
            PaperEquitySnapshot.portfolio_id == portfolio_id,
            PaperEquitySnapshot.source == source,
        )
        .order_by(PaperEquitySnapshot.snapshot_date.asc())
        .limit(limit)
    )
    return list(session.scalars(stmt))


# ---------------------------------------------------------------------------
# Positions + trade log
# ---------------------------------------------------------------------------


def list_open_positions(session: Session, portfolio_id: str) -> list[dict[str, Any]]:
    stmt = (
        select(PaperPosition, Asset)
        .join(Asset, PaperPosition.asset_id == Asset.id)
        .where(
            PaperPosition.portfolio_id == portfolio_id,
            PaperPosition.is_open.is_(True),
        )
        .order_by(Asset.symbol.asc())
    )
    out: list[dict[str, Any]] = []
    for pos, asset in session.execute(stmt).all():
        bar = session.scalars(
            select(PriceBar)
            .where(PriceBar.asset_id == pos.asset_id, PriceBar.timeframe == "1d")
            .order_by(PriceBar.ts.desc())
            .limit(1)
        ).first()
        last_price = None
        if bar is not None:
            last_price = _d(bar.close if bar.close is not None else bar.open)
        qty = _d(pos.quantity)
        basis = _d(pos.avg_cost)
        market_value = qty * last_price if last_price is not None else None
        unrealized = (
            qty * (last_price - basis) if last_price is not None else None
        )
        out.append({
            "position_id": pos.id,
            "asset_id": pos.asset_id,
            "symbol": asset.symbol,
            "quantity": qty,
            "avg_cost": basis,
            "last_price": last_price,
            "market_value": market_value,
            "unrealized_pnl": unrealized,
            "opened_at": pos.opened_at.isoformat() if pos.opened_at else None,
        })
    return out


def list_trades(
    session: Session, portfolio_id: str, limit: int = 500
) -> list[dict[str, Any]]:
    stmt = (
        select(PaperTrade, Asset)
        .join(Asset, PaperTrade.asset_id == Asset.id)
        .where(PaperTrade.portfolio_id == portfolio_id)
        .order_by(PaperTrade.fill_ts.desc())
        .limit(limit)
    )
    out: list[dict[str, Any]] = []
    for trade, asset in session.execute(stmt).all():
        out.append({
            "trade_id": trade.id,
            "asset_id": trade.asset_id,
            "symbol": asset.symbol,
            "side": trade.side,
            "quantity": _d(trade.quantity),
            "fill_price": _d(trade.fill_price),
            "fill_ts": trade.fill_ts.isoformat() if trade.fill_ts else None,
            "submitted_at": trade.submitted_at.isoformat() if trade.submitted_at else None,
            "realized_pnl": _d(trade.realized_pnl) if trade.realized_pnl is not None else None,
            "reason": trade.reason,
            "recommendation_id": trade.recommendation_id,
        })
    return out


def trade_counts(session: Session, portfolio_id: str) -> dict[str, int]:
    """Winning / losing / break-even counts among SELL trades (has realized_pnl)."""
    stmt = (
        select(PaperTrade.realized_pnl)
        .where(
            PaperTrade.portfolio_id == portfolio_id,
            PaperTrade.side == "sell",
            PaperTrade.realized_pnl.isnot(None),
        )
    )
    wins = losses = breakeven = 0
    for (pnl,) in session.execute(stmt).all():
        if pnl is None:
            continue
        pnl_d = _d(pnl)
        if pnl_d > 0:
            wins += 1
        elif pnl_d < 0:
            losses += 1
        else:
            breakeven += 1
    return {"wins": wins, "losses": losses, "breakeven": breakeven}


# ---------------------------------------------------------------------------
# Validation layer
# ---------------------------------------------------------------------------


def compute_paper_max_drawdown(
    snapshots: list[PaperEquitySnapshot],
) -> dict[str, Any]:
    """Compute max peak-to-trough drawdown + duration from the equity curve.

    Returns {"max_drawdown_pct", "max_drawdown_duration_days", "peak_equity",
    "trough_equity"}. Fields are None when insufficient data.
    """
    if len(snapshots) < 2:
        return {
            "max_drawdown_pct": None,
            "max_drawdown_duration_days": None,
            "peak_equity": None,
            "trough_equity": None,
        }
    sorted_snaps = sorted(snapshots, key=lambda s: s.snapshot_date)
    peak = _d(sorted_snaps[0].total_equity)
    peak_idx = 0
    worst_dd = Decimal("0")
    worst_trough_idx = 0
    worst_peak_idx = 0

    for i, s in enumerate(sorted_snaps):
        eq = _d(s.total_equity)
        if eq > peak:
            peak = eq
            peak_idx = i
        if peak > 0:
            dd = (eq - peak) / peak   # <= 0
            if dd < worst_dd:
                worst_dd = dd
                worst_trough_idx = i
                worst_peak_idx = peak_idx

    if worst_dd >= 0:
        return {
            "max_drawdown_pct": None,
            "max_drawdown_duration_days": None,
            "peak_equity": None,
            "trough_equity": None,
        }

    duration_days = (
        sorted_snaps[worst_trough_idx].snapshot_date
        - sorted_snaps[worst_peak_idx].snapshot_date
    ).days
    return {
        "max_drawdown_pct": worst_dd,
        "max_drawdown_duration_days": max(duration_days, 0),
        "peak_equity": _d(sorted_snaps[worst_peak_idx].total_equity),
        "trough_equity": _d(sorted_snaps[worst_trough_idx].total_equity),
    }


def _confidence_bucket(conf: Decimal | None) -> str:
    if conf is None:
        return "Unknown"
    if conf < Decimal("30"):
        return "Low (0-30)"
    if conf < Decimal("60"):
        return "Medium (30-60)"
    return "High (60-100)"


def compute_confidence_validation(
    session: Session, portfolio_id: str
) -> list[dict[str, Any]]:
    """For closed (sell) trades linked to a Recommendation, bucket by the
    recommendation's conviction and report count + hit_rate + avg realized P&L.

    Hit rate here = fraction of closed trades with positive realized_pnl.
    """
    from apps.api.src.db.models import Recommendation

    stmt = (
        select(PaperTrade, Recommendation.conviction)
        .outerjoin(Recommendation, PaperTrade.recommendation_id == Recommendation.id)
        .where(
            PaperTrade.portfolio_id == portfolio_id,
            PaperTrade.side == "sell",
            PaperTrade.realized_pnl.isnot(None),
        )
    )
    buckets: dict[str, dict[str, Any]] = {
        "Low (0-30)": {"wins": 0, "losses": 0, "sum_pnl": Decimal("0"), "count": 0},
        "Medium (30-60)": {"wins": 0, "losses": 0, "sum_pnl": Decimal("0"), "count": 0},
        "High (60-100)": {"wins": 0, "losses": 0, "sum_pnl": Decimal("0"), "count": 0},
        "Unknown": {"wins": 0, "losses": 0, "sum_pnl": Decimal("0"), "count": 0},
    }

    for trade, conviction in session.execute(stmt).all():
        conf = _d(conviction) if conviction is not None else None
        bucket = _confidence_bucket(conf)
        pnl = _d(trade.realized_pnl)
        b = buckets[bucket]
        b["count"] += 1
        b["sum_pnl"] += pnl
        if pnl > 0:
            b["wins"] += 1
        elif pnl < 0:
            b["losses"] += 1

    out = []
    for label in ("Low (0-30)", "Medium (30-60)", "High (60-100)", "Unknown"):
        b = buckets[label]
        decisive = b["wins"] + b["losses"]
        hit_rate = (Decimal(b["wins"]) / Decimal(decisive)) if decisive else None
        avg_pnl = (b["sum_pnl"] / Decimal(b["count"])) if b["count"] else None
        out.append({
            "bucket": label,
            "count": b["count"],
            "wins": b["wins"],
            "losses": b["losses"],
            "hit_rate": hit_rate,
            "avg_realized_pnl": avg_pnl,
        })
    return out
