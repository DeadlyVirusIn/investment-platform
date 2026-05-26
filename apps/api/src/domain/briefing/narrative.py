"""Narrative engine — 2-4 sentence daily summary + Δ-vs-yesterday deltas.

Pure-ish composer. Reads from regime_snapshot, candidate_idea, the
intelligence modules (portfolio + tuning + decision review), and the
paper_equity_snapshot history to compute yesterday's NAV for a day-over-day
delta.
"""

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
    PaperEquitySnapshot,
    PaperPosition,
    RegimeSnapshot,
)
from apps.api.src.domain.intelligence.decision_review import review_decisions
from apps.api.src.domain.intelligence.portfolio_intelligence import (
    analyze_portfolio,
)
from apps.api.src.domain.intelligence.tuning_advisor import advise
from apps.api.src.domain.pnl.engine import portfolio_pnl, resolve_portfolio


@dataclass
class Delta:
    nav: Decimal | None
    nav_pct: Decimal | None
    positions: int | None
    candidates: int | None
    accepted_buys: int | None
    regime_changed: bool
    prev_regime: dict[str, str] | None


@dataclass
class NarrativePayload:
    as_of_date: str | None
    narrative: str
    regime: dict[str, str] | None
    portfolio_flags: list[str]
    tuning_top: list[dict[str, str]]
    delta: Delta


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _latest_candidate_date(session: Session) -> dt.date | None:
    row = session.execute(
        select(func.max(CandidateIdea.as_of_date))
    ).first()
    return row[0] if row and row[0] else None


def _regime_for_date(
    session: Session, day: dt.date,
) -> RegimeSnapshot | None:
    return session.get(RegimeSnapshot, day)


def _previous_regime(
    session: Session, before: dt.date,
) -> RegimeSnapshot | None:
    stmt = (
        select(RegimeSnapshot)
        .where(RegimeSnapshot.as_of_date < before)
        .order_by(desc(RegimeSnapshot.as_of_date))
        .limit(1)
    )
    return session.scalars(stmt).first()


def _candidates_count(
    session: Session, day: dt.date,
) -> tuple[int, int]:
    stmt = (
        select(CandidateIdea.status, func.count())
        .where(CandidateIdea.as_of_date == day)
        .group_by(CandidateIdea.status)
    )
    total = 0
    accepted_buys = 0
    for status, n in session.execute(stmt).all():
        total += int(n)
    # Count accepted Buys separately
    buy_stmt = (
        select(func.count())
        .where(
            CandidateIdea.as_of_date == day,
            CandidateIdea.status == "accepted",
            CandidateIdea.action == "Buy",
            CandidateIdea.rejection_reason.is_(None),
        )
    )
    accepted_buys = int(session.execute(buy_stmt).scalar() or 0)
    return total, accepted_buys


def _previous_candidate_date(
    session: Session, before: dt.date,
) -> dt.date | None:
    stmt = (
        select(func.max(CandidateIdea.as_of_date))
        .where(CandidateIdea.as_of_date < before)
    )
    row = session.execute(stmt).first()
    return row[0] if row and row[0] else None


def _top_buy_symbols(
    session: Session, day: dt.date, n: int = 3,
) -> list[str]:
    stmt = (
        select(Asset.symbol)
        .join(CandidateIdea, CandidateIdea.asset_id == Asset.id)
        .where(
            CandidateIdea.as_of_date == day,
            CandidateIdea.status == "accepted",
            CandidateIdea.action == "Buy",
            CandidateIdea.rejection_reason.is_(None),
        )
        .order_by(desc(CandidateIdea.composite_score))
        .limit(n)
    )
    return [row[0] for row in session.execute(stmt).all()]


def _yesterday_snapshot(
    session: Session, portfolio_id: str, today: dt.date,
) -> tuple[Decimal | None, int | None]:
    """(nav, position_count) at the most recent equity snapshot strictly
    before ``today``. Position count is inferred as rows open at snapshot."""
    # Phase L M079: canonical user-facing briefing — live-only.
    stmt = (
        select(PaperEquitySnapshot)
        .where(
            PaperEquitySnapshot.portfolio_id == portfolio_id,
            PaperEquitySnapshot.source == "live",
            PaperEquitySnapshot.snapshot_date < dt.datetime.combine(
                today, dt.time(0, 0, 0, tzinfo=dt.timezone.utc),
            ),
        )
        .order_by(
            desc(PaperEquitySnapshot.snapshot_date),
            desc(PaperEquitySnapshot.recorded_at),
        )
        .limit(1)
    )
    snap = session.scalars(stmt).first()
    if snap is None:
        return None, None
    nav = snap.total_equity
    if nav is not None and not isinstance(nav, Decimal):
        nav = Decimal(str(nav))
    # Positions open at snapshot.snapshot_date
    pos_stmt = (
        select(func.count())
        .select_from(PaperPosition)
        .where(
            PaperPosition.portfolio_id == portfolio_id,
            PaperPosition.opened_at <= snap.snapshot_date,
            (PaperPosition.closed_at.is_(None)) | (PaperPosition.closed_at > snap.snapshot_date),
        )
    )
    pos_count = int(session.execute(pos_stmt).scalar() or 0)
    return nav, pos_count


def _fmt_money(v: Decimal | None) -> str:
    if v is None:
        return "—"
    sign = "-" if v < 0 else ""
    return f"{sign}${abs(v):,.2f}"


def _fmt_pct(v: Decimal | None) -> str:
    if v is None:
        return "—"
    return f"{v*100:+.2f}%"


# ---------------------------------------------------------------------------
# Core composer
# ---------------------------------------------------------------------------


def compose_narrative(
    session: Session, portfolio_id: str | None = None,
) -> NarrativePayload:
    portfolio = resolve_portfolio(session, portfolio_id)
    today = _latest_candidate_date(session) or dt.date.today()

    regime_today = _regime_for_date(session, today)
    regime_prev = _previous_regime(session, today)
    regime_changed = bool(
        regime_today is not None
        and regime_prev is not None
        and (
            regime_today.market_trend != regime_prev.market_trend
            or regime_today.vol_regime != regime_prev.vol_regime
        )
    )

    cand_total, accepted_buys = _candidates_count(session, today)
    prev_day = _previous_candidate_date(session, today)
    prev_cand_total = 0
    if prev_day is not None:
        prev_cand_total, _ = _candidates_count(session, prev_day)
    top_syms = _top_buy_symbols(session, today, n=3)

    pnl = portfolio_pnl(session, portfolio) if portfolio is not None else None

    nav_delta = None
    nav_pct = None
    positions_delta = None
    if portfolio is not None and pnl is not None:
        prev_nav, prev_positions = _yesterday_snapshot(session, portfolio.id, today)
        if prev_nav is not None and pnl.nav is not None:
            nav_delta = pnl.nav - prev_nav
            if prev_nav > 0:
                nav_pct = nav_delta / prev_nav
        if prev_positions is not None:
            positions_delta = pnl.open_positions_count - prev_positions

    candidates_delta = (
        cand_total - prev_cand_total if prev_day is not None else None
    )

    # Intelligence modules for flags + tuning
    portfolio_intel = analyze_portfolio(session, portfolio_id)
    review = review_decisions(session, portfolio_id)
    suggestions = advise(
        session, portfolio_id=portfolio_id,
        review=review, portfolio=portfolio_intel,
    )
    top_tuning = [
        {"code": s.code, "severity": s.severity, "message": s.message}
        for s in suggestions[:3]
    ]

    # Compose 2-4 sentences
    sentences: list[str] = []

    # S1: regime state + change badge
    if regime_today is not None:
        verb = "shifted to" if regime_changed else "remains"
        prev_note = ""
        if regime_changed and regime_prev is not None:
            prev_note = (
                f" (from {regime_prev.market_trend}/{regime_prev.vol_regime})"
            )
        sentences.append(
            f"Regime {verb} {regime_today.market_trend}/"
            f"{regime_today.vol_regime}{prev_note}."
        )
    else:
        sentences.append("No regime snapshot for today.")

    # S2: signals
    if accepted_buys > 0:
        syms_txt = ", ".join(top_syms) if top_syms else ""
        if syms_txt:
            sentences.append(
                f"{accepted_buys} Buy signal(s) today: {syms_txt}."
            )
        else:
            sentences.append(f"{accepted_buys} Buy signal(s) today.")
    else:
        top_reasons = sorted(
            (review.rejection_quality or []),
            key=lambda r: -r.rejected_count,
        )[:2]
        if top_reasons:
            reasons_txt = ", ".join(r.reason for r in top_reasons)
            sentences.append(
                f"No Buys today — dominant rejection reasons: {reasons_txt}."
            )
        else:
            sentences.append("No Buys today.")

    # S3: portfolio state
    if pnl is not None:
        nav_s = _fmt_money(pnl.nav)
        daily_s = _fmt_money(nav_delta) if nav_delta is not None else "—"
        daily_pct_s = _fmt_pct(nav_pct) if nav_pct is not None else ""
        paren = f" ({daily_pct_s})" if daily_pct_s else ""
        sentences.append(
            f"Portfolio NAV {nav_s}; day change {daily_s}{paren}; "
            f"{pnl.open_positions_count} open position(s)."
        )

    # S4: top concern
    warn = next(
        (s for s in suggestions if s.severity in ("warn", "critical")), None,
    )
    if warn is not None:
        sentences.append(f"Concern: {warn.message.lower()}.")

    narrative_text = " ".join(sentences).strip()

    return NarrativePayload(
        as_of_date=today.isoformat() if today else None,
        narrative=narrative_text,
        regime=(
            {
                "market_trend": regime_today.market_trend,
                "vol_regime": regime_today.vol_regime,
            }
            if regime_today is not None else None
        ),
        portfolio_flags=portfolio_intel.flags,
        tuning_top=top_tuning,
        delta=Delta(
            nav=nav_delta,
            nav_pct=nav_pct,
            positions=positions_delta,
            candidates=candidates_delta,
            accepted_buys=accepted_buys,
            regime_changed=regime_changed,
            prev_regime=(
                {
                    "market_trend": regime_prev.market_trend,
                    "vol_regime": regime_prev.vol_regime,
                }
                if regime_prev is not None else None
            ),
        ),
    )
