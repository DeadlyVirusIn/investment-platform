"""Module A — Decision Review Engine.

Evaluates decision quality by comparing accepted Buys vs blocked-alpha sim,
per-score-bucket performance, rejection reason counts, and the biggest
missed winners from the blocked-alpha set.

Pure aggregation over existing tables. No writes.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from apps.api.src.db.models import CandidateIdea, PaperPortfolio
from apps.api.src.domain.pnl.attribution import (
    DEFAULT_BLOCKED_HORIZON_DAYS,
    DEFAULT_BLOCKED_MIN_SCORE,
    SimTrade,
    attribution_by_score_bucket,
    blocked_alpha_sim,
)
from apps.api.src.domain.pnl.engine import per_symbol_pnl, resolve_portfolio


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclass
class AcceptedVsBlocked:
    accepted_count: int
    accepted_avg_return_pct: Decimal | None   # total_pnl / qty*avg_cost per trade → approx
    accepted_win_rate: Decimal | None
    blocked_count: int
    blocked_avg_return_pct: Decimal | None
    blocked_win_rate: Decimal | None
    win_rate_delta: Decimal | None            # accepted − blocked


@dataclass
class BucketPerf:
    bucket: str
    trade_count: int
    wins: int
    avg_pnl_per_trade: Decimal | None
    win_rate: Decimal | None


@dataclass
class RejectionQuality:
    reason: str
    rejected_count: int
    simulated_count: int
    simulated_avg_return: Decimal | None
    simulated_win_rate: Decimal | None


@dataclass
class MissedOpportunity:
    symbol: str | None
    as_of_date: str
    rejection_reason: str
    return_pct: Decimal
    composite_score: Decimal


@dataclass
class DecisionReview:
    sample_notes: list[str] = field(default_factory=list)
    accepted_vs_blocked: AcceptedVsBlocked | None = None
    bucket_performance: list[BucketPerf] = field(default_factory=list)
    rejection_quality: list[RejectionQuality] = field(default_factory=list)
    missed_opportunities: list[MissedOpportunity] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mean(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    return sum(values, Decimal("0")) / Decimal(len(values))


def _accepted_buy_returns(
    session: Session, portfolio: PaperPortfolio,
) -> tuple[list[Decimal], int, int]:
    """Return (per-trade return %, wins, total)."""
    rows = per_symbol_pnl(session, portfolio)
    rets: list[Decimal] = []
    wins = 0
    for r in rows:
        if r.avg_cost is None or r.avg_cost == 0:
            continue
        basis = r.avg_cost * (r.quantity if r.status == "open" else Decimal("1"))
        # For open positions use market-value-based return %, for closed use
        # realized_pnl / (avg_cost × qty). Both relative to cost basis.
        if r.status == "open" and r.avg_cost > 0 and r.mark is not None:
            ret = (r.mark - r.avg_cost) / r.avg_cost
        else:
            # Closed — approximate via total_pnl / first-buy notional. We
            # don't have the original notional directly, so fall back to
            # total_pnl normalized by avg_cost if we can infer quantity.
            if r.avg_cost and r.avg_cost > 0 and basis > 0:
                ret = r.total_pnl / basis
            else:
                continue
        rets.append(ret)
        if ret > 0:
            wins += 1
    return rets, wins, len(rets)


def _bucket_win_rate(bucket) -> Decimal | None:
    if bucket.trade_count == 0:
        return None
    return Decimal(bucket.wins) / Decimal(bucket.trade_count)


def _normalize_sim_return(s: SimTrade) -> Decimal | None:
    return s.return_pct


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------


def review_decisions(
    session: Session,
    portfolio_id: str | None = None,
    *,
    blocked_min_score: Decimal = DEFAULT_BLOCKED_MIN_SCORE,
    blocked_horizon_days: int = DEFAULT_BLOCKED_HORIZON_DAYS,
    blocked_from: dt.date | None = None,
    blocked_to: dt.date | None = None,
) -> DecisionReview:
    out = DecisionReview()
    portfolio = resolve_portfolio(session, portfolio_id)
    if portfolio is None:
        out.sample_notes.append("no_active_portfolio")
        return out

    # Accepted buys
    accepted_returns, accepted_wins, accepted_total = _accepted_buy_returns(
        session, portfolio,
    )

    # Blocked-alpha simulation
    blocked = blocked_alpha_sim(
        session,
        min_score=blocked_min_score,
        horizon_days=blocked_horizon_days,
        from_date=blocked_from, to_date=blocked_to,
    )
    blocked_returns = [s.return_pct for s in blocked.top_winners + blocked.top_losers]
    # blocked_alpha_sim already computes avg/win rate across ALL valid sims
    # (not just top winners). Use its own stats.
    accepted_avg = _mean(accepted_returns)
    accepted_wr = (
        Decimal(accepted_wins) / Decimal(accepted_total)
        if accepted_total > 0 else None
    )
    win_delta = None
    if accepted_wr is not None and blocked.win_rate is not None:
        win_delta = accepted_wr - blocked.win_rate

    out.accepted_vs_blocked = AcceptedVsBlocked(
        accepted_count=accepted_total,
        accepted_avg_return_pct=accepted_avg,
        accepted_win_rate=accepted_wr,
        blocked_count=blocked.simulated_count,
        blocked_avg_return_pct=blocked.avg_return,
        blocked_win_rate=blocked.win_rate,
        win_rate_delta=win_delta,
    )
    if accepted_total < 5:
        out.sample_notes.append("accepted_sample_small")
    if blocked.simulated_count < 5:
        out.sample_notes.append("blocked_sample_small")
    _ = blocked_returns

    # Score bucket performance from existing attribution
    buckets = attribution_by_score_bucket(session, portfolio)
    for b in buckets:
        out.bucket_performance.append(BucketPerf(
            bucket=b.bucket,
            trade_count=b.trade_count,
            wins=b.wins,
            avg_pnl_per_trade=b.avg_pnl_per_trade,
            win_rate=_bucket_win_rate(b),
        ))

    # Rejection quality — counts per reason + per-reason simulated perf
    reason_stmt = (
        select(CandidateIdea.rejection_reason, func.count())
        .where(
            CandidateIdea.status == "rejected",
            CandidateIdea.rejection_reason.is_not(None),
        )
        .group_by(CandidateIdea.rejection_reason)
        .order_by(desc(func.count()))
    )
    reason_counts = {r: int(n) for r, n in session.execute(reason_stmt).all()}

    # Per-reason simulated perf — small sim by filtering blocked set
    sim_by_reason: dict[str, list[Decimal]] = {}
    for s in blocked.top_winners + blocked.top_losers:
        if s.return_pct is None:
            continue
        sim_by_reason.setdefault(s.rejection_reason, []).append(s.return_pct)

    for reason, count in reason_counts.items():
        rets = sim_by_reason.get(reason, [])
        avg = _mean(rets)
        wins_ = sum(1 for r in rets if r > 0)
        wr = Decimal(wins_) / Decimal(len(rets)) if rets else None
        out.rejection_quality.append(RejectionQuality(
            reason=reason,
            rejected_count=count,
            simulated_count=len(rets),
            simulated_avg_return=avg,
            simulated_win_rate=wr,
        ))

    # Missed opportunities — top blocked winners
    for sw in blocked.top_winners[:5]:
        if sw.return_pct is None:
            continue
        out.missed_opportunities.append(MissedOpportunity(
            symbol=sw.symbol,
            as_of_date=sw.as_of_date.isoformat(),
            rejection_reason=sw.rejection_reason,
            return_pct=sw.return_pct,
            composite_score=sw.composite_score,
        ))

    return out
