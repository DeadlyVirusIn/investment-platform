"""Engine B → B2 divergence + tail-risk + readiness analytics.

Pure functions over per-day shadow rows. NEVER mutates state. NEVER
changes thresholds. NEVER triggers execution.

Input row shape (one dict per day):
    {
      "as_of_date": date,
      "engine_b_signal": "LONG" | "FLAT" | None,
      "b2_signal":       "LONG" | "FLAT" | None,
      "routed_signal":   "LONG" | "FLAT" | None,
      "regime_label":    "STRESS" | "DIRECTIONAL" | "NEUTRAL" | None,
      "fwd_return_1d":   float | None,
      "divergence_outcome": float | None,   # B - B2 (sign-aware)
      "divergence_flag": bool,
    }

The caller is the API layer (apps/api/src/api/engine_b_transition.py).
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass


PERIODS_PER_YEAR = 252


# ---------------------------------------------------------------------------
# Stat helpers
# ---------------------------------------------------------------------------

def _finite(xs: Sequence[float | None]) -> list[float]:
    return [float(x) for x in xs
            if x is not None and isinstance(x, (int, float))
            and math.isfinite(float(x))]


def _sharpe(rets: Sequence[float]) -> float:
    a = _finite(rets)
    if len(a) < 2:
        return float("nan")
    mu = sum(a) / len(a)
    try:
        sd = statistics.stdev(a)
    except statistics.StatisticsError:
        return float("nan")
    if sd == 0 or not math.isfinite(sd):
        return float("nan")
    return (mu / sd) * math.sqrt(PERIODS_PER_YEAR)


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


def _engine_ret(row: dict, who: str) -> float | None:
    """Realized return under signal of `engine_b` or `b2`. LONG=fwd_return_1d,
    FLAT=0."""
    sig = row.get(f"{who}_signal")
    r = row.get("fwd_return_1d")
    if r is None or sig not in ("LONG", "FLAT"):
        return None
    return float(r) if sig == "LONG" else 0.0


# ---------------------------------------------------------------------------
# Part 1 — Divergence analytics
# ---------------------------------------------------------------------------

def divergence_analytics(rows: list[dict]) -> dict:
    """Cross-engine outcome stats on divergent days only."""
    div = [r for r in rows
           if r.get("divergence_flag")
           and r.get("fwd_return_1d") is not None]
    if not div:
        return {
            "n_divergent_days": 0,
            "win_rate_b2_vs_b_pct": None,
            "avg_return_diff_bps": None,
            "cumulative_return_diff_pct": None,
            "avoided_loss_count": 0,
            "avoided_loss_avg_bps": None,
            "missed_win_count": 0,
            "missed_win_avg_bps": None,
        }
    advs: list[float] = []        # B2 advantage = -divergence_outcome
    avoided_losses: list[float] = []   # B was LONG, lost; B2 stayed FLAT
    missed_wins: list[float] = []      # B2 was LONG (won); B stayed FLAT
    eq = 1.0
    for r in div:
        do = r.get("divergence_outcome")
        if do is None:
            continue
        adv = -float(do)
        advs.append(adv)
        eq *= (1 + adv)
        b_sig = r.get("engine_b_signal")
        b2_sig = r.get("b2_signal")
        ret = float(r["fwd_return_1d"])
        if b_sig == "LONG" and b2_sig == "FLAT" and ret < 0:
            avoided_losses.append(-ret)            # positive number
        if b_sig == "FLAT" and b2_sig == "LONG" and ret > 0:
            missed_wins.append(ret)                # positive number
    if not advs:
        return {
            "n_divergent_days": int(len(div)),
            "win_rate_b2_vs_b_pct": None,
            "avg_return_diff_bps": None,
            "cumulative_return_diff_pct": None,
            "avoided_loss_count": 0,
            "avoided_loss_avg_bps": None,
            "missed_win_count": 0,
            "missed_win_avg_bps": None,
        }
    n_b2_wins = sum(1 for a in advs if a > 0)
    return {
        "n_divergent_days": int(len(advs)),
        "win_rate_b2_vs_b_pct": round((n_b2_wins / len(advs)) * 100, 2),
        "avg_return_diff_bps": round((sum(advs) / len(advs)) * 1e4, 2),
        "cumulative_return_diff_pct": round((eq - 1) * 100, 4),
        "avoided_loss_count": int(len(avoided_losses)),
        "avoided_loss_avg_bps": (round(
            (sum(avoided_losses) / len(avoided_losses)) * 1e4, 2)
            if avoided_losses else None),
        "missed_win_count": int(len(missed_wins)),
        "missed_win_avg_bps": (round(
            (sum(missed_wins) / len(missed_wins)) * 1e4, 2)
            if missed_wins else None),
    }


# ---------------------------------------------------------------------------
# Part 2 — Tail risk comparison
# ---------------------------------------------------------------------------

def tail_risk(rows: list[dict]) -> dict:
    """Compare worst-tail behavior of B vs B2 daily applied returns."""
    b = _finite([_engine_ret(r, "engine_b") for r in rows])
    b2 = _finite([_engine_ret(r, "b2") for r in rows])
    if not b or not b2:
        return {"engine_b": None, "engine_b2": None,
                "tail_improvement_pct": None}

    def _ws(arr: list[float]) -> dict:
        worst = sorted(arr)[:5]
        return {
            "n": len(arr),
            "worst_5": [round(x * 100, 4) for x in worst],
            "p95_loss_pct":
                round(_quantile(arr, 0.05) * 100, 4)
                if len(arr) > 5 else None,
            "p99_loss_pct":
                round(_quantile(arr, 0.01) * 100, 4)
                if len(arr) > 100 else None,
        }

    b_stats = _ws(b)
    b2_stats = _ws(b2)
    # Improvement = B's p99 loss minus B2's p99 loss (both negative; if
    # B2 is less negative, value is positive = improvement).
    imp = None
    if b_stats["p99_loss_pct"] is not None \
        and b2_stats["p99_loss_pct"] is not None:
        imp = round(b2_stats["p99_loss_pct"] - b_stats["p99_loss_pct"], 4)
    return {
        "engine_b": b_stats,
        "engine_b2": b2_stats,
        "p99_improvement_pct": imp,
    }


# ---------------------------------------------------------------------------
# Part 3 — Transition zones (T-5..T-1 before stress)
# ---------------------------------------------------------------------------

def transition_zones(rows: list[dict]) -> dict:
    """Quantify losses incurred during the days BEFORE a stress regime
    label fires — the documented filter-lag failure mode."""
    if not rows:
        return {"n_pre_stress_obs": 0, "pre_stress_b2_loss_bps": None,
                "pre_stress_share_of_total_loss_pct": None,
                "n_stress_entries": 0}
    # Identify stress entries: regime[t-1] != STRESS AND regime[t] == STRESS
    stress = [str(r.get("regime_label") or "") == "STRESS" for r in rows]
    enter_idxs = [i for i in range(1, len(rows))
                  if stress[i] and not stress[i - 1]]

    def _b2_ret(r):
        return _engine_ret(r, "b2") or 0.0

    pre_stress: list[float] = []
    for i in enter_idxs:
        for off in (-5, -4, -3, -2, -1):
            j = i + off
            if 0 <= j < len(rows):
                v = _b2_ret(rows[j])
                if v is not None:
                    pre_stress.append(float(v))
    all_neg = [x for x in (_b2_ret(r) for r in rows)
                  if x is not None and x < 0]
    pre_neg = [x for x in pre_stress if x < 0]
    total_loss = sum(all_neg) if all_neg else 0.0
    pre_loss = sum(pre_neg) if pre_neg else 0.0
    share = None
    if total_loss < 0:
        share = round((pre_loss / total_loss) * 100, 2)
    return {
        "n_stress_entries": int(len(enter_idxs)),
        "n_pre_stress_obs": int(len(pre_stress)),
        "pre_stress_b2_avg_bps": (round(
            (sum(pre_stress) / len(pre_stress)) * 1e4, 2)
            if pre_stress else None),
        "pre_stress_b2_loss_bps": (round(
            (sum(pre_neg) / len(pre_neg)) * 1e4, 2)
            if pre_neg else None),
        "pre_stress_share_of_total_loss_pct": share,
    }


# ---------------------------------------------------------------------------
# Part 4 — Regime consistency
# ---------------------------------------------------------------------------

def regime_consistency(rows: list[dict]) -> dict:
    """B2 must be ~0% exposed during stress and positive during non-stress."""
    stress_rows = [r for r in rows
                   if str(r.get("regime_label") or "") == "STRESS"]
    nons_rows = [r for r in rows
                  if str(r.get("regime_label") or "") != "STRESS"]
    s_long = sum(1 for r in stress_rows if r.get("b2_signal") == "LONG")
    n_long = sum(1 for r in nons_rows if r.get("b2_signal") == "LONG")
    s_rets = _finite([_engine_ret(r, "b2") for r in stress_rows])
    n_rets = _finite([_engine_ret(r, "b2") for r in nons_rows])

    def _summary(arr):
        if not arr:
            return {"n": 0, "sharpe": None, "cumulative_pct": None,
                    "mean_bps": None}
        eq = 1.0
        for x in arr:
            eq *= 1 + x
        return {
            "n": len(arr),
            "sharpe": round(_sharpe(arr), 4)
                if math.isfinite(_sharpe(arr)) else None,
            "cumulative_pct": round((eq - 1) * 100, 4),
            "mean_bps": round((sum(arr) / len(arr)) * 1e4, 2),
        }

    return {
        "stress_n_days": int(len(stress_rows)),
        "stress_b2_long_pct":
            (round((s_long / len(stress_rows)) * 100, 2)
             if stress_rows else None),
        "stress_perf": _summary(s_rets),
        "nonstress_n_days": int(len(nons_rows)),
        "nonstress_b2_long_pct":
            (round((n_long / len(nons_rows)) * 100, 2)
             if nons_rows else None),
        "nonstress_perf": _summary(n_rets),
    }


# ---------------------------------------------------------------------------
# Edge trajectory (rolling 30d mean edge vs prior 30d)
# ---------------------------------------------------------------------------

EDGE_DEAD_ZONE_BPS = 1.0   # |delta| ≤ 1 bps → stable


def edge_trajectory(
    rows: list[dict],
    *,
    window_days: int = 30,
    dead_zone_bps: float = EDGE_DEAD_ZONE_BPS,
) -> dict:
    """Mean per-day B2-minus-B edge over recent vs prior window.

    Trend label:
      improving  — recent − prior >  +dead_zone
      stable     — |recent − prior| ≤ dead_zone
      declining  — recent − prior <  -dead_zone
    """
    eligible = [r for r in rows if r.get("fwd_return_1d") is not None]
    if len(eligible) < 2 * window_days:
        return {
            "window_days": window_days,
            "recent_mean_edge_bps": None,
            "prior_mean_edge_bps": None,
            "delta_bps": None,
            "slope_bps_per_day": None,
            "trend": "INSUFFICIENT",
            "dead_zone_bps": dead_zone_bps,
            "n_recent": 0, "n_prior": 0,
        }
    recent = eligible[-window_days:]
    prior = eligible[-2 * window_days:-window_days]

    def _mean_edge_bps(rs: list[dict]) -> float | None:
        edges = []
        for r in rs:
            b = _engine_ret(r, "engine_b")
            b2 = _engine_ret(r, "b2")
            if b is None or b2 is None:
                continue
            edges.append(b2 - b)
        if not edges:
            return None
        return (sum(edges) / len(edges)) * 1e4

    recent_e = _mean_edge_bps(recent)
    prior_e = _mean_edge_bps(prior)
    if recent_e is None or prior_e is None:
        return {
            "window_days": window_days,
            "recent_mean_edge_bps": (None if recent_e is None
                                          else round(recent_e, 2)),
            "prior_mean_edge_bps": (None if prior_e is None
                                         else round(prior_e, 2)),
            "delta_bps": None,
            "slope_bps_per_day": None,
            "trend": "INSUFFICIENT",
            "dead_zone_bps": dead_zone_bps,
            "n_recent": len(recent), "n_prior": len(prior),
        }
    delta = recent_e - prior_e
    slope = delta / window_days
    if delta > dead_zone_bps:
        trend = "IMPROVING"
    elif delta < -dead_zone_bps:
        trend = "DECLINING"
    else:
        trend = "STABLE"
    return {
        "window_days": window_days,
        "recent_mean_edge_bps": round(recent_e, 2),
        "prior_mean_edge_bps": round(prior_e, 2),
        "delta_bps": round(delta, 2),
        "slope_bps_per_day": round(slope, 4),
        "trend": trend,
        "dead_zone_bps": dead_zone_bps,
        "n_recent": len(recent),
        "n_prior": len(prior),
    }


# ---------------------------------------------------------------------------
# Part 5 — Stability over time (early vs recent halves)
# ---------------------------------------------------------------------------

def stability_split(rows: list[dict]) -> dict:
    eligible = [r for r in rows if r.get("fwd_return_1d") is not None]
    if not eligible:
        return {"early": None, "recent": None,
                "sharpe_drift": None, "edge_drift_bps": None}
    mid = len(eligible) // 2
    early = eligible[:mid]
    recent = eligible[mid:]

    def _block(rs):
        b_rets = _finite([_engine_ret(r, "engine_b") for r in rs])
        b2_rets = _finite([_engine_ret(r, "b2") for r in rs])
        eq_b = 1.0
        for x in b_rets: eq_b *= 1 + x
        eq_b2 = 1.0
        for x in b2_rets: eq_b2 *= 1 + x
        edge_arr = [b - a for a, b in zip(b_rets, b2_rets)]
        return {
            "n": len(rs),
            "first_date": (str(rs[0]["as_of_date"])
                              if rs else None),
            "last_date": (str(rs[-1]["as_of_date"])
                             if rs else None),
            "engine_b_sharpe":
                round(_sharpe(b_rets), 4)
                if math.isfinite(_sharpe(b_rets)) else None,
            "b2_sharpe":
                round(_sharpe(b2_rets), 4)
                if math.isfinite(_sharpe(b2_rets)) else None,
            "engine_b_cum_pct": round((eq_b - 1) * 100, 4),
            "b2_cum_pct": round((eq_b2 - 1) * 100, 4),
            "mean_b2_edge_bps":
                round((sum(edge_arr) / len(edge_arr)) * 1e4, 2)
                if edge_arr else None,
        }

    e = _block(early); r = _block(recent)
    drift = None
    if (e and r and e["b2_sharpe"] is not None
            and r["b2_sharpe"] is not None):
        drift = round(r["b2_sharpe"] - e["b2_sharpe"], 4)
    edge_drift = None
    if (e and r and e["mean_b2_edge_bps"] is not None
            and r["mean_b2_edge_bps"] is not None):
        edge_drift = round(
            r["mean_b2_edge_bps"] - e["mean_b2_edge_bps"], 2)
    return {
        "early": e, "recent": r,
        "sharpe_drift": drift,
        "edge_drift_bps": edge_drift,
    }


# ---------------------------------------------------------------------------
# Part 6 — Promotion-readiness composite score
# ---------------------------------------------------------------------------

@dataclass
class ReadinessScore:
    score: int                   # 0-100
    label: str                   # NOT_READY | READY_FOR_REVIEW | STRONG_CANDIDATE
    breakdown: dict
    advisory_only: bool = True

    def to_dict(self) -> dict:
        return {
            "score": int(self.score),
            "label": self.label,
            "breakdown": dict(self.breakdown),
            "advisory_only": True,
            "auto_promote": False,
        }


def readiness_score(
    *,
    divergence: dict,
    tail: dict,
    regime: dict,
    stability: dict,
) -> ReadinessScore:
    """Composite readiness 0-100 across 4 dimensions (25 pts each)."""
    breakdown: dict[str, str] = {}
    score = 0

    # 1. Divergence quality (25 pts)
    wr = divergence.get("win_rate_b2_vs_b_pct")
    cum = divergence.get("cumulative_return_diff_pct")
    if wr is None:
        breakdown["divergence_quality"] = "INSUFFICIENT (+0)"
    else:
        pts = 0
        if wr >= 60: pts += 15
        elif wr >= 55: pts += 11
        elif wr >= 50: pts += 7
        if cum is not None and cum > 5: pts += 10
        elif cum is not None and cum > 0: pts += 6
        score += pts
        breakdown["divergence_quality"] = (
            f"+{pts} (win_rate={wr}%, cum_edge={cum}%)")

    # 2. Tail risk improvement (25 pts)
    p99 = tail.get("p99_improvement_pct")
    if p99 is None:
        breakdown["tail_risk"] = "INSUFFICIENT (+0)"
    else:
        if p99 >= 0.5:
            score += 25; breakdown["tail_risk"] = f"+25 (p99 imp={p99}%)"
        elif p99 >= 0.1:
            score += 18; breakdown["tail_risk"] = f"+18 (p99 imp={p99}%)"
        elif p99 >= 0:
            score += 12; breakdown["tail_risk"] = f"+12 (p99 imp={p99}%)"
        else:
            breakdown["tail_risk"] = f"+0 (p99 imp={p99}% — worse)"

    # 3. Regime alignment (25 pts)
    s_long = regime.get("stress_b2_long_pct")
    nperf = regime.get("nonstress_perf") or {}
    nonstress_sharpe = nperf.get("sharpe")
    pts = 0
    if s_long is not None and s_long <= 5:
        pts += 12
    elif s_long is not None and s_long <= 10:
        pts += 8
    if nonstress_sharpe is not None and nonstress_sharpe >= 1.0:
        pts += 13
    elif nonstress_sharpe is not None and nonstress_sharpe >= 0.5:
        pts += 9
    elif nonstress_sharpe is not None and nonstress_sharpe >= 0:
        pts += 5
    score += pts
    breakdown["regime_alignment"] = (
        f"+{pts} (stress_long={s_long}%, "
        f"nonstress_sharpe={nonstress_sharpe})")

    # 4. Stability over halves (25 pts)
    drift = stability.get("sharpe_drift")
    e_b2 = (stability.get("early") or {}).get("b2_sharpe")
    r_b2 = (stability.get("recent") or {}).get("b2_sharpe")
    pts = 0
    if e_b2 is not None and r_b2 is not None:
        if min(e_b2, r_b2) > 0.5:
            pts += 15
        elif min(e_b2, r_b2) > 0:
            pts += 10
        elif min(e_b2, r_b2) >= -0.2:
            pts += 5
    if drift is not None and drift >= 0:
        pts += 10
    elif drift is not None and drift > -0.3:
        pts += 5
    score += pts
    breakdown["stability"] = (
        f"+{pts} (early_sharpe={e_b2}, recent_sharpe={r_b2}, "
        f"drift={drift})")

    if score >= 75:
        label = "STRONG_CANDIDATE"
    elif score >= 50:
        label = "READY_FOR_REVIEW"
    else:
        label = "NOT_READY"

    return ReadinessScore(score=int(score), label=label,
                              breakdown=breakdown)


# ---------------------------------------------------------------------------
# Top-level
# ---------------------------------------------------------------------------

def compute_all(rows: list[dict]) -> dict:
    """Compute all 6 analytic blocks + composite readiness score."""
    div = divergence_analytics(rows)
    tail = tail_risk(rows)
    trans = transition_zones(rows)
    regime = regime_consistency(rows)
    stab = stability_split(rows)
    edge = edge_trajectory(rows)
    score = readiness_score(divergence=div, tail=tail,
                                regime=regime, stability=stab)
    return {
        "n_rows": int(len(rows)),
        "divergence": div,
        "tail_risk": tail,
        "transition_zones": trans,
        "regime_consistency": regime,
        "stability": stab,
        "edge_trajectory": edge,
        "readiness": score.to_dict(),
        "advisory_only": True,
    }
