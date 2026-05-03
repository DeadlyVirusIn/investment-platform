"""Module C — Tuning Advisor (deterministic rules).

Derived from Modules A + B + D plus a couple of quick counts. Emits an
ordered list of tuning suggestions with severity. No auto-tuning. Operator
reads the list and decides.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from apps.api.src.db.models import CandidateIdea
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

# Rule-trigger thresholds — stated defaults
RULE_HIGH_VOL_CAPACITY_MARGIN = Decimal("0.02")      # 2% simulated edge
RULE_CASH_THRESHOLD = Decimal("0.60")                # cash%
RULE_LOW_CANDIDATE_COUNT = 10
RULE_HIGH_REJECT_RATIO = Decimal("0.80")
RULE_CONCENTRATION_TOP2 = Decimal("0.50")
RULE_NEWS_NEGATIVE_UNDERPERFORM_BY = Decimal("0.02")  # 2% underperformance


@dataclass
class Suggestion:
    code: str
    severity: str          # info | warn | critical
    message: str
    reasoning: str


def _latest_candidates_stats(session: Session) -> tuple[int, Decimal | None]:
    """(count, rejected_ratio) for the latest as_of_date."""
    row = session.execute(
        select(func.max(CandidateIdea.as_of_date))
    ).first()
    if not row or not row[0]:
        return 0, None
    as_of = row[0]
    stmt = (
        select(CandidateIdea.status, func.count())
        .where(CandidateIdea.as_of_date == as_of)
        .group_by(CandidateIdea.status)
    )
    counts: dict[str, int] = {}
    for status, n in session.execute(stmt).all():
        counts[status] = int(n)
    total = sum(counts.values())
    if total == 0:
        return 0, None
    rejected = counts.get("rejected", 0)
    return total, Decimal(rejected) / Decimal(total)


def advise(
    session: Session,
    *,
    portfolio_id: str | None = None,
    review: DecisionReview | None = None,
    portfolio: PortfolioIntelligence | None = None,
    news: NewsAnalysis | None = None,
) -> list[Suggestion]:
    review = review or review_decisions(session, portfolio_id)
    portfolio = portfolio or analyze_portfolio(session, portfolio_id)
    news = news or analyze_news(session, portfolio_id)

    out: list[Suggestion] = []

    # Rule 1: High-vol capacity — blocked-alpha outperforming accepted
    avb = review.accepted_vs_blocked
    if avb and avb.accepted_avg_return_pct is not None and avb.blocked_avg_return_pct is not None:
        gap = avb.blocked_avg_return_pct - avb.accepted_avg_return_pct
        if gap > RULE_HIGH_VOL_CAPACITY_MARGIN:
            out.append(Suggestion(
                code="increase_high_vol_topn",
                severity="warn",
                message="Consider increasing high-vol Top-N cap",
                reasoning=(
                    f"Blocked-alpha avg return "
                    f"{float(avb.blocked_avg_return_pct):.2%} "
                    f"exceeds accepted Buy avg return "
                    f"{float(avb.accepted_avg_return_pct):.2%} "
                    f"by {float(gap):.2%}."
                ),
            ))

    # Rule 2: Idle capital
    if (
        portfolio.cash_pct is not None
        and portfolio.cash_pct >= RULE_CASH_THRESHOLD
    ):
        has_buys_today = any(
            b.bucket != "unclassified" and b.trade_count == 0
            for b in review.bucket_performance
        )
        total_count, rej_ratio = _latest_candidates_stats(session)
        accepted_buys_today = max(
            0,
            total_count - int(total_count * (rej_ratio or Decimal("0"))),
        ) if rej_ratio is not None else 0
        if accepted_buys_today > 0:
            out.append(Suggestion(
                code="increase_capital_utilization",
                severity="warn",
                message="Consider increasing capital utilization",
                reasoning=(
                    f"Cash is {float(portfolio.cash_pct):.1%} of NAV while "
                    f"{accepted_buys_today} accepted candidate(s) exist today."
                ),
            ))
        _ = has_buys_today

    # Rule 3: Universe size / rejection ratio
    total_count, rej_ratio = _latest_candidates_stats(session)
    if total_count > 0 and total_count < RULE_LOW_CANDIDATE_COUNT:
        out.append(Suggestion(
            code="expand_universe",
            severity="info",
            message="Consider expanding the universe",
            reasoning=(
                f"Only {total_count} candidates evaluated in the latest batch."
            ),
        ))
    elif rej_ratio is not None and rej_ratio >= RULE_HIGH_REJECT_RATIO:
        out.append(Suggestion(
            code="expand_universe",
            severity="info",
            message="Consider expanding the universe",
            reasoning=(
                f"{float(rej_ratio):.0%} of candidates are being rejected — "
                f"signals may be concentrated; broader set could surface more."
            ),
        ))

    # Rule 4: Concentration
    if (
        portfolio.top2_weight_sum is not None
        and portfolio.top2_weight_sum >= RULE_CONCENTRATION_TOP2
    ):
        out.append(Suggestion(
            code="review_concentration",
            severity="warn",
            message="Review sizing / diversification",
            reasoning=(
                f"Top-2 positions hold "
                f"{float(portfolio.top2_weight_sum):.1%} of NAV."
            ),
        ))

    # Rule 5: Negative-news underperformance
    neg = next((b for b in news.by_sentiment if b.key == "negative"), None)
    pos = next((b for b in news.by_sentiment if b.key == "positive"), None)
    neu = next((b for b in news.by_sentiment if b.key == "neutral"), None)
    if (
        neg and neg.trade_count >= 3 and neg.avg_return_pct is not None
    ):
        baseline = None
        if pos and pos.avg_return_pct is not None:
            baseline = pos.avg_return_pct
        elif neu and neu.avg_return_pct is not None:
            baseline = neu.avg_return_pct
        if (
            baseline is not None
            and baseline - neg.avg_return_pct > RULE_NEWS_NEGATIVE_UNDERPERFORM_BY
        ):
            out.append(Suggestion(
                code="incorporate_news_penalty",
                severity="info",
                message="Consider a news penalty for negative-sentiment entries",
                reasoning=(
                    f"Negative-news trades avg "
                    f"{float(neg.avg_return_pct):.2%} vs baseline "
                    f"{float(baseline):.2%}."
                ),
            ))

    if not out:
        out.append(Suggestion(
            code="no_action",
            severity="info",
            message="No tuning action recommended",
            reasoning="All monitored thresholds are within healthy bounds.",
        ))

    return out
