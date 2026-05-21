"""Engine B2 edge deterioration diagnostic — read-only.

Audits the recent DECLINING edge_trajectory finding to classify the
deterioration as NOISE / REGIME / STRUCTURAL with confidence + a
recommendation. Pure analysis. NEVER mutates DB / thresholds /
execution / ML / risk parameters.

Run:
    DATABASE_URL=postgresql+psycopg://... ./.venv/Scripts/python.exe \
        -m scripts.diagnose_b2_edge_decline
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text

from apps.api.src.db import SessionLocal
from apps.api.src.research.engine_b_analytics import (
    PERIODS_PER_YEAR,
    _engine_ret,
    _finite,
    _quantile,
    _sharpe,
    edge_trajectory,
)


SOURCE_STRATEGY = "tsmom_60_no_stress"


def _print_table(rows: list[dict], cols: list[str]) -> None:
    if not rows:
        print("  (no rows)"); return
    widths = {c: max(len(c), max(len(str(r.get(c, ""))) for r in rows))
              for c in cols}
    fmt = "  " + "  ".join(f"{{:<{widths[c]}}}" for c in cols)
    print(fmt.format(*cols))
    for r in rows:
        print(fmt.format(*[str(r.get(c, "")) for c in cols]))


def _load_rows(session) -> list[dict]:
    rs = session.execute(text("""
        SELECT as_of_date, signal,
               engine_b_signal, b2_signal, routed_signal,
               divergence_flag, divergence_outcome,
               fwd_return_1d, fwd_return_5d,
               regime_label
          FROM paper_shadow_log
         WHERE source_strategy = :s
         ORDER BY as_of_date ASC
    """), {"s": SOURCE_STRATEGY}).mappings().all()
    return [dict(r) for r in rs]


# --------------------------------------------------------------------------
# Part 1 — Multi-window trajectory
# --------------------------------------------------------------------------

def part1(rows: list[dict]) -> list[dict]:
    print("\n=== PART 1 — Multi-window trajectory ===")
    out = []
    for w in (30, 60, 90):
        et = edge_trajectory(rows, window_days=w)
        out.append({"window": f"{w}d", **et})
    cols = ["window", "trend", "recent_mean_edge_bps",
            "prior_mean_edge_bps", "delta_bps", "slope_bps_per_day",
            "n_recent", "n_prior"]
    _print_table(out, cols)
    return out


# --------------------------------------------------------------------------
# Part 2 — Regime split for last 30d
# --------------------------------------------------------------------------

def part2(rows: list[dict]) -> dict:
    print("\n=== PART 2 — Recent 30d regime split ===")
    eligible = [r for r in rows if r.get("fwd_return_1d") is not None]
    sub = eligible[-30:] if len(eligible) >= 30 else eligible
    if not sub:
        print("  insufficient data"); return {}

    def _edge_of(rs):
        edges = []
        for r in rs:
            b = _engine_ret(r, "engine_b")
            b2 = _engine_ret(r, "b2")
            if b is None or b2 is None:
                continue
            edges.append(b2 - b)
        if not edges:
            return None, None, 0
        return ((sum(edges) / len(edges)) * 1e4,
                _sharpe(edges) if len(edges) > 1 else None,
                len(edges))

    stress = [r for r in sub if r.get("regime_label") == "STRESS"]
    direct = [r for r in sub if r.get("regime_label") == "DIRECTIONAL"]
    other = [r for r in sub if r.get("regime_label") not in
             ("STRESS", "DIRECTIONAL")]

    rows_out: list[dict] = []
    for label, rs in (("stress", stress), ("directional", direct),
                          ("other", other), ("ALL_30d", sub)):
        mean_bps, sh, n = _edge_of(rs)
        rows_out.append({
            "bucket": label, "n": n,
            "mean_edge_bps": (None if mean_bps is None
                                  else round(mean_bps, 2)),
            "edge_sharpe": (None if sh is None or
                                not math.isfinite(sh)
                                else round(sh, 3)),
        })
    _print_table(rows_out, ["bucket", "n", "mean_edge_bps", "edge_sharpe"])
    return {"buckets": rows_out}


# --------------------------------------------------------------------------
# Part 3 — Recent divergence quality vs historical
# --------------------------------------------------------------------------

def part3(rows: list[dict]) -> dict:
    print("\n=== PART 3 — Divergence quality: recent 30d vs historical ===")
    eligible = [r for r in rows if r.get("fwd_return_1d") is not None
                and r.get("divergence_flag")
                and r.get("divergence_outcome") is not None]
    if len(eligible) < 5:
        print("  insufficient divergent days"); return {}
    recent = eligible[-30:] if len(eligible) >= 30 else eligible
    historical = eligible[:-30] if len(eligible) > 30 else eligible

    def _stats(rs):
        if not rs:
            return {"n": 0, "win_rate_pct": None,
                    "mean_edge_bps": None,
                    "avoided_losses": 0, "avoided_avg_bps": None,
                    "missed_wins": 0, "missed_avg_bps": None}
        advs = [-float(r["divergence_outcome"]) for r in rs]
        wins = sum(1 for a in advs if a > 0)
        avoided = []
        missed = []
        for r in rs:
            ret = float(r["fwd_return_1d"])
            b = r.get("engine_b_signal"); b2 = r.get("b2_signal")
            if b == "LONG" and b2 == "FLAT" and ret < 0:
                avoided.append(-ret)
            if b == "FLAT" and b2 == "LONG" and ret > 0:
                missed.append(ret)
        return {
            "n": len(rs),
            "win_rate_pct": round((wins / len(rs)) * 100, 2),
            "mean_edge_bps":
                round((sum(advs) / len(advs)) * 1e4, 2),
            "avoided_losses": int(len(avoided)),
            "avoided_avg_bps":
                (round((sum(avoided) / len(avoided)) * 1e4, 1)
                 if avoided else None),
            "missed_wins": int(len(missed)),
            "missed_avg_bps":
                (round((sum(missed) / len(missed)) * 1e4, 1)
                 if missed else None),
        }

    rec = _stats(recent)
    hist = _stats(historical)
    rows_out = [
        {"window": "historical", **hist},
        {"window": "recent_30d", **rec},
    ]
    _print_table(rows_out,
                  ["window", "n", "win_rate_pct", "mean_edge_bps",
                   "avoided_losses", "avoided_avg_bps",
                   "missed_wins", "missed_avg_bps"])
    return {"recent": rec, "historical": hist}


# --------------------------------------------------------------------------
# Part 4 — Loss clustering
# --------------------------------------------------------------------------

def part4(rows: list[dict]) -> dict:
    print("\n=== PART 4 — Top-5 negative divergence days + clustering ===")
    eligible = [r for r in rows
                if r.get("divergence_flag") and
                r.get("divergence_outcome") is not None]
    # divergence_outcome > 0 means B beat B2 → BAD for B2
    losers = sorted(eligible,
                       key=lambda r: -float(r["divergence_outcome"]))[:5]
    if not losers:
        print("  no negative divergence days"); return {}
    rows_out = []
    for r in losers:
        rows_out.append({
            "date": str(r["as_of_date"]),
            "regime": r.get("regime_label"),
            "engine_b": r.get("engine_b_signal"),
            "b2": r.get("b2_signal"),
            "fwd_1d_pct": (round(float(r["fwd_return_1d"]) * 100, 3)
                              if r.get("fwd_return_1d") is not None else None),
            "div_outcome_bps":
                round(float(r["divergence_outcome"]) * 1e4, 1),
        })
    _print_table(rows_out,
                  ["date", "regime", "engine_b", "b2", "fwd_1d_pct",
                   "div_outcome_bps"])

    # Cluster check: how many days span the top 5?
    if len(losers) >= 2:
        ds = [pd.Timestamp(r["as_of_date"]).normalize() for r in losers]
        span_days = int((max(ds) - min(ds)).days)
        # Are 4 of 5 within a 14-day window?
        sorted_ds = sorted(ds)
        clustered = False
        for i in range(len(sorted_ds) - 3):
            if (sorted_ds[i + 3] - sorted_ds[i]).days <= 14:
                clustered = True; break
        print(f"  span (max-min): {span_days} days  · "
              f"4-of-5 within 14d window: {clustered}")
        return {"top5": rows_out, "span_days": span_days,
                "clustered_4_of_5_in_14d": clustered}
    return {"top5": rows_out}


# --------------------------------------------------------------------------
# Part 5 — Transition-zone impact (recent 60d)
# --------------------------------------------------------------------------

def part5(rows: list[dict]) -> dict:
    print("\n=== PART 5 — Transition-zone impact (recent 60d) ===")
    eligible = [r for r in rows if r.get("fwd_return_1d") is not None]
    sub = eligible[-60:] if len(eligible) >= 60 else eligible
    if not sub:
        print("  insufficient data"); return {}
    stress_flags = [r.get("regime_label") == "STRESS" for r in sub]
    enter_idxs = [i for i in range(1, len(sub))
                  if stress_flags[i] and not stress_flags[i - 1]]

    def _b2_ret(r):
        return _engine_ret(r, "b2") or 0.0

    pre_window: list[float] = []
    for i in enter_idxs:
        for off in (-5, -4, -3, -2, -1):
            j = i + off
            if 0 <= j < len(sub):
                v = _b2_ret(sub[j])
                if v is not None:
                    pre_window.append(float(v))
    all_neg = [_b2_ret(r) for r in sub if _b2_ret(r) < 0]
    pre_neg = [v for v in pre_window if v < 0]
    total_loss = sum(all_neg) if all_neg else 0.0
    pre_loss = sum(pre_neg) if pre_neg else 0.0
    share = (round((pre_loss / total_loss) * 100, 2)
              if total_loss < 0 else None)

    print(f"  recent stress entries: {len(enter_idxs)}")
    print(f"  pre-stress observations: {len(pre_window)}")
    print(f"  pre-stress mean ret: "
          f"{(sum(pre_window) / len(pre_window) * 1e4) if pre_window else None:.2f} bps"
          if pre_window else "  pre-stress mean ret: —")
    print(f"  pre-stress losses share of recent total loss: {share}%")
    return {
        "n_stress_entries_recent": int(len(enter_idxs)),
        "n_pre_stress_obs_recent": int(len(pre_window)),
        "pre_stress_mean_bps":
            (round((sum(pre_window) / len(pre_window)) * 1e4, 2)
             if pre_window else None),
        "pre_stress_share_of_recent_loss_pct": share,
    }


# --------------------------------------------------------------------------
# Part 6 — Classification + recommendation
# --------------------------------------------------------------------------

def part6(p1, p2, p3, p4, p5) -> dict:
    print("\n=== PART 6 — Classification ===")

    # Multi-window trends
    trends = {row["window"]: row["trend"] for row in p1}
    deltas = {row["window"]: row["delta_bps"] for row in p1}

    # Recent regime breakdown
    recent_buckets = {b["bucket"]: b for b in (p2.get("buckets") or [])}
    direct_edge_30d = (recent_buckets.get("directional") or {}).get(
        "mean_edge_bps")
    stress_edge_30d = (recent_buckets.get("stress") or {}).get(
        "mean_edge_bps")

    # Recent vs historical divergence
    rec = p3.get("recent") or {}
    hist = p3.get("historical") or {}
    win_rec = rec.get("win_rate_pct")
    win_hist = hist.get("win_rate_pct")
    edge_rec = rec.get("mean_edge_bps")
    edge_hist = hist.get("mean_edge_bps")

    # Cluster
    clustered = bool(p4.get("clustered_4_of_5_in_14d"))
    span = p4.get("span_days")

    # Transition zone share
    tz_share = p5.get("pre_stress_share_of_recent_loss_pct")

    # Decision logic
    classification = "NOISE"
    confidence = "LOW"
    rec_action = "HOLD"
    reasons: list[str] = []

    # If 90d trend is also DECLINING and historical edge was strong:
    if trends.get("90d") == "DECLINING" and trends.get("60d") == "DECLINING":
        classification = "STRUCTURAL"
        confidence = "MED"
        reasons.append("decline visible at 60d AND 90d windows")
    elif trends.get("60d") == "DECLINING":
        classification = "REGIME"
        confidence = "MED"
        reasons.append("decline visible at 60d but not 90d → regime")
    elif trends.get("30d") == "DECLINING" and \
            trends.get("60d") in ("STABLE", "IMPROVING", "INSUFFICIENT"):
        classification = "NOISE"
        confidence = "MED-HIGH"
        reasons.append("only 30d declining; 60d/90d intact → likely noise")
    elif all(trends.get(w) in ("INSUFFICIENT",) for w in
                ("30d", "60d", "90d")):
        classification = "INSUFFICIENT_DATA"
        confidence = "LOW"

    # Strengthen with regime evidence
    if (direct_edge_30d is not None and direct_edge_30d < 0
            and stress_edge_30d is not None and stress_edge_30d <= 0):
        if classification != "STRUCTURAL":
            classification = "STRUCTURAL"
            confidence = "MED"
        reasons.append(
            "directional 30d edge negative — primary regime failing")
    elif (direct_edge_30d is not None and direct_edge_30d < 0):
        if classification == "NOISE":
            classification = "REGIME"
        reasons.append(
            "directional 30d edge negative — regime-specific failure")

    # Win-rate degradation
    if (win_rec is not None and win_hist is not None and
            win_rec < win_hist - 10):
        reasons.append(
            f"win rate dropped {win_hist:.1f}% → {win_rec:.1f}% "
            f"(-{win_hist - win_rec:.1f}pp)")
        if classification == "NOISE":
            classification = "REGIME"
            confidence = "MED"

    # Edge magnitude
    if (edge_rec is not None and edge_hist is not None and
            edge_rec < 0 < edge_hist):
        reasons.append(
            f"mean edge flipped sign ({edge_hist:.1f}bps → "
            f"{edge_rec:.1f}bps)")
        if classification == "NOISE":
            classification = "REGIME"

    # Cluster
    if clustered:
        reasons.append(
            f"top-5 losses clustered (4 within 14d, span {span}d) "
            f"→ event-driven, not structural")
        if classification == "STRUCTURAL":
            classification = "REGIME"

    # Transition share
    if tz_share is not None and tz_share >= 30:
        reasons.append(
            f"pre-stress window contributes {tz_share}% of recent loss "
            f"→ filter-lag amplified during regime transitions")

    # Recommendation
    if classification == "STRUCTURAL":
        rec_action = "INVESTIGATE"
    elif classification == "REGIME":
        rec_action = "EXTEND_OBSERVATION"
    elif classification == "NOISE":
        rec_action = "HOLD"
    else:
        rec_action = "EXTEND_OBSERVATION"

    print(f"\n  CLASSIFICATION: {classification}")
    print(f"  CONFIDENCE:     {confidence}")
    print(f"  RECOMMENDATION: {rec_action}")
    if reasons:
        print("  Reasoning:")
        for r in reasons:
            print(f"    · {r}")

    return {
        "classification": classification,
        "confidence": confidence,
        "recommendation": rec_action,
        "reasoning": reasons,
        "trend_30d": trends.get("30d"),
        "trend_60d": trends.get("60d"),
        "trend_90d": trends.get("90d"),
        "delta_30d_bps": deltas.get("30d"),
        "delta_60d_bps": deltas.get("60d"),
        "delta_90d_bps": deltas.get("90d"),
    }


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main() -> int:
    print("=== B2 Edge Deterioration Diagnostic — read-only ===")
    with SessionLocal() as s:
        rows = _load_rows(s)
    print(f"Rows loaded: {len(rows)}  "
          f"({rows[0]['as_of_date']} -> {rows[-1]['as_of_date']})"
          if rows else "no rows")
    if not rows:
        return 1

    p1 = part1(rows)
    p2 = part2(rows)
    p3 = part3(rows)
    p4 = part4(rows)
    p5 = part5(rows)
    p6 = part6(p1, p2, p3, p4, p5)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path("artifacts") / "edge_diagnostic" / ts
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_utc": ts,
        "n_rows": int(len(rows)),
        "first": str(rows[0]["as_of_date"]),
        "last": str(rows[-1]["as_of_date"]),
        "part1_multi_window_trajectory": p1,
        "part2_regime_split_30d": p2,
        "part3_divergence_recent_vs_historical": p3,
        "part4_loss_clustering": p4,
        "part5_transition_zone_impact": p5,
        "part6_classification": p6,
    }
    (out_dir / "diagnostic.json").write_text(
        json.dumps(payload, indent=2, default=str))
    print(f"\nArtifacts: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
