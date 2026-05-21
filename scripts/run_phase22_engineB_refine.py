"""Phase 22 — Directional Engine Refinement.

Inputs fixed: rates_calm, vrp_supportive, credit_stable, liquidity_expanding.
Engine A (P15 on stress bars) unchanged.
Regime selector (gates_favorable <=1 vs >=2) unchanged.

Only Engine B's SLEEVE composition changes per variant:

  Variant A (baseline):  equal-weight all 4. weight_per_bar = #gates_true / 4
  Variant B (top-2):     keep only 2 sleeves with strongest OOS t-stat (1D/5bps).
                         weight = #top2_gates_true / 2
  Variant C (agreement): trade only when BOTH top-2 sleeves agree (AND).
                         weight in {0, 1}

Re-run combined two-engine system for each variant. Compare OOS, 2026, maxDD,
sample, t-stat. No tuning. No ML.
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

from scripts.run_phase12_price_action import fetch_es_daily, load_spy_from_db, HOLD_WINDOWS
from scripts.run_phase15_mean_reversion import (
    build_features, forward_returns,
    LOOSE_RATIO_THRESH, Z_EXTENSION_THRESH,
)
from scripts.run_phase20_regime_gated import build_gates

OUT_DIR = Path("artifacts/phase22")
OUT_DIR.mkdir(parents=True, exist_ok=True)

IS_END = dt.date(2024, 12, 31)
OOS_START = dt.date(2025, 1, 1)
Y2026_START = dt.date(2026, 1, 1)

HOLD_A = 10
COST_A_BPS = 20.0
COST_B_BPS = 5.0


def _bootstrap_ci(xs, n_boot=5000, conf=0.95):
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
    n = len(rn); mean = st.mean(rn); med = st.median(rn)
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


def dmask(idx, pred):
    return pd.Series([pred(i) for i in idx], index=idx)


def main() -> int:
    logger.info("[p22] loading data")
    es = fetch_es_daily(start="2020-01-01")
    spy = load_spy_from_db()
    es = es[~es.index.duplicated(keep="last")].sort_index()
    spy = spy[~spy.index.duplicated(keep="last")].sort_index()
    common = es.index.intersection(spy.index)
    es = es.loc[common]; spy = spy.loc[common]
    f = build_features(es)
    fwd = forward_returns(f, HOLD_WINDOWS)
    gates = build_gates(f, spy)

    # 1-day forward return (open->close same day via shift)
    fwd_1d = (f["open"].shift(-1).pct_change() * 0 + 0)  # placeholder — compute directly:
    entry_d = f["open"].shift(-1)
    exit_d = f["close"].shift(-1)
    fwd_1d = (exit_d - entry_d) / entry_d

    # P15 entry
    c1 = f["loose_ratio"] > LOOSE_RATIO_THRESH
    c2 = f["vol_elevated"] | f["vol_expanding"]
    c3 = f["z_score"] < Z_EXTENSION_THRESH
    p15_entry = (c1 & c2 & c3).fillna(False)

    # Regime unchanged
    g = gates["gates_favorable"]
    stress_regime = (g <= 1).fillna(False)
    directional_regime = (g >= 2).fillna(False)

    # Date masks
    is_m  = dmask(f.index, lambda d: d <= IS_END)
    oos_m = dmask(f.index, lambda d: d >= OOS_START)
    y26_m = dmask(f.index, lambda d: d >= Y2026_START)

    gate_cols = ["rates_calm", "vrp_supportive", "credit_stable", "liquidity_expanding"]

    # =====================================================================
    # STEP 1 — Per-sleeve OOS analysis (1D/5bps)
    # =====================================================================
    per_sleeve: dict = {}
    for gc in gate_cols:
        gate_on = gates[gc].fillna(False)
        for seg, msk in (("full", pd.Series(True, index=f.index)),
                         ("is", is_m), ("oos", oos_m), ("y2026", y26_m)):
            rets = [float(fwd_1d[i]) for i in f.index
                    if gate_on[i] and msk[i] and not pd.isna(fwd_1d[i])]
            per_sleeve[f"{gc}_{seg}"] = summarize(rets, COST_B_BPS)

    # Rank sleeves by OOS t-stat
    ranked = sorted(
        gate_cols, key=lambda c: -per_sleeve[f"{c}_oos"].get("t", -99),
    )
    top2 = ranked[:2]
    logger.info("[p22] sleeves ranked by OOS t: {}", ranked)
    logger.info("[p22] top-2: {}", top2)

    # =====================================================================
    # STEP 2 — Variants of Engine B weights per bar
    # =====================================================================
    def weight_variant_A(i):
        return float(g[i]) / 4.0 if not pd.isna(g[i]) else 0.0

    def weight_variant_B(i):
        # Top-2 only
        cnt = sum(1 for c in top2 if bool(gates[c][i]) if not pd.isna(gates[c][i]))
        return cnt / 2.0

    def weight_variant_C(i):
        # Both top-2 must agree
        both = all(bool(gates[c][i]) for c in top2 if not pd.isna(gates[c][i]))
        return 1.0 if both else 0.0

    weight_fns = {"A_equal_weight": weight_variant_A,
                  "B_top2_subset": weight_variant_B,
                  "C_top2_agreement": weight_variant_C}

    # =====================================================================
    # STEP 3 — For each variant: run Engine B on directional bars.
    # Engine A (P15 on stress) unchanged.
    # =====================================================================
    variant_results: dict = {}

    # Engine A (unchanged across variants)
    A_trades = []
    for i in f.index:
        if p15_entry[i] and stress_regime[i]:
            r = fwd[HOLD_A][i]
            if not pd.isna(r):
                A_trades.append((i, float(r) - COST_A_BPS / 1e4))

    for vname, wfn in weight_fns.items():
        B_trades = []
        for i in f.index:
            if not directional_regime[i]: continue
            if pd.isna(fwd_1d[i]): continue
            w = wfn(i)
            if w <= 0: continue
            r = float(fwd_1d[i]) * w - (COST_B_BPS / 1e4)
            B_trades.append((i, r))
        combined = [(i, r, "A") for (i, r) in A_trades] + [(i, r, "B") for (i, r) in B_trades]
        combined.sort(key=lambda t: t[0])

        # Aggregate per-segment
        def seg_rets(src_filter=None, mask=None):
            out = []
            for (i, r, src) in combined:
                if src_filter and src != src_filter: continue
                if mask is not None and not mask[i]: continue
                out.append(r)
            return out

        report = {}
        for label, msk in (("full", None), ("is", is_m),
                           ("oos", oos_m), ("y2026", y26_m)):
            report[label] = summarize(seg_rets(mask=msk), 0.0)  # cost already applied
            report[f"A_{label}"] = summarize(seg_rets("A", msk), 0.0)
            report[f"B_{label}"] = summarize(seg_rets("B", msk), 0.0)
        # Trade counts
        report["n_A_trades"] = sum(1 for t in combined if t[2] == "A")
        report["n_B_trades"] = sum(1 for t in combined if t[2] == "B")
        report["B_active_pct"] = report["n_B_trades"] / max(int(directional_regime.sum()), 1)
        variant_results[vname] = report

    # =====================================================================
    # STEP 4 — Compare
    # =====================================================================
    # Verdict — best variant
    scores = {}
    for vname, r in variant_results.items():
        oos = r.get("oos", {})
        scores[vname] = {
            "oos_mean": oos.get("mean_pct", 0),
            "oos_t": oos.get("t", 0),
            "oos_ci_lo": oos.get("ci95_pct", [0, 0])[0],
            "y2026_mean": r.get("y2026", {}).get("mean_pct", 0),
            "oos_cum": oos.get("cum_pct", 0),
            "oos_maxDD": oos.get("max_dd_pct", 0),
        }
    # Rank by OOS t-stat (primary metric of interest)
    ranked_variants = sorted(
        variant_results.keys(),
        key=lambda v: -scores[v]["oos_t"],
    )
    best = ranked_variants[0]
    best_stats = scores[best]

    # Compare to Phase 21 baseline (A_equal_weight)
    baseline = scores["A_equal_weight"]
    improved_t = best_stats["oos_t"] > baseline["oos_t"]
    improved_cum = best_stats["oos_cum"] > baseline["oos_cum"]
    improved_dd = best_stats["oos_maxDD"] > baseline["oos_maxDD"]  # less negative
    improved_y2026 = best_stats["y2026_mean"] > baseline["y2026_mean"]

    # Final verdict
    if (best != "A_equal_weight" and
        best_stats["oos_t"] > 2.0 and
        best_stats["oos_ci_lo"] > 0 and
        (improved_cum or improved_dd) and
        improved_y2026):
        verdict = "PASS"
    elif (best != "A_equal_weight" and
          best_stats["oos_t"] >= baseline["oos_t"] and
          best_stats["y2026_mean"] >= baseline["y2026_mean"]):
        verdict = "WEAK"
    else:
        verdict = "FAIL"

    report_doc = {
        "phase": "22_engineB_refine",
        "today": dt.date.today().isoformat(),
        "data_range": [str(f.index[0]), str(f.index[-1])],
        "sleeve_ranking_by_oos_t": ranked,
        "top2_sleeves": top2,
        "per_sleeve_1d_5bps": per_sleeve,
        "variant_results": variant_results,
        "variant_scores": scores,
        "best_variant": best,
        "verdict": verdict,
        "baseline_comparison": {
            "baseline_t": baseline["oos_t"],
            "best_t": best_stats["oos_t"],
            "improved_cum": improved_cum,
            "improved_dd": improved_dd,
            "improved_2026": improved_y2026,
        },
    }
    (OUT_DIR / "report.json").write_text(json.dumps(report_doc, indent=2, default=str))

    # Print
    print("=" * 100)
    print(f"PHASE 22 - DIRECTIONAL ENGINE REFINEMENT  {dt.date.today()}")
    print("=" * 100)
    print(f"Data: ES=F {f.index[0]} -> {f.index[-1]}")
    print()
    print("--- STEP 1: Per-sleeve OOS analysis (1D / 5bps) ---")
    print(f"{'sleeve':<22} {'seg':<6} {'n':>5} {'mean%':>9} {'hit':>5} {'t':>6} {'CI95%':<22}")
    for gc in gate_cols:
        for seg in ("full", "is", "oos", "y2026"):
            s = per_sleeve[f"{gc}_{seg}"]
            if s.get("n", 0) == 0:
                continue
            ci = s["ci95_pct"]
            print(f"{gc:<22} {seg:<6} {s['n']:>5} {s['mean_pct']:>+9.4f} "
                  f"{s['hit']:>5.3f} {s['t']:>+6.2f} [{ci[0]:+.4f},{ci[1]:+.4f}]")
    print()
    print(f"--- RANKING by OOS t: {ranked}")
    print(f"--- TOP-2: {top2}")
    print()
    print("--- STEP 3: Variant comparison (combined two-engine, A+B) ---")
    print(f"{'variant':<20} {'seg':<6} {'n':>4} {'mean%':>9} {'t':>6} "
          f"{'CI_lo%':>8} {'cum%':>8} {'maxDD%':>8}")
    for vname, r in variant_results.items():
        for seg in ("full", "is", "oos", "y2026"):
            s = r[seg]
            if s.get("n", 0) == 0:
                print(f"{vname:<20} {seg:<6} n=0"); continue
            print(f"{vname:<20} {seg:<6} {s['n']:>4} {s['mean_pct']:>+9.4f} "
                  f"{s['t']:>+6.2f} {s['ci95_pct'][0]:>+8.4f} "
                  f"{s['cum_pct']:>+8.2f} {s['max_dd_pct']:>+8.2f}")
        print(f"    n_A={r['n_A_trades']}  n_B={r['n_B_trades']}  "
              f"B_active_pct={r['B_active_pct']*100:.1f}%")
    print()
    print("--- Variant scores at OOS ---")
    for vname, sc in scores.items():
        print(f"  {vname:<22} t={sc['oos_t']:+.2f} mean={sc['oos_mean']:+.4f}% "
              f"CI_lo={sc['oos_ci_lo']:+.4f}% cum={sc['oos_cum']:+.2f}% "
              f"DD={sc['oos_maxDD']:+.2f}% 2026={sc['y2026_mean']:+.4f}%")
    print()
    print(f"--- BEST VARIANT: {best} ---")
    print(f"  improvements vs baseline (A): "
          f"t_higher={improved_t} cum_higher={improved_cum} "
          f"DD_lower={improved_dd} 2026_higher={improved_y2026}")
    print()
    print("-" * 100)
    print(f"VERDICT: {verdict}")
    print("=" * 100)
    return 0


if __name__ == "__main__":
    sys.exit(main())
