"""Phase 24 — Paper Trading Deployment (forward simulation).

Forward-walks the FROZEN Phase 23 system bar-by-bar with realistic execution:

  * Signals generated using ONLY data available at decision bar t
  * Trade entry on next bar open (t+1)
  * Slippage sampled uniform[5, 15] bps per trade
  * Engine A: 10-bar hold, close at t+11 close
  * Engine B: 1-bar hold, close at t+1 close
  * Both engines book P&L independently; overlap logged

Deterministic: fixed RNG seed for slippage reproducibility.

Compare results vs Phase 23 batch backtest @ 10bps:
  return consistency, trade frequency, regime behavior, rolling PnL curves.
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

OUT_DIR = Path("artifacts/phase24")
OUT_DIR.mkdir(parents=True, exist_ok=True)

HOLD_A = 10
SLIPPAGE_LO_BPS = 5
SLIPPAGE_HI_BPS = 15
RNG_SEED = 20260422


def sample_slippage(rng: random.Random) -> float:
    """Return per-trade slippage (one-side) as fraction (e.g. 0.0010 = 10bps)."""
    bps = rng.uniform(SLIPPAGE_LO_BPS, SLIPPAGE_HI_BPS)
    return bps / 1e4


# ---------------------------------------------------------------------------
# Forward simulation
# ---------------------------------------------------------------------------
def forward_simulate(
    f: pd.DataFrame, gates: pd.DataFrame,
    p15_entry: pd.Series, stress: pd.Series, directional: pd.Series,
) -> list[dict]:
    rng = random.Random(RNG_SEED)
    trades_log: list[dict] = []
    open_a_positions: list[dict] = []

    idx = list(f.index)
    opens = f["open"].tolist()
    closes = f["close"].tolist()

    # Ensure gates series aligned
    cs = gates["credit_stable"].fillna(False).tolist()
    rc = gates["rates_calm"].fillna(False).tolist()
    g_fav = gates["gates_favorable"].tolist()
    p15_list = p15_entry.tolist()
    stress_list = stress.tolist()
    directional_list = directional.tolist()

    for t in range(len(idx)):
        # 1) Close Engine-A positions whose exit_bar is reached
        remaining = []
        for pos in open_a_positions:
            if t >= pos["exit_bar"] and t < len(idx):
                exit_price = closes[pos["exit_bar"]]
                entry_price = pos["entry_price"]
                exit_slip = sample_slippage(rng)
                gross = (exit_price - entry_price) / entry_price
                net = gross - pos["entry_slip"] - exit_slip
                trades_log.append({
                    "engine": "A",
                    "entry_date": idx[pos["entry_bar"]],
                    "entry_bar": pos["entry_bar"],
                    "exit_bar": pos["exit_bar"],
                    "exit_date": idx[pos["exit_bar"]] if pos["exit_bar"] < len(idx) else None,
                    "entry_price": entry_price, "exit_price": exit_price,
                    "entry_slip_bps": pos["entry_slip"] * 1e4,
                    "exit_slip_bps": exit_slip * 1e4,
                    "gross_ret_pct": gross * 100,
                    "net_ret_pct": net * 100,
                    "regime_at_decision": pos["regime_at_decision"],
                    "gates_favorable_at_decision": pos["gates_at_decision"],
                })
            else:
                remaining.append(pos)
        open_a_positions = remaining

        # 2) Decision at bar t (open positions next bar)
        if t + 1 >= len(idx): continue
        entry_bar = t + 1
        entry_price = opens[entry_bar]

        # Engine A: P15 fires AND stress regime at t
        if p15_list[t] and stress_list[t]:
            exit_bar = t + HOLD_A + 1
            if exit_bar < len(idx):
                slip = sample_slippage(rng)
                open_a_positions.append({
                    "entry_bar": entry_bar, "exit_bar": exit_bar,
                    "entry_price": entry_price,
                    "entry_slip": slip,
                    "regime_at_decision": "stress",
                    "gates_at_decision": int(g_fav[t]) if not pd.isna(g_fav[t]) else None,
                })

        # Engine B: credit_stable AND rates_calm AND directional regime at t
        if directional_list[t] and cs[t] and rc[t]:
            exit_bar = t + 2  # 1-bar hold close
            if exit_bar < len(idx):
                exit_price = closes[exit_bar - 1]  # close of bar after entry
                # For 1-day hold we execute fully within a single trade
                entry_slip = sample_slippage(rng)
                exit_slip = sample_slippage(rng)
                gross = (exit_price - entry_price) / entry_price
                net = gross - entry_slip - exit_slip
                trades_log.append({
                    "engine": "B",
                    "entry_date": idx[entry_bar],
                    "entry_bar": entry_bar,
                    "exit_bar": exit_bar - 1,
                    "exit_date": idx[exit_bar - 1],
                    "entry_price": entry_price, "exit_price": exit_price,
                    "entry_slip_bps": entry_slip * 1e4,
                    "exit_slip_bps": exit_slip * 1e4,
                    "gross_ret_pct": gross * 100,
                    "net_ret_pct": net * 100,
                    "regime_at_decision": "directional",
                    "gates_favorable_at_decision": int(g_fav[t]) if not pd.isna(g_fav[t]) else None,
                })

    # Close any remaining Engine-A positions at last bar (mark-to-market)
    for pos in open_a_positions:
        last_bar = len(idx) - 1
        exit_price = closes[last_bar]
        entry_price = pos["entry_price"]
        exit_slip = sample_slippage(rng)
        gross = (exit_price - entry_price) / entry_price
        net = gross - pos["entry_slip"] - exit_slip
        trades_log.append({
            "engine": "A",
            "entry_date": idx[pos["entry_bar"]],
            "entry_bar": pos["entry_bar"],
            "exit_bar": last_bar,
            "exit_date": idx[last_bar],
            "entry_price": entry_price, "exit_price": exit_price,
            "entry_slip_bps": pos["entry_slip"] * 1e4,
            "exit_slip_bps": exit_slip * 1e4,
            "gross_ret_pct": gross * 100,
            "net_ret_pct": net * 100,
            "regime_at_decision": pos["regime_at_decision"],
            "gates_favorable_at_decision": pos["gates_at_decision"],
            "note": "force_close_at_last_bar",
        })

    return trades_log


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------
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


def main() -> int:
    logger.info("[p24] loading data")
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

    logger.info("[p24] running forward simulation with slippage [5,15] bps...")
    trades = forward_simulate(f, gates, p15_entry, stress, directional)
    trades.sort(key=lambda t: t["entry_bar"])
    logger.info("[p24] trades generated: {}", len(trades))

    # ==================================================================
    # Stats per engine + per segment
    # ==================================================================
    is_end = dt.date(2024, 12, 31); oos_start = dt.date(2025, 1, 1)
    y2026_start = dt.date(2026, 1, 1)

    def seg_mask(trade):
        d = trade["entry_date"]
        return {
            "full": True,
            "is": d <= is_end,
            "oos": d >= oos_start,
            "y2026": d >= y2026_start,
        }

    by_engine_seg: dict = {}
    for engine in ("A", "B", "combined"):
        for seg in ("full", "is", "oos", "y2026"):
            rets = []
            for t in trades:
                if engine != "combined" and t["engine"] != engine: continue
                if not seg_mask(t)[seg]: continue
                rets.append(t["net_ret_pct"] / 100)  # decimal
            by_engine_seg[f"{engine}_{seg}"] = summarize(rets)

    # ==================================================================
    # Rolling PnL (daily)
    # ==================================================================
    daily_pnl = pd.Series(0.0, index=f.index)
    for t in trades:
        d = t["entry_date"]
        if d in daily_pnl.index:
            daily_pnl.at[d] += t["net_ret_pct"] / 100
    cum = (1 + daily_pnl).cumprod()
    peak = cum.expanding().max()
    dd_series = (cum - peak) / peak

    # ==================================================================
    # Regime distribution
    # ==================================================================
    regime_counts = {
        "stress_pct": float(stress.mean()),
        "directional_pct": float(directional.mean()),
        "total_bars": len(f),
    }

    # ==================================================================
    # Trade profile
    # ==================================================================
    n_A = sum(1 for t in trades if t["engine"] == "A")
    n_B = sum(1 for t in trades if t["engine"] == "B")
    n_2026 = sum(1 for t in trades if t["entry_date"] >= y2026_start)
    n_A_2026 = sum(1 for t in trades if t["engine"] == "A" and t["entry_date"] >= y2026_start)
    n_B_2026 = sum(1 for t in trades if t["engine"] == "B" and t["entry_date"] >= y2026_start)
    mean_slip = st.mean([t["entry_slip_bps"] + t["exit_slip_bps"] for t in trades]) if trades else 0

    # ==================================================================
    # Consistency vs Phase 23 batch (at 10bps baseline)
    # ==================================================================
    # Phase 23 OOS @ 10bps was: n=88, mean=+0.3125%, t=+2.22, cum=+30.63%, DD=-4.32%
    # Phase 24 live slippage ~10bps (midpoint of 5-15), should land in that range.
    p23_oos_ref = {"n": 88, "mean_pct": 0.3125, "t_stat": 2.22,
                   "cum_pct": 30.63, "max_dd_pct": -4.32}
    p24_oos = by_engine_seg["combined_oos"]
    consistency = {
        "p23_oos_ref": p23_oos_ref,
        "p24_oos_live": p24_oos,
        "delta_mean_pp":   (p24_oos.get("mean_pct", 0) - p23_oos_ref["mean_pct"]),
        "delta_t":         (p24_oos.get("t_stat", 0) - p23_oos_ref["t_stat"]),
        "delta_cum_pp":    (p24_oos.get("cum_pct", 0) - p23_oos_ref["cum_pct"]),
        "delta_maxDD_pp":  (p24_oos.get("max_dd_pct", 0) - p23_oos_ref["max_dd_pct"]),
    }

    # ==================================================================
    # Verdict
    # ==================================================================
    p24_full = by_engine_seg["combined_full"]
    p24_oos_stats = by_engine_seg["combined_oos"]
    p24_2026 = by_engine_seg["combined_y2026"]

    # PASS if OOS stays within 30% of Phase 23 ref AND 2026 stays positive AND DD not worse >10pp
    mean_ok = abs(consistency["delta_mean_pp"]) <= 0.15   # within 0.15% mean/trade
    cum_ok = consistency["delta_cum_pp"] >= -15.0          # don't lose more than 15pp cum
    dd_ok = consistency["delta_maxDD_pp"] >= -5.0           # DD not >5pp worse
    y2026_ok = p24_2026.get("mean_pct", -999) > 0
    t_ok = p24_oos_stats.get("t_stat", 0) > 1.5

    reasons: list[str] = []
    if mean_ok and cum_ok and dd_ok and y2026_ok and t_ok:
        verdict = "PASS"
        reasons.append(f"OOS live consistent with backtest "
                       f"(d_mean={consistency['delta_mean_pp']:+.4f}%, "
                       f"d_cum={consistency['delta_cum_pp']:+.2f}pp, "
                       f"d_DD={consistency['delta_maxDD_pp']:+.2f}pp)")
        reasons.append(f"2026 mean positive: {p24_2026.get('mean_pct', 0):+.4f}%")
        reasons.append(f"OOS t={p24_oos_stats['t_stat']:+.2f}")
    elif (mean_ok or cum_ok) and (y2026_ok or t_ok):
        verdict = "WEAK"
        reasons.append(f"partial consistency: d_mean={consistency['delta_mean_pp']:+.4f}%, "
                       f"d_cum={consistency['delta_cum_pp']:+.2f}pp")
    else:
        verdict = "FAIL"
        reasons.append(f"divergence: d_mean={consistency['delta_mean_pp']:+.4f}%, "
                       f"d_cum={consistency['delta_cum_pp']:+.2f}pp, "
                       f"2026_pos={y2026_ok}, t={p24_oos_stats.get('t_stat', 0):+.2f}")

    report = {
        "phase": "24_paper_trade",
        "today": dt.date.today().isoformat(),
        "data_range": [str(f.index[0]), str(f.index[-1])],
        "rng_seed": RNG_SEED,
        "slippage_bps_band": [SLIPPAGE_LO_BPS, SLIPPAGE_HI_BPS],
        "mean_total_slip_bps": mean_slip,
        "regime_distribution": regime_counts,
        "trade_counts": {
            "total": len(trades),
            "engineA": n_A, "engineB": n_B,
            "y2026_total": n_2026, "y2026_A": n_A_2026, "y2026_B": n_B_2026,
        },
        "stats_by_engine_seg": by_engine_seg,
        "consistency_vs_phase23_batch": consistency,
        "verdict": verdict,
        "verdict_reasons": reasons,
    }
    (OUT_DIR / "report.json").write_text(json.dumps(report, indent=2, default=str))
    # Write trades
    trades_out = []
    for t in trades:
        trades_out.append({
            **{k: (v.isoformat() if hasattr(v, "isoformat") else v)
               for k, v in t.items()}
        })
    (OUT_DIR / "trades.jsonl").write_text(
        "\n".join(json.dumps(t, default=str) for t in trades_out)
    )

    # --- Print ---
    print("=" * 100)
    print(f"PHASE 24 - PAPER TRADING DEPLOYMENT  {dt.date.today()}")
    print("=" * 100)
    print(f"Data: ES=F {f.index[0]} -> {f.index[-1]} ({len(f)} bars)")
    print(f"Slippage band: [{SLIPPAGE_LO_BPS}, {SLIPPAGE_HI_BPS}] bps/side  "
          f"(mean RT slip: {mean_slip:.2f} bps)")
    print(f"RNG seed: {RNG_SEED}")
    print()
    print("--- REGIME DISTRIBUTION ---")
    print(f"  stress: {regime_counts['stress_pct']*100:.1f}% of bars")
    print(f"  directional: {regime_counts['directional_pct']*100:.1f}% of bars")
    print()
    print("--- TRADE COUNTS ---")
    print(f"  total trades:   {len(trades)}")
    print(f"  Engine A:       {n_A}")
    print(f"  Engine B:       {n_B}")
    print(f"  2026 YTD total: {n_2026} (A={n_A_2026} B={n_B_2026})")
    print()
    print("--- STATS BY ENGINE × SEGMENT (live execution) ---")
    print(f"{'engine':<10} {'seg':<6} {'n':>5} {'mean%':>9} {'t':>6} "
          f"{'CI95%':<22} {'cum%':>8} {'maxDD%':>8}")
    for engine in ("A", "B", "combined"):
        for seg in ("full", "is", "oos", "y2026"):
            s = by_engine_seg[f"{engine}_{seg}"]
            if s.get("n", 0) == 0:
                print(f"{engine:<10} {seg:<6} n=0"); continue
            ci = s["ci95_pct"]
            print(f"{engine:<10} {seg:<6} {s['n']:>5} {s['mean_pct']:>+9.4f} "
                  f"{s['t_stat']:>+6.2f} [{ci[0]:+.4f},{ci[1]:+.4f}] "
                  f"{s['cum_pct']:>+8.2f} {s['max_dd_pct']:>+8.2f}")
        print()

    print("--- CONSISTENCY vs PHASE 23 BATCH (OOS 10bps ref) ---")
    r23 = consistency["p23_oos_ref"]
    r24 = consistency["p24_oos_live"]
    print(f"                    {'Phase23 ref':>14}  {'Phase24 live':>14}  {'delta':>10}")
    print(f"  n:                {r23['n']:>14}  {r24.get('n',0):>14}  ")
    print(f"  mean/trade %:     {r23['mean_pct']:>+14.4f}  "
          f"{r24.get('mean_pct',0):>+14.4f}  {consistency['delta_mean_pp']:>+10.4f}")
    print(f"  t-stat:           {r23['t_stat']:>+14.2f}  "
          f"{r24.get('t_stat',0):>+14.2f}  {consistency['delta_t']:>+10.2f}")
    print(f"  cum %:            {r23['cum_pct']:>+14.2f}  "
          f"{r24.get('cum_pct',0):>+14.2f}  {consistency['delta_cum_pp']:>+10.2f} pp")
    print(f"  maxDD %:          {r23['max_dd_pct']:>+14.2f}  "
          f"{r24.get('max_dd_pct',0):>+14.2f}  {consistency['delta_maxDD_pp']:>+10.2f} pp")
    print()
    print("-" * 100)
    print(f"VERDICT: {verdict}")
    for r in reasons: print(f"  {r}")
    print("=" * 100)
    print(f"Report: {OUT_DIR / 'report.json'}")
    print(f"Trades: {OUT_DIR / 'trades.jsonl'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
