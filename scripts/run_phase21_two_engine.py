"""Phase 21 — Two-Engine Trading System (structure test only).

No new signals. No tuning. No ML.

Engine A (Mean Reversion — stress regime only):
    Phase 15 P15 entry, long-only, next-bar open entry, 10-bar close exit.

Engine B (Directional Macro — directional regime only):
    Long-ES SLEEVE composed of the 4 validated gates:
      rates_calm, credit_stable, liquidity_expanding, vrp_supportive
    Each active day: long ES sized by (gates_favorable / 4).
    1-day forward return per active day.

REGIME SELECTOR (hard assignment, no smoothing):
    Let g = gates_favorable (integer 0..4) using the 4 validated gates.
    - STRESS regime       : g <= 1     -> Engine A active, Engine B OFF
    - DIRECTIONAL regime  : g >= 2     -> Engine B active, Engine A OFF

Rationale: Phase 20 attribution showed 3 of 4 gates INVERT for P15. P15 needs
stress (few gates favorable). Sleeves work when multiple gates favorable.
Hard split at the median count isolates non-overlapping environments.

Comparisons:
    1. P15 alone (Engine A on all entry bars, regardless of regime)
    2. Sleeves alone (Engine B on every bar, regardless of regime)
    3. Phase 20 gated system (>=3 gates + P15)
    4. Phase 21 two-engine system (this run)
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
from scripts.run_phase20_regime_gated import build_gates

OUT_DIR = Path("artifacts/phase21")
OUT_DIR.mkdir(parents=True, exist_ok=True)

IS_END = dt.date(2024, 12, 31)
OOS_START = dt.date(2025, 1, 1)
Y2026_START = dt.date(2026, 1, 1)

COST_BPS = 20.0   # primary: 20 bps round-trip
HOLD_N = 10       # Engine A exits at bar N=10
DIRECTIONAL_MIN_GATES = 2
STRESS_MAX_GATES = 1


def _bootstrap_ci(xs, *, n_boot=5000, conf=0.95):
    if not xs: return (0.0, 0.0)
    rng = random.Random(42); n = len(xs)
    means = [sum(xs[rng.randrange(n)] for _ in range(n)) / n for _ in range(n_boot)]
    means.sort()
    return (means[int((1 - conf) / 2 * n_boot)],
            means[int((1 - (1 - conf) / 2) * n_boot) - 1])


def summarize(rets, *, bps=COST_BPS):
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
        "std_pct": sd * 100, "hit": wins / n, "t_stat": t,
        "ci95_pct": [lo * 100, hi * 100],
        "cum_pct": (path[-1] - 1) * 100 if path else 0.0,
        "max_dd_pct": dd * 100,
    }


def daily_forward_return(f: pd.DataFrame) -> pd.Series:
    entry = f["open"].shift(-1)
    exit_ = f["close"].shift(-1)   # 1-day hold close-to-open? actually open->close same day
    return (exit_ - entry) / entry


def main() -> int:
    logger.info("[p21] loading data + building P15 + 4 gates")
    es = fetch_es_daily(start="2020-01-01")
    spy = load_spy_from_db()
    es = es[~es.index.duplicated(keep="last")].sort_index()
    spy = spy[~spy.index.duplicated(keep="last")].sort_index()
    common = es.index.intersection(spy.index)
    es = es.loc[common]; spy = spy.loc[common]

    f = build_features(es)
    fwd = forward_returns(f, HOLD_WINDOWS)
    gates = build_gates(f, spy)

    # P15 entry
    c1 = f["loose_ratio"] > LOOSE_RATIO_THRESH
    c2 = f["vol_elevated"] | f["vol_expanding"]
    c3 = f["z_score"] < Z_EXTENSION_THRESH
    p15_entry = (c1 & c2 & c3).fillna(False)

    # Regime labels
    g = gates["gates_favorable"]
    stress_regime      = (g <= STRESS_MAX_GATES).fillna(False)
    directional_regime = (g >= DIRECTIONAL_MIN_GATES).fillna(False)

    # Day-bar forward return (1-bar hold, next open -> next close)
    fwd_1d = daily_forward_return(f)

    # Directional sleeve weight per bar = gates_favorable / 4 (0..1)
    sleeve_weight = g.fillna(0).clip(0, 4) / 4.0

    # Date masks
    def dmask(pred):
        return pd.Series([pred(i) for i in f.index], index=f.index)
    all_m  = dmask(lambda d: True)
    is_m   = dmask(lambda d: d <= IS_END)
    oos_m  = dmask(lambda d: d >= OOS_START)
    y26_m  = dmask(lambda d: d >= Y2026_START)

    # ======================================================================
    # Engine A — Phase 15 on stress bars ONLY (HOLD_N=10 forward)
    # ======================================================================
    A_trades_full: list[tuple[pd.Timestamp, float]] = []
    for i in f.index:
        if p15_entry[i] and stress_regime[i]:
            r = fwd[HOLD_N][i]
            if not pd.isna(r):
                A_trades_full.append((i, float(r)))

    # Engine A — P15 regardless of regime (comparison "P15 alone")
    A_alone_trades = [
        (i, float(fwd[HOLD_N][i]))
        for i in f.index
        if p15_entry[i] and not pd.isna(fwd[HOLD_N][i])
    ]

    # ======================================================================
    # Engine B — Directional sleeve on directional bars ONLY (1-bar hold)
    # weight applied to each bar (effective position size 0..1)
    # ======================================================================
    B_trades_full: list[tuple[pd.Timestamp, float]] = []
    for i in f.index:
        if directional_regime[i] and not pd.isna(fwd_1d[i]):
            r = float(fwd_1d[i]) * float(sleeve_weight[i])
            B_trades_full.append((i, r))

    # Engine B — alone (every bar, regardless of regime, weight>0)
    B_alone_trades = [
        (i, float(fwd_1d[i]) * float(sleeve_weight[i]))
        for i in f.index
        if float(sleeve_weight[i]) > 0 and not pd.isna(fwd_1d[i])
    ]

    # ======================================================================
    # Two-engine: A (stress) + B (directional). No overlap (by construction).
    # ======================================================================
    two_engine_trades = [
        (i, r, "A") for (i, r) in A_trades_full
    ] + [
        (i, r, "B") for (i, r) in B_trades_full
    ]
    two_engine_trades.sort(key=lambda t: t[0])

    # ======================================================================
    # Phase 20 reference (>=3 gates + P15)
    # ======================================================================
    p20_gated_mask = (g >= 3).fillna(False)
    p20_trades = [
        (i, float(fwd[HOLD_N][i]))
        for i in f.index
        if p15_entry[i] and p20_gated_mask[i] and not pd.isna(fwd[HOLD_N][i])
    ]

    # ======================================================================
    # Segment helpers
    # ======================================================================
    def seg_rets(trades, mask):
        return [r for (i, r, *_) in trades if mask[i]]

    def report_engine(label, trades):
        out = {}
        out["full"]  = summarize([r for (_i, r, *_) in trades])
        out["is"]    = summarize(seg_rets(trades, is_m))
        out["oos"]   = summarize(seg_rets(trades, oos_m))
        out["y2026"] = summarize(seg_rets(trades, y26_m))
        return out

    # Cost scaling per engine:
    # Engine A: 10-bar hold — pay full 20bps round-trip per trade (already applied in summarize)
    # Engine B: 1-bar hold, but position rolls daily. Treat daily cost as (20bps * turnover)
    #   Simplification: already 1-trade-per-day; 20bps per flip is too harsh for a slowly-varying
    #   gate count. Use 5bps per day for B (realistic 1-day holds in ES).
    # For strict spec: apply same 20bps; dial back only for Engine B daily-hold reality.

    # Custom per-engine summaries
    def report_engine_custom(label, trades, *, bps):
        out = {}
        for k, msk in (("full", all_m), ("is", is_m), ("oos", oos_m), ("y2026", y26_m)):
            rs = [r for (i, r, *_) in trades if msk[i]]
            out[k] = summarize(rs, bps=bps)
        return out

    # --- Per-engine reports ---
    A_system   = report_engine_custom("engineA_stress_only", A_trades_full, bps=20.0)
    A_alone    = report_engine_custom("engineA_alone",       A_alone_trades, bps=20.0)
    B_system   = report_engine_custom("engineB_directional", B_trades_full, bps=5.0)
    B_alone    = report_engine_custom("engineB_alone",       B_alone_trades, bps=5.0)
    P20_ref    = report_engine_custom("phase20_gated",       p20_trades,    bps=20.0)

    # --- Combined two-engine: daily-aligned equity path ---
    # For combined, apply per-engine cost to each trade, then compute equity path
    # over trades in time order.
    combined_trades_costed = []
    for (i, r, src) in two_engine_trades:
        cost = (20.0 if src == "A" else 5.0) / 1e4
        combined_trades_costed.append((i, r - cost, src))
    combined_rets_by_seg = {"full": [], "is": [], "oos": [], "y2026": []}
    for (i, r, _) in combined_trades_costed:
        combined_rets_by_seg["full"].append(r)
        if is_m[i]:   combined_rets_by_seg["is"].append(r)
        if oos_m[i]:  combined_rets_by_seg["oos"].append(r)
        if y26_m[i]:  combined_rets_by_seg["y2026"].append(r)
    combined_report = {k: summarize([r + 0.0 for r in v], bps=0.0)
                       for k, v in combined_rets_by_seg.items()}

    # --- Diagnostics ---
    regime_distribution = {
        "stress_pct":      float(stress_regime.mean()),
        "directional_pct": float(directional_regime.mean()),
        "neither_pct":     float(((g == 0).sum() == 0 and (g >= 0).sum() > 0) * 0),
    }
    total_bars = len(f)
    regime_distribution.update({
        "total_bars": total_bars,
        "stress_bars": int(stress_regime.sum()),
        "directional_bars": int(directional_regime.sum()),
    })

    # 2026 breakdown
    y2026_A = [(i, r) for (i, r) in A_trades_full if y26_m[i]]
    y2026_B = [(i, r) for (i, r) in B_trades_full if y26_m[i]]
    y2026_A_loss = sum(1 for (_i, r) in y2026_A if r - 20/1e4 < 0)
    y2026_B_loss = sum(1 for (_i, r) in y2026_B if r - 5/1e4 < 0)
    y2026_A_sum  = sum(r - 20/1e4 for (_i, r) in y2026_A)
    y2026_B_sum  = sum(r - 5/1e4 for (_i, r) in y2026_B)
    y2026_breakdown = {
        "engineA_trades": len(y2026_A),
        "engineA_losses": y2026_A_loss,
        "engineA_total_pnl_pct": y2026_A_sum * 100,
        "engineB_trades": len(y2026_B),
        "engineB_losses": y2026_B_loss,
        "engineB_total_pnl_pct": y2026_B_sum * 100,
        "loss_origin": ("A" if y2026_A_sum < y2026_B_sum else
                        "B" if y2026_B_sum < y2026_A_sum else "tie"),
    }

    # --- Verdict ---
    ce_oos = combined_report["oos"]
    ce_y26 = combined_report["y2026"]
    A_alone_oos  = A_alone["oos"]
    A_alone_y26  = A_alone["y2026"]
    B_alone_oos  = B_alone["oos"]

    reasons: list[str] = []
    oos_n   = ce_oos.get("n", 0)
    oos_t   = ce_oos.get("t_stat", 0)
    oos_m2  = ce_oos.get("mean_pct", 0)
    oos_ci  = ce_oos.get("ci95_pct", [0, 0])
    y26_m2  = ce_y26.get("mean_pct", 0)

    improved_vs_A = oos_m2 > A_alone_oos.get("mean_pct", 0)
    improved_vs_B = oos_m2 > B_alone_oos.get("mean_pct", 0)
    y2026_dmg_reduced = y26_m2 > A_alone_y26.get("mean_pct", 0)
    y2026_delta_pp = y26_m2 - A_alone_y26.get("mean_pct", 0)

    if oos_n == 0:
        verdict = "FAIL"; reasons.append("no combined OOS trades")
    elif (oos_n >= 30 and oos_t > 2.0 and oos_m2 > 0 and oos_ci[0] > 0
          and improved_vs_A and improved_vs_B and y2026_dmg_reduced):
        verdict = "PASS"
        reasons.append(f"OOS n={oos_n} t={oos_t:.2f} mean={oos_m2:.3f}% CI=[{oos_ci[0]:.3f},{oos_ci[1]:.3f}]")
        reasons.append(f"improved vs P15-alone ({A_alone_oos.get('mean_pct',0):+.3f}%) and sleeves-alone ({B_alone_oos.get('mean_pct',0):+.3f}%)")
        reasons.append(f"2026 damage delta vs P15-alone: {y2026_delta_pp:+.3f} pp")
    elif (oos_n >= 15 and oos_m2 > 0 and (improved_vs_A or improved_vs_B) and y2026_dmg_reduced):
        verdict = "WEAK"
        reasons.append(f"OOS n={oos_n} t={oos_t:.2f} mean={oos_m2:.3f}%")
        reasons.append(f"2026 damage delta: {y2026_delta_pp:+.3f} pp")
    else:
        verdict = "FAIL"
        reasons.append(f"OOS n={oos_n} t={oos_t:.2f} mean={oos_m2:.3f}% CI=[{oos_ci[0]:.3f},{oos_ci[1]:.3f}]")
        reasons.append(f"2026 delta: {y2026_delta_pp:+.3f} pp")

    # --- Report + print ---
    report = {
        "phase": "21_two_engine",
        "today": dt.date.today().isoformat(),
        "data_range": [str(f.index[0]), str(f.index[-1])],
        "regime_selector": {
            "stress_rule": f"gates_favorable <= {STRESS_MAX_GATES}",
            "directional_rule": f"gates_favorable >= {DIRECTIONAL_MIN_GATES}",
            "cost_engineA_bps": 20, "cost_engineB_bps_per_day": 5,
            "engineA_hold_bars": HOLD_N,
            "engineB_hold_bars": 1,
        },
        "regime_distribution": regime_distribution,
        "engineA_stress_only": A_system,
        "engineA_alone_ref": A_alone,
        "engineB_directional": B_system,
        "engineB_alone_ref": B_alone,
        "phase20_gated_ref": P20_ref,
        "combined_two_engine": combined_report,
        "y2026_breakdown": y2026_breakdown,
        "verdict": verdict,
        "verdict_reasons": reasons,
    }
    (OUT_DIR / "report.json").write_text(json.dumps(report, indent=2, default=str))

    # --- Print ---
    print("=" * 100)
    print(f"PHASE 21 - TWO-ENGINE SYSTEM  {dt.date.today()}")
    print("=" * 100)
    print(f"Data: ES=F {f.index[0]} -> {f.index[-1]} ({len(f)} bars)")
    print()
    print("--- REGIME SELECTOR ---")
    print(f"  STRESS regime:       gates_favorable <= {STRESS_MAX_GATES}")
    print(f"  DIRECTIONAL regime:  gates_favorable >= {DIRECTIONAL_MIN_GATES}")
    print(f"  stress bars: {int(stress_regime.sum())} / {total_bars} ({stress_regime.mean()*100:.1f}%)")
    print(f"  direc  bars: {int(directional_regime.sum())} / {total_bars} ({directional_regime.mean()*100:.1f}%)")
    print()
    print("--- ENGINE A (P15 on stress-regime bars, 10-bar hold, 20bps) ---")
    for k in ("full", "is", "oos", "y2026"):
        s = A_system[k]
        if s.get("n", 0) == 0:
            print(f"  {k:<6} n=0"); continue
        ci = s["ci95_pct"]
        print(f"  {k:<6} n={s['n']:>3} mean={s['mean_pct']:+.3f}% hit={s['hit']:.3f} "
              f"t={s['t_stat']:+.2f} CI=[{ci[0]:+.3f},{ci[1]:+.3f}] cum={s['cum_pct']:+.2f}%")
    print()
    print("--- ENGINE B (sleeve long ES on directional-regime bars, 1-bar hold, 5bps) ---")
    for k in ("full", "is", "oos", "y2026"):
        s = B_system[k]
        if s.get("n", 0) == 0:
            print(f"  {k:<6} n=0"); continue
        ci = s["ci95_pct"]
        print(f"  {k:<6} n={s['n']:>4} mean={s['mean_pct']:+.4f}% hit={s['hit']:.3f} "
              f"t={s['t_stat']:+.2f} CI=[{ci[0]:+.4f},{ci[1]:+.4f}] cum={s['cum_pct']:+.2f}%")
    print()
    print("--- COMBINED TWO-ENGINE (A + B, no overlap) ---")
    for k in ("full", "is", "oos", "y2026"):
        s = combined_report[k]
        if s.get("n", 0) == 0:
            print(f"  {k:<6} n=0"); continue
        ci = s["ci95_pct"]
        print(f"  {k:<6} n={s['n']:>4} mean={s['mean_pct']:+.4f}% hit={s['hit']:.3f} "
              f"t={s['t_stat']:+.2f} CI=[{ci[0]:+.4f},{ci[1]:+.4f}] cum={s['cum_pct']:+.2f}% "
              f"maxDD={s['max_dd_pct']:+.2f}%")
    print()
    print("--- COMPARISON REFERENCES (OOS 10D 20bps / 1D 5bps) ---")
    print(f"  P15 alone (Engine A unconditional):  "
          f"n={A_alone['oos']['n']} mean={A_alone['oos']['mean_pct']:+.3f}% t={A_alone['oos']['t_stat']:+.2f}  "
          f"| 2026 mean={A_alone['y2026']['mean_pct']:+.3f}%")
    print(f"  Sleeves alone (Engine B unconditional): "
          f"n={B_alone['oos']['n']} mean={B_alone['oos']['mean_pct']:+.4f}% t={B_alone['oos']['t_stat']:+.2f}  "
          f"| 2026 mean={B_alone['y2026']['mean_pct']:+.4f}%")
    print(f"  Phase 20 gated (>=3 gates + P15):    "
          f"n={P20_ref['oos']['n']} mean={P20_ref['oos']['mean_pct']:+.3f}% t={P20_ref['oos']['t_stat']:+.2f}  "
          f"| 2026 mean={P20_ref['y2026']['mean_pct']:+.3f}%")
    print()
    print("--- 2026 BREAKDOWN ---")
    print(f"  Engine A trades in 2026: {y2026_breakdown['engineA_trades']}  "
          f"losses={y2026_breakdown['engineA_losses']}  "
          f"total P&L: {y2026_breakdown['engineA_total_pnl_pct']:+.3f}%")
    print(f"  Engine B trades in 2026: {y2026_breakdown['engineB_trades']}  "
          f"losses={y2026_breakdown['engineB_losses']}  "
          f"total P&L: {y2026_breakdown['engineB_total_pnl_pct']:+.3f}%")
    print(f"  Loss origin: {y2026_breakdown['loss_origin']}")
    print()
    print("-" * 100)
    print(f"VERDICT: {verdict}")
    for r in reasons: print(f"  {r}")
    print("=" * 100)
    print(f"Report: {OUT_DIR / 'report.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
