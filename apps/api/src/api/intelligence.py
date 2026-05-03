"""Intelligence Console API — 5 read-only endpoints."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from apps.api.src.db import get_session
from apps.api.src.domain.intelligence.decision_review import (
    DecisionReview,
    review_decisions,
)
from apps.api.src.domain.intelligence.news_analyzer import (
    NewsAnalysis,
    analyze_news,
)
from apps.api.src.domain.intelligence.portfolio_intelligence import (
    PortfolioIntelligence,
    analyze_portfolio,
)
from apps.api.src.domain.intelligence.tuning_advisor import advise

router = APIRouter(prefix="/intelligence", tags=["intelligence"])


def _dec(v: Decimal | None) -> str | None:
    return str(v) if v is not None else None


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------


def _review_payload(r: DecisionReview) -> dict[str, Any]:
    avb = r.accepted_vs_blocked
    return {
        "sample_notes": r.sample_notes,
        "accepted_vs_blocked": (
            {
                "accepted_count": avb.accepted_count,
                "accepted_avg_return_pct": _dec(avb.accepted_avg_return_pct),
                "accepted_win_rate": _dec(avb.accepted_win_rate),
                "blocked_count": avb.blocked_count,
                "blocked_avg_return_pct": _dec(avb.blocked_avg_return_pct),
                "blocked_win_rate": _dec(avb.blocked_win_rate),
                "win_rate_delta": _dec(avb.win_rate_delta),
            }
            if avb else None
        ),
        "bucket_performance": [
            {
                "bucket": b.bucket,
                "trade_count": b.trade_count,
                "wins": b.wins,
                "avg_pnl_per_trade": _dec(b.avg_pnl_per_trade),
                "win_rate": _dec(b.win_rate),
            }
            for b in r.bucket_performance
        ],
        "rejection_quality": [
            {
                "reason": rq.reason,
                "rejected_count": rq.rejected_count,
                "simulated_count": rq.simulated_count,
                "simulated_avg_return": _dec(rq.simulated_avg_return),
                "simulated_win_rate": _dec(rq.simulated_win_rate),
            }
            for rq in r.rejection_quality
        ],
        "missed_opportunities": [
            {
                "symbol": m.symbol,
                "as_of_date": m.as_of_date,
                "rejection_reason": m.rejection_reason,
                "return_pct": _dec(m.return_pct),
                "composite_score": _dec(m.composite_score),
            }
            for m in r.missed_opportunities
        ],
    }


def _portfolio_payload(p: PortfolioIntelligence) -> dict[str, Any]:
    return {
        "nav": _dec(p.nav),
        "cash": _dec(p.cash),
        "invested": _dec(p.invested),
        "cash_pct": _dec(p.cash_pct),
        "invested_pct": _dec(p.invested_pct),
        "open_positions": p.open_positions,
        "top_positions": [
            {
                "symbol": tp.symbol,
                "weight": _dec(tp.weight),
                "unrealized_pnl": _dec(tp.unrealized_pnl),
                "unrealized_pct": _dec(tp.unrealized_pct),
            }
            for tp in p.top_positions
        ],
        "top1_weight": _dec(p.top1_weight),
        "top2_weight_sum": _dec(p.top2_weight_sum),
        "sector_exposure": [
            {"sector": s.sector, "weight": _dec(s.weight)}
            for s in p.sector_exposure
        ],
        "regime_mix": [
            {
                "market_trend": rm.market_trend,
                "vol_regime": rm.vol_regime,
                "count": rm.count,
            }
            for rm in p.regime_mix
        ],
        "avg_slippage_bps": _dec(p.avg_slippage_bps),
        "max_slippage_bps": _dec(p.max_slippage_bps),
        "flags": p.flags,
        "notes": p.notes,
    }


def _news_payload(n: NewsAnalysis) -> dict[str, Any]:
    return {
        "trades_analyzed": n.trades_analyzed,
        "alignment_pct": _dec(n.alignment_pct),
        "sample_notes": n.sample_notes,
        "by_sentiment": [
            {
                "key": s.key, "trade_count": s.trade_count,
                "avg_return_pct": _dec(s.avg_return_pct),
                "wins": s.wins, "losses": s.losses,
            }
            for s in n.by_sentiment
        ],
        "by_category": [
            {
                "key": s.key, "trade_count": s.trade_count,
                "avg_return_pct": _dec(s.avg_return_pct),
                "wins": s.wins, "losses": s.losses,
            }
            for s in n.by_category
        ],
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/decision-review")
def get_decision_review(
    portfolio_id: str | None = Query(None),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return _review_payload(review_decisions(session, portfolio_id))


@router.get("/portfolio")
def get_portfolio_intelligence(
    portfolio_id: str | None = Query(None),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return _portfolio_payload(analyze_portfolio(session, portfolio_id))


@router.get("/news-analysis")
def get_news_analysis(
    portfolio_id: str | None = Query(None),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return _news_payload(analyze_news(session, portfolio_id))


@router.get("/tuning-advice")
def get_tuning_advice(
    portfolio_id: str | None = Query(None),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    review = review_decisions(session, portfolio_id)
    portfolio = analyze_portfolio(session, portfolio_id)
    news = analyze_news(session, portfolio_id)
    suggestions = advise(
        session,
        portfolio_id=portfolio_id,
        review=review, portfolio=portfolio, news=news,
    )
    return {
        "count": len(suggestions),
        "suggestions": [
            {
                "code": s.code, "severity": s.severity,
                "message": s.message, "reasoning": s.reasoning,
            }
            for s in suggestions
        ],
    }


@router.get("/summary")
def get_intelligence_summary(
    portfolio_id: str | None = Query(None),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    review = review_decisions(session, portfolio_id)
    portfolio = analyze_portfolio(session, portfolio_id)
    news = analyze_news(session, portfolio_id)
    suggestions = advise(
        session, portfolio_id=portfolio_id,
        review=review, portfolio=portfolio, news=news,
    )
    return {
        "decision_review": _review_payload(review),
        "portfolio": _portfolio_payload(portfolio),
        "news": _news_payload(news),
        "tuning_advice": {
            "count": len(suggestions),
            "suggestions": [
                {
                    "code": s.code, "severity": s.severity,
                    "message": s.message, "reasoning": s.reasoning,
                }
                for s in suggestions
            ],
        },
    }
