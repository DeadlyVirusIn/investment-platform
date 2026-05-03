"""Pure aggregation functions — no DB, no I/O.

Inputs are lists of dicts representing joined (signal, outcome) rows. Output
is a deterministic `ScorecardMetrics` object suitable for persistence.

No ML. No weighting. No feedback. Simple aggregates only.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Iterable

# ---------------------------------------------------------------------------
# Calibration bucket edges (Phase 2 frozen)
# ---------------------------------------------------------------------------

CALIBRATION_BUCKETS: list[tuple[float, float, str]] = [
    (0.0, 0.2, "0.0-0.2"),
    (0.2, 0.4, "0.2-0.4"),
    (0.4, 0.6, "0.4-0.6"),
    (0.6, 0.8, "0.6-0.8"),
    (0.8, 1.0001, "0.8-1.0"),   # right-inclusive for max
]

WIN_LABEL = "win"


@dataclass
class ScorecardMetrics:
    total_signals: int = 0
    win_rate: float | None = None
    avg_return: float | None = None
    avg_drawdown: float | None = None
    sharpe_like_metric: float | None = None
    avg_days_to_evaluation: float | None = None
    max_days_to_evaluation: int | None = None
    pct_within_horizon: float | None = None
    calibration: list[dict[str, Any]] = field(default_factory=list)
    factor_effectiveness: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def _bucket_for(confidence: float | None) -> str | None:
    if confidence is None:
        return None
    for lo, hi, label in CALIBRATION_BUCKETS:
        if lo <= confidence < hi:
            return label
    return None


def _safe_mean(xs: list[float]) -> float | None:
    return statistics.fmean(xs) if xs else None


def _sharpe_like(returns: list[float]) -> float | None:
    """Mean / stdev. No annualization; Phase 2 proxy only."""
    if len(returns) < 2:
        return None
    m = statistics.fmean(returns)
    s = statistics.pstdev(returns)
    if s == 0:
        return None
    return round(m / s, 4)


# ---------------------------------------------------------------------------
# Core compute
# ---------------------------------------------------------------------------


def compute_scorecard(
    rows: Iterable[dict[str, Any]],
) -> ScorecardMetrics:
    """Aggregate metrics from joined (signal, signal_outcome) rows.

    Each row must contain at least:
      - outcome_label, realized_return, max_drawdown
      - confidence (0..1)
      - signal_as_of_date (datetime.date)
      - evaluation_timestamp (datetime with tzinfo)
      - holding_period_bars (int)
      - factor_top (list[dict] | None)

    Output is deterministic — no randomness, no iteration-order dependence.
    """
    rows = list(rows)
    if not rows:
        return ScorecardMetrics(total_signals=0)

    # --- core aggregates -----------------------------------------------------
    wins = 0
    returns: list[float] = []
    drawdowns: list[float] = []
    eval_days: list[int] = []
    within_horizon_hits = 0
    non_timeout_total = 0

    # --- calibration ---------------------------------------------------------
    bucket_counts: dict[str, int] = {lbl: 0 for _, _, lbl in CALIBRATION_BUCKETS}
    bucket_wins: dict[str, int] = {lbl: 0 for _, _, lbl in CALIBRATION_BUCKETS}
    bucket_returns: dict[str, list[float]] = {lbl: [] for _, _, lbl in CALIBRATION_BUCKETS}

    # --- factor effectiveness (keyed by top factor key) ----------------------
    factor_counts: dict[str, int] = {}
    factor_wins: dict[str, int] = {}
    factor_returns: dict[str, list[float]] = {}

    for r in rows:
        label = r.get("outcome_label")
        ret = _to_float(r.get("realized_return"))
        dd = _to_float(r.get("max_drawdown"))
        conf = _to_float(r.get("confidence"))
        holding = r.get("holding_period_bars") or 0
        eval_ts = r.get("evaluation_timestamp")
        as_of = r.get("signal_as_of_date")

        if label == WIN_LABEL:
            wins += 1
        if ret is not None:
            returns.append(ret)
        if dd is not None:
            drawdowns.append(dd)

        # Evaluation lag — only meaningful when both dates present
        if eval_ts is not None and as_of is not None:
            try:
                delta = (eval_ts.date() - as_of).days
            except AttributeError:
                delta = None
            if delta is not None and delta >= 0:
                eval_days.append(delta)
                # Non-timeout only — timeout would inflate the denominator unfairly
                if label != "timeout":
                    non_timeout_total += 1
                    if delta <= holding:
                        within_horizon_hits += 1

        # Calibration
        b = _bucket_for(conf)
        if b is not None:
            bucket_counts[b] += 1
            if label == WIN_LABEL:
                bucket_wins[b] += 1
            if ret is not None:
                bucket_returns[b].append(ret)

        # Factor effectiveness — use top-by-|contribution| factor only
        factor_top = r.get("factor_top") or []
        if factor_top:
            # already sorted by materializer; fall back to |contribution| here
            best = max(
                factor_top,
                key=lambda f: abs(_to_float(f.get("contribution")) or 0),
                default=None,
            )
            key = best.get("key") if best else None
            if key:
                factor_counts[key] = factor_counts.get(key, 0) + 1
                if label == WIN_LABEL:
                    factor_wins[key] = factor_wins.get(key, 0) + 1
                if ret is not None:
                    factor_returns.setdefault(key, []).append(ret)

    total = len(rows)
    avg_ret = _safe_mean(returns)
    avg_dd = _safe_mean(drawdowns)
    sharpe = _sharpe_like(returns)

    calibration = [
        {
            "bucket": lbl,
            "count": bucket_counts[lbl],
            "win_rate": round(bucket_wins[lbl] / bucket_counts[lbl], 4)
            if bucket_counts[lbl] > 0 else None,
            "avg_return": round(_safe_mean(bucket_returns[lbl]) or 0.0, 6)
            if bucket_returns[lbl] else None,
        }
        for _, _, lbl in CALIBRATION_BUCKETS
    ]

    factors = sorted(
        [
            {
                "factor": k,
                "count": factor_counts[k],
                "win_rate": round(factor_wins.get(k, 0) / factor_counts[k], 4),
                "avg_return": round(_safe_mean(factor_returns.get(k, [])) or 0.0, 6),
            }
            for k in factor_counts
        ],
        key=lambda x: (-x["count"], x["factor"]),   # deterministic
    )

    pct_within = (
        round(within_horizon_hits / non_timeout_total, 4)
        if non_timeout_total > 0 else None
    )

    return ScorecardMetrics(
        total_signals=total,
        win_rate=round(wins / total, 4) if total > 0 else None,
        avg_return=round(avg_ret, 6) if avg_ret is not None else None,
        avg_drawdown=round(avg_dd, 6) if avg_dd is not None else None,
        sharpe_like_metric=sharpe,
        avg_days_to_evaluation=round(_safe_mean([float(d) for d in eval_days]) or 0.0, 2)
            if eval_days else None,
        max_days_to_evaluation=max(eval_days) if eval_days else None,
        pct_within_horizon=pct_within,
        calibration=calibration,
        factor_effectiveness=factors,
    )
