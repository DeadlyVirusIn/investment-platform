"""Phase 16 — Robustness & Out-of-Sample Validation of Phase 15 signal.

Same entry logic as Phase 15:
  c1: ATR10 / ATR50 > LOOSE_RATIO
  c2: ATR10 >= rolling-252d P60  OR  ATR10 > ATR20
  c3: z_score(close, MA20, std20) < Z_THRESH

Tests:
  1. In-sample (2022-2024) vs Out-of-sample (2025-2026)
  2. Yearly breakdown (stability over time)
  3. Parameter sensitivity: 3 z thresholds × 3 ATR ratios
  4. Cost sensitivity: 10 / 20 / 30 bps
  5. Regime split: bull-only (close > MA50) vs bear-only

No ML. No strategy change. No tuning after results. Stop at verdict.
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
    fetch_es_daily, load_spy_from_db, HOLD_WINDOWS,
)
from scripts.run_phase15_mean_reversion import (
    build_features, forward_returns,
    LOOSE_RATIO_THRESH, Z_EXTENSION_THRESH,
)

OUT_DIR = Path("artifacts/phase16")
OUT_DIR.mkdir(parents=True, exist_ok=True)

IS_END = dt.date(2024, 12, 31)
OOS_START = dt.date(2025, 1, 1)

Z_GRID   = (-0.8, -1.0, -1.2)
RATIO_GRID = (1.1, 1.2, 1.3)
COST_GRID  = (10, 20, 30)


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
        "n": n, "mean_pct": mean * 100, "median_pct": med * 100,
        "std_pct": sd * 100, "hit": wins / n, "t": t,
        "ci95_pct": [lo * 100, hi * 100],
        "cum_pct": (path[-1] - 1) * 100 if path else 0.0,
        "max_dd_pct": dd * 100,
    }


def compute_entry_custom(
    f: pd.DataFrame, *, z_thresh: float, ratio_thresh: float,
) -> pd.Series:
    c1 = f["loose_ratio"] > ratio_thresh
    c2 = f["vol_elevated"] | f["vol_expanding"]
    c3 = f["z_score"] < z_thresh
    return (c1 & c2 & c3).fillna(False)


def subsample_stats(
    f: pd.DataFrame, entry: pd.Series, fwd: dict[int, pd.Series],
    *, N: int, bps: float, mask: pd.Series = None,
) -> dict:
    ret = fwd[N]
    if mask is None:
        mask = pd.Series(True, index=f.index)
    rets = [ret[i] for i in f.index if entry[i] and mask[i] and not pd.isna(ret[i])]
    return summarize(rets, bps)


def main() -> int:
    logger.info("[p16] fetching ES=F + SPY")
    es = fetch_es_daily(start="2020-01-01")
    spy = load_spy_from_db()
    es = es[~es.index.duplicated(keep="last")].sort_index()
    spy = spy[~spy.index.duplicated(keep="last")].sort_index()
    common = es.index.intersection(spy.index)
    es = es.loc[common]
    logger.info("[p16] common {} bars ({} -> {})", len(es), es.index[0], es.index[-1])

    f = build_features(es)
    fwd = forward_returns(f, HOLD_WINDOWS)

    # Primary signal (phase 15 params)
    entry = compute_entry_custom(
        f, z_thresh=Z_EXTENSION_THRESH, ratio_thresh=LOOSE_RATIO_THRESH,
    )

    # === 1. In-sample vs Out-of-sample ==================================
    is_mask  = pd.Series([(d <= IS_END) for d in f.index], index=f.index)
    oos_mask = pd.Series([(d >= OOS_START) for d in f.index], index=f.index)

    is_oos: dict = {}
    for N in HOLD_WINDOWS:
        for bps in (10, 20):
            is_stats  = subsample_stats(f, entry, fwd, N=N, bps=bps, mask=is_mask)
            oos_stats = subsample_stats(f, entry, fwd, N=N, bps=bps, mask=oos_mask)
            is_oos[f"{N}_{bps}bps"] = {"in_sample": is_stats, "oos": oos_stats}

    # === 2. Yearly breakdown =============================================
    yearly: dict = {}
    for yr in sorted({d.year for d in f.index}):
        y_mask = pd.Series([d.year == yr for d in f.index], index=f.index)
        yearly[str(yr)] = {
            "10D_20bps": subsample_stats(f, entry, fwd, N=10, bps=20, mask=y_mask)
        }

    # === 3. Parameter sensitivity ========================================
    param_grid: dict = {}
    for z in Z_GRID:
        for ratio in RATIO_GRID:
            e = compute_entry_custom(f, z_thresh=z, ratio_thresh=ratio)
            s = subsample_stats(f, e, fwd, N=10, bps=20)
            param_grid[f"z{z}_ratio{ratio}"] = {
                "z_thresh": z, "ratio_thresh": ratio, **s,
            }

    # === 4. Cost sensitivity =============================================
    cost_grid: dict = {}
    for c in COST_GRID:
        s = subsample_stats(f, entry, fwd, N=10, bps=c)
        cost_grid[f"{c}bps"] = s

    # === 5. Regime diagnostic ============================================
    bull_mask = (f["close"] > f["ma50"]).fillna(False)
    bear_mask = (f["close"] <= f["ma50"]).fillna(False)
    regime = {
        "bull_above_ma50_10D_20bps":  subsample_stats(f, entry, fwd, N=10, bps=20, mask=bull_mask),
        "bear_below_ma50_10D_20bps": subsample_stats(f, entry, fwd, N=10, bps=20, mask=bear_mask),
    }

    # ==== Robustness verdict ==============================================
    primary_is  = is_oos["10_20bps"]["in_sample"]
    primary_oos = is_oos["10_20bps"]["oos"]
    n_is = primary_is.get("n", 0); n_oos = primary_oos.get("n", 0)
    m_is = primary_is.get("mean_pct", 0); m_oos = primary_oos.get("mean_pct", 0)
    t_oos = primary_oos.get("t", 0)
    oos_ci = primary_oos.get("ci95_pct", [0, 0])

    # Count param-grid cells that pass (mean>0, t>1)
    grid_pass = sum(1 for v in param_grid.values()
                    if v.get("n", 0) >= 20 and v.get("mean_pct", 0) > 0 and v.get("t", 0) > 1.0)
    grid_pass_strict = sum(1 for v in param_grid.values()
                           if v.get("n", 0) >= 20 and v.get("mean_pct", 0) > 0 and v.get("t", 0) > 2.0)

    # Degradation: (m_oos - m_is) / |m_is|
    degrad = (m_oos - m_is) / abs(m_is) if m_is != 0 else None

    # Cost degradation: sign stays positive across 10/20/30
    cost_signs_ok = all(cost_grid[f"{c}bps"].get("mean_pct", 0) > 0 for c in COST_GRID)

    if n_oos == 0:
        verdict = "FAIL"; reasons = ["no OOS signals"]
    elif (n_oos >= 15 and t_oos > 2.0 and m_oos > 0 and oos_ci[0] > 0
          and grid_pass_strict >= 6 and cost_signs_ok):
        verdict = "ROBUST"
        reasons = [
            f"OOS n={n_oos} t={t_oos:.2f} mean={m_oos:.3f}% CI=[{oos_ci[0]:.3f},{oos_ci[1]:.3f}]",
            f"{grid_pass_strict}/9 param cells pass strict (t>2)",
            f"all costs 10/20/30bps still positive",
        ]
    elif (n_oos >= 10 and t_oos > 1.0 and m_oos > 0
          and grid_pass >= 5 and cost_signs_ok):
        verdict = "WEAK"
        reasons = [
            f"OOS n={n_oos} t={t_oos:.2f} mean={m_oos:.3f}% CI=[{oos_ci[0]:.3f},{oos_ci[1]:.3f}]",
            f"{grid_pass}/9 param cells pass t>1",
        ]
    else:
        verdict = "FAIL"
        reasons = [
            f"OOS n={n_oos} t={t_oos:.2f} mean={m_oos:.3f}% CI=[{oos_ci[0]:.3f},{oos_ci[1]:.3f}]",
            f"{grid_pass}/9 param cells pass t>1 / "
            f"{grid_pass_strict}/9 strict / costs_ok={cost_signs_ok}",
        ]

    report = {
        "phase": "16_robustness",
        "today": dt.date.today().isoformat(),
        "data_range": [str(f.index[0]), str(f.index[-1])],
        "data_bars": len(f),
        "is_oos_split": {"is_end": str(IS_END), "oos_start": str(OOS_START)},
        "is_vs_oos_per_window": is_oos,
        "yearly_10d_20bps": yearly,
        "param_sensitivity_10d_20bps": param_grid,
        "cost_sensitivity_10d": cost_grid,
        "regime_diag_10d_20bps": regime,
        "degradation_is_to_oos_pct": degrad,
        "param_grid_pass_t1": grid_pass,
        "param_grid_pass_t2": grid_pass_strict,
        "cost_signs_positive": cost_signs_ok,
        "verdict": verdict,
        "verdict_reasons": reasons,
    }
    (OUT_DIR / "report.json").write_text(json.dumps(report, indent=2, default=str))

    # Print
    print("=" * 95)
    print(f"PHASE 16 — ROBUSTNESS & OOS VALIDATION  {dt.date.today()}")
    print("=" * 95)
    print(f"Data: ES=F {f.index[0]} -> {f.index[-1]} ({len(f)} bars)")
    print(f"Split: IS <= {IS_END}  |  OOS >= {OOS_START}")
    print()

    print("--- 1. IN-SAMPLE vs OUT-OF-SAMPLE (primary params: z<-1.0, ratio>1.2) ---")
    print(f"{'N':>3} {'cost':>5}  {'IS n':>4} {'IS mean%':>9} {'IS t':>6} "
          f"{'OOS n':>5} {'OOS mean%':>10} {'OOS t':>7} {'OOS CI95%':<22} {'d_ mean%':>8}")
    for N in HOLD_WINDOWS:
        for bps in (10, 20):
            k = f"{N}_{bps}bps"
            i = is_oos[k]["in_sample"]; o = is_oos[k]["oos"]
            if i.get("n", 0) == 0 or o.get("n", 0) == 0: continue
            delta = o["mean_pct"] - i["mean_pct"]
            ci = o["ci95_pct"]
            print(f"{N:>3} {bps:>3}bp  {i['n']:>4} {i['mean_pct']:>+9.3f} {i['t']:>+6.2f} "
                  f"{o['n']:>5} {o['mean_pct']:>+10.3f} {o['t']:>+7.2f} "
                  f"[{ci[0]:+.3f},{ci[1]:+.3f}]  {delta:>+8.3f}")
    print()

    print("--- 2. YEARLY BREAKDOWN (10D/20bps) ---")
    print(f"{'year':<6} {'n':>4} {'mean%':>8} {'hit':>5} {'t':>6} {'CI95%':<22}")
    for yr, d in sorted(yearly.items()):
        s = d["10D_20bps"]
        if s.get("n", 0) == 0:
            print(f"{yr:<6} {0:>4}"); continue
        ci = s["ci95_pct"]
        print(f"{yr:<6} {s['n']:>4} {s['mean_pct']:>+8.3f} "
              f"{s['hit']:>5.3f} {s['t']:>+6.2f} [{ci[0]:+.3f},{ci[1]:+.3f}]")
    print()

    print("--- 3. PARAMETER SENSITIVITY (10D/20bps) ---")
    print(f"{'config':<18} {'n':>4} {'mean%':>8} {'hit':>5} {'t':>6} {'CI95%':<22}")
    for k, s in param_grid.items():
        if s.get("n", 0) == 0:
            print(f"{k:<18} 0"); continue
        ci = s["ci95_pct"]
        print(f"{k:<18} {s['n']:>4} {s['mean_pct']:>+8.3f} "
              f"{s['hit']:>5.3f} {s['t']:>+6.2f} [{ci[0]:+.3f},{ci[1]:+.3f}]")
    print(f"  >> {grid_pass}/9 cells pass t>1, {grid_pass_strict}/9 pass t>2")
    print()

    print("--- 4. COST SENSITIVITY (10D) ---")
    print(f"{'cost':>6} {'n':>4} {'mean%':>8} {'t':>6} {'CI95%':<22}")
    for k, s in cost_grid.items():
        if s.get("n", 0) == 0: continue
        ci = s["ci95_pct"]
        print(f"{k:>6} {s['n']:>4} {s['mean_pct']:>+8.3f} "
              f"{s['t']:>+6.2f} [{ci[0]:+.3f},{ci[1]:+.3f}]")
    print(f"  >> all-costs-positive = {cost_signs_ok}")
    print()

    print("--- 5. REGIME DIAGNOSTIC (10D/20bps) ---")
    for k, s in regime.items():
        if s.get("n", 0) == 0: continue
        ci = s["ci95_pct"]
        print(f"  {k:<32} n={s['n']:>3} mean={s['mean_pct']:+.3f}% "
              f"hit={s['hit']:.3f} t={s['t']:+.2f} CI=[{ci[0]:+.3f},{ci[1]:+.3f}]")
    print()

    print("-" * 95)
    print(f"IS->OOS degradation (10D/20bps mean): "
          f"{degrad*100:+.1f}% of |IS|" if degrad is not None else "n/a")
    print()
    print(f"VERDICT: {verdict}")
    for r in reasons: print(f"  {r}")
    print("=" * 95)
    print(f"Report: {OUT_DIR / 'report.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
