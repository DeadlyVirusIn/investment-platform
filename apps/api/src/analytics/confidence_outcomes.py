"""MP2A — read-only confidence→outcome attribution analytics.

Smallest layer that answers: "Are higher-confidence recommendations
performing better?" Two SELECT-only aggregations over the MP1A/MP1S
attribution links:

  STOCKS:  recommendation.conviction
             -> bucket -> closed paper_position.realized_pnl
  OPTIONS: options_strategy_candidate.diagnostics->confidence_v2
             -> bucket -> closed options_paper_trade.realized_pnl_dollars

Honesty contract (mirrors TrackRecord's MIN_CLOSES gate):
  * If total closed attributed outcomes < MIN_CLOSES, return
    note="insufficient_data" and NO rates (win_rate / avg / expectancy
    are null) — counts only, never a fabricated percentage.
  * A bucket with < PER_BUCKET_MIN closes also returns null rates.

No schema, no writes, no ML, no calibration. expectancy == mean realized
P&L per trade (for realized P&L the expectancy IS the per-trade mean).

This module is SELECT-only: the only DB API used is
`session.execute(text(...))`. No INSERT/UPDATE/DELETE.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

# Reuse the TrackRecord threshold (MIN_CLOSES_FOR_STATS = 10) so the two
# surfaces agree on what "enough closed history" means.
MIN_CLOSES = 10
PER_BUCKET_MIN = 3

# (label, lo_inclusive, hi_exclusive); hi=None means open-ended (+inf).
BUCKETS_CONVICTION: list[tuple[str, float, float | None]] = [
    ("low (<40)", 0.0, 40.0),
    ("medium (40–60)", 40.0, 60.0),
    ("high (60–80)", 60.0, 80.0),
    ("very_high (80+)", 80.0, None),
]
BUCKETS_CONFIDENCE_V2: list[tuple[str, float, float | None]] = [
    ("low (<0.4)", 0.0, 0.4),
    ("medium (0.4–0.6)", 0.4, 0.6),
    ("high (0.6–0.8)", 0.6, 0.8),
    ("very_high (0.8+)", 0.8, None),
]


def bucketize(
    rows: list[tuple[float | None, float | None]],
    *,
    buckets: list[tuple[str, float, float | None]],
    min_closes: int = MIN_CLOSES,
    per_bucket_min: int = PER_BUCKET_MIN,
) -> dict[str, Any]:
    """Pure aggregator. `rows` = list of (score, realized_pnl) for CLOSED
    attributed outcomes. Returns per-bucket counts + (when sample is
    sufficient) win_rate / avg_realized_pnl / expectancy / total.

    Deterministic, DB-free — unit tested directly.
    """
    clean = [
        (float(s), float(p))
        for (s, p) in rows
        if s is not None and p is not None
    ]
    total = len(clean)
    sufficient = total >= min_closes

    out: list[dict[str, Any]] = []
    for label, lo, hi in buckets:
        pnls = [
            p for (s, p) in clean
            if s >= lo and (hi is None or s < hi)
        ]
        n = len(pnls)
        tot = round(sum(pnls), 2) if n else 0.0
        if not sufficient or n < per_bucket_min:
            # No rates on thin samples — counts only, never a fake %.
            out.append({
                "bucket": label,
                "trade_count": n,
                "win_rate": None,
                "avg_realized_pnl": None,
                "expectancy": None,
                "total_realized_pnl": tot,
            })
        else:
            wins = sum(1 for p in pnls if p > 0)
            mean = tot / n
            out.append({
                "bucket": label,
                "trade_count": n,
                "win_rate": round(wins / n, 4),
                "avg_realized_pnl": round(mean, 2),
                # For realized P&L, expectancy = mean realized per trade.
                "expectancy": round(mean, 2),
                "total_realized_pnl": tot,
            })

    return {
        "sufficient": sufficient,
        "total_closed": total,
        "min_closes": min_closes,
        "per_bucket_min": per_bucket_min,
        "note": None if sufficient else "insufficient_data",
        "buckets": out,
    }


def conviction_outcome_buckets(session: Session) -> dict[str, Any]:
    """STOCKS — conviction bucket vs executed realized P&L (SELECT-only).

    Closed, attributed paper positions only (MP1S link). Legacy/unattributed
    positions (NULL opened_by_recommendation_id) are excluded.
    """
    rows = session.execute(text(
        """
        SELECT r.conviction        AS score,
               pp.realized_pnl     AS pnl
          FROM paper_position pp
          JOIN recommendation r
            ON r.id = pp.opened_by_recommendation_id
         WHERE pp.opened_by_recommendation_id IS NOT NULL
           AND pp.is_open = false
           AND pp.realized_pnl IS NOT NULL
           AND r.conviction IS NOT NULL
        """
    )).all()
    result = bucketize(
        [(r.score, r.pnl) for r in rows],
        buckets=BUCKETS_CONVICTION,
    )
    result["dimension"] = "stock_conviction"
    return result


def confidence_v2_outcome_buckets(session: Session) -> dict[str, Any]:
    """OPTIONS — confidence_v2 bucket vs executed realized P&L (SELECT-only).

    Extends the candidate→trade attribution (MP1A link) to CLOSED trades
    only, bucketed by the shadow confidence_v2 in candidate diagnostics.
    """
    rows = session.execute(text(
        """
        SELECT (c.diagnostics ->> 'confidence_v2')::numeric AS score,
               t.realized_pnl_dollars                       AS pnl
          FROM options_paper_trade t
          JOIN options_strategy_candidate c
            ON c.id = t.strategy_candidate_id
         WHERE t.strategy_candidate_id IS NOT NULL
           AND t.realized_pnl_dollars IS NOT NULL
           AND (c.diagnostics ? 'confidence_v2')
        """
    )).all()
    result = bucketize(
        [(r.score, r.pnl) for r in rows],
        buckets=BUCKETS_CONFIDENCE_V2,
    )
    result["dimension"] = "options_confidence_v2"
    return result


__all__ = [
    "MIN_CLOSES",
    "PER_BUCKET_MIN",
    "BUCKETS_CONVICTION",
    "BUCKETS_CONFIDENCE_V2",
    "bucketize",
    "conviction_outcome_buckets",
    "confidence_v2_outcome_buckets",
]
