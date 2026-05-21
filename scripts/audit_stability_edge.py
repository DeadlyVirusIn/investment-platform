"""Stability + edge confirmation audit — analysis only.

Validates tsmom_60_no_stress strategy across:
  1. Rolling 1y / 2y / 3y Sharpe
  2. Top-3 drawdowns + duration + recovery
  3. Profit / loss clustering
  4. Exposure profile (% invested, streaks)
  5. Edge decay (first half vs second half, early vs recent)
  6. Simplicity test (raw / dd-only / vol-only / full filter)
  7. Confidence score

Universe: ES=F yfinance from 2001-01-01 (single source, no stitching).
Read-only. NEVER mutates DB / labels / thresholds.

Run:
    PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe \
        -m scripts.audit_stability_edge
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
    DD_60_STRESS,
    RVOL_20_STRESS,
    RVOL_5_STRESS,
    classify_pit,
)


PERIODS_PER_YEAR = 252
TSMOM_HORIZON = 60
COST_BPS = 10.0
WARMUP_BARS = 200


# --------------------------------------------------------------------------
# Stat helpers
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


def _summarize(label: str, rets: Sequence[float]) -> dict:
    a = np.asarray([r for r in rets if pd.notna(r)], dtype=float)
    if len(a) == 0:
        return {"label": label, "n": 0, "sharpe": None, "hit_pct": None,
                "total_pct": None, "max_dd_pct": 0.0, "mean_bps": None}
    eq = (1.0 + a).cumprod()
    peak = np.maximum.accumulate(eq)
    max_dd = float(((eq - peak) / peak).min() * 100.0)
    return {
        "label": label, "n": int(len(a)),
        "sharpe": round(float(_sharpe(a)), 3),
        "hit_pct": round(float((a > 0).mean()) * 100, 2),
        "total_pct": round(float((1 + a).prod() - 1) * 100, 2),
        "max_dd_pct": round(max_dd, 2),
        "mean_bps": round(float(a.mean()) * 1e4, 2),
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
# Walk strategies
# --------------------------------------------------------------------------

def _walk(closes: pd.Series, pos_fn) -> pd.Series:
    """Generic long-flat walker. pos_fn(closes_thru_t, t, date) -> 0/1."""
    cost = COST_BPS / 1e4
    cl = list(closes.values.astype(float))
    idx = closes.index
    out = [np.nan] * len(cl)
    prev = 0
    for t in range(len(cl) - 1):
        if t < WARMUP_BARS:
            continue
        pos = pos_fn(cl, t, idx[t])
        a = cl[t]; b = cl[t + 1]
        if a == 0 or not all(np.isfinite([a, b])):
            prev = pos; continue
        r = b / a - 1.0
        applied = pos * r - (cost if pos != prev else 0.0)
        out[t] = applied
        prev = pos
    return pd.Series(out, index=idx)


def _tsmom_pos(cl, t, _date):
    if t < TSMOM_HORIZON:
        return 0
    a = cl[t - TSMOM_HORIZON]; b = cl[t]
    if a == 0:
        return 0
    return 1 if (b / a - 1.0) > 0 else 0


def _tsmom_filtered_pos(filter_fn):
    def f(cl, t, date):
        if filter_fn(cl, t, date):
            return 0
        return _tsmom_pos(cl, t, date)
    return f


def _stress_full(cl, t, date):
    """Full research_backfill_v1 stress label."""
    labels = classify_pit(date.date(), cl[: t + 1])
    return bool(labels.stress_regime)


def _stress_only_dd(cl, t, date):
    """Stress trigger using ONLY dd_60_60 ≤ -10%."""
    labels = classify_pit(date.date(), cl[: t + 1])
    if labels.insufficient_history:
        return False
    return (math.isfinite(labels.dd_60d) and labels.dd_60d <= DD_60_STRESS)


def _stress_only_vol(cl, t, date):
    """Stress trigger using ONLY rvol_20d / rvol_5d cutoffs."""
    labels = classify_pit(date.date(), cl[: t + 1])
    if labels.insufficient_history:
        return False
    return (
        (math.isfinite(labels.rvol_20d) and labels.rvol_20d >= RVOL_20_STRESS)
        or (math.isfinite(labels.rvol_5d)
              and labels.rvol_5d >= RVOL_5_STRESS)
    )


# --------------------------------------------------------------------------
# Drawdown analysis
# --------------------------------------------------------------------------

def _equity_and_drawdowns(rets: pd.Series, top_n: int = 5) -> dict:
    a = rets.dropna()
    if a.empty:
        return {"equity_final": 1.0, "dds": []}
    eq = (1.0 + a).cumprod()
    peak = eq.cummax()
    dd = (eq - peak) / peak

    # Detect drawdown episodes: contiguous regions where dd < 0
    epochs: list[dict] = []
    in_dd = False
    start_idx = None
    trough_val = 0.0
    trough_idx = None

    for i, (date, v) in enumerate(dd.items()):
        if v < 0 and not in_dd:
            in_dd = True
            start_idx = date
            trough_val = float(v)
            trough_idx = date
        elif v < 0 and in_dd:
            if v < trough_val:
                trough_val = float(v); trough_idx = date
        elif v >= 0 and in_dd:
            in_dd = False
            epochs.append({
                "start": str(start_idx.date()) if hasattr(start_idx, 'date')
                          else str(start_idx),
                "trough_date": str(trough_idx.date()) if hasattr(trough_idx, 'date')
                                  else str(trough_idx),
                "recovery": str(date.date()) if hasattr(date, 'date')
                              else str(date),
                "dd_pct": round(trough_val * 100, 3),
                "duration_days": int((date - start_idx).days),
                "recovery_days": int((date - trough_idx).days),
            })
    if in_dd:
        epochs.append({
            "start": str(start_idx.date()) if hasattr(start_idx, 'date')
                      else str(start_idx),
            "trough_date": str(trough_idx.date()) if hasattr(trough_idx, 'date')
                              else str(trough_idx),
            "recovery": "ONGOING",
            "dd_pct": round(trough_val * 100, 3),
            "duration_days": int((dd.index[-1] - start_idx).days),
            "recovery_days": -1,
        })

    epochs.sort(key=lambda d: d["dd_pct"])
    return {"equity_final": round(float(eq.iloc[-1]), 4),
              "dds": epochs[:top_n]}


# --------------------------------------------------------------------------
# Rolling Sharpe
# --------------------------------------------------------------------------

def _rolling_sharpe(rets: pd.Series, window_days: int) -> dict:
    a = rets.dropna()
    if a.empty:
        return {"window_days": window_days, "n_windows": 0,
                "min": None, "median": None, "max": None,
                "pct_negative": None, "worst_window": None}
    # Rolling annualized Sharpe over `window_days` calendar days
    # Use rolling by row count (252 ≈ 1y)
    win = window_days
    rolling_sh = a.rolling(window=win, min_periods=win).apply(
        lambda x: (x.mean() / x.std(ddof=1)) * math.sqrt(PERIODS_PER_YEAR)
        if x.std(ddof=1) > 0 else float("nan"), raw=True)
    rolling_sh = rolling_sh.dropna()
    if rolling_sh.empty:
        return {"window_days": window_days, "n_windows": 0,
                "min": None, "median": None, "max": None,
                "pct_negative": None, "worst_window": None}
    worst_idx = rolling_sh.idxmin()
    worst_start = a.index[a.index.get_loc(worst_idx) - win + 1]
    return {
        "window_days": window_days,
        "n_windows": int(len(rolling_sh)),
        "min": round(float(rolling_sh.min()), 3),
        "median": round(float(rolling_sh.median()), 3),
        "max": round(float(rolling_sh.max()), 3),
        "pct_negative": round(float((rolling_sh < 0).mean()) * 100, 2),
        "worst_window": {
            "end": str(worst_idx.date()) if hasattr(worst_idx, 'date')
                    else str(worst_idx),
            "start": str(worst_start.date()) if hasattr(worst_start, 'date')
                      else str(worst_start),
            "sharpe": round(float(rolling_sh.min()), 3),
        },
    }


# --------------------------------------------------------------------------
# Clustering
# --------------------------------------------------------------------------

def _clustering(rets: pd.Series) -> dict:
    a = rets.dropna()
    if a.empty:
        return {}
    # Profit / loss month groupings
    monthly = a.groupby(a.index.to_period("M")).sum()
    # Top-5 best / worst months
    best5 = monthly.nlargest(5)
    worst5 = monthly.nsmallest(5)
    total = monthly.sum()
    top5_share = float(best5.sum() / total) if total != 0 else 0.0
    bottom5_share = float(worst5.sum() / total) if total != 0 else 0.0

    # Hit-streak analysis: max consecutive winning / losing days (excl. zeros)
    a_sign = np.where(a > 0, 1, np.where(a < 0, -1, 0))
    max_win = max_loss = cur = 0
    cur_sign = 0
    for s in a_sign:
        if s == cur_sign and s != 0:
            cur += 1
        else:
            cur_sign = s; cur = 1 if s != 0 else 0
        if s == 1 and cur > max_win:
            max_win = cur
        if s == -1 and cur > max_loss:
            max_loss = cur

    return {
        "best_5_months": [{"month": str(m), "ret_pct": round(float(v) * 100, 3)}
                            for m, v in best5.items()],
        "worst_5_months": [{"month": str(m), "ret_pct": round(float(v) * 100, 3)}
                              for m, v in worst5.items()],
        "top_5_months_share_of_total_pct": round(top5_share * 100, 2),
        "bottom_5_months_share_of_total_pct": round(bottom5_share * 100, 2),
        "n_monthly_periods": int(len(monthly)),
        "max_consecutive_winning_days": int(max_win),
        "max_consecutive_losing_days": int(max_loss),
    }


# --------------------------------------------------------------------------
# Exposure profile
# --------------------------------------------------------------------------

def _exposure(rets: pd.Series) -> dict:
    a = rets.dropna()
    if a.empty:
        return {}
    is_active = (a != 0).astype(int).values
    # Streaks
    max_invested = max_flat = cur = 0
    cur_state = -1
    for s in is_active:
        if s == cur_state:
            cur += 1
        else:
            cur_state = s; cur = 1
        if s == 1 and cur > max_invested:
            max_invested = cur
        if s == 0 and cur > max_flat:
            max_flat = cur
    return {
        "n_total_days": int(len(a)),
        "n_invested_days": int(is_active.sum()),
        "active_pct": round(float(is_active.mean()) * 100, 2),
        "max_consecutive_invested_days": int(max_invested),
        "max_consecutive_flat_days": int(max_flat),
    }


# --------------------------------------------------------------------------
# Edge decay (split halves)
# --------------------------------------------------------------------------

def _edge_decay(rets: pd.Series) -> dict:
    a = rets.dropna()
    if a.empty:
        return {}
    mid = len(a) // 2
    first = a.iloc[:mid]
    second = a.iloc[mid:]
    # Also year-cut: 2001-2012 vs 2013-2026
    cut_year = 2013
    early = a[a.index.year < cut_year]
    recent = a[a.index.year >= cut_year]
    return {
        "split_halves": [
            {"window": "first_half", **_summarize("first_half", first.tolist())},
            {"window": "second_half", **_summarize("second_half", second.tolist())},
        ],
        "split_year_2013": [
            {"window": f"early_pre_{cut_year}",
             **_summarize(f"<{cut_year}", early.tolist())},
            {"window": f"recent_{cut_year}+",
             **_summarize(f">={cut_year}", recent.tolist())},
        ],
    }


# --------------------------------------------------------------------------
# Data loader
# --------------------------------------------------------------------------

def _load_es(start: str = "2001-01-01") -> pd.Series:
    df = yf.Ticker("ES=F").history(start=start, interval="1d",
                                          auto_adjust=False)
    if df.empty:
        raise RuntimeError("ES=F empty")
    df = df.rename(columns=str.lower)
    df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df["close"].astype(float)


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main() -> int:
    print("=== Stability + Edge Audit — analysis only ===")
    closes = _load_es("2001-01-01")
    print(f"Bars: {len(closes)}  {closes.index[0].date()} -> "
            f"{closes.index[-1].date()}")
    print(f"Strategy: TSMOM {TSMOM_HORIZON}d long-flat, cost {COST_BPS}bps")

    # ---- Build all variants
    print("\nWalking 4 variants...")
    raw     = _walk(closes, _tsmom_pos)
    full    = _walk(closes, _tsmom_filtered_pos(_stress_full))
    dd_only = _walk(closes, _tsmom_filtered_pos(_stress_only_dd))
    vol_only= _walk(closes, _tsmom_filtered_pos(_stress_only_vol))

    base_summary = _summarize("tsmom_60_no_stress (full filter)",
                                  full.tolist())
    print(f"\nBaseline filtered Sharpe={base_summary['sharpe']}, "
          f"DD={base_summary['max_dd_pct']}%, "
          f"total={base_summary['total_pct']}%, n={base_summary['n']}")

    # ---- Part 1: Rolling Sharpe
    print("\n=== PART 1 — Rolling Sharpe ===")
    rolling = []
    for label, days in (("1y", 252), ("2y", 504), ("3y", 756)):
        r = _rolling_sharpe(full, days)
        r["label"] = label
        rolling.append(r)
    _print_table(rolling, ["label", "n_windows", "min", "median", "max",
                              "pct_negative"])
    for r in rolling:
        ww = r.get("worst_window")
        if ww:
            print(f"  worst {r['label']}: {ww['start']} -> {ww['end']}  "
                  f"Sharpe={ww['sharpe']}")

    # ---- Part 2: Worst drawdowns
    print("\n=== PART 2 — Worst-case drawdowns ===")
    dd_info = _equity_and_drawdowns(full, top_n=5)
    print(f"  equity_final: {dd_info['equity_final']:.3f}x")
    rows = dd_info["dds"]
    _print_table(rows, ["start", "trough_date", "recovery",
                          "dd_pct", "duration_days", "recovery_days"])

    # ---- Part 3: Clustering
    print("\n=== PART 3 — Profit / loss clustering ===")
    cluster = _clustering(full)
    print(f"  monthly periods: {cluster.get('n_monthly_periods')}")
    print(f"  top-5 months share of total return: "
          f"{cluster.get('top_5_months_share_of_total_pct')}%")
    print(f"  bottom-5 months share: "
          f"{cluster.get('bottom_5_months_share_of_total_pct')}%")
    print(f"  max consec WIN days: "
          f"{cluster.get('max_consecutive_winning_days')}")
    print(f"  max consec LOSS days: "
          f"{cluster.get('max_consecutive_losing_days')}")
    print("  --- top 5 months ---")
    _print_table(cluster.get("best_5_months", []), ["month", "ret_pct"])
    print("  --- bottom 5 months ---")
    _print_table(cluster.get("worst_5_months", []), ["month", "ret_pct"])

    # ---- Part 4: Exposure
    print("\n=== PART 4 — Exposure profile ===")
    exposure = _exposure(full)
    print(f"  active%: {exposure.get('active_pct')}")
    print(f"  max consec invested: "
          f"{exposure.get('max_consecutive_invested_days')}")
    print(f"  max consec flat: "
          f"{exposure.get('max_consecutive_flat_days')}")

    # ---- Part 5: Edge decay
    print("\n=== PART 5 — Edge decay ===")
    decay = _edge_decay(full)
    print("  split halves:")
    _print_table(decay.get("split_halves", []),
                  ["window", "n", "sharpe", "hit_pct",
                   "total_pct", "max_dd_pct"])
    print("  split at year 2013:")
    _print_table(decay.get("split_year_2013", []),
                  ["window", "n", "sharpe", "hit_pct",
                   "total_pct", "max_dd_pct"])

    # ---- Part 6: Simplicity test
    print("\n=== PART 6 — Simplicity test ===")
    rows = [
        _summarize("tsmom60_raw (no filter)",   raw.dropna().tolist()),
        _summarize("tsmom60_dd_only_filter",    dd_only.dropna().tolist()),
        _summarize("tsmom60_vol_only_filter",   vol_only.dropna().tolist()),
        _summarize("tsmom60_full_filter (current)", full.dropna().tolist()),
    ]
    _print_table(rows, ["label", "n", "sharpe", "hit_pct",
                          "total_pct", "max_dd_pct", "mean_bps"])

    # ---- Part 7: Confidence score
    print("\n=== PART 7 — Confidence score ===")
    score, score_breakdown = _confidence_score(
        rolling, dd_info, cluster, exposure, decay, rows)
    print(f"\n  CONFIDENCE: {score} / 100")
    for k, v in score_breakdown.items():
        print(f"    {k}: {v}")

    # Persist
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path("artifacts") / "stability_audit" / ts
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_utc": ts,
        "universe": {"symbol": "ES=F", "start": "2001-01-01",
                       "n_bars": int(len(closes)),
                       "first": str(closes.index[0].date()),
                       "last": str(closes.index[-1].date())},
        "params": {"tsmom_horizon": TSMOM_HORIZON, "cost_bps": COST_BPS,
                     "warmup_bars": WARMUP_BARS},
        "baseline_summary": base_summary,
        "part1_rolling_sharpe": rolling,
        "part2_drawdowns": dd_info,
        "part3_clustering": cluster,
        "part4_exposure": exposure,
        "part5_edge_decay": decay,
        "part6_simplicity": rows,
        "part7_confidence": {"score": score,
                                 "breakdown": score_breakdown},
    }
    (out_dir / "audit.json").write_text(json.dumps(payload, indent=2,
                                                          default=str))
    print(f"\nArtifacts: {out_dir}")
    return 0


def _confidence_score(rolling, dd, cluster, exposure, decay,
                          simplicity) -> tuple[int, dict]:
    """Programmatic confidence score (0-100). Each criterion weighted."""
    breakdown: dict[str, str] = {}
    score = 0

    # Rolling Sharpe (30 pts): 3y must have >=80% positive windows
    r3y = next((r for r in rolling if r["label"] == "3y"), None)
    if r3y and r3y["pct_negative"] is not None:
        pos_pct = 100 - r3y["pct_negative"]
        if pos_pct >= 90:
            score += 30; breakdown["rolling_3y_>=90%_positive"] = "✓ +30"
        elif pos_pct >= 80:
            score += 22; breakdown["rolling_3y_>=80%_positive"] = "✓ +22"
        elif pos_pct >= 70:
            score += 15; breakdown["rolling_3y_>=70%_positive"] = "~ +15"
        else:
            breakdown["rolling_3y_<70%_positive"] = f"✗ +0 ({pos_pct:.0f}%)"

    # Worst drawdown (15 pts): top DD shouldn't exceed -30%
    if dd.get("dds"):
        worst = dd["dds"][0]["dd_pct"]
        if worst > -20:
            score += 15; breakdown["worst_dd_>-20%"] = f"✓ +15 ({worst}%)"
        elif worst > -30:
            score += 10; breakdown["worst_dd_>-30%"] = f"~ +10 ({worst}%)"
        else:
            breakdown["worst_dd_<-30%"] = f"✗ +0 ({worst}%)"

    # Recovery time (10 pts): top DD recovery < 1 year
    if dd.get("dds"):
        rec = dd["dds"][0].get("recovery_days")
        if rec is not None and rec >= 0:
            if rec < 252:
                score += 10; breakdown["recovery_<1yr"] = f"✓ +10 ({rec}d)"
            elif rec < 504:
                score += 5; breakdown["recovery_<2yr"] = f"~ +5 ({rec}d)"
            else:
                breakdown["recovery_long"] = f"✗ +0 ({rec}d)"

    # Clustering (15 pts): top-5 months should be < 50% of total
    top5 = cluster.get("top_5_months_share_of_total_pct")
    if top5 is not None:
        if top5 < 30:
            score += 15; breakdown["clustering_<30%"] = f"✓ +15 ({top5}%)"
        elif top5 < 50:
            score += 10; breakdown["clustering_<50%"] = f"~ +10 ({top5}%)"
        else:
            breakdown["clustering_>=50%"] = f"✗ +0 ({top5}%)"

    # Exposure (10 pts): active % between 50% and 90%
    act = exposure.get("active_pct")
    if act is not None:
        if 60 <= act <= 90:
            score += 10; breakdown["active_60-90%"] = f"✓ +10 ({act}%)"
        elif 40 <= act <= 95:
            score += 6; breakdown["active_40-95%"] = f"~ +6 ({act}%)"
        else:
            breakdown["active_extreme"] = f"✗ +0 ({act}%)"

    # Edge decay (10 pts): both halves must be Sharpe > 0
    halves = decay.get("split_halves", [])
    if len(halves) == 2:
        s1, s2 = halves[0]["sharpe"], halves[1]["sharpe"]
        if s1 is not None and s2 is not None:
            if min(s1, s2) > 0.5:
                score += 10
                breakdown["both_halves>0.5"] = f"✓ +10 ({s1}/{s2})"
            elif min(s1, s2) > 0:
                score += 6
                breakdown["both_halves>0"] = f"~ +6 ({s1}/{s2})"
            else:
                breakdown["one_half_negative"] = f"✗ +0 ({s1}/{s2})"

    # Simplicity (10 pts): full filter must beat raw + each-only
    if len(simplicity) >= 4:
        raw_s = simplicity[0]["sharpe"]
        full_s = simplicity[3]["sharpe"]
        if raw_s is not None and full_s is not None and full_s > raw_s:
            score += 10
            breakdown["full_filter_beats_raw"] = \
                f"✓ +10 ({full_s} > {raw_s})"
        else:
            breakdown["full_filter_does_not_beat_raw"] = \
                f"✗ +0 ({full_s} vs {raw_s})"

    return score, breakdown


if __name__ == "__main__":
    sys.exit(main())
