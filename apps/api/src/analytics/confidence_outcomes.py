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

# MP2B.2A — wire the bucket joins to the (gated) calibration math.
from apps.api.src.analytics.calibration import (
    brier_score,
    expected_calibration_error,
    reliability_bins,
)

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
        sel = [(s, p) for (s, p) in clean if s >= lo and (hi is None or s < hi)]
        n = len(sel)
        pnls = [p for (_s, p) in sel]
        tot = round(sum(pnls), 2) if n else 0.0
        # MP2B.1 — mean predicted score in this bucket. Enables an
        # expected-vs-observed reliability view later without retaining
        # item-level rows. Always emitted (not gated) — it is an input
        # descriptor, not an outcome rate.
        expected_score_avg = (
            round(sum(s for (s, _p) in sel) / n, 4) if n else None
        )
        if not sufficient or n < per_bucket_min:
            # No rates on thin samples — counts only, never a fake %.
            out.append({
                "bucket": label,
                "trade_count": n,
                "expected_score_avg": expected_score_avg,
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
                "expected_score_avg": expected_score_avg,
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


def _stock_pairs(rows: Any) -> list[tuple[float, bool]]:
    """Map stock rows (conviction 0–100, realized_pnl) -> (p in [0,1], win).
    Pure — conviction/100 implied probability; realized_pnl>0 = win."""
    return [
        (float(s) / 100.0, float(p) > 0)
        for (s, p) in rows
        if s is not None and p is not None
    ]


def _options_pairs(rows: Any) -> list[tuple[float, bool]]:
    """Map options rows (confidence_v2, realized_pnl_dollars) -> (p, win).
    Pure — confidence_v2 already in [0,1]; realized_pnl_dollars>0 = win."""
    return [
        (float(s), float(p) > 0)
        for (s, p) in rows
        if s is not None and p is not None
    ]


def _calibration_result(
    asset_class: str,
    pairs: list[tuple[float | None, bool]],
) -> dict[str, Any]:
    """Shape the gated calibration helpers into one read-side payload.

    The MIN_CALIBRATION_SAMPLES gate lives in the calibration helpers, so at
    low N this returns status='insufficient_for_calibration' with null
    brier/ece/bins — never a misleading number.
    """
    brier = brier_score(pairs)
    ece = expected_calibration_error(pairs)
    rel = reliability_bins(pairs)
    note = brier["note"]  # None | "insufficient_for_calibration"
    return {
        "asset_class": asset_class,
        "sample_count": brier["n"],
        "status": "ok" if note is None else note,
        "note": note,
        "brier_score": brier["brier_score"],
        "expected_calibration_error": ece["ece"],
        "reliability_bins": rel["bins"],
    }


def stock_conviction_calibration(session: Session) -> dict[str, Any]:
    """STOCKS — is conviction (as implied probability) calibrated to realized
    win rate? p = conviction/100; win = realized_pnl > 0; closed attributed
    paper positions only (MP1S link). SELECT-only. Gated below
    MIN_CALIBRATION_SAMPLES. NOTE: conviction is not a trained probability —
    treat as discrimination-as-probability, not true calibration."""
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
           -- BP7: live calibration must never include replay-namespaced rows
           -- ("{engine}+replay:{run_label}"). Result-invariant on live-only
           -- data; prevents replay outcomes from contaminating live.
           AND r.model_version NOT LIKE '%+replay:%'
        """
    )).all()
    pairs = _stock_pairs((r.score, r.pnl) for r in rows)
    return _calibration_result("stock", pairs)


def _like_escape(s: str) -> str:
    """Escape LIKE metacharacters so a run_label is matched literally."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def conviction_calibration_from_pairs(
    pairs: Any, *, scope: str = "replay", run_label: str | None = None,
) -> dict[str, Any]:
    """Pure calibration from (conviction 0-100, realized_pnl) pairs — e.g.
    ReplayRangeResult.closed_pairs. Reuses the gated math; labels scope/
    run_label so a replay result is never mistaken for live performance."""
    out = _calibration_result("stock", _stock_pairs(pairs))
    out["scope"] = scope
    out["run_label"] = run_label
    return out


def replay_conviction_calibration(
    session: Session, *, run_label: str,
) -> dict[str, Any]:
    """REPLAY-SCOPED stock conviction calibration — same join as the live
    surface but restricted to the replay namespace
    ``model_version LIKE '%+replay:{run_label}'`` (trailing-anchored, so
    run_label 'r1' never matches 'r12'). Reuses the MIN_CALIBRATION_SAMPLES
    gating; the payload is tagged scope='replay' + run_label so it is NOT
    live performance. SELECT-only, no schema."""
    pattern = f"%+replay:{_like_escape(run_label)}"
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
           AND r.model_version LIKE :pat ESCAPE '\\'
        """
    ), {"pat": pattern}).all()
    out = _calibration_result("stock", _stock_pairs((r.score, r.pnl) for r in rows))
    out["scope"] = "replay"
    out["run_label"] = run_label
    return out


def options_confidence_v2_calibration(session: Session) -> dict[str, Any]:
    """OPTIONS — is confidence_v2 calibrated to realized win rate?
    p = confidence_v2 (already 0–1); win = realized_pnl_dollars > 0; closed
    attributed options trades only (MP1A link). SELECT-only. Gated below
    MIN_CALIBRATION_SAMPLES."""
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
    pairs = _options_pairs((r.score, r.pnl) for r in rows)
    return _calibration_result("options", pairs)


__all__ = [
    "MIN_CLOSES",
    "PER_BUCKET_MIN",
    "BUCKETS_CONVICTION",
    "BUCKETS_CONFIDENCE_V2",
    "bucketize",
    "conviction_outcome_buckets",
    "confidence_v2_outcome_buckets",
    "stock_conviction_calibration",
    "replay_conviction_calibration",
    "conviction_calibration_from_pairs",
    "options_confidence_v2_calibration",
]
