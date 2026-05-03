"""Analytics / tuning queries over candidate_idea.

Read-only. No writes. No side effects. Pure SQL aggregations + small
Python reducers. Every function takes a ``Session`` + window and returns a
plain dict ready for JSON serialization.

Design rule: query-first. No cache tables, no pre-aggregations. For
~10-asset universe × 30-day windows the data volume is trivial.

Sector default: ``COALESCE(asset.sector, asset.asset_class)``. Stated
default — when an Asset row has no sector tag the asset_class is used.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from apps.api.src.db.models import Asset, CandidateIdea

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_WINDOW_DAYS = 30
DEFAULT_BLOCKED_ALPHA_MIN_SCORE = Decimal("0.25")
DEFAULT_THRESHOLD_GRID: tuple[Decimal, ...] = (
    Decimal("0.10"),
    Decimal("0.15"),
    Decimal("0.20"),
    Decimal("0.25"),
    Decimal("0.30"),
)
DEFAULT_REGIME_PRESSURE_MIN_SCORE = Decimal("0.25")

# Histogram buckets for composite_score ∈ [-1, +1] in 0.2 steps.
HISTOGRAM_BUCKETS: tuple[tuple[str, Decimal, Decimal], ...] = (
    ("<= -0.8",   Decimal("-1.01"), Decimal("-0.8")),
    ("-0.8..-0.6", Decimal("-0.8"),  Decimal("-0.6")),
    ("-0.6..-0.4", Decimal("-0.6"),  Decimal("-0.4")),
    ("-0.4..-0.2", Decimal("-0.4"),  Decimal("-0.2")),
    ("-0.2..0",    Decimal("-0.2"),  Decimal("0")),
    ("0..0.2",     Decimal("0"),     Decimal("0.2")),
    ("0.2..0.4",   Decimal("0.2"),   Decimal("0.4")),
    ("0.4..0.6",   Decimal("0.4"),   Decimal("0.6")),
    ("0.6..0.8",   Decimal("0.6"),   Decimal("0.8")),
    (">= 0.8",     Decimal("0.8"),   Decimal("1.01")),
)


def _default_window(
    from_date: dt.date | None, to_date: dt.date | None,
) -> tuple[dt.date, dt.date]:
    end = to_date or dt.date.today()
    start = from_date or (end - dt.timedelta(days=DEFAULT_WINDOW_DAYS))
    return start, end


def _sector_col():
    """Resolve sector expression with fallback to asset_class."""
    return func.coalesce(Asset.sector, Asset.asset_class)


def _dec(v: Decimal | None) -> str | None:
    return str(v) if v is not None else None


# ---------------------------------------------------------------------------
# 1. Rejection analytics
# ---------------------------------------------------------------------------


def rejection_analytics(
    session: Session,
    from_date: dt.date | None = None,
    to_date: dt.date | None = None,
    symbol: str | None = None,
    sector: str | None = None,
) -> dict[str, Any]:
    start, end = _default_window(from_date, to_date)

    base_where = [
        CandidateIdea.as_of_date >= start,
        CandidateIdea.as_of_date <= end,
    ]
    if symbol:
        base_where.append(func.upper(Asset.symbol) == symbol.upper())
    if sector:
        base_where.append(_sector_col() == sector)

    # Per-day: total / accepted / rejected
    by_day_stmt = (
        select(
            CandidateIdea.as_of_date,
            func.count().label("total"),
            func.sum(case((CandidateIdea.status == "accepted", 1), else_=0)).label("accepted"),
            func.sum(case((CandidateIdea.status == "rejected", 1), else_=0)).label("rejected"),
        )
        .select_from(CandidateIdea)
        .join(Asset, Asset.id == CandidateIdea.asset_id)
        .where(and_(*base_where))
        .group_by(CandidateIdea.as_of_date)
        .order_by(CandidateIdea.as_of_date.asc())
    )
    per_day = [
        {
            "as_of_date": d.isoformat(),
            "total": int(t),
            "accepted": int(a or 0),
            "rejected": int(r or 0),
        }
        for d, t, a, r in session.execute(by_day_stmt).all()
    ]

    # By reason
    by_reason_stmt = (
        select(CandidateIdea.rejection_reason, func.count())
        .select_from(CandidateIdea)
        .join(Asset, Asset.id == CandidateIdea.asset_id)
        .where(and_(*base_where, CandidateIdea.rejection_reason.is_not(None)))
        .group_by(CandidateIdea.rejection_reason)
        .order_by(func.count().desc())
    )
    by_reason = {
        reason: int(n) for reason, n in session.execute(by_reason_stmt).all()
    }

    # By sector (coalesced)
    by_sector_stmt = (
        select(
            _sector_col().label("sector"),
            func.count().label("total"),
            func.sum(case((CandidateIdea.status == "rejected", 1), else_=0)).label("rejected"),
        )
        .select_from(CandidateIdea)
        .join(Asset, Asset.id == CandidateIdea.asset_id)
        .where(and_(*base_where))
        .group_by(_sector_col())
        .order_by(func.count().desc())
    )
    by_sector = [
        {"sector": s, "total": int(t), "rejected": int(r or 0)}
        for s, t, r in session.execute(by_sector_stmt).all()
    ]

    totals = {
        "total": sum(d["total"] for d in per_day),
        "accepted": sum(d["accepted"] for d in per_day),
        "rejected": sum(d["rejected"] for d in per_day),
    }

    return {
        "from": start.isoformat(),
        "to": end.isoformat(),
        "filters": {"symbol": symbol, "sector": sector},
        "totals": totals,
        "per_day": per_day,
        "by_reason": by_reason,
        "by_sector": by_sector,
    }


# ---------------------------------------------------------------------------
# 2. Blocked alpha
# ---------------------------------------------------------------------------


def blocked_alpha(
    session: Session,
    from_date: dt.date | None = None,
    to_date: dt.date | None = None,
    min_score: Decimal = DEFAULT_BLOCKED_ALPHA_MIN_SCORE,
    rejection_reason: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    start, end = _default_window(from_date, to_date)

    where = [
        CandidateIdea.as_of_date >= start,
        CandidateIdea.as_of_date <= end,
        CandidateIdea.status == "rejected",
        CandidateIdea.composite_score.is_not(None),
        CandidateIdea.composite_score >= min_score,
    ]
    if rejection_reason:
        where.append(CandidateIdea.rejection_reason == rejection_reason)

    stmt = (
        select(CandidateIdea, Asset.symbol, _sector_col().label("sector"))
        .join(Asset, Asset.id == CandidateIdea.asset_id)
        .where(and_(*where))
        .order_by(CandidateIdea.composite_score.desc(),
                  CandidateIdea.as_of_date.desc())
        .limit(limit)
    )
    rows: list[dict[str, Any]] = []
    for cand, symbol, sect in session.execute(stmt).all():
        rows.append({
            "id": cand.id,
            "as_of_date": cand.as_of_date.isoformat(),
            "symbol": symbol,
            "sector": sect,
            "asset_id": cand.asset_id,
            "composite_score": _dec(cand.composite_score),
            "confidence": _dec(cand.confidence),
            "rejection_reason": cand.rejection_reason,
        })

    # Reason breakdown across the filtered set (independent of limit — recount)
    reason_stmt = (
        select(CandidateIdea.rejection_reason, func.count())
        .where(and_(*where))
        .group_by(CandidateIdea.rejection_reason)
    )
    by_reason = {
        r: int(n) for r, n in session.execute(reason_stmt).all()
    }

    return {
        "from": start.isoformat(),
        "to": end.isoformat(),
        "min_score": _dec(min_score),
        "rejection_reason_filter": rejection_reason,
        "count_matched": sum(by_reason.values()),
        "by_reason": by_reason,
        "items": rows,
    }


# ---------------------------------------------------------------------------
# 3. Score distribution
# ---------------------------------------------------------------------------


def _median(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2 == 1:
        return s[mid]
    return (s[mid - 1] + s[mid]) / Decimal("2")


def score_distribution(
    session: Session,
    from_date: dt.date | None = None,
    to_date: dt.date | None = None,
    sector: str | None = None,
) -> dict[str, Any]:
    start, end = _default_window(from_date, to_date)
    where = [
        CandidateIdea.as_of_date >= start,
        CandidateIdea.as_of_date <= end,
        CandidateIdea.composite_score.is_not(None),
    ]
    if sector:
        where.append(_sector_col() == sector)

    stmt = (
        select(
            CandidateIdea.as_of_date,
            CandidateIdea.status,
            CandidateIdea.composite_score,
        )
        .select_from(CandidateIdea)
        .join(Asset, Asset.id == CandidateIdea.asset_id)
        .where(and_(*where))
    )
    rows = session.execute(stmt).all()

    # Per-day stats (min / max / avg / median) over composites
    per_day_raw: dict[dt.date, list[Decimal]] = {}
    accepted_scores: list[Decimal] = []
    rejected_scores: list[Decimal] = []
    for d, status, score in rows:
        if score is None:
            continue
        per_day_raw.setdefault(d, []).append(score)
        if status == "accepted":
            accepted_scores.append(score)
        elif status == "rejected":
            rejected_scores.append(score)

    per_day: list[dict[str, Any]] = []
    for d in sorted(per_day_raw.keys()):
        xs = per_day_raw[d]
        per_day.append({
            "as_of_date": d.isoformat(),
            "n": len(xs),
            "min": _dec(min(xs)),
            "max": _dec(max(xs)),
            "avg": _dec(sum(xs, Decimal("0")) / Decimal(len(xs))),
            "median": _dec(_median(xs)),
        })

    def _histogram(values: list[Decimal]) -> list[dict[str, Any]]:
        out = []
        for label, lo, hi in HISTOGRAM_BUCKETS:
            n = sum(1 for v in values if lo <= v < hi)
            out.append({"bucket": label, "count": n})
        return out

    return {
        "from": start.isoformat(),
        "to": end.isoformat(),
        "filters": {"sector": sector},
        "totals": {
            "accepted": len(accepted_scores),
            "rejected": len(rejected_scores),
        },
        "per_day": per_day,
        "histogram": {
            "all": _histogram(accepted_scores + rejected_scores),
            "accepted": _histogram(accepted_scores),
            "rejected": _histogram(rejected_scores),
        },
    }


# ---------------------------------------------------------------------------
# 4. Threshold sensitivity (read-only simulation)
# ---------------------------------------------------------------------------


def threshold_sensitivity(
    session: Session,
    from_date: dt.date | None = None,
    to_date: dt.date | None = None,
    thresholds: tuple[Decimal, ...] = DEFAULT_THRESHOLD_GRID,
) -> dict[str, Any]:
    """Simulate alternative Buy thresholds over stored composites. Pure
    analysis — no writes, no model_version changes.

    Logic:
        For each threshold T:
          would_be_buys_by_score     = # rows with composite_score >= T
          actually_accepted_buys     = # rows with status='accepted' AND action='Buy'
                                        AND composite_score >= T
          accepted_not_buy_flip      = # rows with status='accepted' AND action != 'Buy'
                                        AND composite_score >= T
          rejected_with_score        = # rows with status='rejected' AND composite_score >= T
          rejected_reason_breakdown  = {reason: count} within rejected_with_score
    """
    start, end = _default_window(from_date, to_date)

    stmt = (
        select(
            CandidateIdea.status,
            CandidateIdea.action,
            CandidateIdea.rejection_reason,
            CandidateIdea.composite_score,
        )
        .where(
            CandidateIdea.as_of_date >= start,
            CandidateIdea.as_of_date <= end,
            CandidateIdea.composite_score.is_not(None),
        )
    )
    rows = list(session.execute(stmt).all())
    total = len(rows)

    per_threshold: list[dict[str, Any]] = []
    for t in thresholds:
        buys_by_score = 0
        accepted_buy = 0
        accepted_flip = 0
        rejected_with_score = 0
        reason_breakdown: dict[str, int] = {}
        for status, action, reason, score in rows:
            if score is None or score < t:
                continue
            buys_by_score += 1
            if status == "accepted" and action == "Buy":
                accepted_buy += 1
            elif status == "accepted":
                accepted_flip += 1
            elif status == "rejected":
                rejected_with_score += 1
                if reason:
                    reason_breakdown[reason] = reason_breakdown.get(reason, 0) + 1
        per_threshold.append({
            "threshold": _dec(t),
            "would_be_buys_by_score": buys_by_score,
            "actually_accepted_buys": accepted_buy,
            "accepted_not_buy_would_flip": accepted_flip,
            "rejected_with_sufficient_score": rejected_with_score,
            "rejected_breakdown_by_reason": reason_breakdown,
        })

    return {
        "from": start.isoformat(),
        "to": end.isoformat(),
        "total_rows": total,
        "thresholds": per_threshold,
    }


# ---------------------------------------------------------------------------
# 5. Regime pressure
# ---------------------------------------------------------------------------


def regime_pressure(
    session: Session,
    from_date: dt.date | None = None,
    to_date: dt.date | None = None,
    min_top_score: Decimal = DEFAULT_REGIME_PRESSURE_MIN_SCORE,
) -> dict[str, Any]:
    """Identify days where EVERY candidate was rejected with
    ``rejection_reason='regime_off'`` AND the day's top composite_score was
    >= ``min_top_score``. Answers "is the regime filter blocking real
    alpha?"."""
    start, end = _default_window(from_date, to_date)

    # Per-day aggregates
    stmt = (
        select(
            CandidateIdea.as_of_date,
            func.count().label("total"),
            func.sum(
                case((CandidateIdea.rejection_reason == "regime_off", 1), else_=0),
            ).label("regime_off"),
            func.max(CandidateIdea.composite_score).label("max_score"),
        )
        .where(
            CandidateIdea.as_of_date >= start,
            CandidateIdea.as_of_date <= end,
        )
        .group_by(CandidateIdea.as_of_date)
        .order_by(CandidateIdea.as_of_date.asc())
    )

    days: list[dict[str, Any]] = []
    triggered_days: list[dict[str, Any]] = []
    triggered_max_scores: list[Decimal] = []

    for d, total, regime_off, max_score in session.execute(stmt).all():
        total = int(total)
        regime_off = int(regime_off or 0)
        all_regime_off = total > 0 and regime_off == total
        row = {
            "as_of_date": d.isoformat(),
            "total": total,
            "regime_off_count": regime_off,
            "all_regime_off": all_regime_off,
            "max_composite_score": _dec(max_score),
        }
        days.append(row)
        if all_regime_off and max_score is not None and max_score >= min_top_score:
            triggered_days.append(row)
            triggered_max_scores.append(max_score)

    avg_blocked = None
    if triggered_max_scores:
        avg_blocked = sum(triggered_max_scores, Decimal("0")) / Decimal(
            len(triggered_max_scores)
        )

    return {
        "from": start.isoformat(),
        "to": end.isoformat(),
        "min_top_score": _dec(min_top_score),
        "triggered_day_count": len(triggered_days),
        "avg_blocked_top_score": _dec(avg_blocked),
        "triggered_days": triggered_days,
        "all_days": days,
    }


# ---------------------------------------------------------------------------
# 6. Sector concentration preview
# ---------------------------------------------------------------------------


def sector_preview(
    session: Session,
    as_of: dt.date | None = None,
    min_blocked_score: Decimal = DEFAULT_BLOCKED_ALPHA_MIN_SCORE,
) -> dict[str, Any]:
    """Per-sector snapshot for the latest (or specified) as_of_date:
      * accepted Buy count
      * total accepted count
      * rejected-high-score count (composite >= min_blocked_score)
      * top per-sector candidate (highest composite, any status)
    """
    if as_of is None:
        row = session.execute(
            select(func.max(CandidateIdea.as_of_date))
        ).first()
        as_of = row[0] if row and row[0] else None
    if as_of is None:
        return {"as_of_date": None, "sectors": [], "totals": {}}

    sect = _sector_col().label("sector")

    # Per-sector accepted-Buy + rejected-high-score counts
    stmt = (
        select(
            sect,
            func.count().label("total"),
            func.sum(
                case(
                    (and_(
                        CandidateIdea.status == "accepted",
                        CandidateIdea.action == "Buy",
                        CandidateIdea.rejection_reason.is_(None),
                    ), 1),
                    else_=0,
                )
            ).label("accepted_buys"),
            func.sum(
                case((CandidateIdea.status == "accepted", 1), else_=0),
            ).label("accepted_total"),
            func.sum(
                case(
                    (and_(
                        CandidateIdea.status == "rejected",
                        CandidateIdea.composite_score.is_not(None),
                        CandidateIdea.composite_score >= min_blocked_score,
                    ), 1),
                    else_=0,
                )
            ).label("rejected_high_score"),
            func.max(CandidateIdea.composite_score).label("max_score"),
        )
        .select_from(CandidateIdea)
        .join(Asset, Asset.id == CandidateIdea.asset_id)
        .where(CandidateIdea.as_of_date == as_of)
        .group_by(_sector_col())
        .order_by(func.count().desc())
    )

    sectors: list[dict[str, Any]] = []
    for s, total, buys, acc_total, rej_high, max_score in session.execute(stmt).all():
        sectors.append({
            "sector": s,
            "total_evaluated": int(total),
            "accepted_buys": int(buys or 0),
            "accepted_total": int(acc_total or 0),
            "rejected_high_score": int(rej_high or 0),
            "max_composite_score": _dec(max_score),
        })

    totals = {
        "total_evaluated": sum(x["total_evaluated"] for x in sectors),
        "accepted_buys": sum(x["accepted_buys"] for x in sectors),
        "accepted_total": sum(x["accepted_total"] for x in sectors),
        "rejected_high_score": sum(x["rejected_high_score"] for x in sectors),
    }

    return {
        "as_of_date": as_of.isoformat(),
        "min_blocked_score": _dec(min_blocked_score),
        "totals": totals,
        "sectors": sectors,
    }
