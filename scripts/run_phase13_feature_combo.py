"""Phase 13 — Feature Combination Model on Variant C base.

Variant C (base):
    long:  trend_up_20 & pullback_long_ctx & compression & breakout_up(5)
    short: trend_down_20 & pullback_short_ctx & compression & breakout_down(5)

Additive structural score (no fit, no weight-tuning):
    +1 if compression_strength in signal-subset STRONG half
    +1 if pullback context satisfied (always true in C — informational)
    +1 if trend-aligned on BOTH MA20 AND MA50
    +1 if breakout magnitude is MODERATE (middle tercile of signal subset)
    -1 if trend countertrend to MA20 (never true in C — guard)
    -1 if breakout magnitude top decile (overextension)
    -1 if compression in signal-subset WEAK half

Buckets:
    low     = score <= 0
    medium  = score == 1
    high    = score >= 2

Tests:
    1. Monotonicity across buckets (does mean return rise with score?)
    2. Raw-C vs filtered-by-score comparison
    3. Ablation — drop one feature at a time, recompute bucket stats
    4. Regime diagnostic (bull/bear, high/low vol) on HIGH bucket

Costs, windows, entry/exit IDENTICAL to Phase 12. No parameter tuning.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import random
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd
from loguru import logger
from sqlalchemy import text

from apps.api.src.db import SessionLocal
from scripts.run_phase12_price_action import (
    build_features, add_confirmation, compute_forward_returns,
    fetch_es_daily, load_spy_from_db,
    HOLD_WINDOWS, COST_BPS,
)

OUT_DIR = Path("artifacts/phase13")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Primary config (frozen to match Phase 12 primary):
BREAKOUT_LB  = 5
TREND_MA     = 20
TREND_MA_LONG = 50   # additional trend confirmation MA


# ---------------------------------------------------------------------------
# Stats helpers
# ---------------------------------------------------------------------------
def _bootstrap_ci(xs, *, n_boot=5000, conf=0.95):
    if not xs:
        return (0.0, 0.0)
    rng = random.Random(42)
    n = len(xs)
    means = [sum(xs[rng.randrange(n)] for _ in range(n)) / n for _ in range(n_boot)]
    means.sort()
    return (means[int((1 - conf) / 2 * n_boot)],
            means[int((1 - (1 - conf) / 2) * n_boot) - 1])


def summarize(returns, *, bps):
    if not returns:
        return {"n": 0}
    cost = bps / 1e4
    rn = [r - cost for r in returns]
    n = len(rn)
    mean = st.mean(rn); med = st.median(rn)
    sd = st.pstdev(rn) if n > 1 else 0.0
    wins = sum(1 for r in rn if r > 0)
    t = mean / (sd / math.sqrt(n)) if sd > 0 else 0.0
    lo, hi = _bootstrap_ci(rn)
    eq = 1.0; path = []
    for r in rn:
        eq *= (1 + r); path.append(eq)
    pk = path[0] if path else 1.0; dd = 0.0
    for v in path:
        pk = max(pk, v); dd = min(dd, (v - pk) / pk)
    return {
        "n": n, "cost_bps": bps,
        "mean_pct": mean * 100, "median_pct": med * 100, "std_pct": sd * 100,
        "hit_rate": wins / n, "t_stat": t,
        "ci95_mean_pct": [lo * 100, hi * 100],
        "mean_gross_pct": st.mean(returns) * 100,
        "cumulative_pct": (path[-1] - 1) * 100 if path else 0.0,
        "max_dd_pct": dd * 100,
    }


# ---------------------------------------------------------------------------
# Variant C signals + scoring features
# ---------------------------------------------------------------------------
def build_variant_c_and_scores(feat: pd.DataFrame) -> pd.DataFrame:
    f = feat.copy()
    # Variant C base
    f["sig_long_C"]  = (
        f[f"trend_up_{TREND_MA}"] & f["pullback_long_ctx"] &
        f["compression"] & f[f"bo_up_{BREAKOUT_LB}"]
    )
    f["sig_short_C"] = (
        f[f"trend_down_{TREND_MA}"] & f["pullback_short_ctx"] &
        f["compression"] & f[f"bo_down_{BREAKOUT_LB}"]
    )
    f["signal_any"] = f["sig_long_C"] | f["sig_short_C"]

    # Continuous features
    f["comp_strength"] = (f["atr10"] - f["tr"]) / f["atr10"]
    prior_max5 = f["high"].shift(1).rolling(5).max()
    prior_min5 = f["low"].shift(1).rolling(5).min()
    f["bo_up_mag"] = (f["close"] - prior_max5) / f["atr10"]
    f["bo_dn_mag"] = (prior_min5 - f["close"]) / f["atr10"]
    f["bo_mag"] = f["bo_up_mag"].where(f["sig_long_C"], f["bo_dn_mag"])

    return f


def compute_score_columns(f: pd.DataFrame) -> pd.DataFrame:
    """Compute score features using SIGNAL-SUBSET medians/deciles
    (non-tautological). Returns DataFrame with added columns:
      cs_strong, cs_weak, bo_moderate, bo_overextended,
      both_ma_aligned, countertrend, pullback_ok, score_total
    """
    f = f.copy()
    mask = f["signal_any"]
    # Compression-strength split on signal-subset median
    cs_med = f.loc[mask, "comp_strength"].median()
    f["cs_strong"] = f["comp_strength"] > cs_med
    f["cs_weak"]   = f["comp_strength"] <= cs_med

    # Breakout-magnitude tercile on signal-subset
    bo_vals = f.loc[mask, "bo_mag"].dropna()
    if len(bo_vals) >= 3:
        q_lo, q_hi = bo_vals.quantile([1/3, 2/3]).values
        top10 = bo_vals.quantile(0.90)
    else:
        q_lo = q_hi = top10 = 0.0
    f["bo_moderate"]      = (f["bo_mag"] >= q_lo) & (f["bo_mag"] < q_hi)
    f["bo_overextended"]  = f["bo_mag"] >= top10

    # Trend alignment on BOTH MA20 AND MA50 (consistent with variant direction)
    both_long  = f[f"trend_up_{TREND_MA}"]   & f[f"trend_up_{TREND_MA_LONG}"]
    both_short = f[f"trend_down_{TREND_MA}"] & f[f"trend_down_{TREND_MA_LONG}"]
    f["both_ma_aligned"] = (f["sig_long_C"] & both_long) | (f["sig_short_C"] & both_short)

    # Countertrend guard — never True for C (C requires trend alignment on MA20)
    f["countertrend"] = (
        (f["sig_long_C"]  & f[f"trend_down_{TREND_MA}"]) |
        (f["sig_short_C"] & f[f"trend_up_{TREND_MA}"])
    )

    # Pullback context (always True for C — keep for completeness / ablation)
    f["pullback_ok"] = (
        (f["sig_long_C"]  & f["pullback_long_ctx"]) |
        (f["sig_short_C"] & f["pullback_short_ctx"])
    )

    # Score components (additive, no weight tuning)
    f["score_cs_strong_plus"]   = f["cs_strong"].astype(int)
    f["score_cs_weak_minus"]    = -f["cs_weak"].astype(int)
    f["score_bo_moderate_plus"] = f["bo_moderate"].astype(int)
    f["score_bo_over_minus"]    = -f["bo_overextended"].astype(int)
    f["score_both_ma_plus"]     = f["both_ma_aligned"].astype(int)
    f["score_countertrend_minus"] = -f["countertrend"].astype(int)
    f["score_pullback_plus"]    = f["pullback_ok"].astype(int)
    f["score_total"] = (
        f["score_cs_strong_plus"] + f["score_cs_weak_minus"] +
        f["score_bo_moderate_plus"] + f["score_bo_over_minus"] +
        f["score_both_ma_plus"] + f["score_countertrend_minus"] +
        f["score_pullback_plus"]
    )
    return f


def bucket_label(score: int) -> str:
    if score <= 0:   return "low"
    if score == 1:   return "medium"
    return "high"


# ---------------------------------------------------------------------------
# Pooled long/short returns
# ---------------------------------------------------------------------------
def pooled_rets(f: pd.DataFrame, fwd: pd.Series, mask: pd.Series) -> list[float]:
    longs  = f["sig_long_C"]  & mask & fwd.notna()
    shorts = f["sig_short_C"] & mask & fwd.notna()
    return fwd[longs].tolist() + [-r for r in fwd[shorts].tolist()]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    logger.info("[p13] fetching ES=F + SPY")
    es = fetch_es_daily(start="2020-01-01")
    spy = load_spy_from_db()
    es = es[~es.index.duplicated(keep="last")].sort_index()
    spy = spy[~spy.index.duplicated(keep="last")].sort_index()
    common = es.index.intersection(spy.index)
    es = es.loc[common]; spy = spy.loc[common]
    logger.info("[p13] common {} bars ({} -> {})", len(es), es.index[0], es.index[-1])

    feat = build_features(es)
    feat = add_confirmation(feat, spy)
    feat = build_variant_c_and_scores(feat)
    feat = compute_score_columns(feat)

    fwd_rets = compute_forward_returns(feat, HOLD_WINDOWS)

    # -- Event counts by score bucket --------------------------------------
    mask_any = feat["signal_any"]
    score_series = feat.loc[mask_any, "score_total"]
    score_counts = score_series.value_counts().sort_index()

    bucket_mask = {
        "low":    (feat["score_total"] <= 0) & mask_any,
        "medium": (feat["score_total"] == 1) & mask_any,
        "high":   (feat["score_total"] >= 2) & mask_any,
    }

    # -- Per-window per-bucket summaries (10bps + 20bps) -------------------
    per_bucket: dict[str, dict] = {}
    for bname, bmask in bucket_mask.items():
        per_bucket[bname] = {"n_signals": int(bmask.sum()), "per_window": {}}
        for N in HOLD_WINDOWS:
            ret = fwd_rets[N]
            pooled = pooled_rets(feat, ret, bmask)
            per_bucket[bname]["per_window"][str(N)] = {
                f"{b}bps": summarize(pooled, bps=b) for b in COST_BPS
            }

    # -- Raw Variant C baseline (same bucketing, no filter) ----------------
    raw_C = {"per_window": {}}
    for N in HOLD_WINDOWS:
        ret = fwd_rets[N]
        pooled = pooled_rets(feat, ret, mask_any)
        raw_C["per_window"][str(N)] = {
            f"{b}bps": summarize(pooled, bps=b) for b in COST_BPS
        }

    # -- Ablation table: drop one score component -------------------------
    ablation_components = {
        "drop_comp_strength": ["score_cs_strong_plus", "score_cs_weak_minus"],
        "drop_pullback":      ["score_pullback_plus"],
        "drop_trend_align":   ["score_both_ma_plus", "score_countertrend_minus"],
        "drop_bo_mag":        ["score_bo_moderate_plus", "score_bo_over_minus"],
    }
    ablation_stats: dict[str, dict] = {}
    for aname, drop_cols in ablation_components.items():
        score_ablated = sum(
            feat[c] for c in [
                "score_cs_strong_plus", "score_cs_weak_minus",
                "score_bo_moderate_plus", "score_bo_over_minus",
                "score_both_ma_plus", "score_countertrend_minus",
                "score_pullback_plus",
            ] if c not in drop_cols
        )
        high_mask = (score_ablated >= 2) & mask_any
        # For comparability, also show low bucket under this ablation
        low_mask = (score_ablated <= 0) & mask_any
        ret10 = fwd_rets[10]
        ablation_stats[aname] = {
            "n_high": int(high_mask.sum()),
            "n_low":  int(low_mask.sum()),
            "high_10d_20bps": summarize(pooled_rets(feat, ret10, high_mask), bps=20),
            "low_10d_20bps":  summarize(pooled_rets(feat, ret10, low_mask),  bps=20),
        }

    # Full-score high bucket for reference
    full_high_mask = bucket_mask["high"]
    ret10 = fwd_rets[10]
    full_high_stats = summarize(pooled_rets(feat, ret10, full_high_mask), bps=20)

    # -- Regime diagnostic on HIGH bucket ----------------------------------
    bull = feat["regime_bull"].fillna(False)
    hv   = feat["regime_high_vol"].fillna(False)
    regime_diag: dict[str, dict] = {}
    for rlabel, rmask in [("bull", bull), ("bear", ~bull),
                          ("high_vol", hv), ("low_vol", ~hv)]:
        msk = full_high_mask & rmask
        regime_diag[rlabel] = {
            "n": int(msk.sum()),
            "stats_10d_20bps": summarize(pooled_rets(feat, ret10, msk), bps=20),
        }

    # -- Monotonicity check -----------------------------------------------
    primary_means = {
        b: per_bucket[b]["per_window"]["10"]["20bps"].get("mean_pct")
        for b in ("low", "medium", "high")
    }
    mono = (
        (primary_means["low"] is not None) and
        (primary_means["medium"] is not None) and
        (primary_means["high"] is not None) and
        (primary_means["low"] <= primary_means["medium"] <= primary_means["high"])
    )

    # -- Verdict -----------------------------------------------------------
    h = per_bucket["high"]["per_window"]["10"]["20bps"]
    n_h = h.get("n", 0); t_h = h.get("t_stat", 0); m_h = h.get("mean_pct", 0)
    ci = h.get("ci95_mean_pct", [0, 0])
    if n_h == 0:
        verdict = "FAIL"; vreason = "no high-bucket trades"
    elif n_h >= 30 and t_h > 2.0 and m_h > 0 and ci[0] > 0 and mono:
        verdict = "PASS"; vreason = "monotonic + credible high-bucket edge"
    elif mono and (t_h > 1.0 or (m_h > 0 and ci[1] > 0)):
        verdict = "WEAK"
        vreason = "monotonicity + suggestive high-bucket edge, sample thin"
    else:
        verdict = "FAIL"
        vreason = (f"no monotonicity / no edge  n={n_h} t={t_h:.2f} "
                   f"mean={m_h:.3f}% CI=[{ci[0]:.3f},{ci[1]:.3f}]")

    # -- Report ------------------------------------------------------------
    report = {
        "phase": "13_feature_combo",
        "today": dt.date.today().isoformat(),
        "params": {
            "breakout_lb": BREAKOUT_LB,
            "trend_ma_short": TREND_MA,
            "trend_ma_long": TREND_MA_LONG,
            "hold_windows": list(HOLD_WINDOWS),
            "cost_bps": list(COST_BPS),
        },
        "data_bars": len(feat),
        "n_variant_C_signals": int(mask_any.sum()),
        "score_distribution": {int(k): int(v) for k, v in score_counts.items()},
        "raw_C_per_window": raw_C,
        "per_bucket": per_bucket,
        "monotonicity_by_mean_10d_20bps": {
            "values": primary_means, "is_monotonic": bool(mono),
        },
        "full_high_bucket_10d_20bps": full_high_stats,
        "ablation_10d_20bps": ablation_stats,
        "regime_diag_high_bucket_10d_20bps": regime_diag,
        "verdict": verdict,
        "verdict_reason": vreason,
    }
    (OUT_DIR / "report.json").write_text(json.dumps(report, indent=2, default=str))

    # -- Print -------------------------------------------------------------
    print("=" * 90)
    print(f"PHASE 13 - FEATURE COMBINATION MODEL ({dt.date.today()})")
    print("=" * 90)
    print(f"Data: ES=F {es.index[0]} -> {es.index[-1]} ({len(es)} bars)")
    print(f"Variant C signal total: {int(mask_any.sum())} "
          f"(long={int(feat['sig_long_C'].sum())} short={int(feat['sig_short_C'].sum())})")
    print(f"Score distribution: {dict(report['score_distribution'])}")
    print()
    print("--- Bucket event counts ---")
    for b in ("low", "medium", "high"):
        print(f"  {b:<6}  n_signals = {per_bucket[b]['n_signals']}")
    print()

    print("--- Per-bucket per-window (10bps net | 20bps net) ---")
    print(f"{'bucket':<8} {'N':>3} {'n':>4} {'gross%':>8} {'net10%':>8} "
          f"{'net20%':>8} {'hit':>5} {'t':>6} {'CI95% 20bps':<22} {'maxDD%':>7}")
    for b in ("low", "medium", "high"):
        for N in HOLD_WINDOWS:
            s10 = per_bucket[b]["per_window"][str(N)]["10bps"]
            s20 = per_bucket[b]["per_window"][str(N)]["20bps"]
            if s20.get("n", 0) == 0:
                print(f"{b:<8} {N:>3} {'0':>4} (empty)"); continue
            ci = s20["ci95_mean_pct"]
            print(f"{b:<8} {N:>3} {s20['n']:>4} "
                  f"{s20['mean_gross_pct']:>+8.3f} "
                  f"{s10['mean_pct']:>+8.3f} "
                  f"{s20['mean_pct']:>+8.3f} "
                  f"{s20['hit_rate']:>5.3f} "
                  f"{s20['t_stat']:>+6.2f} "
                  f"[{ci[0]:+.3f},{ci[1]:+.3f}]  "
                  f"{s20['max_dd_pct']:>+7.2f}")
        print()

    print("--- Monotonicity (mean %, 10D, 20bps) ---")
    for b in ("low", "medium", "high"):
        v = primary_means[b]
        print(f"  {b:<6}  mean = {v:+.3f}%" if v is not None else f"  {b:<6}  n/a")
    print(f"  MONOTONIC: {mono}")
    print()

    print("--- Raw Variant C vs High bucket comparison (10D, 20bps) ---")
    r20 = raw_C["per_window"]["10"]["20bps"]
    h20 = per_bucket["high"]["per_window"]["10"]["20bps"]
    print(f"  raw_C     n={r20.get('n',0)}  mean={r20.get('mean_pct',0):+.3f}%  "
          f"t={r20.get('t_stat',0):+.2f}  hit={r20.get('hit_rate',0):.3f}  "
          f"cum={r20.get('cumulative_pct',0):+.2f}%")
    print(f"  high-only n={h20.get('n',0)}  mean={h20.get('mean_pct',0):+.3f}%  "
          f"t={h20.get('t_stat',0):+.2f}  hit={h20.get('hit_rate',0):.3f}  "
          f"cum={h20.get('cumulative_pct',0):+.2f}%")
    print()

    print("--- Ablation (high-bucket with component removed, 10D/20bps) ---")
    print(f"{'ablation':<22} {'n_high':>7} {'high_mean%':>11} {'high_t':>7} "
          f"{'n_low':>7} {'low_mean%':>10} {'low_t':>7}")
    print(f"{'(full score)':<22} {full_high_stats.get('n',0):>7} "
          f"{full_high_stats.get('mean_pct',0):>+11.3f} "
          f"{full_high_stats.get('t_stat',0):>+7.2f}  (ref)")
    for aname, ab in ablation_stats.items():
        hh = ab["high_10d_20bps"]; ll = ab["low_10d_20bps"]
        print(f"{aname:<22} {ab['n_high']:>7} "
              f"{hh.get('mean_pct',0):>+11.3f} "
              f"{hh.get('t_stat',0):>+7.2f} "
              f"{ab['n_low']:>7} "
              f"{ll.get('mean_pct',0):>+10.3f} "
              f"{ll.get('t_stat',0):>+7.2f}")
    print()

    print("--- Regime diagnostic (HIGH bucket, 10D/20bps) ---")
    for r, d in regime_diag.items():
        s = d["stats_10d_20bps"]
        if s.get("n", 0) == 0:
            print(f"  {r:<10}  n=0"); continue
        ci = s["ci95_mean_pct"]
        print(f"  {r:<10}  n={d['n']:>3}  mean={s['mean_pct']:+.3f}%  "
              f"hit={s['hit_rate']:.3f}  t={s['t_stat']:+.2f}  "
              f"CI=[{ci[0]:+.3f},{ci[1]:+.3f}]")
    print()

    print("-" * 90)
    print(f"VERDICT: {verdict}")
    print(f"  reason: {vreason}")
    print("=" * 90)
    print(f"Report: {OUT_DIR / 'report.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
