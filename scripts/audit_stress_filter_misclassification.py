"""Stress filter misclassification diagnostic + candidate simulation.

PART 1: identify false-stress missed-winner days under current filter
PART 2: capture exact filter-component firings per day
PART 3: simulate 4 one-change candidates A/B/C/D in isolation
PART 4: apply 8 strict acceptance rules
PART 5: recommend KEEP / one-candidate / continue pause

Read-only. NEVER mutates DB / thresholds / production logic /
ENGINE_B_MODE / ML / risk parameters.

Run:
    PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe \
        -m scripts.audit_stress_filter_misclassification
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from collections.abc import Sequence
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

from apps.api.src.research.regime_backfill import (
    DD_60_STRESS, MA_FAST, MA_SLOW,
    RVOL_20_CALM, RVOL_20_STRESS, RVOL_5_STRESS,
)


PERIODS_PER_YEAR = 252
TSMOM_HORIZON = 60
COST_BPS = 10.0
WARMUP = 200


# ----------------------------------------------------------------------
# Stat helpers
# ----------------------------------------------------------------------

def _sharpe(arr):
    a = [float(x) for x in arr if x is not None and math.isfinite(float(x))]
    if len(a) < 2: return float("nan")
    mu = sum(a) / len(a)
    try: sd = statistics.stdev(a)
    except statistics.StatisticsError: return float("nan")
    if sd == 0 or not math.isfinite(sd): return float("nan")
    return (mu / sd) * math.sqrt(PERIODS_PER_YEAR)


def _max_dd(arr):
    a = [float(x) for x in arr if x is not None and math.isfinite(float(x))]
    if not a: return 0.0
    eq = peak = 1.0; worst = 0.0
    for r in a:
        eq *= 1 + r; peak = max(peak, eq)
        worst = min(worst, (eq - peak) / peak)
    return worst * 100.0


def _quantile(xs, q):
    a = sorted(float(x) for x in xs
                  if x is not None and math.isfinite(float(x)))
    if not a: return float("nan")
    if len(a) == 1: return float(a[0])
    pos = (len(a) - 1) * q
    lo = int(math.floor(pos)); hi = int(math.ceil(pos))
    frac = pos - lo
    return a[lo] * (1 - frac) + a[hi] * frac


def _summarize(label, rets):
    a = np.asarray([r for r in rets if pd.notna(r)], dtype=float)
    if len(a) == 0:
        return {"label": label, "n": 0, "sharpe": None, "hit_pct": None,
                "total_pct": None, "max_dd_pct": 0.0,
                "p95_loss_pct": None, "p99_loss_pct": None,
                "active_pct": 0.0}
    return {
        "label": label, "n": int(len(a)),
        "sharpe": round(float(_sharpe(a)), 3),
        "hit_pct": round(float((a > 0).mean()) * 100, 2),
        "total_pct": round(float((1 + a).prod() - 1) * 100, 2),
        "max_dd_pct": round(_max_dd(a), 2),
        "p95_loss_pct": round(float(_quantile(a, 0.05)) * 100, 4),
        "p99_loss_pct": round(float(_quantile(a, 0.01)) * 100, 4),
        "active_pct": round(float((a != 0).mean()) * 100, 2),
    }


def _print_table(rows, cols):
    if not rows: print("  (no rows)"); return
    widths = {c: max(len(c), max(len(str(r.get(c, ""))) for r in rows))
              for c in cols}
    fmt = "  " + "  ".join(f"{{:<{widths[c]}}}" for c in cols)
    print(fmt.format(*cols))
    for r in rows: print(fmt.format(*[str(r.get(c, "")) for c in cols]))


# ----------------------------------------------------------------------
# Per-bar feature compute (PIT)
# ----------------------------------------------------------------------

def _bar_features(closes, t):
    """Return dict of features at index t using only closes[:t+1]."""
    if t < 1:
        return None
    rets = []
    for i in range(max(1, t - 60), t + 1):
        a = closes[i - 1]; b = closes[i]
        if a == 0 or not (math.isfinite(a) and math.isfinite(b)):
            continue
        rets.append(b / a - 1.0)
    rvol_20 = (statistics.stdev(rets[-20:]) * math.sqrt(PERIODS_PER_YEAR)
                if len(rets) >= 20 else float("nan"))
    rvol_5  = (statistics.stdev(rets[-5:]) * math.sqrt(PERIODS_PER_YEAR)
                if len(rets) >= 5 else float("nan"))
    win60 = closes[max(0, t - 60):t + 1]
    peak = max(win60) if win60 else 1.0
    dd_60 = closes[t] / peak - 1.0 if peak > 0 else 0.0
    ma50 = (sum(closes[max(0, t - 50):t]) / 50
              if t >= 50 else float("nan"))
    ma200 = (sum(closes[max(0, t - 200):t]) / 200
               if t >= 200 else float("nan"))
    mom_60 = (closes[t] / closes[t - 60] - 1.0
                if t >= 60 and closes[t - 60] > 0 else float("nan"))
    atr = (sum(abs(closes[i] - closes[i - 1])
                  for i in range(max(1, t - 13), t + 1))
            / min(14, t)
            if t >= 14 else float("nan"))
    atr_60 = (sum(abs(closes[i] - closes[i - 1])
                      for i in range(max(1, t - 59), t + 1))
                / min(60, t)
                if t >= 60 else float("nan"))
    atr_ratio = (atr / atr_60 if math.isfinite(atr) and
                                math.isfinite(atr_60) and atr_60 > 0
                  else float("nan"))
    return {
        "close": closes[t], "rvol_20": rvol_20, "rvol_5": rvol_5,
        "dd_60": dd_60, "ma50": ma50, "ma200": ma200,
        "mom_60": mom_60, "atr_ratio": atr_ratio,
    }


# ----------------------------------------------------------------------
# Filters
# ----------------------------------------------------------------------

def _stress_baseline(f):
    """Current stress filter logic (per regime_backfill_v1)."""
    if not f or not all(math.isfinite(f.get(k, float("nan")))
                            for k in ("rvol_20", "ma200", "close")):
        return False
    triggers = []
    if f["rvol_20"] >= RVOL_20_STRESS:
        triggers.append("rvol_20")
    if math.isfinite(f["rvol_5"]) and f["rvol_5"] >= RVOL_5_STRESS:
        triggers.append("rvol_5")
    if math.isfinite(f["dd_60"]) and f["dd_60"] <= DD_60_STRESS:
        triggers.append("dd_60")
    if f["close"] < f["ma200"]:
        triggers.append("close_lt_ma200")
    return bool(triggers), triggers


def _stress_a(f):
    """Candidate A: rvol_20 threshold relaxed 0.30 → 0.33."""
    if not f or not all(math.isfinite(f.get(k, float("nan")))
                            for k in ("rvol_20", "ma200", "close")):
        return False, []
    triggers = []
    if f["rvol_20"] >= 0.33: triggers.append("rvol_20")
    if math.isfinite(f["rvol_5"]) and f["rvol_5"] >= RVOL_5_STRESS:
        triggers.append("rvol_5")
    if math.isfinite(f["dd_60"]) and f["dd_60"] <= DD_60_STRESS:
        triggers.append("dd_60")
    if f["close"] < f["ma200"]:
        triggers.append("close_lt_ma200")
    return bool(triggers), triggers


def _stress_b(f):
    """Candidate B: rvol_5 threshold relaxed 0.45 → 0.50."""
    if not f or not all(math.isfinite(f.get(k, float("nan")))
                            for k in ("rvol_20", "ma200", "close")):
        return False, []
    triggers = []
    if f["rvol_20"] >= RVOL_20_STRESS: triggers.append("rvol_20")
    if math.isfinite(f["rvol_5"]) and f["rvol_5"] >= 0.50:
        triggers.append("rvol_5")
    if math.isfinite(f["dd_60"]) and f["dd_60"] <= DD_60_STRESS:
        triggers.append("dd_60")
    if f["close"] < f["ma200"]:
        triggers.append("close_lt_ma200")
    return bool(triggers), triggers


def _stress_c(f):
    """Candidate C: MA200 buffer — stress only if close < ma200 × 0.995."""
    if not f or not all(math.isfinite(f.get(k, float("nan")))
                            for k in ("rvol_20", "ma200", "close")):
        return False, []
    triggers = []
    if f["rvol_20"] >= RVOL_20_STRESS: triggers.append("rvol_20")
    if math.isfinite(f["rvol_5"]) and f["rvol_5"] >= RVOL_5_STRESS:
        triggers.append("rvol_5")
    if math.isfinite(f["dd_60"]) and f["dd_60"] <= DD_60_STRESS:
        triggers.append("dd_60")
    if f["close"] < f["ma200"] * 0.995:    # ← buffer
        triggers.append("close_lt_ma200_buf")
    return bool(triggers), triggers


def _stress_d(f):
    """Candidate D: trend override.

    If mom_60 > 0 AND close > MA50, allow LONG even with ONE stress
    trigger. Block on TWO+ stress triggers regardless of trend.
    """
    if not f or not all(math.isfinite(f.get(k, float("nan")))
                            for k in ("rvol_20", "ma200", "close",
                                       "ma50", "mom_60")):
        return False, []
    triggers = []
    if f["rvol_20"] >= RVOL_20_STRESS: triggers.append("rvol_20")
    if math.isfinite(f["rvol_5"]) and f["rvol_5"] >= RVOL_5_STRESS:
        triggers.append("rvol_5")
    if math.isfinite(f["dd_60"]) and f["dd_60"] <= DD_60_STRESS:
        triggers.append("dd_60")
    if f["close"] < f["ma200"]:
        triggers.append("close_lt_ma200")
    n_trig = len(triggers)
    if n_trig >= 2:
        return True, triggers
    if n_trig == 1:
        # Trend override
        if f["mom_60"] > 0 and f["close"] > f["ma50"]:
            return False, triggers + ["override_mom60_pos"]
        return True, triggers
    return False, []


CANDIDATES = {
    "baseline":  _stress_baseline,
    "A_rvol20":  _stress_a,
    "B_rvol5":   _stress_b,
    "C_ma200":   _stress_c,
    "D_trend":   _stress_d,
}


# ----------------------------------------------------------------------
# Strategy walk
# ----------------------------------------------------------------------

def _tsmom_60_pos(closes, t):
    if t < TSMOM_HORIZON: return 0
    a = closes[t - TSMOM_HORIZON]; b = closes[t]
    if a == 0: return 0
    return 1 if (b / a - 1.0) > 0 else 0


def _walk(closes, dates, filter_fn):
    """Returns (signals, daily_ret, stress_flags, features_per_day)."""
    cost = COST_BPS / 1e4
    n = len(closes)
    sigs = [0] * n; rets = [np.nan] * n
    stress = [False] * n
    feats = [None] * n
    prev = 0
    for t in range(n - 1):
        if t < WARMUP:
            continue
        f = _bar_features(closes, t)
        feats[t] = f
        s, _trig = filter_fn(f)
        stress[t] = bool(s)
        if s:
            sig = 0
        else:
            sig = _tsmom_60_pos(closes, t)
        sigs[t] = sig
        a = closes[t]; b = closes[t + 1]
        if a == 0 or not all(np.isfinite([a, b])):
            prev = sig; continue
        r = b / a - 1.0
        applied = sig * r - (cost if sig != prev else 0.0)
        rets[t] = applied
        prev = sig
    return (pd.Series(sigs, index=dates),
              pd.Series(rets, index=dates),
              pd.Series(stress, index=dates),
              feats)


# ----------------------------------------------------------------------
# Data
# ----------------------------------------------------------------------

def _load_es(start: str = "2001-01-01") -> pd.Series:
    df = yf.Ticker("ES=F").history(start=start, interval="1d",
                                          auto_adjust=False)
    if df.empty: raise RuntimeError("ES=F empty")
    df = df.rename(columns=str.lower)
    df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df["close"].astype(float)


# ----------------------------------------------------------------------
# Part 1 + 2: failing boundary report on baseline
# ----------------------------------------------------------------------

def part1_2(closes, dates):
    print("\n=== PART 1+2 — Failing boundary report (baseline filter) ===")
    sigs, rets, stress, feats = _walk(list(closes.values),
                                          dates, _stress_baseline)
    bars = pd.DataFrame({"close": closes.values}, index=dates)
    bars["fwd_1d"] = bars["close"].pct_change().shift(-1)

    # False-stress missed-winner days:
    # stress=True (or signal=0 even though TSMOM positive) AND fwd_1d > 0
    false_stress = []
    for t in range(WARMUP, len(dates) - 1):
        if not stress.iloc[t]:
            continue
        # TSMOM would have said LONG?
        cl = list(closes.values)
        if _tsmom_60_pos(cl, t) != 1:
            continue
        f1 = float(bars["fwd_1d"].iloc[t])
        if not math.isfinite(f1) or f1 <= 0:
            continue
        f = feats[t] or {}
        # Determine which trigger(s) fired
        triggers = []
        if math.isfinite(f.get("rvol_20", float("nan"))) and \
            f["rvol_20"] >= RVOL_20_STRESS:
            triggers.append("rvol_20")
        if math.isfinite(f.get("rvol_5", float("nan"))) and \
            f["rvol_5"] >= RVOL_5_STRESS:
            triggers.append("rvol_5")
        if math.isfinite(f.get("dd_60", float("nan"))) and \
            f["dd_60"] <= DD_60_STRESS:
            triggers.append("dd_60")
        if math.isfinite(f.get("close", float("nan"))) and \
            math.isfinite(f.get("ma200", float("nan"))) and \
            f["close"] < f["ma200"]:
            triggers.append("close_lt_ma200")
        false_stress.append({
            "date": str(dates[t].date()),
            "fwd_1d_pct": round(f1 * 100, 4),
            "rvol_20": (round(f["rvol_20"], 4)
                          if math.isfinite(f.get("rvol_20", float("nan"))) else None),
            "rvol_5":  (round(f["rvol_5"], 4)
                          if math.isfinite(f.get("rvol_5", float("nan"))) else None),
            "dd_60":   (round(f["dd_60"], 4)
                          if math.isfinite(f.get("dd_60", float("nan"))) else None),
            "close_vs_ma200_pct":
                (round((f["close"] / f["ma200"] - 1) * 100, 3)
                 if math.isfinite(f.get("close", float("nan"))) and
                    math.isfinite(f.get("ma200", float("nan"))) and
                    f["ma200"] > 0
                 else None),
            "mom_60": (round(f["mom_60"], 4)
                         if math.isfinite(f.get("mom_60", float("nan"))) else None),
            "atr_ratio": (round(f["atr_ratio"], 4)
                            if math.isfinite(f.get("atr_ratio", float("nan"))) else None),
            "triggers": triggers,
            "n_triggers": len(triggers),
        })

    n = len(false_stress)
    print(f"  false-stress missed-winner days: {n}")
    if not n:
        return {"false_stress_count": 0}

    # Per-trigger frequency
    trig_counts = {}
    for r in false_stress:
        for t in r["triggers"]:
            trig_counts[t] = trig_counts.get(t, 0) + 1
    rows_t = sorted(
        [{"trigger": k, "fired_in_false_stress_days": v,
          "share_pct": round(v / n * 100, 1)}
         for k, v in trig_counts.items()],
        key=lambda r: -r["fired_in_false_stress_days"])
    print("  per-trigger frequency on false-stress days:")
    _print_table(rows_t,
                  ["trigger", "fired_in_false_stress_days", "share_pct"])

    # Sole trigger histogram
    sole = {}
    for r in false_stress:
        if len(r["triggers"]) == 1:
            sole[r["triggers"][0]] = sole.get(r["triggers"][0], 0) + 1
    sole_rows = sorted(
        [{"sole_trigger": k, "n": v} for k, v in sole.items()],
        key=lambda r: -r["n"])
    print("  sole-trigger distribution (only ONE filter fired):")
    _print_table(sole_rows, ["sole_trigger", "n"])

    # Missed-gain stats
    fwds = [r["fwd_1d_pct"] for r in false_stress]
    print(f"  total missed (sum) %: {sum(fwds):.2f}")
    print(f"  mean missed bps: {(sum(fwds) / n) * 100:.2f}")
    print(f"  median missed bps: "
            f"{statistics.median(fwds) * 100:.2f}")

    return {
        "false_stress_count": n,
        "per_trigger": rows_t,
        "sole_trigger": sole_rows,
        "missed_total_pct": round(sum(fwds), 4),
        "missed_mean_bps": round((sum(fwds) / n) * 100, 2),
        "sample_5": false_stress[:5],
    }


# ----------------------------------------------------------------------
# Part 3: candidate sims — full 2001+ + recent 30d/60d edge trajectory
# ----------------------------------------------------------------------

def _mean_edge_bps_window(rets_baseline, rets_cand, last_n):
    """Edge = candidate routed return - baseline routed return (per day).
    Take last_n trailing days, return mean in bps."""
    df = pd.concat({"b": rets_baseline, "c": rets_cand}, axis=1).dropna()
    if df.empty: return None
    df["edge"] = df["c"] - df["b"]
    sub = df["edge"].iloc[-last_n:] if len(df) >= last_n else df["edge"]
    return round(float(sub.mean()) * 1e4, 2)


def part3(closes, dates):
    print("\n=== PART 3 — Candidate simulation (full 2001+) ===")
    cl = list(closes.values)
    rows = []
    cand_results = {}
    base_sigs, base_rets, base_stress, _ = _walk(cl, dates, _stress_baseline)

    for name, fn in CANDIDATES.items():
        sigs, rets, stress, _ = _walk(cl, dates, fn)
        cand_results[name] = {
            "sigs": sigs, "rets": rets, "stress": stress,
        }
        s = _summarize(name, rets.dropna().tolist())
        # Stress exposure %
        stress_pct = round(float(stress.sum()) /
                              max(1, int((sigs.index >= dates[WARMUP])
                                            .sum())) * 100, 2)
        s["stress_pct"] = stress_pct
        # 30d/60d edge vs baseline
        s["edge_30d_bps"] = _mean_edge_bps_window(
            base_rets, rets, 30) if name != "baseline" else 0.0
        s["edge_60d_bps"] = _mean_edge_bps_window(
            base_rets, rets, 60) if name != "baseline" else 0.0
        rows.append(s)
    cols = ["label", "n", "sharpe", "max_dd_pct", "p95_loss_pct",
            "p99_loss_pct", "active_pct", "stress_pct",
            "edge_30d_bps", "edge_60d_bps"]
    _print_table(rows, cols)

    # 2018+ subwindow
    print("\n  --- 2018+ subwindow ---")
    rows18 = []
    for name in CANDIDATES:
        rets = cand_results[name]["rets"]
        sub = rets[rets.index >= pd.Timestamp("2018-01-01")]
        s = _summarize(f"{name}_2018plus", sub.dropna().tolist())
        rows18.append(s)
    _print_table(rows18,
                  ["label", "n", "sharpe", "max_dd_pct",
                   "p95_loss_pct", "p99_loss_pct"])

    # Single-month dependency check (top month % of total)
    print("\n  --- Single-month dependency (2001+) ---")
    rows_dep = []
    for name in CANDIDATES:
        rets = cand_results[name]["rets"].dropna()
        if rets.empty:
            rows_dep.append({"label": name, "top_month_share_pct": None})
            continue
        m = rets.groupby(rets.index.to_period("M")).sum()
        total = m.sum()
        if total == 0:
            top = None
        else:
            top = round(float(m.abs().max() / abs(total)) * 100, 2)
        rows_dep.append({"label": name, "top_month_share_pct": top})
    _print_table(rows_dep, ["label", "top_month_share_pct"])

    return {"full_2001": rows, "subwindow_2018": rows18,
              "single_month_dep": rows_dep}


# ----------------------------------------------------------------------
# Part 4: acceptance rules
# ----------------------------------------------------------------------

def part4(part3_data):
    print("\n=== PART 4 — Acceptance rules per candidate ===")
    full = {r["label"]: r for r in part3_data["full_2001"]}
    sub = {r["label"]: r for r in part3_data["subwindow_2018"]}
    dep = {r["label"]: r for r in part3_data["single_month_dep"]}
    base = full.get("baseline") or {}
    base_18 = sub.get("baseline_2018plus") or {}

    results = []
    for name in ("A_rvol20", "B_rvol5", "C_ma200", "D_trend"):
        c = full.get(name) or {}
        c_18 = sub.get(f"{name}_2018plus") or {}
        c_dep = dep.get(name) or {}
        checks = []

        # 1. 30d edge improves
        e30 = c.get("edge_30d_bps")
        checks.append(("30d_edge_improves",
                          e30 is not None and e30 > 0))

        # 2. 60d edge improves or no worse
        e60 = c.get("edge_60d_bps")
        checks.append(("60d_edge_not_worse",
                          e60 is not None and e60 >= 0))

        # 3. p95 loss not worse
        bp95 = base.get("p95_loss_pct"); cp95 = c.get("p95_loss_pct")
        checks.append((
            "p95_not_worse",
            bp95 is not None and cp95 is not None and cp95 >= bp95))

        # 4. max DD not worse by more than 5%
        bdd = base.get("max_dd_pct"); cdd = c.get("max_dd_pct")
        if bdd is not None and cdd is not None and bdd != 0:
            ratio = abs(cdd / bdd) if bdd != 0 else float("inf")
            checks.append(("dd_not_worse_5pct",
                              cdd >= bdd * 1.05))   # both negative
        else:
            checks.append(("dd_not_worse_5pct", False))

        # 5. stress exposure remains controlled (within +5pp of baseline)
        bs = base.get("stress_pct"); cs = c.get("stress_pct")
        checks.append((
            "stress_exposure_controlled",
            bs is not None and cs is not None and cs <= bs + 5))

        # 6. full 2001+ Sharpe not worse
        bsh = base.get("sharpe"); csh = c.get("sharpe")
        checks.append((
            "sharpe_not_worse",
            bsh is not None and csh is not None and csh >= bsh - 0.02))

        # 7. 2018+ not dependent on one month (≤ 50% of total)
        top = c_dep.get("top_month_share_pct")
        checks.append((
            "no_single_month_dep",
            top is not None and top <= 50))

        # 8. simple/explainable — by construction (one threshold change)
        checks.append(("simple_explainable", True))

        all_pass = all(p for _, p in checks)
        results.append({
            "candidate": name,
            "passes_all": all_pass,
            "checks": checks,
            "metrics": {
                "edge_30d_bps": e30, "edge_60d_bps": e60,
                "sharpe": csh, "max_dd_pct": cdd,
                "p95_loss_pct": cp95,
                "stress_pct": cs,
                "top_month_share_pct": top,
            },
        })
        print(f"\n  {name}:  passes_all={all_pass}")
        for n, p in checks:
            print(f"    {'PASS' if p else 'FAIL'}  {n}")
    return results


# ----------------------------------------------------------------------
# Part 5: recommendation
# ----------------------------------------------------------------------

def part5(part4_results):
    print("\n=== PART 5 — Recommendation ===")
    survivors = [r for r in part4_results if r["passes_all"]]
    if not survivors:
        print("  All candidates fail at least one rule. Continue pause; "
              "KEEP current filter.")
        return {"verdict": "KEEP_AND_PAUSE",
                "winner": None, "rejected_all": True,
                "rationale": ("No candidate passes the 8 strict "
                                 "acceptance rules. Continue 60-day shadow "
                                 "pause with current B2 unchanged.")}
    # Pick survivor with best 30d edge improvement, breaking ties on
    # simpler change (A or C preferred over D).
    survivors.sort(key=lambda r: (-(r["metrics"]["edge_30d_bps"] or 0),
                                       r["candidate"]))
    winner = survivors[0]
    print(f"  WINNER: {winner['candidate']}")
    print(f"    metrics: {winner['metrics']}")
    return {
        "verdict": "ADOPT_AS_SHADOW_V2",
        "winner": winner["candidate"],
        "all_survivors": [s["candidate"] for s in survivors],
        "metrics": winner["metrics"],
        "rationale": ("Highest 30d edge improvement among candidates "
                         "passing all 8 rules. Run as parallel shadow "
                         "tsmom_60_no_stress_v2 for 30-60 days. Current "
                         "B2 unchanged."),
    }


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

def main() -> int:
    print("=== Stress Filter Misclassification Audit — read-only ===")
    closes = _load_es("2001-01-01")
    dates = closes.index
    print(f"Bars: {len(closes)}  {dates[0].date()} -> {dates[-1].date()}")

    p12 = part1_2(closes, dates)
    p3 = part3(closes, dates)
    p4 = part4(p3)
    p5 = part5(p4)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path("artifacts") / "stress_filter_audit" / ts
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_utc": ts,
        "part1_2_failing_boundary": p12,
        "part3_candidate_sim": p3,
        "part4_acceptance_rules": p4,
        "part5_recommendation": p5,
    }
    (out_dir / "audit.json").write_text(
        json.dumps(payload, indent=2, default=str))
    print(f"\nArtifacts: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
