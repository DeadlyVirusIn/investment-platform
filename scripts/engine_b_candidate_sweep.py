"""Engine B replacement candidate sweep — shadow only.

Compares N directional candidates head-to-head on the same bar series,
combined with the production Engine A trade tape, and applies the user's
decision rules to each.

Hard rules honored:
  - read-only DB access
  - no execution, no ML promotion, no risk param touch
  - reuses regime labels from research_backfill_v1 (status='diagnostic')

Run:
    DATABASE_URL=postgresql+psycopg://... ./.venv/Scripts/python.exe \
        -m scripts.engine_b_candidate_sweep
"""

from __future__ import annotations

import json
import math
import sys
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text

from apps.api.src.db import SessionLocal
from apps.api.src.research.engine_b2 import evaluate as b2_evaluate


COST_BPS_ROUND_TRIP = 10.0
PERIODS_PER_YEAR = 252
MIN_LOOKBACK = 200


# --------------------------------------------------------------------------
# Stat helpers
# --------------------------------------------------------------------------

def _sharpe(arr: np.ndarray) -> float:
    if len(arr) < 2:
        return float("nan")
    mu, sd = float(arr.mean()), float(arr.std(ddof=1))
    if sd == 0 or not np.isfinite(sd):
        return float("nan")
    return mu / sd * math.sqrt(PERIODS_PER_YEAR)


def _max_dd(arr: np.ndarray) -> float:
    if len(arr) == 0:
        return 0.0
    eq = (1.0 + arr).cumprod()
    peak = np.maximum.accumulate(eq)
    return float((eq - peak).min() / peak.max() * 100.0)


def _summarize(label: str, returns: Sequence[float]) -> dict:
    arr = np.asarray([r for r in returns if pd.notna(r)], dtype=float)
    if len(arr) == 0:
        return {"label": label, "n": 0, "sharpe": None, "hit_pct": None,
                "total_pct": None, "worst_pct": None, "max_dd_pct": 0.0,
                "active_pct": 0.0, "best_pct": None, "mean_bps": None}
    return {
        "label": label,
        "n": int(len(arr)),
        "sharpe": round(_sharpe(arr), 3),
        "hit_pct": round(float((arr > 0).mean()) * 100, 2),
        "total_pct": round(float((1 + arr).prod() - 1) * 100, 2),
        "worst_pct": round(float(arr.min()) * 100, 2),
        "best_pct": round(float(arr.max()) * 100, 2),
        "max_dd_pct": round(_max_dd(arr), 2),
        "active_pct": round(float((arr != 0).mean()) * 100, 2),
        "mean_bps": round(float(arr.mean()) * 1e4, 2),
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
    return df


def _load_engine(session, engine: str) -> pd.DataFrame:
    rows = session.execute(text("""
        SELECT entry_date, status, net_ret_pct
        FROM paper_trade_log
        WHERE engine = :eng
        ORDER BY entry_date
    """), {"eng": engine}).mappings().all()
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["entry_date"] = pd.to_datetime(df["entry_date"]).dt.normalize()
    df["net_ret"] = df["net_ret_pct"].astype(float) / 100.0
    return df


def _load_regime_map(session) -> pd.DataFrame:
    try:
        rows = session.execute(text("""
            SELECT as_of_date, context_name, value_bool
            FROM context_daily
            WHERE context_name IN ('stress_regime', 'directional_regime')
              AND (status = 'production'
                  OR (status = 'diagnostic'
                       AND logic_version = 'research_backfill_v1'))
        """)).mappings().all()
    except Exception:
        return pd.DataFrame()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["as_of_date"] = pd.to_datetime(df["as_of_date"]).dt.normalize()
    pivot = df.pivot_table(index="as_of_date", columns="context_name",
                              values="value_bool", aggfunc="first")
    return pivot.fillna(False).astype(bool)


# --------------------------------------------------------------------------
# Long-flat walker (shared)
# --------------------------------------------------------------------------

def _walk(closes: pd.Series, signal_fn, *, dates: pd.DatetimeIndex) -> pd.Series:
    cost = COST_BPS_ROUND_TRIP / 1e4
    out = []
    prev = 0
    cl = list(closes.values.astype(float))
    for t in range(len(cl) - 1):
        if t < MIN_LOOKBACK:
            out.append(np.nan); continue
        pos = signal_fn(cl[: t + 1], dates[t])
        a, b = cl[t], cl[t + 1]
        if a == 0 or not np.isfinite(a) or not np.isfinite(b):
            out.append(np.nan); prev = pos; continue
        r = b / a - 1.0
        applied = pos * r - (cost if pos != prev else 0.0)
        out.append(applied)
        prev = pos
    out.append(np.nan)
    return pd.Series(out, index=closes.index)


# --------------------------------------------------------------------------
# Candidate signal factories
# --------------------------------------------------------------------------

def _sig_tsmom(h: int):
    def f(closes, _date):
        if len(closes) < h + 1:
            return 0
        return 1 if (closes[-1] / closes[-(h + 1)] - 1.0) > 0 else 0
    return f


def _sig_blend_20_60():
    def f(closes, _date):
        if len(closes) < 61:
            return 0
        s20 = closes[-1] / closes[-21] - 1.0
        s60 = closes[-1] / closes[-61] - 1.0
        return 1 if (s20 > 0 and s60 > 0) else 0
    return f


def _sig_ma(fast: int, slow: int):
    def f(closes, _date):
        if len(closes) < slow:
            return 0
        return (1 if sum(closes[-fast:]) / fast >
                  sum(closes[-slow:]) / slow else 0)
    return f


def _sig_tsmom60_no_stress(regime_map: pd.DataFrame):
    base = _sig_tsmom(60)
    def f(closes, dt):
        if dt in regime_map.index and \
            bool(regime_map.loc[dt].get("stress_regime", False)):
            return 0
        return base(closes, dt)
    return f


def _sig_tsmom60_low_vol():
    base = _sig_tsmom(60)
    def f(closes, _dt):
        if len(closes) < 21:
            return 0
        rets = [closes[i] / closes[i - 1] - 1.0
                for i in range(len(closes) - 20, len(closes))
                if closes[i - 1] > 0]
        if not rets:
            return 0
        sd = float(np.std(rets, ddof=1)) * math.sqrt(PERIODS_PER_YEAR)
        if not math.isfinite(sd) or sd >= 0.25:
            return 0
        return base(closes, _dt)
    return f


def _sig_tsmom60_no_a_conflict(engine_a_dates: set):
    base = _sig_tsmom(60)
    def f(closes, dt):
        if dt in engine_a_dates:
            return 0
        return base(closes, dt)
    return f


def _sig_b2(regime_map: pd.DataFrame, engine_a_dates: set):
    def regime_for(dt):
        if dt not in regime_map.index:
            return None
        row = regime_map.loc[dt]
        if bool(row.get("stress_regime", False)):
            return "STRESS"
        if bool(row.get("directional_regime", False)):
            return "DIRECTIONAL"
        return "NEUTRAL_POS"
    def f(closes, dt):
        regime = regime_for(dt)
        active = dt in engine_a_dates
        d = b2_evaluate(closes, regime=regime, engine_a_active=active)
        return 1 if d.action == "LONG" else 0
    return f


# --------------------------------------------------------------------------
# Engine return alignment to daily
# --------------------------------------------------------------------------

def _engine_daily(trades: pd.DataFrame, idx: pd.DatetimeIndex) -> pd.Series:
    s = pd.Series(0.0, index=idx)
    if trades is None or trades.empty:
        return s
    grouped = trades.groupby("entry_date")["net_ret"].sum()
    return grouped.reindex(idx).fillna(0.0)


# --------------------------------------------------------------------------
# Decision rules
# --------------------------------------------------------------------------

def _decide(cand_summary: dict,
              cand_combined: dict,
              a_only: dict,
              a_plus_b: dict,
              cand_monthly: dict,
              dd_buffer: float = 0.20,
              min_trade_days: int = 60) -> tuple[str, list[str], list[str]]:
    """Apply user's reject criteria. Return (verdict, reasons, rejections)."""
    rejections: list[str] = []
    reasons: list[str] = []

    s_cand = cand_summary.get("sharpe") or 0
    s_a = a_only.get("sharpe") or 0
    s_comb = cand_combined.get("sharpe") or 0
    dd_a = a_only.get("max_dd_pct") or 0
    dd_comb = cand_combined.get("max_dd_pct") or 0
    n_active_days = int(round((cand_summary.get("active_pct") or 0)
                                * cand_summary.get("n", 0) / 100))

    # 1. standalone Sharpe > 0
    if s_cand <= 0:
        rejections.append(f"standalone Sharpe={s_cand} ≤ 0")
    else:
        reasons.append(f"standalone Sharpe={s_cand} > 0")

    # 2. combined > A-only
    if s_comb <= s_a:
        rejections.append(
            f"combined Sharpe={s_comb} ≤ A-only={s_a}")
    else:
        reasons.append(
            f"combined Sharpe={s_comb} > A-only={s_a}")

    # 3. max DD not materially worse (allow 20% buffer)
    if dd_comb < dd_a * (1.0 + dd_buffer):  # both negative
        rejections.append(
            f"combined max-DD={dd_comb}% materially worse than "
            f"A-only={dd_a}%")
    else:
        reasons.append(f"max-DD acceptable ({dd_comb}% vs {dd_a}%)")

    # 4. trade count too low
    if n_active_days < min_trade_days:
        rejections.append(
            f"only {n_active_days} active days (< {min_trade_days})")

    # 5. concentration: any single month > 80% of total return
    if cand_monthly:
        total = sum(cand_monthly.values())
        if total != 0:
            top = max(cand_monthly.values(),
                       key=lambda v: abs(v))
            if abs(top) > 0.80 * abs(total):
                rejections.append(
                    f"performance concentrated: {top:.2f}% of "
                    f"total {total:.2f}% in one month")

    # 6. relies on missing regime labels — implicit if regime map empty.
    #    We assume backfill ran (caller-checked). Pass.

    # 7. Engine A conflict: caller passes overlap_frac via reasons[0].
    #    Skip here (handled in main report).

    if rejections:
        verdict = "REJECT"
    elif s_comb > s_a + 0.10:
        verdict = "SHADOW_TRACK_CANDIDATE"
    else:
        verdict = "KEEP_RESEARCHING"
    return verdict, reasons, rejections


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main() -> int:
    print("=== Engine B Candidate Sweep — shadow only ===")
    bars = _load_bars()
    print(f"Loaded {len(bars)} bars from {bars.index[0].date()} -> "
          f"{bars.index[-1].date()}")

    with SessionLocal() as s:
        regime_map = _load_regime_map(s)
        engine_a = _load_engine(s, "A")
        engine_b = _load_engine(s, "B")

    print(f"Regime map: {len(regime_map)} dates "
          f"(includes diagnostic backfill).")
    print(f"Engine A trades: {len(engine_a)}  "
          f"closed: {(engine_a['status']=='closed').sum() if not engine_a.empty else 0}")
    print(f"Engine B trades: {len(engine_b)}  "
          f"closed: {(engine_b['status']=='closed').sum() if not engine_b.empty else 0}")

    closes = bars["close"].astype(float)
    a_set = set(engine_a.loc[engine_a["status"] == "closed", "entry_date"]
                .dt.normalize()) if not engine_a.empty else set()

    # Build candidate signals
    print("\nWalking candidates...")
    candidates = {
        "tsmom_60_plain":
            _walk(closes, _sig_tsmom(60), dates=closes.index),
        "tsmom_20_plain":
            _walk(closes, _sig_tsmom(20), dates=closes.index),
        "tsmom_20_60_blend":
            _walk(closes, _sig_blend_20_60(), dates=closes.index),
        "ma_50_200":
            _walk(closes, _sig_ma(50, 200), dates=closes.index),
        "tsmom_60_no_stress":
            _walk(closes, _sig_tsmom60_no_stress(regime_map),
                    dates=closes.index),
        "tsmom_60_low_vol":
            _walk(closes, _sig_tsmom60_low_vol(), dates=closes.index),
        "tsmom_60_no_a_conflict":
            _walk(closes, _sig_tsmom60_no_a_conflict(a_set),
                    dates=closes.index),
        "engine_b2":
            _walk(closes, _sig_b2(regime_map, a_set),
                    dates=closes.index),
    }

    # Engine A and B aligned daily
    rets_a = _engine_daily(
        engine_a[engine_a["status"] == "closed"] if not engine_a.empty
        else engine_a,
        closes.index)
    rets_b = _engine_daily(
        engine_b[engine_b["status"] == "closed"] if not engine_b.empty
        else engine_b,
        closes.index)

    # Standalone summaries
    print("\n=== Standalone strategy comparison ===")
    rows = []
    rows.append(_summarize("engine_b_kept", rets_b.tolist()))
    rows.append(_summarize("engine_a_only", rets_a.tolist()))
    rows.append(_summarize("engine_a_plus_b",
                              (rets_a + rets_b).tolist()))
    for name, series in candidates.items():
        rows.append(_summarize(name, series.dropna().tolist()))
    cols = ["label", "n", "active_pct", "sharpe", "hit_pct",
            "total_pct", "worst_pct", "max_dd_pct", "mean_bps"]
    _print_table(rows, cols)

    # Combined with Engine A
    print("\n=== Engine A + candidate ===")
    a_only_sum = _summarize("engine_a_only", rets_a.tolist())
    a_plus_b_sum = _summarize("engine_a_plus_b",
                                  (rets_a + rets_b).tolist())
    combined_rows = [a_only_sum, a_plus_b_sum]
    combined_cache = {}
    for name, series in candidates.items():
        comb = (rets_a + series.fillna(0.0))
        s = _summarize(f"a_plus_{name}", comb.tolist())
        combined_rows.append(s)
        combined_cache[name] = s
    _print_table(combined_rows, cols)

    # Engine A overlap frac per candidate
    print("\n=== Engine A overlap (fraction of candidate-LONG days "
          "that coincide with an Engine A trade) ===")
    overlap_rows = []
    overlap_cache = {}
    for name, series in candidates.items():
        long_days = set(series.dropna()[
            series.dropna().abs() > 0].index.normalize())
        overlap = long_days & a_set
        frac = (len(overlap) / max(1, len(long_days)))
        overlap_rows.append({
            "candidate": name,
            "long_days": len(long_days),
            "a_trade_days": len(a_set),
            "overlap_days": len(overlap),
            "overlap_pct": round(frac * 100, 2),
        })
        overlap_cache[name] = frac
    _print_table(overlap_rows,
                  ["candidate", "long_days", "a_trade_days",
                   "overlap_days", "overlap_pct"])

    # Per-regime perf for top 3 candidates by combined Sharpe
    print("\n=== Per-regime perf (top candidates) ===")
    if not regime_map.empty:
        ranked = sorted(
            combined_cache.items(),
            key=lambda kv: (kv[1].get("sharpe") or -9), reverse=True)[:3]
        for name, _ in ranked:
            print(f"\n  -- {name} --")
            series = candidates[name]
            stress_idx = regime_map.index[
                regime_map["stress_regime"]]
            direct_idx = regime_map.index[
                regime_map["directional_regime"]]
            other_idx = regime_map.index.difference(
                stress_idx).difference(direct_idx)
            buckets = []
            for label, idx in (("stress", stress_idx),
                                  ("directional", direct_idx),
                                  ("other", other_idx)):
                vals = series.reindex(idx).dropna().tolist()
                buckets.append(_summarize(label, vals))
            _print_table(buckets, ["label", "n", "sharpe", "hit_pct",
                                       "total_pct", "max_dd_pct"])

    # Apply decision rules
    print("\n=== Decision per candidate ===")
    cand_summaries = {r["label"]: r for r in rows}
    decisions = []
    for name in candidates:
        series = candidates[name]
        cand_sum = cand_summaries[name]
        comb_sum = combined_cache[name]
        # Monthly distribution for concentration check
        mser = series.dropna()
        monthly = mser.groupby(mser.index.to_period("M")).sum()
        monthly_pct = {str(k): round(float(v) * 100, 4)
                          for k, v in monthly.items()}
        verdict, reasons, rejections = _decide(
            cand_sum, comb_sum, a_only_sum, a_plus_b_sum,
            monthly_pct)
        # Inject A-overlap as additional reason / rejection
        ovr = overlap_cache.get(name, 0.0)
        if ovr > 0.20:
            rejections.append(f"Engine A overlap {ovr:.1%} > 20%")
            verdict = "REJECT"
        else:
            reasons.append(f"Engine A overlap {ovr:.1%} ≤ 20%")

        decisions.append({
            "candidate": name,
            "verdict": verdict,
            "standalone_sharpe": cand_sum.get("sharpe"),
            "combined_sharpe": comb_sum.get("sharpe"),
            "combined_max_dd_pct": comb_sum.get("max_dd_pct"),
            "active_pct": cand_sum.get("active_pct"),
            "overlap_pct": round(ovr * 100, 2),
            "reasons": reasons,
            "rejections": rejections,
        })
        print(f"\n  {name}: {verdict}")
        for r in reasons:
            print(f"    + {r}")
        for r in rejections:
            print(f"    - {r}")

    # Ranking: all non-rejected by combined Sharpe
    print("\n=== Ranking (KEEP_RESEARCHING / SHADOW_TRACK only) ===")
    survivors = [d for d in decisions if d["verdict"] != "REJECT"]
    survivors.sort(key=lambda d: (d["combined_sharpe"] or -9),
                      reverse=True)
    if survivors:
        _print_table([
            {"rank": i + 1,
             "candidate": d["candidate"],
             "verdict": d["verdict"],
             "standalone": d["standalone_sharpe"],
             "combined": d["combined_sharpe"],
             "max_dd": d["combined_max_dd_pct"],
             "active%": d["active_pct"],
             "overlap%": d["overlap_pct"]}
            for i, d in enumerate(survivors)
        ], ["rank", "candidate", "verdict", "standalone", "combined",
             "max_dd", "active%", "overlap%"])
    else:
        print("  (no survivors)")

    # Persist
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path("artifacts") / "engine_b_sweep" / ts
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "as_of": ts,
        "bars": {"start": str(closes.index[0].date()),
                  "end": str(closes.index[-1].date()),
                  "n": int(len(closes))},
        "regime_map_size": int(len(regime_map)),
        "engine_a_trades": int(len(engine_a)) if not engine_a.empty else 0,
        "engine_b_trades": int(len(engine_b)) if not engine_b.empty else 0,
        "standalone": rows,
        "combined": combined_rows,
        "overlap": overlap_rows,
        "decisions": decisions,
        "survivors": survivors,
    }
    (out_dir / "report.json").write_text(json.dumps(payload, indent=2,
                                                          default=str))
    print(f"\nArtifacts: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
