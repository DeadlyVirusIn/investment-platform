"""Phase X2 — Engine C (VIX Term Structure Overlay).

No changes to Engine A or Engine B.
No tuning.

Overlay definition:
  ts_ratio = VIX / VIX3M
  BACKWARDATION: ts_ratio > 1
  CONTANGO:      ts_ratio <= 1

Rule:
  When BACKWARDATION at decision bar: SKIP Engine A entry.
  Engine B: unchanged.

Compare vs Phase 23 baseline.
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
import yfinance as yf
from loguru import logger

from scripts.run_phase12_price_action import fetch_es_daily, load_spy_from_db, HOLD_WINDOWS
from scripts.run_phase15_mean_reversion import (
    build_features, forward_returns,
    LOOSE_RATIO_THRESH, Z_EXTENSION_THRESH,
)
from scripts.run_phase20_regime_gated import build_gates

OUT_DIR = Path("artifacts/phase25x2")
OUT_DIR.mkdir(parents=True, exist_ok=True)
CACHE = OUT_DIR / "vix3m.csv"

HOLD_A = 10
COST_A_BPS = 20.0
COST_B_BPS = 5.0


def fetch_vix_pair() -> pd.DataFrame:
    if CACHE.exists():
        df = pd.read_csv(CACHE, index_col=0)
        df.index = [dt.date.fromisoformat(i) for i in df.index]
        return df
    out = {}
    for sym in ("^VIX", "^VIX3M"):
        t = yf.Ticker(sym)
        h = t.history(start="2020-01-01", interval="1d", auto_adjust=False)
        s = h["Close"].copy()
        s.index = [i.date() for i in s.index]
        s = s[~s.index.duplicated(keep="last")]
        out[sym] = s
    df = pd.DataFrame(out).sort_index()
    df.to_csv(CACHE)
    return df


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


def build_trades(f, fwd, p15_entry, stress, directional, gates, backward, *,
                 apply_backward_skip_A):
    cs = gates["credit_stable"].fillna(False)
    rc = gates["rates_calm"].fillna(False)
    b_active = cs & rc
    entry_1d = f["open"].shift(-1)
    exit_1d = f["close"].shift(-1)
    fwd_1d = (exit_1d - entry_1d) / entry_1d
    trades = []
    for i in f.index:
        if p15_entry[i] and stress[i]:
            if apply_backward_skip_A and backward[i]:
                continue
            r = fwd[HOLD_A][i]
            if not pd.isna(r):
                trades.append((i, float(r) - COST_A_BPS / 1e4, "A"))
        if directional[i] and b_active[i]:
            r = fwd_1d[i]
            if not pd.isna(r):
                trades.append((i, float(r) - COST_B_BPS / 1e4, "B"))
    trades.sort(key=lambda t: t[0])
    return trades


def main() -> int:
    logger.info("[p25x2] loading data + fetching VIX pair")
    es = fetch_es_daily(start="2020-01-01")
    spy = load_spy_from_db()
    es = es[~es.index.duplicated(keep="last")].sort_index()
    spy = spy[~spy.index.duplicated(keep="last")].sort_index()
    common = es.index.intersection(spy.index)
    es = es.loc[common]; spy = spy.loc[common]
    f = build_features(es)
    fwd = forward_returns(f, HOLD_WINDOWS)
    gates = build_gates(f, spy)

    vix_pair = fetch_vix_pair()
    vix = vix_pair["^VIX"].reindex(f.index).ffill()
    vix3m = vix_pair["^VIX3M"].reindex(f.index).ffill()
    ts_ratio = vix / vix3m
    backward = (ts_ratio > 1).fillna(False)
    logger.info("[p25x2] backwardation {:.1f}% of bars  (VIX>VIX3M)", backward.mean() * 100)

    c1 = f["loose_ratio"] > LOOSE_RATIO_THRESH
    c2 = f["vol_elevated"] | f["vol_expanding"]
    c3 = f["z_score"] < Z_EXTENSION_THRESH
    p15_entry = (c1 & c2 & c3).fillna(False)
    stress = (gates["gates_favorable"] <= 1).fillna(False)
    directional = (gates["gates_favorable"] >= 2).fillna(False)

    # Entries falling in backwardation
    p15_in_back = int((p15_entry & backward).sum())
    p15_total = int(p15_entry.sum())
    logger.info("[p25x2] P15 entries in backwardation: {}/{} ({:.1f}%)",
                p15_in_back, p15_total, 100 * p15_in_back / max(p15_total, 1))

    baseline_trades = build_trades(
        f, fwd, p15_entry, stress, directional, gates, backward,
        apply_backward_skip_A=False,
    )
    overlay_trades = build_trades(
        f, fwd, p15_entry, stress, directional, gates, backward,
        apply_backward_skip_A=True,
    )

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
            "A_y2026": summarize(seg_rets(trades, y26_m, src="A")),
            "n_A": sum(1 for t in trades if t[2] == "A"),
            "n_B": sum(1 for t in trades if t[2] == "B"),
        }

    baseline = report_system(baseline_trades)
    overlay  = report_system(overlay_trades)

    # Audit the skipped A trades
    skipped = []
    for i in f.index:
        if p15_entry[i] and stress[i] and backward[i]:
            r = fwd[HOLD_A][i]
            if not pd.isna(r):
                skipped.append((i, float(r) - COST_A_BPS / 1e4))
    skipped_stats = summarize([r for (_i, r) in skipped])

    # Verdict
    b_oos = baseline["oos"]; o_oos = overlay["oos"]
    b_y26 = baseline["y2026"]; o_y26 = overlay["y2026"]
    b_full = baseline["full"]; o_full = overlay["full"]

    dd_improve_oos = (o_oos.get("max_dd_pct", 0) - b_oos.get("max_dd_pct", 0)) >= 2.0
    dd_improve_full = (o_full.get("max_dd_pct", 0) - b_full.get("max_dd_pct", 0)) >= 2.0
    t_improve = o_oos.get("t_stat", 0) > b_oos.get("t_stat", 0)
    y26_improve = o_y26.get("mean_pct", 0) > b_y26.get("mean_pct", 0)
    oos_not_degraded = o_oos.get("mean_pct", 0) >= (b_oos.get("mean_pct", 0) - 0.05)
    full_cum_not_degraded = o_full.get("cum_pct", 0) >= (b_full.get("cum_pct", 0) - 5.0)

    reasons: list[str] = []
    if ((dd_improve_oos or dd_improve_full) and t_improve and oos_not_degraded and y26_improve):
        verdict = "PASS"
        reasons.append(f"maxDD improved + t+ + 2026+")
    elif (dd_improve_oos or y26_improve) and oos_not_degraded and full_cum_not_degraded:
        verdict = "WEAK"
        reasons.append(f"partial: dd_oos_imp={dd_improve_oos} y26_imp={y26_improve} "
                       f"oos_ok={oos_not_degraded} cum_ok={full_cum_not_degraded}")
    else:
        verdict = "FAIL"
        reasons.append(f"no meaningful improvement / degradation")

    report = {
        "phase": "25x2_vix_term_overlay",
        "today": dt.date.today().isoformat(),
        "data_range": [str(f.index[0]), str(f.index[-1])],
        "overlay_rule": "skip Engine A when VIX/VIX3M > 1 (backwardation)",
        "backwardation_pct_of_bars": float(backward.mean()),
        "p15_entries_in_backwardation": p15_in_back,
        "p15_total_entries": p15_total,
        "skipped_A_stats": skipped_stats,
        "baseline": baseline,
        "overlay": overlay,
        "verdict": verdict,
        "verdict_reasons": reasons,
    }
    (OUT_DIR / "report.json").write_text(json.dumps(report, indent=2, default=str))

    # Print
    print("=" * 100)
    print(f"PHASE X2 - VIX TERM STRUCTURE OVERLAY  {dt.date.today()}")
    print("=" * 100)
    print(f"Data: ES=F {f.index[0]} -> {f.index[-1]} ({len(f)} bars)")
    print(f"Backwardation (VIX/VIX3M > 1): {backward.mean()*100:.1f}% of bars")
    print(f"P15 entries in backwardation: {p15_in_back}/{p15_total} "
          f"({100*p15_in_back/max(p15_total,1):.1f}%)")
    print()
    print("--- SKIPPED A TRADES (Engine C removes these) ---")
    if skipped_stats.get("n", 0) > 0:
        s = skipped_stats
        ci = s["ci95_pct"]
        print(f"  n={s['n']} mean={s['mean_pct']:+.4f}% t={s['t_stat']:+.2f} "
              f"CI=[{ci[0]:+.4f},{ci[1]:+.4f}] cum={s['cum_pct']:+.2f}% "
              f"maxDD={s['max_dd_pct']:+.2f}%")
    else:
        print("  n=0")
    print()
    for lbl, rep in (("BASELINE (Phase 23)", baseline), ("OVERLAY (Engine C VIX-term)", overlay)):
        print(f"--- {lbl} ---")
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
    print("--- HEAD-TO-HEAD (OOS) ---")
    for k, lab in [("mean_pct", "mean%"), ("t_stat", "t"),
                   ("cum_pct", "cum%"), ("max_dd_pct", "maxDD%"),
                   ("hit", "hit")]:
        b = baseline["oos"].get(k, 0); o = overlay["oos"].get(k, 0)
        print(f"  {lab:<14} {b:>+12.4f} {o:>+12.4f} delta={o-b:>+9.4f}")
    print()
    print("--- HEAD-TO-HEAD (2026 YTD) ---")
    for k, lab in [("mean_pct", "mean%"), ("t_stat", "t"),
                   ("cum_pct", "cum%"), ("max_dd_pct", "maxDD%")]:
        b = baseline["y2026"].get(k, 0); o = overlay["y2026"].get(k, 0)
        print(f"  {lab:<14} {b:>+12.4f} {o:>+12.4f} delta={o-b:>+9.4f}")
    print()
    print("-" * 100)
    print(f"VERDICT: {verdict}")
    for r in reasons: print(f"  {r}")
    print("=" * 100)
    return 0


if __name__ == "__main__":
    sys.exit(main())
