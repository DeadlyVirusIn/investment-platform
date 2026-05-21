"""MA200 stress-trigger redesign audit — read-only.

Tests 5 richer MA200 candidates against the baseline stress filter:

  1. MA200_slope    — close<MA200 AND slope(MA200, 20d) < 0
  2. MA200_mom      — close<MA200 AND mom_60 < 0
  3. MA200_volexp   — close<MA200 AND rvol_20 > rvol_60 (expanding)
  4. MA200_persist  — close<MA200 for 3 consecutive closes
  5. NoMA200        — drop MA200 trigger; keep rvol_20/rvol_5/dd_60

Pure analysis. NEVER modifies thresholds, B2 logic, ENGINE_B_MODE,
ML, or risk.
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
import yfinance as yf

from apps.api.src.research.regime_backfill import (
    DD_60_STRESS, RVOL_20_STRESS, RVOL_5_STRESS,
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
        return {"label": label, "n": 0, "sharpe": None,
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
# Per-bar features
# ----------------------------------------------------------------------

def _features_at(closes, t):
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
    rvol_60 = (statistics.stdev(rets[-60:]) * math.sqrt(PERIODS_PER_YEAR)
                if len(rets) >= 60 else float("nan"))
    win60 = closes[max(0, t - 60):t + 1]
    peak = max(win60) if win60 else 1.0
    dd_60 = closes[t] / peak - 1.0 if peak > 0 else 0.0
    ma200_now = (sum(closes[max(0, t - 200):t]) / 200
                    if t >= 200 else float("nan"))
    ma200_then = (sum(closes[max(0, t - 220):t - 20]) / 200
                      if t >= 220 else float("nan"))
    ma200_slope = ((ma200_now - ma200_then) / 20
                       if math.isfinite(ma200_now)
                          and math.isfinite(ma200_then) else float("nan"))
    mom_60 = (closes[t] / closes[t - 60] - 1.0
                if t >= 60 and closes[t - 60] > 0 else float("nan"))
    # Persistence: count consecutive closes < ma200 ending at t
    persist = 0
    for i in range(t, max(0, t - 5) - 1, -1):
        ma200_i = (sum(closes[max(0, i - 200):i]) / 200
                      if i >= 200 else float("nan"))
        if math.isfinite(ma200_i) and closes[i] < ma200_i:
            persist += 1
        else:
            break
    return {
        "close": closes[t], "rvol_20": rvol_20,
        "rvol_5": rvol_5, "rvol_60": rvol_60,
        "dd_60": dd_60, "ma200": ma200_now,
        "ma200_slope": ma200_slope, "mom_60": mom_60,
        "persist_below_ma200": persist,
    }


# ----------------------------------------------------------------------
# Baseline trigger components (shared)
# ----------------------------------------------------------------------

def _vol_dd_triggers_fired(f):
    triggers = []
    if math.isfinite(f["rvol_20"]) and f["rvol_20"] >= RVOL_20_STRESS:
        triggers.append("rvol_20")
    if math.isfinite(f["rvol_5"]) and f["rvol_5"] >= RVOL_5_STRESS:
        triggers.append("rvol_5")
    if math.isfinite(f["dd_60"]) and f["dd_60"] <= DD_60_STRESS:
        triggers.append("dd_60")
    return triggers


def _ok(f, *keys):
    return f and all(math.isfinite(f.get(k, float("nan"))) for k in keys)


# ----------------------------------------------------------------------
# Candidate filters
# ----------------------------------------------------------------------

def _stress_baseline(f):
    if not _ok(f, "close", "ma200"):
        return False, []
    triggers = _vol_dd_triggers_fired(f)
    if f["close"] < f["ma200"]:
        triggers.append("close_lt_ma200")
    return bool(triggers), triggers


def _stress_slope(f):
    """Candidate 1: close<MA200 AND ma200_slope < 0."""
    if not _ok(f, "close", "ma200", "ma200_slope"):
        return False, []
    triggers = _vol_dd_triggers_fired(f)
    if f["close"] < f["ma200"] and f["ma200_slope"] < 0:
        triggers.append("close_lt_ma200_AND_slope_down")
    return bool(triggers), triggers


def _stress_mom(f):
    """Candidate 2: close<MA200 AND mom_60 < 0."""
    if not _ok(f, "close", "ma200", "mom_60"):
        return False, []
    triggers = _vol_dd_triggers_fired(f)
    if f["close"] < f["ma200"] and f["mom_60"] < 0:
        triggers.append("close_lt_ma200_AND_mom60_neg")
    return bool(triggers), triggers


def _stress_volexp(f):
    """Candidate 3: close<MA200 AND rvol_20 > rvol_60 (vol expanding)."""
    if not _ok(f, "close", "ma200", "rvol_20", "rvol_60"):
        return False, []
    triggers = _vol_dd_triggers_fired(f)
    if f["close"] < f["ma200"] and f["rvol_20"] > f["rvol_60"]:
        triggers.append("close_lt_ma200_AND_volexp")
    return bool(triggers), triggers


def _stress_persist(f):
    """Candidate 4: close<MA200 for 3 consecutive closes."""
    if not _ok(f, "close", "ma200"):
        return False, []
    triggers = _vol_dd_triggers_fired(f)
    if f.get("persist_below_ma200", 0) >= 3:
        triggers.append("close_lt_ma200_persist3")
    return bool(triggers), triggers


def _stress_no_ma200(f):
    """Candidate 5: drop MA200 trigger; keep rvol_20/rvol_5/dd_60 only."""
    if not _ok(f, "rvol_20"):
        return False, []
    triggers = _vol_dd_triggers_fired(f)
    return bool(triggers), triggers


CANDIDATES = {
    "baseline":     _stress_baseline,
    "1_slope":      _stress_slope,
    "2_mom":        _stress_mom,
    "3_volexp":     _stress_volexp,
    "4_persist3":   _stress_persist,
    "5_no_ma200":   _stress_no_ma200,
}


# ----------------------------------------------------------------------
# Strategy walk
# ----------------------------------------------------------------------

def _tsmom_pos(closes, t):
    if t < TSMOM_HORIZON: return 0
    a = closes[t - TSMOM_HORIZON]; b = closes[t]
    if a == 0: return 0
    return 1 if (b / a - 1.0) > 0 else 0


def _walk(closes, dates, filter_fn):
    cost = COST_BPS / 1e4
    n = len(closes)
    rets = [np.nan] * n
    stress_flags = [False] * n
    feats = [None] * n
    prev = 0
    for t in range(n - 1):
        if t < WARMUP:
            continue
        f = _features_at(closes, t)
        feats[t] = f
        s, _trig = filter_fn(f)
        stress_flags[t] = bool(s)
        sig = 0 if s else _tsmom_pos(closes, t)
        a = closes[t]; b = closes[t + 1]
        if a == 0 or not all(np.isfinite([a, b])):
            prev = sig; continue
        r = b / a - 1.0
        applied = sig * r - (cost if sig != prev else 0.0)
        rets[t] = applied
        prev = sig
    return (pd.Series(rets, index=dates),
              pd.Series(stress_flags, index=dates), feats)


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
# Comparison
# ----------------------------------------------------------------------

def _edge_window_bps(rets_baseline, rets_cand, last_n):
    df = pd.concat({"b": rets_baseline, "c": rets_cand}, axis=1).dropna()
    if df.empty: return None
    edge = (df["c"] - df["b"]).iloc[-last_n:] if len(df) >= last_n \
        else (df["c"] - df["b"])
    return round(float(edge.mean()) * 1e4, 2)


def _false_stress_recovery(base_stress, cand_stress, fwd_1d, base_sig, cand_sig):
    """Days where baseline=stress (sig=0) but candidate allows trade,
    and forward return > 0 → recovered missed winner. Symmetric: count
    new false-non-stress losses (candidate trades, baseline didn't,
    market lost)."""
    df = pd.concat({"bs": base_stress, "cs": cand_stress,
                       "fwd": fwd_1d, "bsig": base_sig, "csig": cand_sig},
                     axis=1).dropna()
    if df.empty:
        return {"recovered_wins": 0, "recovered_avg_bps": None,
                "new_losses": 0, "new_loss_avg_bps": None}
    rec = df[(df["bs"]) & (~df["cs"]) & (df["csig"] == 1) & (df["fwd"] > 0)]
    new_l = df[(~df["bs"]) & (~df["cs"]) & (df["csig"] == 1)
                & (df["fwd"] < 0)]
    # New losses better defined as: candidate trades when baseline did not
    new_l = df[(df["bs"]) & (~df["cs"]) & (df["csig"] == 1) & (df["fwd"] < 0)]
    return {
        "recovered_wins": int(len(rec)),
        "recovered_avg_bps":
            (round(float(rec["fwd"].mean()) * 1e4, 2)
             if len(rec) else None),
        "new_losses": int(len(new_l)),
        "new_loss_avg_bps":
            (round(float(new_l["fwd"].mean()) * 1e4, 2)
             if len(new_l) else None),
    }


def _signals_from_walk(closes, dates, filter_fn):
    """Walk producing per-day signal {0,1} (independent of returns)."""
    n = len(closes)
    sigs = [0] * n
    for t in range(n - 1):
        if t < WARMUP:
            continue
        f = _features_at(closes, t)
        s, _ = filter_fn(f)
        sigs[t] = 0 if s else _tsmom_pos(closes, t)
    return pd.Series(sigs, index=dates)


# ----------------------------------------------------------------------
# Main analysis
# ----------------------------------------------------------------------

def main() -> int:
    print("=== MA200 Redesign Audit — read-only ===")
    closes = _load_es("2001-01-01")
    dates = closes.index
    cl = list(closes.values)
    bars = pd.DataFrame({"close": closes.values}, index=dates)
    bars["fwd_1d"] = bars["close"].pct_change().shift(-1)
    print(f"Bars: {len(closes)}  {dates[0].date()} -> {dates[-1].date()}")

    # Walk all candidates
    walks: dict = {}
    print("\nWalking candidates...")
    for name, fn in CANDIDATES.items():
        rets, stress, _ = _walk(cl, dates, fn)
        sigs = _signals_from_walk(cl, dates, fn)
        walks[name] = {"rets": rets, "stress": stress, "sigs": sigs}
        print(f"  {name}: done")

    base = walks["baseline"]

    # Full-period summary
    print("\n=== Full 2001+ ===")
    rows = []
    for name in CANDIDATES:
        s = _summarize(name, walks[name]["rets"].dropna().tolist())
        s["stress_pct"] = round(
            float(walks[name]["stress"].sum()) / max(1, len(closes) - WARMUP)
            * 100, 2)
        s["edge_30d_bps"] = (
            _edge_window_bps(base["rets"], walks[name]["rets"], 30)
            if name != "baseline" else 0.0)
        s["edge_60d_bps"] = (
            _edge_window_bps(base["rets"], walks[name]["rets"], 60)
            if name != "baseline" else 0.0)
        rows.append(s)
    cols = ["label", "n", "sharpe", "max_dd_pct",
            "p95_loss_pct", "p99_loss_pct", "active_pct",
            "stress_pct", "edge_30d_bps", "edge_60d_bps"]
    _print_table(rows, cols)

    # 2018+ subwindow
    print("\n=== 2018+ subwindow ===")
    rows18 = []
    for name in CANDIDATES:
        sub = walks[name]["rets"]
        sub = sub[sub.index >= pd.Timestamp("2018-01-01")]
        s = _summarize(name + "_2018", sub.dropna().tolist())
        rows18.append(s)
    _print_table(rows18, ["label", "n", "sharpe", "max_dd_pct",
                              "p95_loss_pct", "p99_loss_pct"])

    # Single-month dependency
    print("\n=== Single-month dependency ===")
    dep_rows = []
    for name in CANDIDATES:
        rets = walks[name]["rets"].dropna()
        if rets.empty:
            dep_rows.append({"label": name, "top_month_share_pct": None})
            continue
        m = rets.groupby(rets.index.to_period("M")).sum()
        total = m.sum()
        top = (round(float(m.abs().max() / abs(total)) * 100, 2)
                if total != 0 else None)
        dep_rows.append({"label": name, "top_month_share_pct": top})
    _print_table(dep_rows, ["label", "top_month_share_pct"])

    # False-stress recovery vs new losses
    print("\n=== False-stress recovery vs new losses (vs baseline) ===")
    rec_rows = []
    for name in CANDIDATES:
        if name == "baseline":
            continue
        rec = _false_stress_recovery(
            base["stress"], walks[name]["stress"],
            bars["fwd_1d"],
            base["sigs"], walks[name]["sigs"])
        rec["candidate"] = name
        rec_rows.append(rec)
    _print_table(rec_rows,
                  ["candidate", "recovered_wins", "recovered_avg_bps",
                   "new_losses", "new_loss_avg_bps"])

    # Acceptance rules
    print("\n=== Acceptance rules ===")
    base_full = next(r for r in rows if r["label"] == "baseline")
    base_18 = next(r for r in rows18 if r["label"] == "baseline_2018")
    accept_rows = []
    for name in CANDIDATES:
        if name == "baseline":
            continue
        full = next(r for r in rows if r["label"] == name)
        sub = next(r for r in rows18 if r["label"] == name + "_2018")
        dep = next(r for r in dep_rows if r["label"] == name)

        e30 = full["edge_30d_bps"]
        e60 = full["edge_60d_bps"]
        bp95 = base_full["p95_loss_pct"]; cp95 = full["p95_loss_pct"]
        bdd = base_full["max_dd_pct"]; cdd = full["max_dd_pct"]
        bsh = base_full["sharpe"]; csh = full["sharpe"]
        top = dep["top_month_share_pct"]

        checks = [
            ("30d_edge_improves",
                e30 is not None and e30 > 0),
            ("60d_edge_not_worse",
                e60 is not None and e60 >= 0),
            ("p95_not_worse",
                bp95 is not None and cp95 is not None and cp95 >= bp95),
            ("dd_not_worse_5pct",
                bdd is not None and cdd is not None and
                cdd >= bdd * 1.05),
            ("sharpe_2001_not_worse",
                bsh is not None and csh is not None and
                csh >= bsh - 0.02),
            ("no_single_month_dep",
                top is not None and top <= 50),
            ("simple_explainable", True),
        ]
        all_pass = all(p for _, p in checks)
        accept_rows.append({
            "candidate": name, "passes_all": all_pass,
            "checks": checks,
            "metrics": {
                "edge_30d_bps": e30, "edge_60d_bps": e60,
                "sharpe": csh, "max_dd_pct": cdd,
                "p95_loss_pct": cp95, "top_month_pct": top,
                "stress_pct": full["stress_pct"],
                "sharpe_2018": sub["sharpe"],
                "dd_2018": sub["max_dd_pct"],
            },
        })
        print(f"\n  {name}:  passes_all={all_pass}")
        for n_, p_ in checks:
            print(f"    {'PASS' if p_ else 'FAIL'}  {n_}")

    # Recommendation
    print("\n=== Recommendation ===")
    survivors = [r for r in accept_rows if r["passes_all"]]
    if not survivors:
        verdict = "KEEP_CURRENT_NO_V2"
        winner = None
        rationale = ("No MA200 redesign candidate satisfies all 7 "
                       "acceptance rules. KEEP current filter and "
                       "continue pause.")
    else:
        survivors.sort(key=lambda r: (-(r["metrics"]["edge_30d_bps"] or 0),
                                            -(r["metrics"]["sharpe"] or 0)))
        winner = survivors[0]["candidate"]
        verdict = "CREATE_V2_SHADOW"
        rationale = (f"{winner} passes all acceptance rules. Recommend "
                       f"parallel shadow strategy "
                       f"tsmom_60_no_stress_v2_{winner}.")
    print(f"  VERDICT: {verdict}")
    if winner:
        print(f"  WINNER:  {winner}")
        print(f"  metrics: {[s for s in survivors if s['candidate']==winner][0]['metrics']}")

    # Persist
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path("artifacts") / "ma200_redesign" / ts
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_utc": ts,
        "full_2001": rows,
        "subwindow_2018": rows18,
        "single_month_dep": dep_rows,
        "recovery": rec_rows,
        "acceptance": accept_rows,
        "verdict": verdict, "winner": winner,
        "rationale": rationale,
    }
    (out_dir / "audit.json").write_text(
        json.dumps(payload, indent=2, default=str))
    print(f"\nArtifacts: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
