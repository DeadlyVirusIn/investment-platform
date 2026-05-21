"""Engine B2 backtest harness - shadow-only.

Compares Engine B2 (regime-aware multi-horizon TSMOM long-flat) against:
  • Engine B as-is (current production directional engine)
  • Remove Engine B (zeros on B's entry dates)
  • TSMOM 20d / 60d / 120d long-flat
  • MA 50/200 long-flat
  • Engine A only (closed paper trades)
  • Combined: Engine A + B2 vs Engine A + B

NEVER mutates trading state. Outputs report + JSON to artifacts/.

Run:
    DATABASE_URL=postgresql+psycopg://... ./.venv/Scripts/python.exe \
        -m scripts.engine_b2_simulate
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


# ---------------------------------------------------------------------------
# Stat helpers
# ---------------------------------------------------------------------------

def _sharpe(returns: Sequence[float]) -> float:
    arr = np.asarray([r for r in returns if pd.notna(r)], dtype=float)
    if len(arr) < 2:
        return float("nan")
    mu, sd = float(arr.mean()), float(arr.std(ddof=1))
    if sd == 0 or not np.isfinite(sd):
        return float("nan")
    return mu / sd * math.sqrt(PERIODS_PER_YEAR)


def _hit(returns: Sequence[float]) -> float:
    arr = np.asarray([r for r in returns if pd.notna(r)], dtype=float)
    return float((arr > 0).mean()) if len(arr) else float("nan")


def _max_dd(returns: Sequence[float]) -> float:
    arr = np.asarray([r for r in returns if pd.notna(r)], dtype=float)
    if len(arr) == 0:
        return 0.0
    eq = (1.0 + arr).cumprod()
    peak = np.maximum.accumulate(eq)
    return float((eq - peak).min() / peak.max() * 100.0)


def _summarize(label: str, returns: Sequence[float]) -> dict:
    arr = np.asarray([r for r in returns if pd.notna(r)], dtype=float)
    if len(arr) == 0:
        return {"label": label, "n": 0,
                "sharpe": None, "hit_pct": None,
                "total_pct": None, "best_pct": None, "worst_pct": None,
                "mean_bps": None, "stdev_bps": None,
                "max_dd_pct": 0.0}
    return {
        "label": label,
        "n": int(len(arr)),
        "sharpe": round(_sharpe(arr), 3),
        "hit_pct": round(_hit(arr) * 100, 2),
        "total_pct": round(float((1 + arr).prod() - 1) * 100, 2),
        "best_pct": round(float(arr.max()) * 100, 2),
        "worst_pct": round(float(arr.min()) * 100, 2),
        "mean_bps": round(float(arr.mean()) * 1e4, 2),
        "stdev_bps": round(float(arr.std(ddof=1)) * 1e4, 2),
        "max_dd_pct": round(_max_dd(arr), 2),
    }


def _print_table(rows: list[dict], cols: list[str]) -> None:
    if not rows:
        print("  (no rows)")
        return
    widths = {c: max(len(c), max(len(str(r.get(c, ""))) for r in rows))
              for c in cols}
    fmt = "  " + "  ".join(f"{{:<{widths[c]}}}" for c in cols)
    print(fmt.format(*cols))
    for r in rows:
        print(fmt.format(*[str(r.get(c, "")) for c in cols]))


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def _load_bars() -> pd.DataFrame:
    from scripts.run_phase12_price_action import fetch_es_daily
    df = fetch_es_daily(start="2018-01-01")
    df = df.copy()
    df.index = pd.to_datetime(df.index).normalize()
    df["ret"] = df["close"].pct_change()
    return df


def _load_engine_trades(session, engine: str) -> pd.DataFrame:
    rows = session.execute(text("""
        SELECT entry_date, exit_date, net_ret_pct,
               regime_at_entry, position_size_pct, status
        FROM paper_trade_log
        WHERE engine = :eng
        ORDER BY entry_date
    """), {"eng": engine}).mappings().all()
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["entry_date"] = pd.to_datetime(df["entry_date"]).dt.normalize()
    df["exit_date"] = pd.to_datetime(df["exit_date"]).dt.normalize()
    df["net_ret"] = df["net_ret_pct"].astype(float) / 100.0
    return df


def _load_regime_map(session) -> pd.DataFrame:
    """Load stress_regime + directional_regime per date.

    Prefers status='production' v1.0.0 rows; falls back to the research
    backfill (status='diagnostic', logic_version='research_backfill_v1')
    when production coverage is incomplete.
    """
    try:
        rows = session.execute(text("""
            SELECT as_of_date, context_name, value_bool
            FROM context_daily
            WHERE context_name IN ('stress_regime', 'directional_regime')
              AND (
                    status = 'production'
                 OR (status = 'diagnostic'
                      AND logic_version = 'research_backfill_v1')
                  )
        """)).mappings().all()
    except Exception:
        return pd.DataFrame()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["as_of_date"] = pd.to_datetime(df["as_of_date"]).dt.normalize()
    pivot = df.pivot_table(index="as_of_date", columns="context_name",
                              values="value_bool", aggfunc="first")
    pivot = pivot.fillna(False).astype(bool)
    return pivot


def _regime_for(date, regime_map: pd.DataFrame) -> str | None:
    if regime_map is None or regime_map.empty or date not in regime_map.index:
        return None
    row = regime_map.loc[date]
    stress = bool(row.get("stress_regime", False))
    direct = bool(row.get("directional_regime", False))
    if stress:
        return "STRESS"
    if direct:
        return "DIRECTIONAL"
    return "NEUTRAL_POS"


# ---------------------------------------------------------------------------
# Strategy simulators (long-flat with cost on flips)
# ---------------------------------------------------------------------------

def _walk_long_flat(closes: pd.Series, signal_fn,
                     min_lookback: int = 200) -> pd.Series:
    """Returns time-aligned net daily returns (FAT NaN before lookback)."""
    cost = COST_BPS_ROUND_TRIP / 1e4
    rets_out: list[float] = []
    prev_pos = 0
    closes_list = list(closes.values.astype(float))
    for t in range(len(closes_list) - 1):
        if t < min_lookback:
            rets_out.append(np.nan)
            continue
        window = closes_list[: t + 1]
        pos = signal_fn(window, t)
        a = closes_list[t]; b = closes_list[t + 1]
        if a == 0 or not np.isfinite(a) or not np.isfinite(b):
            rets_out.append(np.nan)
            prev_pos = pos
            continue
        r = b / a - 1.0
        applied = pos * r
        if pos != prev_pos:
            applied -= cost
        rets_out.append(applied)
        prev_pos = pos
    rets_out.append(np.nan)   # last bar has no forward return
    return pd.Series(rets_out, index=closes.index)


def _sig_tsmom(h: int):
    def f(closes, t):
        if len(closes) < h + 1:
            return 0
        return 1 if (closes[-1] / closes[-(h + 1)] - 1.0) > 0 else 0
    return f


def _sig_ma(fast: int, slow: int):
    def f(closes, t):
        if len(closes) < slow:
            return 0
        ma_f = sum(closes[-fast:]) / fast
        ma_s = sum(closes[-slow:]) / slow
        return 1 if ma_f > ma_s else 0
    return f


def _sig_b2(regime_map, engine_a_dates):
    a_set = set(engine_a_dates)

    def f(closes, t):
        # date corresponds to closes index t; we don't have date here,
        # so we rely on the wrapper supplying it. Use a closure on the
        # outer caller for date alignment.
        return 0   # placeholder - overridden in walk_b2
    return f


def _walk_b2(closes: pd.Series, regime_map: pd.DataFrame,
              engine_a_dates: set) -> tuple[pd.Series, list[dict]]:
    """B2 walk - needs dates (not just position) for regime + Engine A
    overlap. So we replicate the long-flat walker but enriched."""
    cost = COST_BPS_ROUND_TRIP / 1e4
    rets_out: list[float] = []
    audit: list[dict] = []
    prev_pos = 0
    dates = closes.index
    closes_list = list(closes.values.astype(float))

    for t in range(len(closes_list) - 1):
        if t < 200:
            rets_out.append(np.nan)
            continue
        window = closes_list[: t + 1]
        date_t = dates[t]
        regime = _regime_for(date_t, regime_map)
        engine_a = date_t in a_set if (a_set := engine_a_dates) else False
        decision = b2_evaluate(window, regime=regime,
                                  engine_a_active=engine_a)
        pos = 1 if decision.action == "LONG" else 0
        a = closes_list[t]; b = closes_list[t + 1]
        if a == 0 or not np.isfinite(a) or not np.isfinite(b):
            rets_out.append(np.nan)
            prev_pos = pos
            continue
        r = b / a - 1.0
        applied = pos * r
        if pos != prev_pos:
            applied -= cost
        rets_out.append(applied)
        if pos == 1:
            audit.append({
                "date": str(date_t.date()),
                "regime": regime,
                "engine_a_active": bool(engine_a),
                "trend_score": (None if not math.isfinite(decision.trend_score)
                                  else round(decision.trend_score, 4)),
                "fwd_ret_pct": round(applied * 100, 4),
            })
        prev_pos = pos
    rets_out.append(np.nan)
    return pd.Series(rets_out, index=closes.index), audit


# ---------------------------------------------------------------------------
# Engine combination helpers
# ---------------------------------------------------------------------------

def _engine_returns_aligned(engine_trades: pd.DataFrame,
                                  index: pd.DatetimeIndex) -> pd.Series:
    """Map per-trade net returns onto a daily index by entry_date.
    Days with no trade -> 0 (no exposure)."""
    s = pd.Series(0.0, index=index)
    if engine_trades is None or engine_trades.empty:
        return s
    grouped = engine_trades.groupby("entry_date")["net_ret"].sum()
    aligned = grouped.reindex(index).fillna(0.0)
    return aligned


# ---------------------------------------------------------------------------
# Sub-bucket analysis
# ---------------------------------------------------------------------------

def _bucket_by_rvol(closes: pd.Series, rets: pd.Series) -> dict:
    rvol = closes.pct_change().rolling(20).std() * math.sqrt(PERIODS_PER_YEAR)
    aligned = pd.concat([rets, rvol], axis=1).dropna()
    aligned.columns = ["ret", "rvol"]
    if aligned.empty:
        return {}
    aligned["bucket"] = pd.qcut(aligned["rvol"], 3,
                                   labels=["low", "mid", "high"],
                                   duplicates="drop")
    out = {}
    for b in aligned["bucket"].dropna().unique():
        sub = aligned[aligned["bucket"] == b]
        out[str(b)] = _summarize(f"rvol_{b}", sub["ret"].tolist())
    return out


def _monthly(rets: pd.Series) -> dict:
    if rets.dropna().empty:
        return {}
    monthly = rets.dropna().groupby(rets.dropna().index.to_period("M")).sum()
    return {str(k): round(float(v) * 100, 3) for k, v in monthly.items()}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    print("=== Engine B2 Backtest Harness - shadow only ===")
    bars = _load_bars()
    print(f"Loaded {len(bars)} bars from {bars.index[0].date()} -> "
          f"{bars.index[-1].date()}")

    with SessionLocal() as s:
        regime_map = _load_regime_map(s)
        engine_a = _load_engine_trades(s, "A")
        engine_b = _load_engine_trades(s, "B")

    print(f"Regime map covers {len(regime_map)} dates" if not regime_map.empty
          else "Regime map: empty (B2 will run permissive).")
    print(f"Engine A trades: {len(engine_a)} (closed: "
          f"{int((engine_a['status']=='closed').sum()) if not engine_a.empty else 0})")
    print(f"Engine B trades: {len(engine_b)} (closed: "
          f"{int((engine_b['status']=='closed').sum()) if not engine_b.empty else 0})")

    closes = bars["close"]
    a_set = (set(engine_a["entry_date"].dt.normalize())
              if not engine_a.empty else set())

    # Build all strategies on aligned daily index
    print("\nWalking strategies...")
    rets_tsmom20  = _walk_long_flat(closes, _sig_tsmom(20))
    rets_tsmom60  = _walk_long_flat(closes, _sig_tsmom(60))
    rets_tsmom120 = _walk_long_flat(closes, _sig_tsmom(120))
    rets_ma       = _walk_long_flat(closes, _sig_ma(50, 200))
    rets_b2, b2_audit = _walk_b2(closes, regime_map, a_set)

    # Engine A and B daily-aligned
    rets_a = _engine_returns_aligned(
        engine_a[engine_a["status"] == "closed"]
        if not engine_a.empty else engine_a,
        closes.index)
    rets_b = _engine_returns_aligned(
        engine_b[engine_b["status"] == "closed"]
        if not engine_b.empty else engine_b,
        closes.index)

    # Common index (drop bars before any has data)
    aligned = pd.concat({
        "tsmom20": rets_tsmom20, "tsmom60": rets_tsmom60,
        "tsmom120": rets_tsmom120, "ma50_200": rets_ma,
        "b2": rets_b2, "engine_a": rets_a, "engine_b": rets_b,
    }, axis=1).dropna(how="all")

    # ------------------- Phase A: standalone summaries --------------------
    print("\n=== A - Standalone strategy comparison ===")
    rows = [
        _summarize("engine_b_kept",        aligned["engine_b"].tolist()),
        _summarize("remove_engine_b",      [0.0] * int(aligned["engine_b"].astype(bool).sum())),
        _summarize("tsmom_20",             aligned["tsmom20"].tolist()),
        _summarize("tsmom_60",             aligned["tsmom60"].tolist()),
        _summarize("tsmom_120",            aligned["tsmom120"].tolist()),
        _summarize("ma_50_200",            aligned["ma50_200"].tolist()),
        _summarize("engine_b2",            aligned["b2"].tolist()),
    ]
    cols = ["label", "n", "sharpe", "hit_pct", "total_pct",
            "worst_pct", "max_dd_pct", "mean_bps"]
    _print_table(rows, cols)

    # ------------------- Phase B: combined with Engine A ------------------
    print("\n=== B - Combined: Engine A + (B|B2|none) ===")
    combined_a_only = aligned["engine_a"]
    combined_a_b    = aligned["engine_a"] + aligned["engine_b"]
    combined_a_b2   = aligned["engine_a"] + aligned["b2"]
    rows_b = [
        _summarize("engine_a_only",            combined_a_only.tolist()),
        _summarize("engine_a + engine_b",      combined_a_b.tolist()),
        _summarize("engine_a + engine_b2",     combined_a_b2.tolist()),
    ]
    _print_table(rows_b, cols)

    # ------------------- Phase C: B2 by rvol bucket -----------------------
    print("\n=== C - Engine B2 by rvol bucket ===")
    by_rvol = _bucket_by_rvol(closes, aligned["b2"])
    rows_c = [v for v in by_rvol.values()]
    if rows_c:
        _print_table(rows_c, cols)
    else:
        print("  (no rvol buckets - insufficient data)")

    # ------------------- Phase D: Engine A overlap conflict ---------------
    print("\n=== D - Engine A / B2 overlap ===")
    b2_long_dates = {pd.Timestamp(d["date"]).normalize()
                       for d in b2_audit}
    overlap = b2_long_dates & a_set
    print(f"  B2 long-days: {len(b2_long_dates)}")
    print(f"  Engine A trade-days: {len(a_set)}")
    print(f"  Same-day overlap: {len(overlap)}")
    print(f"  Overlap %: "
          f"{(len(overlap) / max(1, len(b2_long_dates))) * 100:.1f}% of B2 days")

    # ------------------- Phase E: Monthly distribution --------------------
    print("\n=== E - B2 monthly returns (sum of daily, pct) ===")
    monthly_b2 = _monthly(aligned["b2"])
    if monthly_b2:
        items = sorted(monthly_b2.items())[-12:]
        for k, v in items:
            print(f"  {k}: {v:+.2f}%")
    else:
        print("  (no monthly data)")

    # ------------------- Decision rules -----------------------------------
    print("\n=== F - Decision rules ===")
    b2_summary    = _summarize("b2", aligned["b2"].tolist())
    a_only_sum    = _summarize("a_only", combined_a_only.tolist())
    a_plus_b2_sum = _summarize("a+b2", combined_a_b2.tolist())
    a_plus_b_sum  = _summarize("a+b",  combined_a_b.tolist())

    reasons: list[str] = []
    rejections: list[str] = []
    if (b2_summary["sharpe"] or 0) <= 0:
        rejections.append(
            f"B2 standalone Sharpe={b2_summary['sharpe']} <= 0")
    if (b2_summary["sharpe"] or 0) <= 0:
        # remove_engine_b is 0 - anything <= 0 fails this rule trivially
        rejections.append("B2 fails 'better than remove Engine B' rule")
    if a_plus_b2_sum["sharpe"] is None or a_only_sum["sharpe"] is None or \
        a_plus_b2_sum["sharpe"] < a_only_sum["sharpe"]:
        rejections.append("A+B2 Sharpe <= A-only Sharpe (no system uplift)")
    if a_plus_b2_sum["max_dd_pct"] is not None and \
        a_only_sum["max_dd_pct"] is not None and \
        a_plus_b2_sum["max_dd_pct"] < a_only_sum["max_dd_pct"] * 1.20:
        # max_dd_pct is negative; "more negative" = worse
        if a_plus_b2_sum["max_dd_pct"] < a_only_sum["max_dd_pct"]:
            rejections.append(
                f"A+B2 max-DD={a_plus_b2_sum['max_dd_pct']:.2f}% worse "
                f"than A-only={a_only_sum['max_dd_pct']:.2f}%")
    overlap_frac = (len(overlap) / max(1, len(b2_long_dates)))
    if overlap_frac > 0.20:
        rejections.append(
            f"B2 overlaps Engine A on {overlap_frac:.1%} of B2-long days")
    else:
        reasons.append(
            f"Low Engine A overlap ({overlap_frac:.1%})")

    if rejections:
        verdict = "REJECT"
    elif (b2_summary["sharpe"] or 0) > 0 and \
        (a_plus_b2_sum["sharpe"] or 0) > (a_only_sum["sharpe"] or 0):
        verdict = "SHADOW_TRACK_CANDIDATE"
        reasons.append(
            f"B2 standalone Sharpe={b2_summary['sharpe']}, "
            f"system uplift "
            f"{a_plus_b2_sum['sharpe']} vs {a_only_sum['sharpe']}")
    else:
        verdict = "KEEP_RESEARCHING"

    print(f"\n  VERDICT: {verdict}")
    if reasons:
        print("  Supporting:")
        for r in reasons:
            print(f"    + {r}")
    if rejections:
        print("  Rejection rules fired:")
        for r in rejections:
            print(f"    - {r}")

    # ------------------- Persist artifacts --------------------------------
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path("artifacts") / "engine_b2" / ts
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "verdict": verdict,
        "rejections": rejections,
        "reasons": reasons,
        "standalone": rows,
        "combined": rows_b,
        "by_rvol": rows_c,
        "monthly_b2": monthly_b2,
        "engine_a_overlap": {
            "b2_long_days": len(b2_long_dates),
            "engine_a_days": len(a_set),
            "same_day_overlap": len(overlap),
            "overlap_frac_of_b2": round(overlap_frac, 4),
        },
        "n_b2_audit": len(b2_audit),
    }
    (out_dir / "report.json").write_text(json.dumps(payload, indent=2,
                                                          default=str))
    (out_dir / "b2_audit.json").write_text(json.dumps(b2_audit, indent=2,
                                                            default=str))
    print(f"\nArtifacts written: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
