"""Tiered performance report: recommendation-level + experimental.

Tier 1 (core, trusted):
    Trade-counting stats with direct, defensible meaning over
    recommendation-level outcomes. Decimal-native.

Tier 2 (conditional):
    Grouped breakdowns — confidence buckets, per-asset, per-month.
    Each breakdown entry runs Tier-1 stats over its subgroup.

Tier 3 (experimental):
    Annualized risk-adjusted ratios (Sharpe/Sortino/Calmar) + drawdown.
    These treat the sequence of recommendation returns as a portfolio
    return series — they ARE NOT a true portfolio P&L stream. Interpret
    with care. Emitted alongside a warning.
"""

from __future__ import annotations

import statistics as stats
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from apps.api.src.domain.features.regime_classifier import (
    DD_REGIMES,
    TREND_REGIMES,
    VOL_REGIMES,
)
from apps.api.src.domain.performance.metrics import compute_metrics


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------


@dataclass
class OutcomeRecord:
    """Flat record used for tiered aggregation.

    Empty ``return_value`` or ``label`` fields cause the record to be
    skipped (unlabeled outcomes don't participate in metrics).
    """
    generated_at_iso: str
    symbol: str
    asset_id: str
    confidence: Decimal | None
    return_value: Decimal | None
    label: int | None
    trend_regime: str | None = None
    volatility_regime: str | None = None
    drawdown_regime: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _filter_labeled(records: list[OutcomeRecord]) -> list[OutcomeRecord]:
    return [
        r for r in records
        if r.return_value is not None and r.label is not None
    ]


def _returns_and_labels(
    records: list[OutcomeRecord],
) -> tuple[list[Decimal], list[int]]:
    returns = [r.return_value for r in records if r.return_value is not None]  # type: ignore[misc]
    labels = [r.label for r in records if r.label is not None]
    return returns, labels  # type: ignore[return-value]


def _hit_rate(wins: int, losses: int) -> Decimal | None:
    decisive = wins + losses
    if decisive == 0:
        return None
    return Decimal(wins) / Decimal(decisive)


def _median(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    return Decimal(str(stats.median(values)))


# ---------------------------------------------------------------------------
# Tier 1
# ---------------------------------------------------------------------------


def compute_core_metrics(
    records: list[OutcomeRecord],
) -> dict[str, Any]:
    """Trade-counting Tier-1 metrics. Always safe to report."""
    labeled = _filter_labeled(records)
    returns, labels = _returns_and_labels(labeled)
    base = compute_metrics(returns, labels)

    return {
        "total_trades": base.total_trades,
        "wins": base.wins,
        "losses": base.losses,
        "neutral": base.neutral,
        # decisive-only hit rate (preferred)
        "hit_rate": _hit_rate(base.wins, base.losses),
        # legacy: wins / total_trades (includes neutral)
        "win_rate": base.win_rate,
        "expectancy": base.expectancy,
        "avg_return": base.expectancy,
        "median_return": _median(returns),
        "profit_factor": base.profit_factor,
        "total_return": base.total_return,
    }


# ---------------------------------------------------------------------------
# Tier 2 — conditional breakdowns
# ---------------------------------------------------------------------------


def _bucket_for_confidence(conf: Decimal | None) -> str:
    if conf is None:
        return "Unknown"
    if conf < Decimal("30"):
        return "Low (0-30)"
    if conf < Decimal("60"):
        return "Medium (30-60)"
    return "High (60-100)"


def compute_confidence_buckets(
    records: list[OutcomeRecord],
) -> list[dict[str, Any]]:
    """Confidence calibration: hit rate + avg return per confidence bucket."""
    buckets: dict[str, list[OutcomeRecord]] = {
        "Low (0-30)": [],
        "Medium (30-60)": [],
        "High (60-100)": [],
        "Unknown": [],
    }
    for r in _filter_labeled(records):
        buckets[_bucket_for_confidence(r.confidence)].append(r)

    out: list[dict[str, Any]] = []
    for label, rows in buckets.items():
        if not rows:
            out.append({
                "bucket": label,
                "count": 0,
                "hit_rate": None,
                "expectancy": None,
                "median_return": None,
            })
            continue
        rets, lbls = _returns_and_labels(rows)
        wins = sum(1 for l in lbls if l == 1)
        losses = sum(1 for l in lbls if l == -1)
        out.append({
            "bucket": label,
            "count": len(rows),
            "hit_rate": _hit_rate(wins, losses),
            "expectancy": (
                sum(rets, Decimal("0")) / Decimal(len(rets))
                if rets else None
            ),
            "median_return": _median(rets),
        })
    return out


def compute_per_asset(
    records: list[OutcomeRecord],
) -> list[dict[str, Any]]:
    by_symbol: dict[str, list[OutcomeRecord]] = {}
    for r in _filter_labeled(records):
        by_symbol.setdefault(r.symbol, []).append(r)

    out: list[dict[str, Any]] = []
    for symbol, rows in by_symbol.items():
        rets, lbls = _returns_and_labels(rows)
        wins = sum(1 for l in lbls if l == 1)
        losses = sum(1 for l in lbls if l == -1)
        out.append({
            "symbol": symbol,
            "asset_id": rows[0].asset_id,
            "count": len(rows),
            "hit_rate": _hit_rate(wins, losses),
            "expectancy": (
                sum(rets, Decimal("0")) / Decimal(len(rets))
                if rets else None
            ),
            "median_return": _median(rets),
            "wins": wins,
            "losses": losses,
        })
    # Deterministic ordering
    out.sort(key=lambda d: d["symbol"])
    return out


def _compute_per_regime(
    records: list[OutcomeRecord],
    attr: str,
    emit_states: tuple[str, ...],
) -> list[dict[str, Any]]:
    """Group records by regime attribute; emit fixed bucket list deterministically."""
    by_state: dict[str, list[OutcomeRecord]] = {s: [] for s in emit_states}
    by_state["unknown"] = []
    for r in _filter_labeled(records):
        state = getattr(r, attr, None)
        if state in by_state:
            by_state[state].append(r)
        else:
            by_state["unknown"].append(r)

    out: list[dict[str, Any]] = []
    ordered_keys = list(emit_states) + ["unknown"]
    for state in ordered_keys:
        rows = by_state[state]
        if not rows:
            out.append({
                "regime": state,
                "count": 0,
                "hit_rate": None,
                "expectancy": None,
                "median_return": None,
            })
            continue
        rets, lbls = _returns_and_labels(rows)
        wins = sum(1 for l in lbls if l == 1)
        losses = sum(1 for l in lbls if l == -1)
        out.append({
            "regime": state,
            "count": len(rows),
            "hit_rate": _hit_rate(wins, losses),
            "expectancy": (
                sum(rets, Decimal("0")) / Decimal(len(rets))
                if rets else None
            ),
            "median_return": _median(rets),
        })
    return out


def compute_per_trend_regime(records: list[OutcomeRecord]) -> list[dict[str, Any]]:
    return _compute_per_regime(records, "trend_regime", TREND_REGIMES)


def compute_per_volatility_regime(records: list[OutcomeRecord]) -> list[dict[str, Any]]:
    return _compute_per_regime(records, "volatility_regime", VOL_REGIMES)


def compute_per_drawdown_regime(records: list[OutcomeRecord]) -> list[dict[str, Any]]:
    return _compute_per_regime(records, "drawdown_regime", DD_REGIMES)


# ---------------------------------------------------------------------------
# Confidence × regime cross-tab
# ---------------------------------------------------------------------------


CONFIDENCE_BUCKETS: tuple[str, ...] = (
    "Low (0-30)",
    "Medium (30-60)",
    "High (60-100)",
    "Unknown",
)


def compute_confidence_regime_matrix(
    records: list[OutcomeRecord],
    regime_attr: str,
    regime_states: tuple[str, ...],
) -> list[dict[str, Any]]:
    """Cross-tab: confidence bucket × regime state.

    Emits ``len(CONFIDENCE_BUCKETS) * (len(regime_states) + 1)`` rows in
    deterministic order — confidence outer, regime inner. Empty cells carry
    ``count=0`` with None metrics.
    """
    regime_keys = list(regime_states) + ["unknown"]
    rows: list[dict[str, Any]] = []
    for bucket in CONFIDENCE_BUCKETS:
        for regime in regime_keys:
            matching: list[OutcomeRecord] = []
            for r in _filter_labeled(records):
                if _bucket_for_confidence(r.confidence) != bucket:
                    continue
                state = getattr(r, regime_attr, None) or "unknown"
                if state != regime:
                    continue
                matching.append(r)

            if not matching:
                rows.append({
                    "confidence_bucket": bucket,
                    "regime": regime,
                    "count": 0,
                    "hit_rate": None,
                    "expectancy": None,
                    "median_return": None,
                })
                continue

            rets, lbls = _returns_and_labels(matching)
            wins = sum(1 for l in lbls if l == 1)
            losses = sum(1 for l in lbls if l == -1)
            rows.append({
                "confidence_bucket": bucket,
                "regime": regime,
                "count": len(matching),
                "hit_rate": _hit_rate(wins, losses),
                "expectancy": (
                    sum(rets, Decimal("0")) / Decimal(len(rets))
                    if rets else None
                ),
                "median_return": _median(rets),
            })
    return rows


# ---------------------------------------------------------------------------
# Insight flags
# ---------------------------------------------------------------------------


LOW_SAMPLE_THRESHOLD = 5
INVERSION_MIN_SAMPLES = 5
REGIME_SENSITIVITY_SPREAD = Decimal("0.20")


def _to_decimal(v: Any) -> Decimal | None:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return v
    try:
        return Decimal(str(v))
    except (ValueError, TypeError):
        return None


def compute_insights(
    confidence_buckets: list[dict[str, Any]],
    regime_breakdowns: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Derive lightweight insight flags from tier-2 aggregates.

    - ``confidence_inversion``: higher-confidence bucket hit_rate < lower bucket
      (both with >= INVERSION_MIN_SAMPLES samples).
    - ``regime_sensitivity``: per dimension, spread(best - worst hit_rate) over
      regimes with >= LOW_SAMPLE_THRESHOLD samples exceeds 0.20.
    - ``low_sample_warnings``: non-empty buckets with count < LOW_SAMPLE_THRESHOLD.
    """
    conf_by_name = {b["bucket"]: b for b in confidence_buckets}

    # ---------- confidence inversion ----------
    inversions: list[dict[str, Any]] = []
    ordered_pairs = [
        ("High (60-100)", "Low (0-30)"),
        ("High (60-100)", "Medium (30-60)"),
        ("Medium (30-60)", "Low (0-30)"),
    ]
    for higher, lower in ordered_pairs:
        hi = conf_by_name.get(higher) or {}
        lo = conf_by_name.get(lower) or {}
        hi_n = hi.get("count", 0)
        lo_n = lo.get("count", 0)
        hi_hr = _to_decimal(hi.get("hit_rate"))
        lo_hr = _to_decimal(lo.get("hit_rate"))
        if hi_n < INVERSION_MIN_SAMPLES or lo_n < INVERSION_MIN_SAMPLES:
            continue
        if hi_hr is None or lo_hr is None:
            continue
        if hi_hr < lo_hr:
            inversions.append({
                "higher_bucket": higher,
                "higher_hit_rate": hi_hr,
                "lower_bucket": lower,
                "lower_hit_rate": lo_hr,
                "spread": lo_hr - hi_hr,
            })

    # ---------- regime sensitivity ----------
    sensitivity: list[dict[str, Any]] = []
    for dimension in ("trend", "volatility", "drawdown"):
        rows = regime_breakdowns.get(dimension, [])
        eligible: list[tuple[str, Decimal]] = []
        for r in rows:
            if r.get("regime") == "unknown":
                continue
            hr = _to_decimal(r.get("hit_rate"))
            if hr is None:
                continue
            if r.get("count", 0) < LOW_SAMPLE_THRESHOLD:
                continue
            eligible.append((r["regime"], hr))
        if len(eligible) < 2:
            continue
        # Deterministic: sort by (hit_rate, regime) to stabilize tiebreaks.
        eligible_sorted = sorted(eligible, key=lambda t: (t[1], t[0]))
        worst_regime, worst_hr = eligible_sorted[0]
        best_regime, best_hr = eligible_sorted[-1]
        spread = best_hr - worst_hr
        if spread > REGIME_SENSITIVITY_SPREAD:
            sensitivity.append({
                "dimension": dimension,
                "best_regime": best_regime,
                "best_hit_rate": best_hr,
                "worst_regime": worst_regime,
                "worst_hit_rate": worst_hr,
                "spread": spread,
            })

    # ---------- low-sample warnings ----------
    warnings: list[dict[str, Any]] = []
    for b in confidence_buckets:
        count = b.get("count", 0)
        if 0 < count < LOW_SAMPLE_THRESHOLD:
            warnings.append({
                "dimension": "confidence",
                "label": b["bucket"],
                "count": count,
            })
    for dimension, rows in regime_breakdowns.items():
        for r in rows:
            count = r.get("count", 0)
            if 0 < count < LOW_SAMPLE_THRESHOLD and r.get("regime") != "unknown":
                warnings.append({
                    "dimension": f"regime.{dimension}",
                    "label": r["regime"],
                    "count": count,
                })

    return {
        "confidence_inversion": inversions,
        "regime_sensitivity": sensitivity,
        "low_sample_warnings": warnings,
    }


def compute_per_month(
    records: list[OutcomeRecord],
) -> list[dict[str, Any]]:
    by_month: dict[str, list[OutcomeRecord]] = {}
    for r in _filter_labeled(records):
        month_key = r.generated_at_iso[:7]  # "YYYY-MM"
        by_month.setdefault(month_key, []).append(r)

    out: list[dict[str, Any]] = []
    for month, rows in by_month.items():
        rets, lbls = _returns_and_labels(rows)
        wins = sum(1 for l in lbls if l == 1)
        losses = sum(1 for l in lbls if l == -1)
        out.append({
            "month": month,
            "count": len(rows),
            "hit_rate": _hit_rate(wins, losses),
            "expectancy": (
                sum(rets, Decimal("0")) / Decimal(len(rets))
                if rets else None
            ),
        })
    out.sort(key=lambda d: d["month"])
    return out


# ---------------------------------------------------------------------------
# Tier 3 — experimental
# ---------------------------------------------------------------------------


EXPERIMENTAL_WARNING = (
    "EXPERIMENTAL: Sharpe / Sortino / Calmar and drawdown metrics treat the "
    "sequence of recommendation returns as a portfolio return series. This "
    "system does NOT yet track an actual invested portfolio; recommendations "
    "may overlap, differ in sizing, or never be acted on. Annualization "
    "assumes equal spacing between trades at the window frequency. Use these "
    "figures as a directional quality signal only — not as true portfolio "
    "performance."
)


def compute_experimental_metrics(
    records: list[OutcomeRecord],
    annualization: int,
) -> dict[str, Any]:
    labeled = _filter_labeled(records)
    returns, labels = _returns_and_labels(labeled)
    base = compute_metrics(returns, labels, annualization=annualization)
    return {
        "__warning__": EXPERIMENTAL_WARNING,
        "annualization": annualization,
        "sharpe_ratio": base.sharpe_ratio,
        "sortino_ratio": base.sortino_ratio,
        "calmar_ratio": base.calmar_ratio,
        "max_drawdown": base.max_drawdown,
        "max_drawdown_duration": base.max_drawdown_duration,
    }


# ---------------------------------------------------------------------------
# Full report
# ---------------------------------------------------------------------------


def compute_report(
    records: list[OutcomeRecord],
    annualization: int,
) -> dict[str, Any]:
    """Build the tiered performance report for a single window."""
    conf_buckets = compute_confidence_buckets(records)
    by_trend = compute_per_trend_regime(records)
    by_vol = compute_per_volatility_regime(records)
    by_dd = compute_per_drawdown_regime(records)
    regime_breakdowns = {
        "trend": by_trend,
        "volatility": by_vol,
        "drawdown": by_dd,
    }

    cross_matrix = {
        "trend": compute_confidence_regime_matrix(records, "trend_regime", TREND_REGIMES),
        "volatility": compute_confidence_regime_matrix(records, "volatility_regime", VOL_REGIMES),
        "drawdown": compute_confidence_regime_matrix(records, "drawdown_regime", DD_REGIMES),
    }
    insights = compute_insights(conf_buckets, regime_breakdowns)

    return {
        "recommendation_metrics": {
            "tier_1_core": compute_core_metrics(records),
            "tier_2_conditional": {
                "confidence_buckets": conf_buckets,
                "per_asset": compute_per_asset(records),
                "per_month": compute_per_month(records),
                "by_trend_regime": by_trend,
                "by_volatility_regime": by_vol,
                "by_drawdown_regime": by_dd,
                "confidence_regime_matrix": cross_matrix,
                "insights": insights,
            },
        },
        "experimental_metrics": compute_experimental_metrics(
            records, annualization=annualization
        ),
    }
