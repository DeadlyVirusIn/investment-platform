"""Phase 15 — Mean Reversion Edge Model (long-only).

Entry (ALL three required):
  1. LOOSE RANGE:          ATR10 / ATR50 > 1.2
  2. VOL ELEVATED/EXPAND:  ATR10 in upper 40% of 252-day rolling distribution
                           OR ATR10 > ATR20
  3. DOWNWARD EXTENSION:   (close - MA20) / std20  <  -1

Entry: next bar OPEN.
Exit:  close of bar N. Windows = 1, 3, 5, 10, 20.
Costs: 10 bps + 20 bps round-trip.

Diagnostic breakdowns:
  * z_score buckets: [-inf,-2), [-2,-1.5), [-1.5,-1)
  * ATR10 quartile buckets
  * trend context: close > MA50 (bull) vs <= MA50 (bear)

No ML. No threshold tuning post-results. No short side. Stop after verdict.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import random
import statistics as st
import sys
from pathlib import Path

import pandas as pd
from loguru import logger

from scripts.run_phase12_price_action import (
    fetch_es_daily, load_spy_from_db, HOLD_WINDOWS, COST_BPS,
)

OUT_DIR = Path("artifacts/phase15")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Frozen thresholds (from spec — do not tune)
LOOSE_RATIO_THRESH   = 1.2
VOL_UPPER_PERCENTILE = 0.60   # upper 40% = >= 60th percentile
VOL_ROLLING_WINDOW   = 252
Z_EXTENSION_THRESH   = -1.0
Z_WINDOW             = 20


# ---------------------------------------------------------------------------
# Features
# ---------------------------------------------------------------------------
def true_range(df: pd.DataFrame) -> pd.Series:
    pc = df["close"].shift(1)
    return pd.concat([
        df["high"] - df["low"],
        (df["high"] - pc).abs(),
        (df["low"] - pc).abs(),
    ], axis=1).max(axis=1)


def build_features(es: pd.DataFrame) -> pd.DataFrame:
    f = es.copy()
    f["tr"]     = true_range(f)
    f["atr10"]  = f["tr"].rolling(10).mean()
    f["atr20"]  = f["tr"].rolling(20).mean()
    f["atr50"]  = f["tr"].rolling(50).mean()
    f["ma20"]   = f["close"].rolling(Z_WINDOW).mean()
    f["std20"]  = f["close"].rolling(Z_WINDOW).std()
    f["ma50"]   = f["close"].rolling(50).mean()
    f["loose_ratio"]  = f["atr10"] / f["atr50"]
    f["z_score"]      = (f["close"] - f["ma20"]) / f["std20"]
    # Rolling 252-day 60th percentile of ATR10
    f["atr10_p60"] = f["atr10"].rolling(VOL_ROLLING_WINDOW, min_periods=60).quantile(
        VOL_UPPER_PERCENTILE,
    )
    f["vol_elevated"] = f["atr10"] >= f["atr10_p60"]
    f["vol_expanding"] = f["atr10"] > f["atr20"]
    return f


def compute_entry(f: pd.DataFrame) -> pd.Series:
    c1 = f["loose_ratio"] > LOOSE_RATIO_THRESH
    c2 = f["vol_elevated"] | f["vol_expanding"]
    c3 = f["z_score"] < Z_EXTENSION_THRESH
    return (c1 & c2 & c3).fillna(False)


def forward_returns(f: pd.DataFrame, windows: tuple[int, ...]) -> dict[int, pd.Series]:
    out: dict[int, pd.Series] = {}
    for N in windows:
        entry = f["open"].shift(-1)
        exit_ = f["close"].shift(-N)
        out[N] = (exit_ - entry) / entry
    return out


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------
def _bootstrap_ci(xs, *, n_boot=5000, conf=0.95):
    if not xs: return (0.0, 0.0)
    rng = random.Random(42); n = len(xs)
    means = [sum(xs[rng.randrange(n)] for _ in range(n)) / n for _ in range(n_boot)]
    means.sort()
    return (means[int((1 - conf) / 2 * n_boot)],
            means[int((1 - (1 - conf) / 2) * n_boot) - 1])


def summarize(rets, bps):
    if not rets: return {"n": 0}
    cost = bps / 1e4
    rn = [r - cost for r in rets]
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
        "hit": wins / n, "t": t,
        "ci95_pct": [lo * 100, hi * 100],
        "mean_gross_pct": st.mean(rets) * 100,
        "cum_pct": (path[-1] - 1) * 100 if path else 0.0,
        "max_dd_pct": dd * 100,
    }


def bucketed(f, entry_mask, fwd, key_fn, *, bps=20.0):
    groups: dict[str, list[float]] = {}
    cost = bps / 1e4
    for idx, enter in zip(f.index, entry_mask):
        if not enter or pd.isna(fwd[idx]):
            continue
        k = key_fn(f.loc[idx])
        if k is None:
            continue
        groups.setdefault(k, []).append(fwd[idx] - cost)
    return {k: summarize([r + cost for r in v], bps=bps) for k, v in groups.items()}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    logger.info("[p15] fetching ES=F + SPY")
    es = fetch_es_daily(start="2020-01-01")
    spy = load_spy_from_db()
    es = es[~es.index.duplicated(keep="last")].sort_index()
    spy = spy[~spy.index.duplicated(keep="last")].sort_index()
    common = es.index.intersection(spy.index)
    es = es.loc[common]
    logger.info("[p15] common {} bars ({} -> {})", len(es), es.index[0], es.index[-1])

    f = build_features(es)
    entry = compute_entry(f)
    fwd = forward_returns(f, HOLD_WINDOWS)

    # Entry-condition counts
    c1 = (f["loose_ratio"] > LOOSE_RATIO_THRESH).fillna(False)
    c2 = (f["vol_elevated"] | f["vol_expanding"]).fillna(False)
    c3 = (f["z_score"] < Z_EXTENSION_THRESH).fillna(False)
    n_c1 = int(c1.sum()); n_c2 = int(c2.sum()); n_c3 = int(c3.sum())
    n_entry = int(entry.sum())

    # Main backtest — per window / per cost
    main_table: dict = {}
    for N in HOLD_WINDOWS:
        ret = fwd[N]
        rets = [ret[i] for i in f.index if entry[i] and not pd.isna(ret[i])]
        main_table[str(N)] = {f"{b}bps": summarize(rets, b) for b in COST_BPS}

    # Baseline: long_all (no entry condition)
    base_table: dict = {}
    for N in HOLD_WINDOWS:
        ret = fwd[N]
        rets = [ret[i] for i in f.index if not pd.isna(ret[i])]
        base_table[str(N)] = {f"{b}bps": summarize(rets, b) for b in COST_BPS}

    # Diagnostic splits — all at 10D/20bps
    N = 10
    ret10 = fwd[N]
    entry_idx = [i for i in f.index if entry[i] and not pd.isna(ret10[i])]

    # z_score buckets
    def _z_bucket(row):
        z = row["z_score"]
        if pd.isna(z): return None
        if z < -2.0:  return "z_lt_-2"
        if z < -1.5:  return "z_-2_to_-1.5"
        return "z_-1.5_to_-1"
    z_bucket_stats = bucketed(f, entry, ret10, _z_bucket)

    # ATR10 quartile buckets
    atr10_q = f["atr10"].quantile([0.25, 0.5, 0.75]).values
    def _atr_bucket(row):
        a = row["atr10"]
        if pd.isna(a): return None
        if a < atr10_q[0]: return "Q1_lowvol"
        if a < atr10_q[1]: return "Q2"
        if a < atr10_q[2]: return "Q3"
        return "Q4_highvol"
    atr_bucket_stats = bucketed(f, entry, ret10, _atr_bucket)

    # Trend context: close vs MA50
    def _trend_ctx(row):
        c, m = row["close"], row["ma50"]
        if pd.isna(m): return None
        return "bull_above_ma50" if c > m else "bear_below_ma50"
    trend_stats = bucketed(f, entry, ret10, _trend_ctx)

    # Verdict — 10D/20bps gate on main
    primary = main_table["10"]["20bps"]
    n = primary.get("n", 0); t = primary.get("t", 0); m = primary.get("mean_pct", 0)
    ci = primary.get("ci95_pct", [0, 0])
    base10 = base_table["10"]["20bps"]
    edge_vs_baseline = m - base10.get("mean_pct", 0)

    if n == 0:
        verdict = "FAIL"; vreason = "no entries"
    elif n >= 30 and t > 2.0 and m > 0 and ci[0] > 0 and edge_vs_baseline > 0:
        verdict = "PASS"
        vreason = (f"n={n} t={t:.2f} mean={m:.3f}% CI=[{ci[0]:.3f},{ci[1]:.3f}] "
                   f"edge_vs_baseline=+{edge_vs_baseline:.3f}%")
    elif n >= 15 and t > 1.0 and m > 0 and edge_vs_baseline > 0:
        verdict = "WEAK"
        vreason = (f"suggestive n={n} t={t:.2f} mean={m:.3f}% CI=[{ci[0]:.3f},{ci[1]:.3f}] "
                   f"edge_vs_baseline=+{edge_vs_baseline:.3f}%")
    else:
        verdict = "FAIL"
        vreason = (f"n={n} t={t:.2f} mean={m:.3f}% CI=[{ci[0]:.3f},{ci[1]:.3f}] "
                   f"edge_vs_baseline={edge_vs_baseline:+.3f}%")

    report = {
        "phase": "15_mean_reversion",
        "today": dt.date.today().isoformat(),
        "params": {
            "loose_ratio_thresh": LOOSE_RATIO_THRESH,
            "vol_upper_percentile": VOL_UPPER_PERCENTILE,
            "vol_rolling_window": VOL_ROLLING_WINDOW,
            "z_extension_thresh": Z_EXTENSION_THRESH,
            "z_window": Z_WINDOW,
            "hold_windows": list(HOLD_WINDOWS),
            "cost_bps": list(COST_BPS),
        },
        "data_bars": len(f),
        "data_range": [str(f.index[0]), str(f.index[-1])],
        "condition_counts": {
            "c1_loose": n_c1, "c2_vol": n_c2, "c3_downext": n_c3,
            "all_three_entry": n_entry,
        },
        "main_per_window": main_table,
        "baseline_per_window": base_table,
        "z_bucket_10d_20bps": z_bucket_stats,
        "atr_bucket_10d_20bps": atr_bucket_stats,
        "trend_context_10d_20bps": trend_stats,
        "verdict": verdict,
        "verdict_reason": vreason,
        "edge_vs_baseline_10d_20bps_pct": edge_vs_baseline,
    }
    (OUT_DIR / "report.json").write_text(json.dumps(report, indent=2, default=str))

    # Print
    print("=" * 90)
    print(f"PHASE 15 — MEAN REVERSION EDGE MODEL (long-only)  {dt.date.today()}")
    print("=" * 90)
    print(f"Data: ES=F {f.index[0]} -> {f.index[-1]} ({len(f)} bars)")
    print()
    print("--- Entry-condition frequencies ---")
    print(f"  c1 (ATR10/ATR50 > 1.2):           {n_c1:>5}")
    print(f"  c2 (vol elevated OR expanding):   {n_c2:>5}")
    print(f"  c3 (z_score < -1):                {n_c3:>5}")
    print(f"  ALL-THREE entry signals:          {n_entry:>5}")
    print()
    print("--- Main results (entry-gated, per window) ---")
    print(f"{'N':>3} {'n':>4} {'gross%':>8} {'net10%':>8} {'net20%':>8} "
          f"{'hit':>5} {'t':>6} {'CI95% 20bps':<22} {'cum%':>7} {'maxDD%':>7}")
    for N in HOLD_WINDOWS:
        s10 = main_table[str(N)]["10bps"]; s20 = main_table[str(N)]["20bps"]
        if s20.get("n", 0) == 0:
            continue
        ci = s20["ci95_pct"]
        print(f"{N:>3} {s20['n']:>4} {s20['mean_gross_pct']:>+8.3f} "
              f"{s10['mean_pct']:>+8.3f} {s20['mean_pct']:>+8.3f} "
              f"{s20['hit']:>5.3f} {s20['t']:>+6.2f} "
              f"[{ci[0]:+.3f},{ci[1]:+.3f}]  "
              f"{s20['cum_pct']:>+7.2f} {s20['max_dd_pct']:>+7.2f}")
    print()
    print("--- Baseline (long_all, same windows / costs) ---")
    print(f"{'N':>3} {'n':>4} {'net20%':>8} {'hit':>5} {'t':>6}")
    for N in HOLD_WINDOWS:
        b20 = base_table[str(N)]["20bps"]
        if b20.get("n", 0) == 0: continue
        print(f"{N:>3} {b20['n']:>4} {b20['mean_pct']:>+8.3f} "
              f"{b20['hit']:>5.3f} {b20['t']:>+6.2f}")
    print()
    print("--- Edge vs baseline (10D/20bps): "
          f"{edge_vs_baseline:+.3f}% ---")
    print()
    print("--- z_score buckets (10D/20bps) ---")
    for k, s in sorted(z_bucket_stats.items()):
        if s.get("n", 0) == 0: continue
        ci = s["ci95_pct"]
        print(f"  {k:<16}  n={s['n']:>3}  mean={s['mean_pct']:+.3f}%  "
              f"hit={s['hit']:.3f}  t={s['t']:+.2f}  "
              f"CI=[{ci[0]:+.3f},{ci[1]:+.3f}]")
    print()
    print("--- ATR10 quartile buckets (10D/20bps) ---")
    for k, s in sorted(atr_bucket_stats.items()):
        if s.get("n", 0) == 0: continue
        ci = s["ci95_pct"]
        print(f"  {k:<16}  n={s['n']:>3}  mean={s['mean_pct']:+.3f}%  "
              f"hit={s['hit']:.3f}  t={s['t']:+.2f}  "
              f"CI=[{ci[0]:+.3f},{ci[1]:+.3f}]")
    print()
    print("--- Trend context (10D/20bps) ---")
    for k, s in sorted(trend_stats.items()):
        if s.get("n", 0) == 0: continue
        ci = s["ci95_pct"]
        print(f"  {k:<16}  n={s['n']:>3}  mean={s['mean_pct']:+.3f}%  "
              f"hit={s['hit']:.3f}  t={s['t']:+.2f}  "
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
