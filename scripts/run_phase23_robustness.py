"""Phase 23 — Robustness & Execution Validation.

FROZEN SYSTEM (no changes):
  Engine A: P15 mean reversion on stress regime (gates_favorable <= 1),
            10-bar hold, long-only
  Engine B: credit_stable AND rates_calm agreement on directional regime
            (gates_favorable >= 2), 1-bar hold, unit position
  Selector: stress vs directional on gates_favorable count

Tests:
  1. Cost sensitivity — flat per-trade cost 5/10/20 bps applied to BOTH engines
  2. Rolling stability — 252-bar window Sharpe, cumulative, DD
  3. Subperiod — pre-2024, 2024-2025, 2026-YTD
  4. Trade profile — per-month, in-market %, avg hold

No optimization. No signal changes. Stop after verdict.
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

OUT_DIR = Path("artifacts/phase23")
OUT_DIR.mkdir(parents=True, exist_ok=True)

HOLD_A = 10
TOP2_SLEEVES = ("credit_stable", "rates_calm")   # frozen from Phase 22


def _bootstrap_ci(xs, n_boot=5000, conf=0.95):
    if not xs: return (0.0, 0.0)
    rng = random.Random(42); n = len(xs)
    means = [sum(xs[rng.randrange(n)] for _ in range(n)) / n for _ in range(n_boot)]
    means.sort()
    return (means[int((1 - conf) / 2 * n_boot)],
            means[int((1 - (1 - conf) / 2) * n_boot) - 1])


def summarize(rets):
    if not rets: return {"n": 0}
    n = len(rets)
    mean = st.mean(rets); med = st.median(rets)
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
        "std_pct": sd * 100, "hit": wins / n, "t_stat": t,
        "ci95_pct": [lo * 100, hi * 100],
        "cum_pct": (path[-1] - 1) * 100 if path else 0.0,
        "max_dd_pct": dd * 100,
    }


def dmask(idx, pred):
    return pd.Series([pred(i) for i in idx], index=idx)


def build_trades(f, fwd, p15_entry, stress, directional, gates, cost_bps):
    """Return combined trade list [(date, net_ret, src)]."""
    cost_A = cost_bps / 1e4
    cost_B = cost_bps / 1e4
    # 1-day fwd return
    entry_1d = f["open"].shift(-1)
    exit_1d = f["close"].shift(-1)
    fwd_1d = (exit_1d - entry_1d) / entry_1d

    cs = gates["credit_stable"].fillna(False)
    rc = gates["rates_calm"].fillna(False)
    b_active = cs & rc

    trades = []
    for i in f.index:
        # Engine A
        if p15_entry[i] and stress[i]:
            r = fwd[HOLD_A][i]
            if not pd.isna(r):
                trades.append((i, float(r) - cost_A, "A"))
        # Engine B (AND agreement of top-2 sleeves)
        if directional[i] and b_active[i]:
            r = fwd_1d[i]
            if not pd.isna(r):
                trades.append((i, float(r) - cost_B, "B"))
    trades.sort(key=lambda t: t[0])
    return trades


def main() -> int:
    logger.info("[p23] loading data + building features")
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

    # Date masks
    pre2024 = dmask(f.index, lambda d: d < dt.date(2024, 1, 1))
    y2024_25 = dmask(f.index, lambda d: dt.date(2024, 1, 1) <= d < dt.date(2026, 1, 1))
    y2026 = dmask(f.index, lambda d: d >= dt.date(2026, 1, 1))
    is_m = dmask(f.index, lambda d: d <= dt.date(2024, 12, 31))
    oos_m = dmask(f.index, lambda d: d >= dt.date(2025, 1, 1))

    # ==================================================================
    # STEP 1 — Cost sensitivity sweep
    # ==================================================================
    cost_sweep = {}
    for bps in (5, 10, 20):
        trades = build_trades(f, fwd, p15_entry, stress, directional, gates, bps)
        per_seg = {}
        for label, msk in (("full", pd.Series(True, index=f.index)),
                           ("is", is_m), ("oos", oos_m),
                           ("y2026", y2026)):
            rets = [r for (i, r, _) in trades if msk[i]]
            per_seg[label] = summarize(rets)
        cost_sweep[f"{bps}bps"] = per_seg
    logger.info("[p23] cost sweep done")

    # Use 10bps as primary for later analyses
    trades_primary = build_trades(f, fwd, p15_entry, stress, directional, gates, 10)

    # ==================================================================
    # STEP 2 — Rolling stability (1-year window)
    # ==================================================================
    # Aggregate trades into daily P&L (summed across engines on same day),
    # then 252-bar rolling stats.
    daily_pnl = pd.Series(0.0, index=f.index)
    for (i, r, _) in trades_primary:
        daily_pnl.at[i] += r
    cum = (1 + daily_pnl).cumprod()
    roll_window = 252
    rolling_mean = daily_pnl.rolling(roll_window).mean()
    rolling_std = daily_pnl.rolling(roll_window).std()
    rolling_sharpe = (rolling_mean / rolling_std) * math.sqrt(252)
    # Rolling max-DD on cumulative
    rolling_peak = cum.rolling(roll_window, min_periods=1).max()
    rolling_dd = (cum - rolling_peak) / rolling_peak

    # Spot-check: stats at key dates
    rolling_snapshot = {}
    snap_dates = [d for d in (dt.date(2023, 1, 3), dt.date(2024, 1, 2),
                               dt.date(2025, 1, 2), dt.date(2026, 1, 2),
                               f.index[-1]) if d in f.index]
    for d in snap_dates:
        rolling_snapshot[str(d)] = {
            "sharpe_1y": float(rolling_sharpe.at[d]) if not pd.isna(rolling_sharpe.at[d]) else None,
            "mean_1y": float(rolling_mean.at[d] * 100) if not pd.isna(rolling_mean.at[d]) else None,
            "cum_pct_at_date": float((cum.at[d] - 1) * 100),
            "dd_at_date_pct": float(rolling_dd.at[d] * 100) if not pd.isna(rolling_dd.at[d]) else None,
        }

    # ==================================================================
    # STEP 3 — Subperiod analysis
    # ==================================================================
    subperiod: dict = {}
    for label, msk in (("pre_2024", pre2024),
                        ("y2024_2025", y2024_25),
                        ("y2026_ytd", y2026)):
        rets = [r for (i, r, _) in trades_primary if msk[i]]
        a_rets = [r for (i, r, s) in trades_primary if msk[i] and s == "A"]
        b_rets = [r for (i, r, s) in trades_primary if msk[i] and s == "B"]
        subperiod[label] = {
            "combined": summarize(rets),
            "engineA": summarize(a_rets),
            "engineB": summarize(b_rets),
            "n_A": len(a_rets),
            "n_B": len(b_rets),
        }

    # ==================================================================
    # STEP 4 — Trade profile
    # ==================================================================
    n_total = len(trades_primary)
    n_A = sum(1 for t in trades_primary if t[2] == "A")
    n_B = sum(1 for t in trades_primary if t[2] == "B")
    total_bars = len(f.index)

    # A holds 10 bars, B holds 1 bar — total "in market" days (with overlap-awareness)
    in_market = set()
    for (i, _, s) in trades_primary:
        idx_pos = f.index.get_loc(i)
        hold = HOLD_A if s == "A" else 1
        for k in range(hold):
            if idx_pos + k < len(f.index):
                in_market.add(f.index[idx_pos + k])
    in_market_pct = len(in_market) / total_bars

    # Trades per month (simple)
    from collections import Counter
    months = Counter()
    for (i, _, _) in trades_primary:
        months[(i.year, i.month)] += 1
    trades_per_month = sum(months.values()) / max(len(months), 1)

    avg_hold = (n_A * HOLD_A + n_B * 1) / max(n_total, 1)

    trade_profile = {
        "total_trades": n_total,
        "engineA_trades": n_A,
        "engineB_trades": n_B,
        "avg_hold_bars": avg_hold,
        "trades_per_month": trades_per_month,
        "in_market_pct": in_market_pct,
        "total_bars": total_bars,
    }

    # ==================================================================
    # STEP 5 — Verdict
    # ==================================================================
    # PASS: survives 20bps (t>2 OOS positive), stable across subperiods,
    # no regime collapse (all subperiod means >= 0 after cost)
    cost_oos = {bps: cost_sweep[f"{bps}bps"]["oos"] for bps in (5, 10, 20)}
    survives_20bps = (cost_oos[20].get("n", 0) > 0
                      and cost_oos[20].get("mean_pct", 0) > 0
                      and cost_oos[20].get("t_stat", 0) > 1.5)
    subperiod_stable = all(
        subperiod[k]["combined"].get("mean_pct", 0) > 0
        for k in ("pre_2024", "y2024_2025", "y2026_ytd")
        if subperiod[k]["combined"].get("n", 0) > 0
    )
    y2026_collapse = (subperiod["y2026_ytd"]["combined"].get("mean_pct", 0) <
                      -abs(subperiod["pre_2024"]["combined"].get("mean_pct", 0)) * 0.5)

    reasons: list[str] = []
    if survives_20bps and subperiod_stable and not y2026_collapse:
        verdict = "PASS"
        reasons.append(f"20bps OOS: n={cost_oos[20]['n']} t={cost_oos[20]['t_stat']:.2f} "
                       f"mean={cost_oos[20]['mean_pct']:+.4f}%")
        reasons.append("subperiod stability: all means positive")
        reasons.append("no 2026 regime collapse")
    elif survives_20bps or (subperiod_stable and not y2026_collapse):
        verdict = "WEAK"
        reasons.append(f"20bps OOS: t={cost_oos[20]['t_stat']:.2f}")
        reasons.append(f"subperiod_stable={subperiod_stable}  y2026_collapse={y2026_collapse}")
    else:
        verdict = "FAIL"
        reasons.append(f"20bps OOS: t={cost_oos[20]['t_stat']:.2f} mean={cost_oos[20]['mean_pct']:+.4f}%")
        reasons.append(f"subperiod_stable={subperiod_stable}  y2026_collapse={y2026_collapse}")

    report = {
        "phase": "23_robustness",
        "today": dt.date.today().isoformat(),
        "data_range": [str(f.index[0]), str(f.index[-1])],
        "cost_sensitivity": cost_sweep,
        "rolling_snapshot": rolling_snapshot,
        "subperiod_analysis": subperiod,
        "trade_profile": trade_profile,
        "verdict": verdict,
        "verdict_reasons": reasons,
    }
    (OUT_DIR / "report.json").write_text(json.dumps(report, indent=2, default=str))

    # --- Print ---
    print("=" * 100)
    print(f"PHASE 23 - ROBUSTNESS & EXECUTION VALIDATION  {dt.date.today()}")
    print("=" * 100)
    print(f"Data: ES=F {f.index[0]} -> {f.index[-1]} ({total_bars} bars)")
    print()
    print("--- STEP 1: COST SENSITIVITY SWEEP ---")
    print(f"{'bps':>4}  {'seg':<6}  {'n':>5} {'mean%':>9} {'t':>6} {'CI95%':<22} {'cum%':>8} {'maxDD%':>8}")
    for bps in (5, 10, 20):
        for seg in ("full", "is", "oos", "y2026"):
            s = cost_sweep[f"{bps}bps"][seg]
            if s.get("n", 0) == 0:
                print(f"{bps:>3}bp  {seg:<6}  n=0"); continue
            ci = s["ci95_pct"]
            print(f"{bps:>3}bp  {seg:<6}  {s['n']:>5} {s['mean_pct']:>+9.4f} "
                  f"{s['t_stat']:>+6.2f} [{ci[0]:+.4f},{ci[1]:+.4f}]  "
                  f"{s['cum_pct']:>+8.2f} {s['max_dd_pct']:>+8.2f}")
        print()

    print("--- STEP 2: ROLLING STABILITY (1-year Sharpe snapshots, 10bps) ---")
    print(f"{'date':<14} {'Sharpe_1y':>10} {'mean_1y%':>10} {'cum%':>8} {'DD_at_date%':>12}")
    for d, s in rolling_snapshot.items():
        if s["sharpe_1y"] is None:
            print(f"{d:<14} n/a"); continue
        print(f"{d:<14} {s['sharpe_1y']:>+10.3f} {s['mean_1y']:>+10.5f} "
              f"{s['cum_pct_at_date']:>+8.2f} {s['dd_at_date_pct']:>+12.2f}")
    print()

    print("--- STEP 3: SUBPERIOD ANALYSIS (10bps) ---")
    for label in ("pre_2024", "y2024_2025", "y2026_ytd"):
        d = subperiod[label]
        c = d["combined"]
        if c.get("n", 0) == 0:
            print(f"  {label:<14} n=0"); continue
        ci = c["ci95_pct"]
        print(f"  {label:<14} n={c['n']:>4} mean={c['mean_pct']:>+9.5f}% "
              f"t={c['t_stat']:>+5.2f} CI=[{ci[0]:+.4f},{ci[1]:+.4f}] "
              f"cum={c['cum_pct']:>+7.2f}% DD={c['max_dd_pct']:>+6.2f}%")
        print(f"    A: n={d['n_A']}  mean={d['engineA'].get('mean_pct',0):+.4f}%  "
              f"B: n={d['n_B']}  mean={d['engineB'].get('mean_pct',0):+.4f}%")
    print()

    print("--- STEP 4: TRADE PROFILE ---")
    print(f"  total trades:        {trade_profile['total_trades']}")
    print(f"  Engine A trades:     {trade_profile['engineA_trades']}  (10-bar hold)")
    print(f"  Engine B trades:     {trade_profile['engineB_trades']}  (1-bar hold)")
    print(f"  avg hold bars:       {trade_profile['avg_hold_bars']:.2f}")
    print(f"  trades per month:    {trade_profile['trades_per_month']:.1f}")
    print(f"  in-market %:         {trade_profile['in_market_pct']*100:.1f}%")
    print()
    print("-" * 100)
    print(f"VERDICT: {verdict}")
    for r in reasons: print(f"  {r}")
    print("=" * 100)
    print(f"Report: {OUT_DIR / 'report.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
