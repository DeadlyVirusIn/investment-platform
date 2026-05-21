"""Phase 17 — Regime Filter Model on Phase 15 signal.

Base entry (frozen, unchanged from Phase 15):
    ATR10 / ATR50 > 1.2
    ATR10 >= rolling-252d P60  OR  ATR10 > ATR20
    z_score(close, MA20, std20) < -1.0
    long-only

Filters tested (applied on top of base):
    A. bear only:                close < MA50
    B. bear + elevated vol:      close < MA50  AND  ATR10 >= rolling-252d P60
    C. bear + expanding vol:     close < MA50  AND  ATR10 > ATR20
    D. bear + (elevated OR expanding): close < MA50  AND  (elevated OR expanding)

For each filter: windows 1/3/5/10/20, costs 10bps + 20bps. IS (2022-2024) vs
OOS (2025-2026). 2026-YTD diagnostic. Sample-retention vs unfiltered P15.

No new features. No tuning. No ML. Stop at verdict.
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

OUT_DIR = Path("artifacts/phase17")
OUT_DIR.mkdir(parents=True, exist_ok=True)

IS_END    = dt.date(2024, 12, 31)
OOS_START = dt.date(2025, 1, 1)
YEAR_2026_START = dt.date(2026, 1, 1)

COST_BPS = (10, 20)


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
        "mean_gross_pct": st.mean(rets) * 100,
        "cum_pct": (path[-1] - 1) * 100 if path else 0.0,
        "max_dd_pct": dd * 100,
    }


def base_p15_entry(f: pd.DataFrame) -> pd.Series:
    c1 = f["loose_ratio"] > LOOSE_RATIO_THRESH
    c2 = f["vol_elevated"] | f["vol_expanding"]
    c3 = f["z_score"] < Z_EXTENSION_THRESH
    return (c1 & c2 & c3).fillna(False)


def filter_masks(f: pd.DataFrame) -> dict[str, pd.Series]:
    bear = (f["close"] < f["ma50"]).fillna(False)
    elev = f["vol_elevated"].fillna(False)
    expd = f["vol_expanding"].fillna(False)
    return {
        "A_bear":              bear,
        "B_bear_elev":         bear & elev,
        "C_bear_expanding":    bear & expd,
        "D_bear_elev_or_expand": bear & (elev | expd),
    }


def run_subset(
    f: pd.DataFrame, entry: pd.Series, fwd: dict[int, pd.Series],
    mask: pd.Series, *, N: int, bps: float,
) -> dict:
    ret = fwd[N]
    rets = [ret[i] for i in f.index
            if entry[i] and mask[i] and not pd.isna(ret[i])]
    return summarize(rets, bps)


def main() -> int:
    logger.info("[p17] fetching ES=F + SPY")
    es = fetch_es_daily(start="2020-01-01")
    spy = load_spy_from_db()
    es = es[~es.index.duplicated(keep="last")].sort_index()
    spy = spy[~spy.index.duplicated(keep="last")].sort_index()
    common = es.index.intersection(spy.index)
    es = es.loc[common]
    logger.info("[p17] common {} bars ({} -> {})", len(es), es.index[0], es.index[-1])

    f = build_features(es)
    fwd = forward_returns(f, HOLD_WINDOWS)
    base = base_p15_entry(f)
    filters = filter_masks(f)

    # Date masks
    is_mask  = pd.Series([d <= IS_END for d in f.index], index=f.index)
    oos_mask = pd.Series([d >= OOS_START for d in f.index], index=f.index)
    y2026_mask = pd.Series([d >= YEAR_2026_START for d in f.index], index=f.index)
    all_mask = pd.Series(True, index=f.index)

    # Unfiltered P15 baseline reference (to measure retention / improvement)
    p15_full = {
        str(N): {f"{b}bps": run_subset(f, base, fwd, all_mask, N=N, bps=b)
                 for b in COST_BPS}
        for N in HOLD_WINDOWS
    }
    p15_is    = run_subset(f, base, fwd, is_mask,    N=10, bps=20)
    p15_oos   = run_subset(f, base, fwd, oos_mask,   N=10, bps=20)
    p15_2026  = run_subset(f, base, fwd, y2026_mask, N=10, bps=20)
    n_base_total = int(base.sum())

    per_filter: dict = {}
    for fname, fmask in filters.items():
        entry_f = (base & fmask).fillna(False)
        n_kept = int(entry_f.sum())
        retention = n_kept / max(n_base_total, 1)

        per_window: dict = {}
        for N in HOLD_WINDOWS:
            per_window[str(N)] = {
                f"{b}bps": run_subset(f, entry_f, fwd, all_mask, N=N, bps=b)
                for b in COST_BPS
            }

        is_stats    = run_subset(f, entry_f, fwd, is_mask,    N=10, bps=20)
        oos_stats   = run_subset(f, entry_f, fwd, oos_mask,   N=10, bps=20)
        y2026_stats = run_subset(f, entry_f, fwd, y2026_mask, N=10, bps=20)

        per_filter[fname] = {
            "n_base": n_base_total,
            "n_kept": n_kept,
            "retention_pct": retention,
            "per_window_full": per_window,
            "is_10d_20bps":   is_stats,
            "oos_10d_20bps":  oos_stats,
            "y2026_10d_20bps": y2026_stats,
        }

    # Robustness verdict — compare each filter's OOS vs unfiltered OOS
    verdicts: dict = {}
    oos_lo_base = p15_oos.get("ci95_pct", [0, 0])[0]
    y2026_mean_base = p15_2026.get("mean_pct", 0)

    for fname, pf in per_filter.items():
        oos = pf["oos_10d_20bps"]
        y26 = pf["y2026_10d_20bps"]
        ci = oos.get("ci95_pct", [0, 0])
        n_oos = oos.get("n", 0)
        m_oos = oos.get("mean_pct", 0)
        t_oos = oos.get("t", 0)
        m_26  = y26.get("mean_pct", 0)
        n_26  = y26.get("n", 0)

        lo_crosses_zero = ci[0] > 0
        oos_improved = ci[0] > oos_lo_base
        y2026_damage_reduced = m_26 > y2026_mean_base

        if n_oos == 0:
            v = "FAIL"; reasons = ["no OOS signals"]
        elif (n_oos >= 15 and t_oos > 2.0 and m_oos > 0 and lo_crosses_zero
              and y2026_damage_reduced):
            v = "ROBUST"
            reasons = [
                f"OOS n={n_oos} t={t_oos:.2f} mean={m_oos:.3f}% CI=[{ci[0]:.3f},{ci[1]:.3f}]",
                f"2026 YTD: mean={m_26:+.3f}% (vs base {y2026_mean_base:+.3f}%) damage reduced",
                f"OOS CI lower bound {ci[0]:+.3f} > 0 ✓",
            ]
        elif (n_oos >= 10 and m_oos > 0 and t_oos > 1.0 and y2026_damage_reduced):
            v = "WEAK"
            reasons = [
                f"OOS n={n_oos} t={t_oos:.2f} mean={m_oos:.3f}% CI=[{ci[0]:.3f},{ci[1]:.3f}]",
                f"2026 YTD: mean={m_26:+.3f}% vs base {y2026_mean_base:+.3f}%",
                f"improvement present but sample/statistics thin",
            ]
        else:
            v = "FAIL"
            reasons = [
                f"OOS n={n_oos} t={t_oos:.2f} mean={m_oos:.3f}% CI=[{ci[0]:.3f},{ci[1]:.3f}]",
                f"2026 YTD: mean={m_26:+.3f}% vs base {y2026_mean_base:+.3f}%",
            ]
        verdicts[fname] = {"verdict": v, "reasons": reasons,
                           "oos_lo_vs_base_pp": ci[0] - oos_lo_base,
                           "y2026_delta_vs_base_pp": m_26 - y2026_mean_base}

    # Pick best filter per stratified gate
    def _rank_key(v):
        order = {"ROBUST": 0, "WEAK": 1, "FAIL": 2}
        return (order.get(verdicts[v]["verdict"], 3),
                -verdicts[v]["y2026_delta_vs_base_pp"])
    best_filter = sorted(verdicts.keys(), key=_rank_key)[0]

    report = {
        "phase": "17_regime_filter",
        "today": dt.date.today().isoformat(),
        "data_range": [str(f.index[0]), str(f.index[-1])],
        "unfiltered_p15_10d_20bps_full": p15_full["10"]["20bps"],
        "unfiltered_p15_is":    p15_is,
        "unfiltered_p15_oos":   p15_oos,
        "unfiltered_p15_y2026": p15_2026,
        "filters": per_filter,
        "verdicts": verdicts,
        "best_filter": best_filter,
    }
    (OUT_DIR / "report.json").write_text(json.dumps(report, indent=2, default=str))

    # Print
    print("=" * 100)
    print(f"PHASE 17 — REGIME FILTER MODEL  {dt.date.today()}")
    print("=" * 100)
    print(f"Data: ES=F {f.index[0]} -> {f.index[-1]} ({len(f)} bars)")
    print(f"Unfiltered P15 signals total: {n_base_total}")
    print()
    print("--- UNFILTERED PHASE 15 BASELINE (10D/20bps) ---")
    p20 = p15_full["10"]["20bps"]
    print(f"  full:  n={p20['n']}  mean={p20['mean_pct']:+.3f}%  t={p20['t']:+.2f}  "
          f"CI=[{p20['ci95_pct'][0]:+.3f},{p20['ci95_pct'][1]:+.3f}]")
    print(f"  IS:    n={p15_is['n']}  mean={p15_is['mean_pct']:+.3f}%  t={p15_is['t']:+.2f}")
    print(f"  OOS:   n={p15_oos['n']}  mean={p15_oos['mean_pct']:+.3f}%  t={p15_oos['t']:+.2f}  "
          f"CI=[{p15_oos['ci95_pct'][0]:+.3f},{p15_oos['ci95_pct'][1]:+.3f}]")
    print(f"  2026:  n={p15_2026['n']}  mean={p15_2026['mean_pct']:+.3f}%  t={p15_2026['t']:+.2f}")
    print()

    for fname, pf in per_filter.items():
        print(f"========== FILTER {fname} ==========")
        print(f"n_kept={pf['n_kept']} / n_base={pf['n_base']}  "
              f"retention={pf['retention_pct']*100:.1f}%")
        print()
        print("  --- full-sample, per-window (10bps | 20bps) ---")
        print(f"  {'N':>3} {'n':>4} {'gross%':>8} {'net10%':>8} {'net20%':>8} "
              f"{'hit':>5} {'t':>6} {'CI95% 20bps':<22} {'cum%':>8} {'maxDD%':>8}")
        for N in HOLD_WINDOWS:
            s10 = pf["per_window_full"][str(N)]["10bps"]
            s20 = pf["per_window_full"][str(N)]["20bps"]
            if s20.get("n", 0) == 0:
                print(f"  {N:>3} 0"); continue
            ci = s20["ci95_pct"]
            print(f"  {N:>3} {s20['n']:>4} {s20['mean_gross_pct']:>+8.3f} "
                  f"{s10['mean_pct']:>+8.3f} {s20['mean_pct']:>+8.3f} "
                  f"{s20['hit']:>5.3f} {s20['t']:>+6.2f} "
                  f"[{ci[0]:+.3f},{ci[1]:+.3f}]  "
                  f"{s20['cum_pct']:>+8.2f} {s20['max_dd_pct']:>+8.2f}")
        print()
        print("  --- IS vs OOS vs 2026 YTD (10D/20bps) ---")
        for label, s in (("IS",    pf["is_10d_20bps"]),
                         ("OOS",   pf["oos_10d_20bps"]),
                         ("2026", pf["y2026_10d_20bps"])):
            if s.get("n", 0) == 0:
                print(f"    {label:<5}  n=0"); continue
            ci = s["ci95_pct"]
            print(f"    {label:<5}  n={s['n']:>3}  mean={s['mean_pct']:+.3f}%  "
                  f"hit={s['hit']:.3f}  t={s['t']:+.2f}  "
                  f"CI=[{ci[0]:+.3f},{ci[1]:+.3f}]")
        v = verdicts[fname]
        print(f"  VERDICT: {v['verdict']}")
        for r in v['reasons']:
            print(f"    - {r}")
        print(f"  OOS CI_lo improvement vs base: {v['oos_lo_vs_base_pp']:+.3f} pp")
        print(f"  2026 mean improvement vs base: {v['y2026_delta_vs_base_pp']:+.3f} pp")
        print()

    print("=" * 100)
    print(f"BEST FILTER (by verdict rank + 2026 damage reduction): {best_filter}")
    v = verdicts[best_filter]
    print(f"  {v['verdict']}  2026 improvement={v['y2026_delta_vs_base_pp']:+.3f} pp")
    print("=" * 100)
    print(f"Report: {OUT_DIR / 'report.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
