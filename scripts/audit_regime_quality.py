"""Regime classification quality audit — analysis only.

Validates the research_backfill_v1 stress/directional regime labels
used by the tsmom_60_no_stress shadow strategy.

Read-only. NEVER mutates DB, regime labels, or thresholds.

Six parts:
  1. Regime correctness — per-regime TSMOM Sharpe + hit + distribution
  2. Misclassification — false non-stress / false stress rates
  3. Transition zones — pre/post regime change behavior
  4. Sensitivity — vary rvol_20d / dd_60d cutoffs ±10%
  5. Robustness — by year / vol bucket / trend bucket
  6. Output JSON + markdown summary

Run:
    DATABASE_URL=postgresql+psycopg://... ./.venv/Scripts/python.exe \
        -m scripts.audit_regime_quality
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text

from apps.api.src.db import SessionLocal
from apps.api.src.research.regime_backfill import (
    DD_60_STRESS,
    LOGIC_VERSION,
    MA_FAST,
    MA_SLOW,
    RVOL_20_CALM,
    RVOL_20_STRESS,
    RVOL_5_STRESS,
    classify_pit,
)


PERIODS_PER_YEAR = 252
TSMOM_HORIZON = 60
COST_BPS = 10.0


# --------------------------------------------------------------------------
# Stats
# --------------------------------------------------------------------------

def _sharpe(arr: Sequence[float]) -> float:
    a = [float(x) for x in arr if x is not None and math.isfinite(float(x))]
    if len(a) < 2:
        return float("nan")
    mu = sum(a) / len(a)
    try:
        sd = statistics.stdev(a)
    except statistics.StatisticsError:
        return float("nan")
    if sd == 0 or not math.isfinite(sd):
        return float("nan")
    return (mu / sd) * math.sqrt(PERIODS_PER_YEAR)


def _max_dd(arr: Sequence[float]) -> float:
    a = [float(x) for x in arr if x is not None and math.isfinite(float(x))]
    if not a:
        return 0.0
    eq = 1.0; peak = 1.0; worst = 0.0
    for r in a:
        eq *= 1 + r
        peak = max(peak, eq)
        worst = min(worst, (eq - peak) / peak)
    return worst * 100.0


def _summarize(label: str, rets: Sequence[float]) -> dict:
    a = np.asarray([r for r in rets if pd.notna(r)], dtype=float)
    if len(a) == 0:
        return {"label": label, "n": 0, "sharpe": None, "hit_pct": None,
                "total_pct": None, "mean_bps": None, "stdev_bps": None,
                "p10_bps": None, "p90_bps": None, "max_dd_pct": 0.0}
    return {
        "label": label,
        "n": int(len(a)),
        "sharpe": round(float(_sharpe(a)), 3),
        "hit_pct": round(float((a > 0).mean()) * 100, 2),
        "total_pct": round(float((1 + a).prod() - 1) * 100, 2),
        "mean_bps": round(float(a.mean()) * 1e4, 2),
        "stdev_bps": round(float(a.std(ddof=1) if len(a) > 1 else 0)
                              * 1e4, 2),
        "p10_bps": round(float(np.percentile(a, 10)) * 1e4, 2),
        "p90_bps": round(float(np.percentile(a, 90)) * 1e4, 2),
        "max_dd_pct": round(float(_max_dd(a)), 2),
    }


def _print_table(rows: list[dict], cols: list[str]) -> None:
    if not rows:
        print("  (no rows)"); return
    widths = {c: max(len(c), max(len(str(r.get(c, ""))) for r in rows))
              for c in cols}
    fmt = "  " + "  ".join(f"{{:<{widths[c]}}}" for c in cols)
    print(fmt.format(*cols))
    for r in rows:
        print(fmt.format(*[str(r.get(c, "")) for c in cols]))


# --------------------------------------------------------------------------
# Loaders
# --------------------------------------------------------------------------

def _load_bars() -> pd.DataFrame:
    from scripts.run_phase12_price_action import fetch_es_daily
    df = fetch_es_daily(start="2018-01-01")
    df = df.copy()
    df.index = pd.to_datetime(df.index).normalize()
    df["ret"] = df["close"].pct_change()
    df["fwd_ret_1d"] = df["close"].pct_change().shift(-1)
    return df


def _load_regimes(session) -> pd.DataFrame:
    rows = session.execute(text(f"""
        SELECT as_of_date, context_name, value_bool
          FROM context_daily
         WHERE context_name IN ('stress_regime', 'directional_regime')
           AND status = 'diagnostic'
           AND logic_version = '{LOGIC_VERSION}'
    """)).mappings().all()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["as_of_date"] = pd.to_datetime(df["as_of_date"]).dt.normalize()
    return df.pivot_table(index="as_of_date", columns="context_name",
                              values="value_bool", aggfunc="first")\
            .fillna(False).astype(bool)


# --------------------------------------------------------------------------
# TSMOM walk (long-flat, 1d hold) — no regime filter
# --------------------------------------------------------------------------

def _walk_tsmom(closes: pd.Series, *, h: int = TSMOM_HORIZON,
                  apply_cost: bool = True) -> tuple[pd.Series, pd.Series]:
    """Returns (signal, daily_ret_1d_long_flat)."""
    cost = COST_BPS / 1e4 if apply_cost else 0.0
    cl = list(closes.values.astype(float))
    sigs: list[int] = []
    rets: list[float] = []
    prev = 0
    for t in range(len(cl) - 1):
        if t < h:
            sigs.append(0); rets.append(np.nan); continue
        a = cl[t - h]; b = cl[t]; c = cl[t + 1]
        if a == 0 or not all(np.isfinite([a, b, c])):
            sigs.append(0); rets.append(np.nan); continue
        sig = 1 if (b / a - 1.0) > 0 else 0
        applied = sig * (c / b - 1.0)
        if sig != prev:
            applied -= cost
        sigs.append(sig); rets.append(applied); prev = sig
    sigs.append(0); rets.append(np.nan)
    return (pd.Series(sigs, index=closes.index, name="sig"),
            pd.Series(rets, index=closes.index, name="ret"))


# --------------------------------------------------------------------------
# Per-regime correctness (Part 1)
# --------------------------------------------------------------------------

def part1(closes, ret_unfilt, regimes):
    print("\n=== PART 1 — Regime correctness ===")
    # Align
    df = pd.concat([ret_unfilt.rename("r"),
                       regimes.reindex(closes.index).fillna(False)],
                      axis=1).dropna(subset=["r"])
    if df.empty:
        print("  (no aligned data)"); return {}

    stress_idx = df.index[df["stress_regime"]]
    direct_idx = df.index[df["directional_regime"]]
    other_idx  = df.index.difference(stress_idx).difference(direct_idx)

    rows = [
        _summarize("stress", df.loc[stress_idx, "r"].tolist()),
        _summarize("directional", df.loc[direct_idx, "r"].tolist()),
        _summarize("neutral_other", df.loc[other_idx, "r"].tolist()),
        _summarize("ALL", df["r"].tolist()),
    ]
    _print_table(rows, ["label", "n", "sharpe", "hit_pct",
                          "mean_bps", "stdev_bps",
                          "p10_bps", "p90_bps", "max_dd_pct"])
    return {"per_regime": rows}


# --------------------------------------------------------------------------
# Misclassification (Part 2)
# --------------------------------------------------------------------------

def part2(closes, ret_unfilt, regimes):
    print("\n=== PART 2 — Misclassification ===")
    df = pd.concat([ret_unfilt.rename("r"),
                       regimes.reindex(closes.index).fillna(False)],
                      axis=1).dropna(subset=["r"])

    # False NON-STRESS: labeled non-stress AND TSMOM loses heavily
    # (bottom-decile of NON-stress days in absolute return)
    non_stress = df[~df["stress_regime"]]
    if not non_stress.empty:
        worst_thresh = float(non_stress["r"].quantile(0.10))
        false_non_stress = non_stress[non_stress["r"] <= worst_thresh]
        false_ns_rate = len(false_non_stress) / len(non_stress)
    else:
        worst_thresh = float("nan"); false_ns_rate = 0.0; false_non_stress = pd.DataFrame()

    # False STRESS: labeled stress AND TSMOM positive (filter stole edge)
    stress = df[df["stress_regime"]]
    if not stress.empty:
        false_stress = stress[stress["r"] > 0]
        false_s_rate = len(false_stress) / len(stress)
    else:
        false_stress = pd.DataFrame(); false_s_rate = 0.0

    print(f"  Non-stress days        : {len(non_stress)}")
    print(f"  Non-stress bottom-10%  : {len(false_non_stress)} "
            f"(threshold ≤ {worst_thresh*1e4:.1f} bps)")
    print(f"  False non-stress rate  : {false_ns_rate*100:.2f}% "
            f"of non-stress days had heavy TSMOM losses")
    print()
    print(f"  Stress days            : {len(stress)}")
    print(f"  Stress positive-TSMOM  : {len(false_stress)} (filter "
            f"prevented these wins)")
    print(f"  False stress rate      : {false_s_rate*100:.2f}% of "
            f"stress days had positive TSMOM")

    fs_summary = _summarize("false_stress_returns",
                                false_stress["r"].tolist())
    fns_summary = _summarize("worst_non_stress_returns",
                                  false_non_stress["r"].tolist())
    print()
    _print_table([fs_summary, fns_summary],
                  ["label", "n", "sharpe", "hit_pct", "mean_bps",
                   "p10_bps", "p90_bps"])

    return {
        "non_stress_n": int(len(non_stress)),
        "stress_n": int(len(stress)),
        "false_non_stress_rate_pct": round(false_ns_rate * 100, 2),
        "false_stress_rate_pct": round(false_s_rate * 100, 2),
        "false_stress_summary": fs_summary,
        "false_non_stress_summary": fns_summary,
        "non_stress_p10_threshold_bps":
            None if not math.isfinite(worst_thresh) else round(worst_thresh * 1e4, 2),
    }


# --------------------------------------------------------------------------
# Transitions (Part 3)
# --------------------------------------------------------------------------

def part3(closes, ret_unfilt, regimes):
    print("\n=== PART 3 — Transition zones ===")
    df = pd.concat([ret_unfilt.rename("r"),
                       regimes.reindex(closes.index).fillna(False)],
                      axis=1).dropna(subset=["r"])
    if df.empty:
        print("  (no data)"); return {}

    stress = df["stress_regime"].astype(int).values
    rets = df["r"].values
    n = len(stress)

    # Find transition entry indices: 0 → 1 (entering stress)
    enter_idxs = [i for i in range(1, n)
                  if stress[i] == 1 and stress[i - 1] == 0]
    exit_idxs  = [i for i in range(1, n)
                  if stress[i] == 0 and stress[i - 1] == 1]

    def _window_avg_bps(idxs: list[int], lo: int, hi: int) -> dict:
        """Mean return (bps) in window [lo, hi] relative to transition i."""
        all_r = []
        for i in idxs:
            for off in range(lo, hi + 1):
                j = i + off
                if 0 <= j < n and np.isfinite(rets[j]):
                    all_r.append(rets[j])
        if not all_r:
            return {"n_transitions": len(idxs),
                    "n_obs": 0, "mean_bps": None, "sharpe": None}
        return {
            "n_transitions": len(idxs),
            "n_obs": int(len(all_r)),
            "mean_bps": round(float(np.mean(all_r)) * 1e4, 2),
            "sharpe": round(float(_sharpe(all_r)), 3),
        }

    rows = [
        # Pre-stress: 5 / 3 / 1 days before entering stress
        {"phase": "T-5..T-3 before stress",
         **_window_avg_bps(enter_idxs, -5, -3)},
        {"phase": "T-2..T-1 before stress",
         **_window_avg_bps(enter_idxs, -2, -1)},
        {"phase": "T (entry day)",
         **_window_avg_bps(enter_idxs, 0, 0)},
        {"phase": "T+1..T+3 after stress entry",
         **_window_avg_bps(enter_idxs, 1, 3)},
        # Post-stress: 1..3 days after stress exit
        {"phase": "T+1..T+3 after stress exit",
         **_window_avg_bps(exit_idxs, 1, 3)},
        {"phase": "T+4..T+10 after stress exit",
         **_window_avg_bps(exit_idxs, 4, 10)},
    ]
    _print_table(rows, ["phase", "n_transitions", "n_obs",
                          "mean_bps", "sharpe"])
    return {"transitions": rows,
            "n_enter_events": len(enter_idxs),
            "n_exit_events": len(exit_idxs)}


# --------------------------------------------------------------------------
# Sensitivity (Part 4)
# --------------------------------------------------------------------------

def part4(closes, ret_unfilt):
    print("\n=== PART 4 — Threshold sensitivity ===")

    cl_list = list(closes.values.astype(float))
    cl_idx = closes.index

    def _classify_with(rvol_thr: float, dd_thr: float) -> pd.DataFrame:
        """Re-classify with custom thresholds. Returns DF with bool flags
        per date. Uses same other rules (rvol_5, MA200, MA50, calm)."""
        out = []
        for i, dt in enumerate(cl_idx):
            base = classify_pit(dt.date(), cl_list[: i + 1])
            if base.insufficient_history:
                out.append((False, False)); continue
            stress = (
                (math.isfinite(base.rvol_20d) and base.rvol_20d >= rvol_thr)
                or (math.isfinite(base.rvol_5d)
                      and base.rvol_5d >= RVOL_5_STRESS)
                or (math.isfinite(base.dd_60d) and base.dd_60d <= dd_thr)
                or (base.close < base.ma200)
            )
            directional = (
                (math.isfinite(base.ma50) and math.isfinite(base.ma200)
                 and base.ma50 > base.ma200)
                and base.close > base.ma50
                and (math.isfinite(base.rvol_20d)
                       and base.rvol_20d < RVOL_20_CALM)
                and (not stress)
            )
            out.append((stress, directional))
        return pd.DataFrame(out, index=cl_idx,
                                columns=["stress_regime",
                                         "directional_regime"])

    def _filtered_perf(stress_series: pd.Series) -> dict:
        """Apply stress filter to ret_unfilt → return perf summary."""
        ret = ret_unfilt.copy()
        # When stress=True, force ret to 0 (FLAT, no exposure)
        ret_filtered = ret.where(~stress_series.reindex(ret.index)
                                            .fillna(False), 0.0)
        return _summarize("filtered", ret_filtered.dropna().tolist())

    grid = []
    base = _classify_with(RVOL_20_STRESS, DD_60_STRESS)
    grid.append({"variant": "baseline",
                 "rvol_20_stress": RVOL_20_STRESS,
                 "dd_60_stress": DD_60_STRESS,
                 **_filtered_perf(base["stress_regime"])})

    for d_pct in (-0.10, -0.05, +0.05, +0.10):
        rvol_t = RVOL_20_STRESS * (1 + d_pct)
        df = _classify_with(rvol_t, DD_60_STRESS)
        grid.append({"variant": f"rvol*{1+d_pct:+.0%}",
                     "rvol_20_stress": round(rvol_t, 4),
                     "dd_60_stress": DD_60_STRESS,
                     **_filtered_perf(df["stress_regime"])})

    for d_pct in (-0.10, -0.05, +0.05, +0.10):
        dd_t = DD_60_STRESS * (1 + d_pct)
        df = _classify_with(RVOL_20_STRESS, dd_t)
        grid.append({"variant": f"dd*{1+d_pct:+.0%}",
                     "rvol_20_stress": RVOL_20_STRESS,
                     "dd_60_stress": round(dd_t, 4),
                     **_filtered_perf(df["stress_regime"])})

    cols = ["variant", "rvol_20_stress", "dd_60_stress",
            "n", "sharpe", "max_dd_pct", "total_pct", "hit_pct"]
    _print_table(grid, cols)
    return {"sensitivity_grid": grid}


# --------------------------------------------------------------------------
# Robustness (Part 5)
# --------------------------------------------------------------------------

def part5(closes, ret_unfilt, regimes):
    print("\n=== PART 5 — Robustness ===")
    # Apply stress filter to get ret_filtered
    stress_series = regimes.reindex(closes.index).fillna(False)\
                              ["stress_regime"]
    ret_filtered = ret_unfilt.where(~stress_series, 0.0)

    df = pd.DataFrame({
        "ret_filtered": ret_filtered,
        "ret_unfilt":   ret_unfilt,
    }, index=closes.index)

    df["close"] = closes
    df["rvol_20"] = closes.pct_change().rolling(20).std() \
                          * math.sqrt(PERIODS_PER_YEAR)
    df["mom_60"] = closes / closes.shift(60) - 1.0

    df = df.dropna(subset=["ret_filtered"])

    # By year
    print("\n  --- By year (filtered = stress=>0) ---")
    rows = []
    for yr, sub in df.groupby(df.index.year):
        rows.append({"year": int(yr),
                     **_summarize(f"{yr}", sub["ret_filtered"].tolist())})
    _print_table(rows, ["year", "n", "sharpe", "hit_pct",
                          "total_pct", "max_dd_pct", "mean_bps"])

    # By rvol bucket
    print("\n  --- By volatility bucket ---")
    df_v = df.dropna(subset=["rvol_20"])
    if not df_v.empty:
        df_v["bucket"] = pd.qcut(df_v["rvol_20"], 4,
                                    labels=["q1_low", "q2", "q3",
                                              "q4_high"],
                                    duplicates="drop")
        vrows = []
        for b, sub in df_v.groupby("bucket", observed=True):
            vrows.append({"bucket": str(b),
                            **_summarize(str(b),
                                            sub["ret_filtered"].tolist())})
        _print_table(vrows, ["bucket", "n", "sharpe", "hit_pct",
                              "total_pct", "max_dd_pct", "mean_bps"])
    else:
        vrows = []

    # By trend strength
    print("\n  --- By trend strength bucket ---")
    df_t = df.dropna(subset=["mom_60"])
    if not df_t.empty:
        df_t["tbucket"] = pd.qcut(df_t["mom_60"], 4,
                                      labels=["t1_weak_or_neg", "t2", "t3",
                                                "t4_strong"],
                                      duplicates="drop")
        trows = []
        for b, sub in df_t.groupby("tbucket", observed=True):
            trows.append({"trend": str(b),
                            **_summarize(str(b),
                                            sub["ret_filtered"].tolist())})
        _print_table(trows, ["trend", "n", "sharpe", "hit_pct",
                              "total_pct", "max_dd_pct", "mean_bps"])
    else:
        trows = []

    return {
        "by_year": rows,
        "by_vol_bucket": vrows,
        "by_trend_bucket": trows,
    }


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main() -> int:
    print("=== Regime Quality Audit — analysis only ===")
    print(f"Logic version: {LOGIC_VERSION}")
    print(f"Defaults: rvol20>={RVOL_20_STRESS}  rvol5>={RVOL_5_STRESS}  "
            f"dd60<={DD_60_STRESS}  rvol20_calm<{RVOL_20_CALM}  "
            f"ma_fast={MA_FAST} ma_slow={MA_SLOW}")

    bars = _load_bars()
    print(f"Bars: {len(bars)}  {bars.index[0].date()} -> {bars.index[-1].date()}")

    with SessionLocal() as s:
        regimes = _load_regimes(s)
    print(f"Regime rows: {len(regimes)}")
    if regimes.empty:
        print("ABORT: no regime data; run scripts.backfill_research_regime first.")
        return 1

    closes = bars["close"].astype(float)
    sigs, ret_unfilt = _walk_tsmom(closes, h=TSMOM_HORIZON, apply_cost=True)

    p1 = part1(closes, ret_unfilt, regimes)
    p2 = part2(closes, ret_unfilt, regimes)
    p3 = part3(closes, ret_unfilt, regimes)
    p4 = part4(closes, ret_unfilt)
    p5 = part5(closes, ret_unfilt, regimes)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path("artifacts") / "regime_audit" / ts
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "logic_version": LOGIC_VERSION,
        "thresholds": {
            "rvol_20_stress": RVOL_20_STRESS,
            "rvol_5_stress": RVOL_5_STRESS,
            "dd_60_stress": DD_60_STRESS,
            "rvol_20_calm": RVOL_20_CALM,
            "ma_fast": MA_FAST, "ma_slow": MA_SLOW,
        },
        "bars": {"start": str(bars.index[0].date()),
                  "end": str(bars.index[-1].date()),
                  "n": int(len(bars))},
        "part1_per_regime": p1,
        "part2_misclassification": p2,
        "part3_transitions": p3,
        "part4_sensitivity": p4,
        "part5_robustness": p5,
    }
    (out_dir / "audit.json").write_text(json.dumps(payload, indent=2,
                                                          default=str))
    print(f"\nArtifacts: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
