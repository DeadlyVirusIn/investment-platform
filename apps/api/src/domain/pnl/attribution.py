"""PnL attribution + blocked-alpha counterfactual simulator.

Trade → candidate_idea linkage: for each asset traded by a portfolio, find
the candidate_idea with ``as_of_date <= first_buy_ts.date()`` closest to
the first buy. That row's ``composite_score`` and JSON regime snapshot are
the entry context.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from apps.api.src.db.models import (
    Asset,
    CandidateIdea,
    PaperPortfolio,
    PaperTrade,
    PriceBar,
)

SCORE_BUCKETS: tuple[tuple[str, Decimal, Decimal], ...] = (
    ("0.25-0.35", Decimal("0.25"), Decimal("0.35")),
    ("0.35-0.45", Decimal("0.35"), Decimal("0.45")),
    ("0.45+",     Decimal("0.45"), Decimal("1.0001")),
)
UNCLASSIFIED_BUCKET = "unclassified"

DEFAULT_BLOCKED_MIN_SCORE = Decimal("0.25")
DEFAULT_BLOCKED_HORIZON_DAYS = 14   # ~10 trading days, calendar-day approx


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _d(v: object) -> Decimal:
    if v is None:
        return Decimal("0")
    return v if isinstance(v, Decimal) else Decimal(str(v))


def _first_buy_ts_by_asset(
    session: Session, portfolio_id: str,
) -> dict[str, dt.datetime]:
    stmt = (
        select(PaperTrade.asset_id, PaperTrade.fill_ts)
        .where(
            PaperTrade.portfolio_id == portfolio_id,
            PaperTrade.side == "buy",
        )
        .order_by(PaperTrade.fill_ts.asc())
    )
    out: dict[str, dt.datetime] = {}
    for aid, ts in session.execute(stmt).all():
        out.setdefault(aid, ts)
    return out


def _resolve_entry_candidate(
    session: Session, asset_id: str, first_buy: dt.datetime,
) -> CandidateIdea | None:
    """Candidate row with as_of_date <= first_buy.date(), most recent."""
    stmt = (
        select(CandidateIdea)
        .where(
            CandidateIdea.asset_id == asset_id,
            CandidateIdea.as_of_date <= first_buy.date(),
            CandidateIdea.status == "accepted",
        )
        .order_by(desc(CandidateIdea.as_of_date))
        .limit(1)
    )
    return session.scalars(stmt).first()


def entry_context_map(
    session: Session, portfolio_id: str,
) -> dict[str, dict[str, Any]]:
    """asset_id → {composite_score, confidence, market_trend, vol_regime}."""
    out: dict[str, dict[str, Any]] = {}
    firsts = _first_buy_ts_by_asset(session, portfolio_id)
    for aid, ts in firsts.items():
        cand = _resolve_entry_candidate(session, aid, ts)
        if cand is None:
            continue
        reg = cand.regime_snapshot or {}
        out[aid] = {
            "composite_score": cand.composite_score,
            "confidence": cand.confidence,
            "market_trend": reg.get("market_trend") if isinstance(reg, dict) else None,
            "vol_regime": reg.get("vol_regime") if isinstance(reg, dict) else None,
            "as_of_date": cand.as_of_date.isoformat(),
        }
    return out


# ---------------------------------------------------------------------------
# Score-bucket attribution
# ---------------------------------------------------------------------------


@dataclass
class BucketStat:
    bucket: str
    trade_count: int
    wins: int
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    total_pnl: Decimal
    avg_pnl_per_trade: Decimal | None


def _bucket_for(score: Decimal | None) -> str:
    if score is None:
        return UNCLASSIFIED_BUCKET
    for label, lo, hi in SCORE_BUCKETS:
        if lo <= score < hi:
            return label
    return UNCLASSIFIED_BUCKET


def attribution_by_score_bucket(
    session: Session, portfolio: PaperPortfolio,
    now: dt.datetime | None = None,
) -> list[BucketStat]:
    from apps.api.src.domain.pnl.engine import per_symbol_pnl

    rows = per_symbol_pnl(session, portfolio, now=now)
    agg: dict[str, dict[str, Decimal | int]] = {}
    # Ensure defined buckets always appear
    for label, _lo, _hi in SCORE_BUCKETS:
        agg[label] = {
            "trade_count": 0, "wins": 0,
            "realized_pnl": Decimal("0"), "unrealized_pnl": Decimal("0"),
            "total_pnl": Decimal("0"),
        }
    agg[UNCLASSIFIED_BUCKET] = {
        "trade_count": 0, "wins": 0,
        "realized_pnl": Decimal("0"), "unrealized_pnl": Decimal("0"),
        "total_pnl": Decimal("0"),
    }

    for r in rows:
        bucket = _bucket_for(
            _d(r.entry_composite_score) if r.entry_composite_score is not None else None
        )
        if r.entry_composite_score is None:
            bucket = UNCLASSIFIED_BUCKET
        entry = agg[bucket]
        entry["trade_count"] += 1
        if r.total_pnl > 0:
            entry["wins"] += 1
        entry["realized_pnl"] += r.realized_pnl
        entry["unrealized_pnl"] += r.unrealized_pnl
        entry["total_pnl"] += r.total_pnl

    out: list[BucketStat] = []
    for label in [b[0] for b in SCORE_BUCKETS] + [UNCLASSIFIED_BUCKET]:
        e = agg[label]
        n = int(e["trade_count"])
        total = e["total_pnl"]
        avg = total / Decimal(n) if n > 0 else None
        out.append(BucketStat(
            bucket=label,
            trade_count=n,
            wins=int(e["wins"]),
            realized_pnl=e["realized_pnl"],
            unrealized_pnl=e["unrealized_pnl"],
            total_pnl=total,
            avg_pnl_per_trade=avg,
        ))
    return out


# ---------------------------------------------------------------------------
# Regime attribution
# ---------------------------------------------------------------------------


@dataclass
class RegimeStat:
    market_trend: str
    vol_regime: str
    trade_count: int
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    total_pnl: Decimal
    avg_pnl_per_trade: Decimal | None


STANDARD_REGIMES: tuple[tuple[str, str], ...] = (
    ("uptrend",  "low"),
    ("uptrend",  "normal"),
    ("uptrend",  "high"),
    ("sideways", "low"),
    ("sideways", "normal"),
    ("sideways", "high"),
)


def attribution_by_regime(
    session: Session, portfolio: PaperPortfolio,
    now: dt.datetime | None = None,
) -> list[RegimeStat]:
    from apps.api.src.domain.pnl.engine import per_symbol_pnl

    rows = per_symbol_pnl(session, portfolio, now=now)
    agg: dict[tuple[str, str], dict[str, Decimal | int]] = {}
    for key in STANDARD_REGIMES:
        agg[key] = {
            "trade_count": 0,
            "realized_pnl": Decimal("0"), "unrealized_pnl": Decimal("0"),
            "total_pnl": Decimal("0"),
        }
    agg[("other", "other")] = {
        "trade_count": 0,
        "realized_pnl": Decimal("0"), "unrealized_pnl": Decimal("0"),
        "total_pnl": Decimal("0"),
    }

    for r in rows:
        trend = r.entry_market_trend or "other"
        vol = r.entry_vol_regime or "other"
        key = (trend, vol) if (trend, vol) in agg else ("other", "other")
        entry = agg[key]
        entry["trade_count"] += 1
        entry["realized_pnl"] += r.realized_pnl
        entry["unrealized_pnl"] += r.unrealized_pnl
        entry["total_pnl"] += r.total_pnl

    out: list[RegimeStat] = []
    for (trend, vol), e in agg.items():
        n = int(e["trade_count"])
        total = e["total_pnl"]
        avg = total / Decimal(n) if n > 0 else None
        out.append(RegimeStat(
            market_trend=trend, vol_regime=vol,
            trade_count=n,
            realized_pnl=e["realized_pnl"],
            unrealized_pnl=e["unrealized_pnl"],
            total_pnl=total,
            avg_pnl_per_trade=avg,
        ))
    return out


# ---------------------------------------------------------------------------
# Blocked-alpha counterfactual
# ---------------------------------------------------------------------------


@dataclass
class SimTrade:
    asset_id: str
    symbol: str | None
    rejection_reason: str
    composite_score: Decimal
    as_of_date: dt.date
    entry_date: dt.date | None
    entry_price: Decimal | None
    exit_date: dt.date | None
    exit_price: Decimal | None
    return_pct: Decimal | None


@dataclass
class BlockedAlphaReport:
    min_score: Decimal
    horizon_days: int
    from_date: dt.date
    to_date: dt.date
    simulated_count: int
    skipped_count: int
    avg_return: Decimal | None
    total_return: Decimal
    wins: int
    losses: int
    win_rate: Decimal | None
    top_winners: list[SimTrade]
    top_losers: list[SimTrade]


BLOCKED_REASONS: tuple[str, ...] = ("regime_off", "high_vol_topn_overflow")


def _next_trading_day_close(
    session: Session, asset_id: str, after_date: dt.date,
) -> tuple[dt.date, Decimal] | None:
    upper_lower = dt.datetime.combine(
        after_date + dt.timedelta(days=1),
        dt.time(0, 0, 0), tzinfo=dt.timezone.utc,
    )
    stmt = (
        select(PriceBar.ts, PriceBar.close)
        .where(
            PriceBar.asset_id == asset_id,
            PriceBar.timeframe == "1d",
            PriceBar.ts >= upper_lower,
        )
        .order_by(PriceBar.ts.asc())
        .limit(1)
    )
    row = session.execute(stmt).first()
    if row is None or row[1] is None:
        return None
    return row[0].date(), _d(row[1])


def _close_on_or_before(
    session: Session, asset_id: str, target: dt.date,
) -> tuple[dt.date, Decimal] | None:
    upper = dt.datetime.combine(
        target, dt.time(23, 59, 59, 999999), tzinfo=dt.timezone.utc,
    )
    stmt = (
        select(PriceBar.ts, PriceBar.close)
        .where(
            PriceBar.asset_id == asset_id,
            PriceBar.timeframe == "1d",
            PriceBar.ts <= upper,
        )
        .order_by(desc(PriceBar.ts))
        .limit(1)
    )
    row = session.execute(stmt).first()
    if row is None or row[1] is None:
        return None
    return row[0].date(), _d(row[1])


def blocked_alpha_sim(
    session: Session,
    *,
    min_score: Decimal = DEFAULT_BLOCKED_MIN_SCORE,
    horizon_days: int = DEFAULT_BLOCKED_HORIZON_DAYS,
    from_date: dt.date | None = None,
    to_date: dt.date | None = None,
) -> BlockedAlphaReport:
    end = to_date or dt.date.today()
    start = from_date or (end - dt.timedelta(days=90))

    stmt = (
        select(CandidateIdea, Asset.symbol)
        .join(Asset, Asset.id == CandidateIdea.asset_id)
        .where(
            CandidateIdea.as_of_date >= start,
            CandidateIdea.as_of_date <= end,
            CandidateIdea.status == "rejected",
            CandidateIdea.rejection_reason.in_(BLOCKED_REASONS),
            CandidateIdea.composite_score.is_not(None),
            CandidateIdea.composite_score >= min_score,
        )
        .order_by(CandidateIdea.as_of_date.asc())
    )

    sims: list[SimTrade] = []
    skipped = 0
    for cand, symbol in session.execute(stmt).all():
        entry = _next_trading_day_close(session, cand.asset_id, cand.as_of_date)
        if entry is None:
            # Fallback to as_of close if no later bar exists
            entry = _close_on_or_before(session, cand.asset_id, cand.as_of_date)
        if entry is None:
            skipped += 1
            sims.append(SimTrade(
                asset_id=cand.asset_id, symbol=symbol,
                rejection_reason=cand.rejection_reason or "",
                composite_score=_d(cand.composite_score),
                as_of_date=cand.as_of_date,
                entry_date=None, entry_price=None,
                exit_date=None, exit_price=None, return_pct=None,
            ))
            continue
        entry_date, entry_price = entry
        target_exit = entry_date + dt.timedelta(days=horizon_days)
        exit_ = _close_on_or_before(session, cand.asset_id, target_exit)
        if exit_ is None or exit_[1] is None or entry_price <= 0:
            skipped += 1
            sims.append(SimTrade(
                asset_id=cand.asset_id, symbol=symbol,
                rejection_reason=cand.rejection_reason or "",
                composite_score=_d(cand.composite_score),
                as_of_date=cand.as_of_date,
                entry_date=entry_date, entry_price=entry_price,
                exit_date=None, exit_price=None, return_pct=None,
            ))
            continue
        exit_date, exit_price = exit_
        ret = (exit_price - entry_price) / entry_price
        sims.append(SimTrade(
            asset_id=cand.asset_id, symbol=symbol,
            rejection_reason=cand.rejection_reason or "",
            composite_score=_d(cand.composite_score),
            as_of_date=cand.as_of_date,
            entry_date=entry_date, entry_price=entry_price,
            exit_date=exit_date, exit_price=exit_price,
            return_pct=ret,
        ))

    valid = [s for s in sims if s.return_pct is not None]
    wins = sum(1 for s in valid if s.return_pct > 0)
    losses = sum(1 for s in valid if s.return_pct < 0)
    decisive = wins + losses
    win_rate = Decimal(wins) / Decimal(decisive) if decisive > 0 else None
    total = sum((s.return_pct for s in valid), Decimal("0"))
    avg = total / Decimal(len(valid)) if valid else None
    top_winners = sorted(valid, key=lambda s: s.return_pct, reverse=True)[:5]
    top_losers = sorted(valid, key=lambda s: s.return_pct)[:5]

    return BlockedAlphaReport(
        min_score=min_score, horizon_days=horizon_days,
        from_date=start, to_date=end,
        simulated_count=len(valid),
        skipped_count=skipped,
        avg_return=avg, total_return=total,
        wins=wins, losses=losses, win_rate=win_rate,
        top_winners=top_winners, top_losers=top_losers,
    )
