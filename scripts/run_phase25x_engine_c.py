"""Phase X — Engine C (Flow / Persistence Overlay).

No changes to Engine A or B.
No new data sources.
Only uses recent return persistence + vol behavior.

FLOW regime detector (deterministic):
  sign_sum_5 = sum(sign(daily_return_{t-4..t-0}))   # range [-5, +5]
  vol_stable = atr20_t < 1.5 * atr50_t              # not chaotic blow-up
  flow_regime = (|sign_sum_5| >= 3) AND vol_stable

When flow_regime AND P15 would fire: SKIP Engine A entry.
Engine B: unchanged.

Compare vs Phase 23 baseline (frozen system).
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

OUT_DIR = Path("artifacts/phase25x")
OUT_DIR.mkdir(parents=True, exist_ok=True)

HOLD_A = 10
COST_A_BPS = 20.0
COST_B_BPS = 5.0
SIGN_SUM_THRESH = 3
VOL_STABLE_RATIO = 1.5


def _bootstrap_ci(xs, n_boot=5000, conf=0.95):
    if not xs: return (0.0, 0.0)
    rng = random.Random(42); n = len(xs)
    means = [sum(xs[rng.randrange(n)] for _ in range(n)) / n for _ in range(n_boot)]
    means.sort()
    return (means[int((1 - conf) / 2 * n_boot)],
            means[int((1 - (1 - conf) / 2) * n_boot) - 1])


def summarize(rets):
    if not rets: return {"n": 0}
    n = len(rets); mean = st.mean(rets); med = st.median(rets)
    sd = st.pstdev(rets) if n > 1 else 0.0
    wins = sum(1 for r in rets if r > 0)
    t = mean / (sd / math.sqrt(n)) if sd > 0 else 0.0
    lo, hi = _bootstrap_ci(rets)
    eq = 1.0; path = []
    for r in rets:
        eq *= (1 + r); path.append(eq)
    pk = path[0] if path else 1.0; dd = 0.0
    for v in path:
        pk = max(pk, v); dd = min(dd, (v - pk) / pk)
    return {
        "n": n, "mean_pct": mean * 100, "median_pct": med * 100,
        "hit": wins / n, "t_stat": t,
        "ci95_pct": [lo * 100, hi * 100],
        "cum_pct": (path[-1] - 1) * 100 if path else 0.0,
        "max_dd_pct": dd * 100,
    }


def dmask(idx, pred):
    return pd.Series([pred(i) for i in idx], index=idx)


def build_flow_regime(f: pd.DataFrame) -> pd.Series:
    ret1 = f["close"].pct_change()
    sign_series = ret1.apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
    sign_sum_5 = sign_series.rolling(5).sum()
    # atr20 and atr50 already built by build_features via tr rolling means
    # rebuild if missing
    if "atr50" not in f.columns:
        tr = f["tr"]
        f["atr50"] = tr.rolling(50).mean()
    vol_stable = f["atr20"] < VOL_STABLE_RATIO * f["atr50"]
    persistent = sign_sum_5.abs() >= SIGN_SUM_THRESH
    flow = (persistent & vol_stable).fillna(False)
    return flow


def build_trades(f, fwd, p15_entry, stress, directional, gates, flow, *,
                 apply_flow_skip_A):
    """Build A+B trades. If apply_flow_skip_A=True, skip Engine A on flow bars."""
    cs = gates["credit_stable"].fillna(False)
    rc = gates["rates_calm"].fillna(False)
    b_active = cs & rc
    entry_1d = f["open"].shift(-1)
    exit_1d = f["close"].shift(-1)
    fwd_1d = (exit_1d - entry_1d) / entry_1d

    trades = []
    for i in f.index:
        # Engine A
        if p15_entry[i] and stress[i]:
            if apply_flow_skip_A and flow[i]:
                continue   # skip per Engine C overlay
            r = fwd[HOLD_A][i]
            if not pd.isna(r):
                trades.append((i, float(r) - COST_A_BPS / 1e4, "A"))
        # Engine B — unchanged regardless of flow
        if directional[i] and b_active[i]:
            r = fwd_1d[i]
            if not pd.isna(r):
                trades.append((i, float(r) - COST_B_BPS / 1e4, "B"))
    trades.sort(key=lambda t: t[0])
    return trades


def main() -> int:
    logger.info("[p25x] loading data + building features")
    es = fetch_es_daily(start="2020-01-01")
    spy = load_spy_from_db()
    es = es[~es.index.duplicated(keep="last")].sort_index()
    spy = spy[~spy.index.duplicated(keep="last")].sort_index()
    common = es.index.intersection(spy.index)
    es = es.loc[common]; spy = spy.loc[common]
    f = build_features(es)
    fwd = forward_returns(f, HOLD_WINDOWS)
    gates = build_gates(f, spy)

    c1 = f["loose_ratio"] > LOOSE_RATIO_THRESH
    c2 = f["vol_elevated"] | f["vol_expanding"]
    c3 = f["z_score"] < Z_EXTENSION_THRESH
    p15_entry = (c1 & c2 & c3).fillna(False)
    stress = (gates["gates_favorable"] <= 1).fillna(False)
    directional = (gates["gates_favorable"] >= 2).fillna(False)

    # Engine C — flow regime
    flow = build_flow_regime(f)
    logger.info("[p25x] flow regime: {}% of bars", f"{flow.mean()*100:.1f}")

    # P15 entries and how many fall in flow regime
    p15_in_flow = int((p15_entry & flow).sum())
    p15_total = int(p15_entry.sum())
    logger.info("[p25x] P15 entries in flow regime: {}/{} ({:.1f}%)",
                p15_in_flow, p15_total, 100 * p15_in_flow / max(p15_total, 1))

    # Baseline trades (Phase 23 system, no Engine C)
    baseline_trades = build_trades(
        f, fwd, p15_entry, stress, directional, gates, flow,
        apply_flow_skip_A=False,
    )
    # With Engine C overlay: skip Engine A on flow bars
    overlay_trades = build_trades(
        f, fwd, p15_entry, stress, directional, gates, flow,
        apply_flow_skip_A=True,
    )

    # Date masks
    is_m  = dmask(f.index, lambda d: d <= dt.date(2024, 12, 31))
    oos_m = dmask(f.index, lambda d: d >= dt.date(2025, 1, 1))
    y26_m = dmask(f.index, lambda d: d >= dt.date(2026, 1, 1))

    def seg_rets(trades, msk=None, src=None):
        out = []
        for (i, r, s) in trades:
            if src and s != src: continue
            if msk is not None and not msk[i]: continue
            out.append(r)
        return out

    def report_system(trades):
        return {
            "full":   summarize(seg_rets(trades)),
            "is":     summarize(seg_rets(trades, is_m)),
            "oos":    summarize(seg_rets(trades, oos_m)),
            "y2026":  summarize(seg_rets(trades, y26_m)),
            "A_full": summarize(seg_rets(trades, src="A")),
            "A_oos":  summarize(seg_rets(trades, oos_m, src="A")),
            "A_y2026": summarize(seg_rets(trades, y26_m, src="A")),
            "B_full": summarize(seg_rets(trades, src="B")),
            "B_oos":  summarize(seg_rets(trades, oos_m, src="B")),
            "B_y2026": summarize(seg_rets(trades, y26_m, src="B")),
            "n_A": sum(1 for t in trades if t[2] == "A"),
            "n_B": sum(1 for t in trades if t[2] == "B"),
        }

    baseline = report_system(baseline_trades)
    overlay  = report_system(overlay_trades)

    # Skipped-A-trade audit (what we avoided)
    skipped_A = []
    for i in f.index:
        if p15_entry[i] and stress[i] and flow[i]:
            r = fwd[HOLD_A][i]
            if not pd.isna(r):
                skipped_A.append((i, float(r) - COST_A_BPS / 1e4))
    skipped_stats = summarize([r for (_i, r) in skipped_A])

    # Verdict
    # PASS if overlay reduces maxDD >= 2pp or improves t-stat AND preserves OOS mean within tolerance
    b_oos = baseline["oos"]; o_oos = overlay["oos"]
    b_y26 = baseline["y2026"]; o_y26 = overlay["y2026"]
    b_full = baseline["full"]; o_full = overlay["full"]

    dd_improve = (o_oos.get("max_dd_pct", 0) - b_oos.get("max_dd_pct", 0)) >= 2.0  # less-negative
    dd_improve_full = (o_full.get("max_dd_pct", 0) - b_full.get("max_dd_pct", 0)) >= 2.0
    t_improve = o_oos.get("t_stat", 0) > b_oos.get("t_stat", 0)
    y26_improve = o_y26.get("mean_pct", 0) >= b_y26.get("mean_pct", 0)
    oos_not_degraded = o_oos.get("mean_pct", 0) >= (b_oos.get("mean_pct", 0) - 0.05)
    full_cum_not_degraded = o_full.get("cum_pct", 0) >= b_full.get("cum_pct", 0) - 5.0

    reasons: list[str] = []
    if ((dd_improve or dd_improve_full) and t_improve
        and oos_not_degraded and y26_improve):
        verdict = "PASS"
        reasons.append(f"maxDD improved (OOS: {b_oos.get('max_dd_pct',0):+.2f}% -> "
                       f"{o_oos.get('max_dd_pct',0):+.2f}%)")
        reasons.append(f"t-stat improved (OOS: {b_oos.get('t_stat',0):+.2f} -> "
                       f"{o_oos.get('t_stat',0):+.2f})")
    elif (dd_improve or dd_improve_full or t_improve) and oos_not_degraded and full_cum_not_degraded:
        verdict = "WEAK"
        reasons.append(f"partial improvement: "
                       f"dd_imp={dd_improve or dd_improve_full} "
                       f"t_imp={t_improve}")
    else:
        verdict = "FAIL"
        reasons.append(f"no meaningful improvement")
        reasons.append(f"OOS mean {b_oos.get('mean_pct',0):+.4f} -> {o_oos.get('mean_pct',0):+.4f}")
        reasons.append(f"OOS DD {b_oos.get('max_dd_pct',0):+.2f} -> {o_oos.get('max_dd_pct',0):+.2f}")

    report = {
        "phase": "25x_engine_c_flow_overlay",
        "today": dt.date.today().isoformat(),
        "data_range": [str(f.index[0]), str(f.index[-1])],
        "flow_regime_params": {
            "sign_sum_threshold": SIGN_SUM_THRESH,
            "vol_stable_ratio": VOL_STABLE_RATIO,
        },
        "flow_pct_of_bars": float(flow.mean()),
        "p15_in_flow": p15_in_flow,
        "p15_total": p15_total,
        "skipped_A_stats": skipped_stats,
        "baseline": baseline,
        "overlay": overlay,
        "verdict": verdict,
        "verdict_reasons": reasons,
    }
    (OUT_DIR / "report.json").write_text(json.dumps(report, indent=2, default=str))

    # Print
    print("=" * 100)
    print(f"PHASE X - ENGINE C FLOW/PERSISTENCE OVERLAY  {dt.date.today()}")
    print("=" * 100)
    print(f"Data: ES=F {f.index[0]} -> {f.index[-1]} ({len(f)} bars)")
    print(f"Flow regime definition: |sign_sum_5| >= {SIGN_SUM_THRESH} AND ATR20 < {VOL_STABLE_RATIO} * ATR50")
    print(f"Flow regime occupies {flow.mean()*100:.1f}% of bars")
    print(f"P15 entries falling in flow regime: {p15_in_flow}/{p15_total} "
          f"({100*p15_in_flow/max(p15_total,1):.1f}%)")
    print()
    print("--- SKIPPED A TRADES (would-have-taken, now skipped) ---")
    if skipped_stats.get("n", 0) > 0:
        s = skipped_stats
        ci = s["ci95_pct"]
        print(f"  n={s['n']} mean={s['mean_pct']:+.4f}% t={s['t_stat']:+.2f} "
              f"CI=[{ci[0]:+.4f},{ci[1]:+.4f}] cum={s['cum_pct']:+.2f}% "
              f"maxDD={s['max_dd_pct']:+.2f}%")
    else:
        print("  n=0  (no A trades in flow regime)")
    print()

    for label, rep in (("BASELINE (Phase 23)", baseline), ("OVERLAY (Engine C)", overlay)):
        print(f"--- {label} ---")
        print(f"  A trades: {rep['n_A']}  B trades: {rep['n_B']}")
        for seg in ("full", "is", "oos", "y2026"):
            s = rep[seg]
            if s.get("n", 0) == 0:
                print(f"  {seg:<6} n=0"); continue
            ci = s["ci95_pct"]
            print(f"  {seg:<6} n={s['n']:>4} mean={s['mean_pct']:>+9.4f}% "
                  f"t={s['t_stat']:>+6.2f} CI=[{ci[0]:+.4f},{ci[1]:+.4f}] "
                  f"cum={s['cum_pct']:>+7.2f}% DD={s['max_dd_pct']:>+6.2f}%")
        print()

    # Side-by-side comparison for key metrics
    print("--- HEAD-TO-HEAD (OOS) ---")
    print(f"{'metric':<14} {'baseline':>12} {'overlay':>12} {'delta':>10}")
    for k, lab in [("mean_pct", "mean%"), ("t_stat", "t"),
                   ("cum_pct", "cum%"), ("max_dd_pct", "maxDD%"),
                   ("hit", "hit")]:
        b = baseline["oos"].get(k, 0); o = overlay["oos"].get(k, 0)
        print(f"  {lab:<14} {b:>+12.4f} {o:>+12.4f} {o - b:>+10.4f}")
    print()
    print("--- HEAD-TO-HEAD (2026 YTD) ---")
    for k, lab in [("mean_pct", "mean%"), ("t_stat", "t"),
                   ("cum_pct", "cum%"), ("max_dd_pct", "maxDD%")]:
        b = baseline["y2026"].get(k, 0); o = overlay["y2026"].get(k, 0)
        print(f"  {lab:<14} {b:>+12.4f} {o:>+12.4f} {o - b:>+10.4f}")
    print()
    print("-" * 100)
    print(f"VERDICT: {verdict}")
    for r in reasons: print(f"  {r}")
    print("=" * 100)
    print(f"Report: {OUT_DIR / 'report.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
