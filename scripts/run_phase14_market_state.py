"""Phase 14 — Market State Model on ES=F daily.

Pivot from signal-based to state-conditional forward return testing. No ML,
no parameter tuning, no discretionary logic. Same data stack (ES via yfinance,
SPY via DB), same honest cost model (10bps/20bps).

State variables (built on ES):
  1. vol_quartile      — ATR20 sample quartile (Q1-Q4, Q4 = highest vol)
  2. vol_trend         — ATR20_t > ATR20_{t-10} : 'expanding' | 'contracting'
  3. trend_strength    — MA20 slope over 10 bars: 'up' | 'flat' | 'down'
  4. compression       — ATR10 / ATR50 ratio tercile: 'tight' | 'mid' | 'loose'
  5. calendar          — day-of-week (Mon..Fri), turn-of-month (±3 trading days)

Actions:
  A. long_N        — enter next open, hold N bars
  B. short_N       — short next open, hold N bars
  C. breakout_up   — long if close > prior 5-day high (else skip)
  D. mean_rev_fade — short if 3d return > +2%; long if 3d return < -2%

Windows: 1, 3, 5, 10, 20.
Costs:   10 bps + 20 bps round-trip.

Outputs: unconditional baseline, per-state tables, action×state matrix,
monotonicity tests on vol and compression, sample diagnostics, verdict.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import random
import statistics as st
from collections import defaultdict
from pathlib import Path

import pandas as pd
from loguru import logger

from scripts.run_phase12_price_action import (
    fetch_es_daily, load_spy_from_db,
    HOLD_WINDOWS, COST_BPS,
)

OUT_DIR = Path("artifacts/phase14")
OUT_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Features (self-contained so Phase 14 is independent of Phase 12 params)
# ---------------------------------------------------------------------------
def true_range(df: pd.DataFrame) -> pd.Series:
    pc = df["close"].shift(1)
    return pd.concat([
        df["high"] - df["low"],
        (df["high"] - pc).abs(),
        (df["low"] - pc).abs(),
    ], axis=1).max(axis=1)


def build_states(es: pd.DataFrame) -> pd.DataFrame:
    f = es.copy()
    f["tr"] = true_range(f)
    f["atr10"] = f["tr"].rolling(10).mean()
    f["atr20"] = f["tr"].rolling(20).mean()
    f["atr50"] = f["tr"].rolling(50).mean()
    f["ma20"] = f["close"].rolling(20).mean()

    # 1. Vol quartiles (use expanding-window quartiles to avoid look-ahead;
    # for simplicity we accept full-sample quartiles here — state labels are
    # diagnostic, not entry filters. Clearly mark as full-sample for
    # reproducibility.)
    atr20_q = f["atr20"].quantile([0.25, 0.50, 0.75]).values
    def _vq(x):
        if pd.isna(x): return None
        if x < atr20_q[0]: return "Q1_lowvol"
        if x < atr20_q[1]: return "Q2"
        if x < atr20_q[2]: return "Q3"
        return "Q4_highvol"
    f["vol_quartile"] = f["atr20"].apply(_vq)

    # 2. Vol trend
    f["vol_trend"] = (
        (f["atr20"] > f["atr20"].shift(10)).map({True: "expanding", False: "contracting"})
    )

    # 3. Trend strength — MA20 slope over 10 bars, terciled relative to ATR20
    slope = (f["ma20"] - f["ma20"].shift(10)) / f["atr20"]
    s_q = slope.quantile([1/3, 2/3]).values
    def _tr(x):
        if pd.isna(x): return None
        if x < s_q[0]: return "down"
        if x < s_q[1]: return "flat"
        return "up"
    f["trend_strength"] = slope.apply(_tr)

    # 4. Compression — ATR10 / ATR50 ratio
    ratio = f["atr10"] / f["atr50"]
    r_q = ratio.quantile([1/3, 2/3]).values
    def _cp(x):
        if pd.isna(x): return None
        if x < r_q[0]: return "tight"
        if x < r_q[1]: return "mid"
        return "loose"
    f["compression"] = ratio.apply(_cp)

    # 5. Calendar
    f["day_of_week"] = [d.strftime("%a") if hasattr(d, "strftime") else
                        dt.date.fromisoformat(str(d)).strftime("%a") for d in f.index]
    # Turn-of-month: last 3 trading days of prev month + first 3 of current = ±3 window
    idx_list = list(f.index)
    tom_flag = [False] * len(idx_list)
    for i, d in enumerate(idx_list):
        next_month = (i + 3 < len(idx_list)
                      and idx_list[i + 3].month != d.month)
        prev_month = (i - 3 >= 0
                      and idx_list[i - 3].month != d.month)
        tom_flag[i] = next_month or prev_month
    f["turn_of_month"] = ["tom" if x else "mid-month" for x in tom_flag]
    return f


# ---------------------------------------------------------------------------
# Forward returns per action
# ---------------------------------------------------------------------------
def compute_actions(f: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Return action_name -> DataFrame[bool] of 'enter' flags per bar."""
    # Action A: long every bar
    # Action B: short every bar
    # Action C: breakout_up only
    # Action D: mean-rev fade — short if 3d ret > +2%, long if 3d ret < -2%
    close = f["close"]
    ret3 = close.pct_change(3)
    prior_hi5 = f["high"].shift(1).rolling(5).max()
    acts: dict[str, pd.DataFrame] = {}
    acts["long_all"] = pd.DataFrame({
        "long": pd.Series(True, index=f.index),
        "short": pd.Series(False, index=f.index),
    })
    acts["short_all"] = pd.DataFrame({
        "long": pd.Series(False, index=f.index),
        "short": pd.Series(True, index=f.index),
    })
    acts["breakout_up"] = pd.DataFrame({
        "long": close > prior_hi5,
        "short": pd.Series(False, index=f.index),
    })
    acts["mean_rev_fade"] = pd.DataFrame({
        "long":  ret3 < -0.02,
        "short": ret3 > 0.02,
    })
    return acts


def forward_returns(f: pd.DataFrame, windows: tuple[int, ...]) -> dict[int, pd.Series]:
    out: dict[int, pd.Series] = {}
    for N in windows:
        entry = f["open"].shift(-1)
        exit_ = f["close"].shift(-N)
        out[N] = (exit_ - entry) / entry
    return out


def pooled_action_returns(
    action: pd.DataFrame, fwd: pd.Series, mask: pd.Series,
) -> list[float]:
    longs  = action["long"]  & mask & fwd.notna()
    shorts = action["short"] & mask & fwd.notna()
    return fwd[longs].tolist() + [-r for r in fwd[shorts].tolist()]


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
    return {
        "n": n, "mean_pct": mean * 100, "median_pct": med * 100,
        "std_pct": sd * 100, "hit": wins / n, "t": t,
        "ci95_pct": [lo * 100, hi * 100],
    }


# ---------------------------------------------------------------------------
# Table builders
# ---------------------------------------------------------------------------
def unconditional_table(
    actions: dict[str, pd.DataFrame], fwd_rets: dict[int, pd.Series],
) -> dict:
    out = {}
    for aname, act in actions.items():
        out[aname] = {}
        for N in HOLD_WINDOWS:
            rets = pooled_action_returns(act, fwd_rets[N], pd.Series(True, index=act.index))
            out[aname][str(N)] = {
                f"{b}bps": summarize(rets, b) for b in COST_BPS
            }
    return out


def state_table(
    f: pd.DataFrame, actions: dict[str, pd.DataFrame],
    fwd_rets: dict[int, pd.Series], state_col: str,
) -> dict:
    """Per-state, per-action, per-window stats (20bps net). Primary N=10."""
    out: dict = {}
    values = sorted([v for v in f[state_col].dropna().unique()])
    for v in values:
        mask = (f[state_col] == v).fillna(False)
        out[str(v)] = {"n_bars": int(mask.sum()), "actions": {}}
        for aname, act in actions.items():
            per_N = {}
            for N in HOLD_WINDOWS:
                rets = pooled_action_returns(act, fwd_rets[N], mask)
                per_N[str(N)] = summarize(rets, 20)
            out[str(v)]["actions"][aname] = per_N
    return out


def monotonicity_check(state_table_d: dict, action: str, N: int) -> dict:
    vals = []
    for state_val in sorted(state_table_d.keys()):
        s = state_table_d[state_val]["actions"].get(action, {}).get(str(N), {})
        if s.get("n", 0) == 0:
            vals.append(None)
        else:
            vals.append(s["mean_pct"])
    # Check strict monotonicity (either all ascending or all descending)
    non_null = [v for v in vals if v is not None]
    asc = all(non_null[i] <= non_null[i+1] for i in range(len(non_null) - 1))
    desc = all(non_null[i] >= non_null[i+1] for i in range(len(non_null) - 1))
    return {
        "state_values_ordered": sorted(state_table_d.keys()),
        "means_by_state_pct": vals,
        "monotonic_ascending": asc,
        "monotonic_descending": desc,
        "monotonic": asc or desc,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    logger.info("[p14] fetching ES=F + SPY")
    es = fetch_es_daily(start="2020-01-01")
    spy = load_spy_from_db()
    es = es[~es.index.duplicated(keep="last")].sort_index()
    spy = spy[~spy.index.duplicated(keep="last")].sort_index()
    common = es.index.intersection(spy.index)
    es = es.loc[common]
    logger.info("[p14] common {} bars ({} -> {})", len(es), es.index[0], es.index[-1])

    f = build_states(es)
    actions = compute_actions(f)
    fwd_rets = forward_returns(f, HOLD_WINDOWS)

    # 1. Unconditional baseline
    uncond = unconditional_table(actions, fwd_rets)

    # 2. Per-state tables (one-variable marginals)
    state_tables = {}
    for state_col in ("vol_quartile", "vol_trend", "trend_strength",
                      "compression", "day_of_week", "turn_of_month"):
        state_tables[state_col] = state_table(f, actions, fwd_rets, state_col)

    # 3. Action × state matrix — primary: (long_all, short_all) at 10D/20bps
    action_state_matrix: dict = {}
    for state_col, tbl in state_tables.items():
        action_state_matrix[state_col] = {}
        for v in tbl:
            action_state_matrix[state_col][v] = {}
            for a in actions:
                s = tbl[v]["actions"].get(a, {}).get("10", {})
                action_state_matrix[state_col][v][a] = {
                    "n": s.get("n", 0),
                    "mean_pct": s.get("mean_pct"),
                    "t": s.get("t"),
                }

    # 4. Monotonicity — vol and compression (10D, long_all)
    mono_checks = {
        "vol_quartile_long_10d":     monotonicity_check(state_tables["vol_quartile"],     "long_all", 10),
        "vol_quartile_short_10d":    monotonicity_check(state_tables["vol_quartile"],     "short_all", 10),
        "compression_long_10d":      monotonicity_check(state_tables["compression"],      "long_all", 10),
        "compression_short_10d":     monotonicity_check(state_tables["compression"],      "short_all", 10),
        "trend_strength_long_10d":   monotonicity_check(state_tables["trend_strength"],   "long_all", 10),
        "trend_strength_short_10d":  monotonicity_check(state_tables["trend_strength"],   "short_all", 10),
    }

    # 5. Best / worst state-action cells at 10D/20bps with n>=30
    cells = []
    for state_col, tbl in state_tables.items():
        for v, vdata in tbl.items():
            for a, per_N in vdata["actions"].items():
                s = per_N.get("10", {})
                if s.get("n", 0) >= 30:
                    cells.append({
                        "state": state_col, "value": v, "action": a,
                        "n": s["n"], "mean_pct": s["mean_pct"],
                        "t": s["t"], "hit": s["hit"],
                        "ci95": s["ci95_pct"],
                    })
    cells.sort(key=lambda c: c["mean_pct"])
    worst = cells[:5]
    best = cells[-5:][::-1]

    # 6. Verdict — PASS if any state-action cell has n>=30, t>2, mean>0, CI_lo>0,
    # and state axis is monotonic on relevant variable OR if there's a strong
    # contrast between high-vs-low states (|diff| > 0.5% at 10D).
    best_cell = cells[-1] if cells else None
    any_monotonic_structure = any(m["monotonic"] for m in mono_checks.values())

    verdict = "FAIL"
    vreasons = []
    if best_cell:
        ci_lo, ci_hi = best_cell["ci95"]
        if (best_cell["n"] >= 30 and best_cell["t"] > 2.0
            and best_cell["mean_pct"] > 0 and ci_lo > 0
            and any_monotonic_structure):
            verdict = "PASS"
            vreasons.append(
                f"best cell: {best_cell['state']}={best_cell['value']} "
                f"action={best_cell['action']} n={best_cell['n']} "
                f"t={best_cell['t']:.2f} mean={best_cell['mean_pct']:.3f}% "
                f"CI=[{ci_lo:.3f},{ci_hi:.3f}]"
            )
        elif any(m["monotonic"] for m in mono_checks.values()) or (
            best_cell["n"] >= 30 and best_cell["t"] > 1.0
            and best_cell["mean_pct"] > 0
        ):
            verdict = "WEAK"
            mono_names = [k for k, m in mono_checks.items() if m["monotonic"]]
            vreasons.append(f"monotonic state axes: {mono_names}")
            vreasons.append(
                f"best n>=30 cell: {best_cell['state']}={best_cell['value']} "
                f"action={best_cell['action']} n={best_cell['n']} "
                f"t={best_cell['t']:.2f} mean={best_cell['mean_pct']:.3f}%"
            )
        else:
            vreasons.append(f"best n>=30 cell t={best_cell['t']:.2f} "
                            f"mean={best_cell['mean_pct']:.3f}% — below gates")
    else:
        vreasons.append("no state-action cell with n>=30")

    report = {
        "phase": "14_market_state",
        "today": dt.date.today().isoformat(),
        "data_bars": len(f),
        "data_range": [str(f.index[0]), str(f.index[-1])],
        "unconditional_baseline": uncond,
        "state_tables": state_tables,
        "action_state_matrix_10d_20bps": action_state_matrix,
        "monotonicity": mono_checks,
        "best_cells_10d_20bps_n_ge_30": best,
        "worst_cells_10d_20bps_n_ge_30": worst,
        "verdict": verdict,
        "verdict_reasons": vreasons,
    }
    (OUT_DIR / "report.json").write_text(json.dumps(report, indent=2, default=str))

    # -- Print -------------------------------------------------------------
    print("=" * 100)
    print(f"PHASE 14 — MARKET STATE MODEL ({dt.date.today()})")
    print("=" * 100)
    print(f"Data: ES=F {f.index[0]} -> {f.index[-1]} ({len(f)} bars)")
    print()
    print("--- UNCONDITIONAL BASELINE (1 trade per bar, 10D/20bps pooled) ---")
    for aname, per_N in uncond.items():
        s = per_N["10"]["20bps"]
        if s.get("n", 0) == 0:
            continue
        print(f"  {aname:<16} n={s['n']:>5} mean={s['mean_pct']:+.3f}% "
              f"hit={s['hit']:.3f} t={s['t']:+.2f} "
              f"CI=[{s['ci95_pct'][0]:+.3f},{s['ci95_pct'][1]:+.3f}]")
    print()

    for state_col, tbl in state_tables.items():
        print(f"--- STATE: {state_col} (10D/20bps) ---")
        print(f"{'value':<14} {'n_bars':>7}  "
              f"{'long_all':>22} {'short_all':>22} "
              f"{'breakout_up':>22} {'mean_rev_fade':>22}")
        for v in sorted(tbl.keys()):
            vd = tbl[v]
            line = f"{v:<14} {vd['n_bars']:>7}  "
            for a in ("long_all", "short_all", "breakout_up", "mean_rev_fade"):
                s = vd["actions"].get(a, {}).get("10", {})
                if s.get("n", 0) == 0:
                    line += f"{'(n=0)':>22} "
                else:
                    line += (f" n={s['n']:>3} m={s['mean_pct']:+.2f}% "
                             f"t={s['t']:+.2f}").rjust(22) + " "
            print(line)
        print()

    print("--- MONOTONICITY CHECKS (10D/20bps) ---")
    for name, m in mono_checks.items():
        print(f"  {name}")
        print(f"    states:  {m['state_values_ordered']}")
        print(f"    means:   {[f'{v:+.3f}%' if v is not None else 'n/a' for v in m['means_by_state_pct']]}")
        print(f"    monotonic={m['monotonic']}  "
              f"(asc={m['monotonic_ascending']}, desc={m['monotonic_descending']})")
    print()

    print("--- TOP 5 BEST CELLS (n>=30, 10D/20bps) ---")
    for c in best:
        print(f"  {c['state']:<18}={c['value']:<14} action={c['action']:<15} "
              f"n={c['n']:>4} mean={c['mean_pct']:+.3f}% hit={c['hit']:.3f} "
              f"t={c['t']:+.2f} CI=[{c['ci95'][0]:+.3f},{c['ci95'][1]:+.3f}]")
    print()
    print("--- TOP 5 WORST CELLS (n>=30, 10D/20bps) ---")
    for c in worst:
        print(f"  {c['state']:<18}={c['value']:<14} action={c['action']:<15} "
              f"n={c['n']:>4} mean={c['mean_pct']:+.3f}% hit={c['hit']:.3f} "
              f"t={c['t']:+.2f} CI=[{c['ci95'][0]:+.3f},{c['ci95'][1]:+.3f}]")
    print()
    print("-" * 100)
    print(f"VERDICT: {verdict}")
    for r in vreasons: print(f"  {r}")
    print("=" * 100)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
