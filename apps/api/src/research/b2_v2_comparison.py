"""B2 vs V2 head-to-head comparison analytics.

Pure functions over per-day joined rows. NEVER mutates state. NEVER
changes thresholds. NEVER triggers execution. NEVER touches promotion
or routing systems.

Compares the production-shadow strategy B2 (`tsmom_60_no_stress`)
against the research-shadow strategy V2 (`tsmom_60_no_stress_v2_persist3`)
on days where both engines decided.

Input row shape (one dict per joined date, produced by the API layer
joining `paper_shadow_log` on `(as_of_date, instrument)` across the
two `source_strategy` values):

    {
      "as_of_date":     date,
      "instrument":     str,
      "b2_signal":      "LONG" | "FLAT",
      "v2_signal":      "LONG" | "FLAT",
      "b2_regime":      "STRESS" | "DIRECTIONAL" | "NEUTRAL" | None,
      "v2_regime":      "STRESS" | "DIRECTIONAL" | "NEUTRAL" | None,
      "fwd_return_1d":  float | None,
      "fwd_return_5d":  float | None,
      "b2_trend":       float | None,
      "v2_trend":       float | None,
    }

Output verdict pipeline order is fixed:
    base verdict  →  tail-sensitivity guard  →  readiness

The guard is downgrade-only and never modifies thresholds.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Frozen thresholds — change only with revision history doc update
# ---------------------------------------------------------------------------

VERDICT_EDGE_BPS_THRESHOLD = 5.0
VERDICT_CUM_DIFF_PCT_THRESHOLD = 0.5
VERDICT_P99_DELTA_BPS_THRESHOLD = -10.0
VERDICT_P99_DELTA_BPS_HARD = -25.0

CONFIDENCE_N_SATURATION = 60
CONFIDENCE_N_FLOOR = 10

READINESS_STRONG_CONFIDENCE = 0.7
READINESS_REVIEW_CONFIDENCE = 0.4
READINESS_STRONG_MIN_N = 30

TAIL_GUARD_EDGE_MIN_BPS = 10.0
TAIL_GUARD_CONFIDENCE_CAP = 0.5

STABILITY_TREND_DEAD_ZONE_BPS = 5.0
STABILITY_LAST_N_DAYS = 30


# ---------------------------------------------------------------------------
# Stat helpers
# ---------------------------------------------------------------------------

def _finite(xs: Sequence[float | None]) -> list[float]:
    return [
        float(x) for x in xs
        if x is not None
        and isinstance(x, (int, float))
        and math.isfinite(float(x))
    ]


def _quantile(xs: Sequence[float], q: float) -> float:
    a = sorted(_finite(xs))
    if not a:
        return float("nan")
    if len(a) == 1:
        return float(a[0])
    pos = (len(a) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    frac = pos - lo
    return float(a[lo] * (1 - frac) + a[hi] * frac)


def _engine_return(signal: str | None, fwd_ret: float | None) -> float | None:
    """LONG → fwd_ret, FLAT → 0.0, anything else → None."""
    if fwd_ret is None or signal not in ("LONG", "FLAT"):
        return None
    return float(fwd_ret) if signal == "LONG" else 0.0


def _b2_return(row: dict) -> float | None:
    return _engine_return(row.get("b2_signal"), row.get("fwd_return_1d"))


def _v2_return(row: dict) -> float | None:
    return _engine_return(row.get("v2_signal"), row.get("fwd_return_1d"))


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


# ---------------------------------------------------------------------------
# Part 1 — Divergence extraction
# ---------------------------------------------------------------------------

def extract_divergence(rows: list[dict]) -> list[dict]:
    """Return rows where b2_signal != v2_signal, tagged with class + returns.

    Skips rows missing fwd_return_1d (unrealized) or with non-LONG/FLAT
    signals on either side. Each output row is a shallow-copy with three
    added fields: divergence_class, b2_return, v2_return, delta.
    """
    out: list[dict] = []
    for r in rows:
        b2 = r.get("b2_signal")
        v2 = r.get("v2_signal")
        ret = r.get("fwd_return_1d")
        if ret is None:
            continue
        if b2 not in ("LONG", "FLAT") or v2 not in ("LONG", "FLAT"):
            continue
        if b2 == v2:
            continue
        b2_ret = float(ret) if b2 == "LONG" else 0.0
        v2_ret = float(ret) if v2 == "LONG" else 0.0
        cls = (
            "B2_FLAT_V2_LONG" if (b2 == "FLAT" and v2 == "LONG")
            else "B2_LONG_V2_FLAT"
        )
        new = dict(r)
        new["divergence_class"] = cls
        new["b2_return"] = b2_ret
        new["v2_return"] = v2_ret
        new["delta"] = v2_ret - b2_ret
        out.append(new)
    return out


# ---------------------------------------------------------------------------
# Part 2 — Divergence metrics (incl. impact-weighted edge)
# ---------------------------------------------------------------------------

_EMPTY_METRICS = {
    "n_divergent_days": 0,
    "n_b2_flat_v2_long": 0,
    "n_b2_long_v2_flat": 0,
    "win_rate_v2_vs_b2_pct": None,
    "avg_return_diff_1d_bps": None,
    "avg_return_diff_5d_bps": None,
    "cumulative_return_diff_pct": None,
    "avoided_losses_count": 0,
    "avoided_losses_avg_bps": None,
    "new_losses_count": 0,
    "new_losses_avg_bps": None,
    "impact_weighted_edge": None,
}


def divergence_metrics(div_rows: list[dict]) -> dict:
    """Stats over divergent days only. Pass output of extract_divergence()."""
    if not div_rows:
        return dict(_EMPTY_METRICS)

    deltas: list[float] = []
    deltas_5d: list[float] = []
    avoided_losses: list[float] = []   # B2 LONG, V2 FLAT, ret < 0
    new_losses: list[float] = []       # B2 FLAT, V2 LONG, ret < 0
    n_b2flat_v2long = 0
    n_b2long_v2flat = 0
    eq_b2 = 1.0
    eq_v2 = 1.0
    sum_abs_returns = 0.0
    sum_delta = 0.0

    for r in div_rows:
        d = float(r["delta"])
        b2_ret = float(r["b2_return"])
        v2_ret = float(r["v2_return"])
        ret = float(r["fwd_return_1d"])
        deltas.append(d)
        sum_delta += d
        sum_abs_returns += abs(b2_ret) + abs(v2_ret)
        eq_b2 *= 1.0 + b2_ret
        eq_v2 *= 1.0 + v2_ret
        cls = r["divergence_class"]
        if cls == "B2_FLAT_V2_LONG":
            n_b2flat_v2long += 1
            if ret < 0:
                new_losses.append(-ret)
        else:  # B2_LONG_V2_FLAT
            n_b2long_v2flat += 1
            if ret < 0:
                avoided_losses.append(-ret)

        ret5 = r.get("fwd_return_5d")
        if ret5 is not None and isinstance(ret5, (int, float)) \
                and math.isfinite(float(ret5)):
            b2_ret5 = float(ret5) if r["b2_signal"] == "LONG" else 0.0
            v2_ret5 = float(ret5) if r["v2_signal"] == "LONG" else 0.0
            deltas_5d.append(v2_ret5 - b2_ret5)

    n = len(deltas)
    n_wins = sum(1 for d in deltas if d > 0)
    iw_edge = (sum_delta / sum_abs_returns) if sum_abs_returns > 0 else None

    return {
        "n_divergent_days": int(n),
        "n_b2_flat_v2_long": int(n_b2flat_v2long),
        "n_b2_long_v2_flat": int(n_b2long_v2flat),
        "win_rate_v2_vs_b2_pct": round((n_wins / n) * 100, 2),
        "avg_return_diff_1d_bps": round((sum_delta / n) * 1e4, 2),
        "avg_return_diff_5d_bps": (
            round((sum(deltas_5d) / len(deltas_5d)) * 1e4, 2)
            if deltas_5d else None
        ),
        "cumulative_return_diff_pct": round((eq_v2 - eq_b2) * 100, 4),
        "avoided_losses_count": int(len(avoided_losses)),
        "avoided_losses_avg_bps": (
            round((sum(avoided_losses) / len(avoided_losses)) * 1e4, 2)
            if avoided_losses else None
        ),
        "new_losses_count": int(len(new_losses)),
        "new_losses_avg_bps": (
            round((sum(new_losses) / len(new_losses)) * 1e4, 2)
            if new_losses else None
        ),
        "impact_weighted_edge": (
            round(iw_edge, 6) if iw_edge is not None else None
        ),
    }


# ---------------------------------------------------------------------------
# Part 2b — Regime-conditioned metrics
# ---------------------------------------------------------------------------

REGIMES = ("STRESS", "DIRECTIONAL", "NEUTRAL")


def metrics_by_regime(div_rows: list[dict]) -> dict:
    """divergence_metrics partitioned by B2's regime_label.

    Partitions are exclusive — each div_row contributes to exactly one
    bucket (or to none if b2_regime is missing/unknown). Sum of
    n_divergent_days across buckets equals the count of div_rows whose
    b2_regime is in REGIMES.
    """
    out: dict = {}
    for regime in REGIMES:
        bucket = [r for r in div_rows if r.get("b2_regime") == regime]
        out[regime.lower()] = divergence_metrics(bucket)
    return out


# ---------------------------------------------------------------------------
# Part 3 — Tail comparison (over ALL rows, not just divergent)
# ---------------------------------------------------------------------------

def tail_comparison(rows: list[dict]) -> dict:
    """Compare tail behavior of B2 vs V2 daily realized returns."""
    b2 = _finite([_b2_return(r) for r in rows])
    v2 = _finite([_v2_return(r) for r in rows])

    def _stats(arr: list[float]) -> dict:
        if not arr:
            return {
                "n": 0,
                "p95_loss_bps": None,
                "p99_loss_bps": None,
                "worst_5_losses_bps": [],
            }
        worst = sorted(arr)[:5]
        return {
            "n": int(len(arr)),
            "p95_loss_bps": (
                round(_quantile(arr, 0.05) * 1e4, 2)
                if len(arr) > 5 else None
            ),
            "p99_loss_bps": (
                round(_quantile(arr, 0.01) * 1e4, 2)
                if len(arr) > 100 else None
            ),
            "worst_5_losses_bps": [round(x * 1e4, 2) for x in worst],
        }

    b2_stats = _stats(b2)
    v2_stats = _stats(v2)

    def _delta(field: str) -> float | None:
        b2v = b2_stats.get(field)
        v2v = v2_stats.get(field)
        if b2v is None or v2v is None:
            return None
        return round(v2v - b2v, 2)

    return {
        "b2": b2_stats,
        "v2": v2_stats,
        "tail_delta_p95_bps": _delta("p95_loss_bps"),
        "tail_delta_p99_bps": _delta("p99_loss_bps"),
    }


# ---------------------------------------------------------------------------
# Part 4 — Stability
# ---------------------------------------------------------------------------

def _trend_label(recent: float | None, prior: float | None) -> str:
    if recent is None or prior is None:
        return "INSUFFICIENT"
    delta = recent - prior
    if delta > STABILITY_TREND_DEAD_ZONE_BPS:
        return "IMPROVING"
    if delta < -STABILITY_TREND_DEAD_ZONE_BPS:
        return "DECLINING"
    return "STABLE"


def stability_check(div_rows: list[dict]) -> dict:
    """Halves split + last_30 vs prior_30 windows on divergent days."""
    n = len(div_rows)
    half = n // 2
    first_half = div_rows[:half]
    second_half = div_rows[half:]

    last_30 = div_rows[-STABILITY_LAST_N_DAYS:] if n >= STABILITY_LAST_N_DAYS else []
    prior_30 = (
        div_rows[-2 * STABILITY_LAST_N_DAYS:-STABILITY_LAST_N_DAYS]
        if n >= 2 * STABILITY_LAST_N_DAYS else []
    )

    fh = divergence_metrics(first_half)
    sh = divergence_metrics(second_half)
    l30 = divergence_metrics(last_30)
    p30 = divergence_metrics(prior_30)

    return {
        "first_half_vs_second_half": {
            "first_half_edge_bps": fh["avg_return_diff_1d_bps"],
            "second_half_edge_bps": sh["avg_return_diff_1d_bps"],
            "n_first": fh["n_divergent_days"],
            "n_second": sh["n_divergent_days"],
            "trend": _trend_label(
                sh["avg_return_diff_1d_bps"],
                fh["avg_return_diff_1d_bps"],
            ),
        },
        "last_30_vs_prior_30": {
            "last_30_edge_bps": l30["avg_return_diff_1d_bps"],
            "prior_30_edge_bps": p30["avg_return_diff_1d_bps"],
            "n_last": l30["n_divergent_days"],
            "n_prior": p30["n_divergent_days"],
            "trend": _trend_label(
                l30["avg_return_diff_1d_bps"],
                p30["avg_return_diff_1d_bps"],
            ),
        },
    }


# ---------------------------------------------------------------------------
# Part 5 — Verdict (base → tail guard → readiness)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _BaseVerdict:
    label: str          # V2_BETTER | B2_BETTER | INCONCLUSIVE
    confidence: float   # 0..1


def _base_verdict(metrics: dict, tail: dict, stability: dict) -> _BaseVerdict:
    n = metrics["n_divergent_days"]
    edge = metrics["avg_return_diff_1d_bps"]
    cum = metrics["cumulative_return_diff_pct"]
    p99_d = tail["tail_delta_p99_bps"]

    if n < CONFIDENCE_N_FLOOR or edge is None:
        label = "INCONCLUSIVE"
    elif (
        edge >= VERDICT_EDGE_BPS_THRESHOLD
        and cum is not None
        and cum >= VERDICT_CUM_DIFF_PCT_THRESHOLD
        and (p99_d is None or p99_d >= VERDICT_P99_DELTA_BPS_THRESHOLD)
    ):
        label = "V2_BETTER"
    elif (
        edge <= -VERDICT_EDGE_BPS_THRESHOLD
        or (cum is not None and cum <= -VERDICT_CUM_DIFF_PCT_THRESHOLD)
        or (p99_d is not None and p99_d <= VERDICT_P99_DELTA_BPS_HARD)
    ):
        label = "B2_BETTER"
    else:
        label = "INCONCLUSIVE"

    sample_score = _clamp(
        (n - CONFIDENCE_N_FLOOR) / max(1, CONFIDENCE_N_SATURATION - CONFIDENCE_N_FLOOR),
        0.0, 1.0,
    )
    fh = stability["first_half_vs_second_half"]
    fh_e = fh["first_half_edge_bps"]
    sh_e = fh["second_half_edge_bps"]
    if fh_e is not None and sh_e is not None:
        sign_consistency = 1.0 if (fh_e > 0) == (sh_e > 0) else 0.0
    else:
        sign_consistency = 0.0
    trend = stability["last_30_vs_prior_30"]["trend"]
    trend_score = 1.0 if trend in ("IMPROVING", "STABLE") else 0.0

    confidence = _clamp(
        0.4 * sample_score
        + 0.3 * sign_consistency
        + 0.3 * trend_score,
        0.0, 1.0,
    )
    return _BaseVerdict(label=label, confidence=round(confidence, 4))


_DOWNGRADE_MAP = {
    "V2_BETTER": "INCONCLUSIVE",
    "INCONCLUSIVE": "B2_BETTER",
    "B2_BETTER": "B2_BETTER",
}


def _apply_tail_guard(
    base: _BaseVerdict,
    metrics: dict,
    tail: dict,
) -> dict:
    edge = metrics["avg_return_diff_1d_bps"]
    p99_d = tail["tail_delta_p99_bps"]

    p99_worsens = (p99_d is not None) and (p99_d < 0)
    edge_small = (edge is not None) and (edge < TAIL_GUARD_EDGE_MIN_BPS)

    triggered = bool(p99_worsens and edge_small)

    if triggered:
        label = _DOWNGRADE_MAP[base.label]
        confidence = round(min(base.confidence, TAIL_GUARD_CONFIDENCE_CAP), 4)
        reason = (
            f"p99 worsens {abs(p99_d):.1f} bps; "
            f"edge gain {edge:.1f} bps < {TAIL_GUARD_EDGE_MIN_BPS:.1f} threshold"
        )
    else:
        label = base.label
        confidence = base.confidence
        reason = None

    return {
        "verdict": label,
        "confidence": confidence,
        "tail_guard_triggered": triggered,
        "tail_guard_reason": reason,
    }


def _readiness(verdict_label: str, confidence: float, n: int) -> str:
    if (
        verdict_label == "V2_BETTER"
        and confidence >= READINESS_STRONG_CONFIDENCE
        and n >= READINESS_STRONG_MIN_N
    ):
        return "STRONG_CANDIDATE"
    if verdict_label == "V2_BETTER" and confidence >= READINESS_REVIEW_CONFIDENCE:
        return "REVIEW"
    return "NOT_READY"


def verdict(metrics: dict, tail: dict, stability: dict) -> dict:
    """Pipeline: base verdict → tail-sensitivity guard → readiness."""
    base = _base_verdict(metrics, tail, stability)
    guarded = _apply_tail_guard(base, metrics, tail)
    readiness = _readiness(
        guarded["verdict"],
        guarded["confidence"],
        metrics["n_divergent_days"],
    )
    return {
        **guarded,
        "readiness": readiness,
        "base_verdict_before_guard": base.label,
        "base_confidence_before_guard": base.confidence,
    }


# ---------------------------------------------------------------------------
# Bundle
# ---------------------------------------------------------------------------

def compute_all(rows: list[dict]) -> dict:
    """Full bundle: divergence + metrics + regime breakdown + tail + stability + verdict."""
    div = extract_divergence(rows)
    metrics = divergence_metrics(div)
    by_regime = metrics_by_regime(div)
    tail = tail_comparison(rows)
    stab = stability_check(div)
    verd = verdict(metrics, tail, stab)
    return {
        "n_input_rows": len(rows),
        "n_divergent_rows": len(div),
        "metrics": metrics,
        "metrics_by_regime": by_regime,
        "tail": tail,
        "stability": stab,
        "verdict": verd,
        "thresholds": {
            "verdict_edge_bps": VERDICT_EDGE_BPS_THRESHOLD,
            "verdict_cum_diff_pct": VERDICT_CUM_DIFF_PCT_THRESHOLD,
            "verdict_p99_delta_bps": VERDICT_P99_DELTA_BPS_THRESHOLD,
            "verdict_p99_delta_bps_hard": VERDICT_P99_DELTA_BPS_HARD,
            "tail_guard_edge_min_bps": TAIL_GUARD_EDGE_MIN_BPS,
            "tail_guard_confidence_cap": TAIL_GUARD_CONFIDENCE_CAP,
            "stability_trend_dead_zone_bps": STABILITY_TREND_DEAD_ZONE_BPS,
            "readiness_strong_confidence": READINESS_STRONG_CONFIDENCE,
            "readiness_review_confidence": READINESS_REVIEW_CONFIDENCE,
            "readiness_strong_min_n": READINESS_STRONG_MIN_N,
        },
    }
