"""Shadow strategy metrics API.

Read-only. Returns rolling Sharpe / drawdown / hit rate / regime split
for shadow strategy candidates tracked in paper_shadow_log. Never
exposes mutation endpoints.
"""

from __future__ import annotations

import math
import statistics
from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.db import SessionLocal


router = APIRouter(prefix="/shadow", tags=["shadow"])

PERIODS_PER_YEAR = 252
DEFAULT_STRATEGY = "tsmom_60_no_stress"


def _s() -> Session:
    return SessionLocal()


def _sharpe(rets: list[float]) -> float | None:
    arr = [float(r) for r in rets if r is not None and math.isfinite(float(r))]
    if len(arr) < 2:
        return None
    mu = sum(arr) / len(arr)
    try:
        sd = statistics.stdev(arr)
    except statistics.StatisticsError:
        return None
    if sd == 0 or not math.isfinite(sd):
        return None
    return (mu / sd) * math.sqrt(PERIODS_PER_YEAR)


def _max_dd_pct(applied_returns: list[float]) -> float:
    eq = 1.0
    peak = 1.0
    worst = 0.0
    for r in applied_returns:
        if r is None or not math.isfinite(float(r)):
            continue
        eq *= 1 + float(r)
        peak = max(peak, eq)
        worst = min(worst, (eq - peak) / peak)
    return worst * 100.0


def _applied(rows: list[dict]) -> list[float]:
    """Map rows → 'as-traded' daily returns: fwd_1d if signal=LONG else 0."""
    out: list[float] = []
    for r in rows:
        sig = r.get("signal")
        ret = r.get("fwd_return_1d")
        if ret is None:
            continue
        if sig == "LONG":
            out.append(float(ret))
        else:
            out.append(0.0)
    return out


def _hit_rate(rows: list[dict]) -> float | None:
    longs = [r for r in rows
              if r.get("signal") == "LONG"
              and r.get("fwd_return_1d") is not None]
    if not longs:
        return None
    wins = sum(1 for r in longs if float(r["fwd_return_1d"]) > 0)
    return wins / len(longs)


@router.get("/strategies")
async def list_strategies() -> dict[str, Any]:
    with _s() as s:
        rows = s.execute(text("""
            SELECT source_strategy,
                   COUNT(*) AS n,
                   MIN(as_of_date) AS first_date,
                   MAX(as_of_date) AS last_date
              FROM paper_shadow_log
             GROUP BY source_strategy
             ORDER BY source_strategy
        """)).mappings().all()
    return {"strategies": [dict(r) for r in rows]}


@router.get("/strategy/{name}")
async def get_strategy(
    name: str = DEFAULT_STRATEGY,
    days: int = 365,
) -> dict[str, Any]:
    """Return current signal + recent + cumulative + rolling Sharpe + DD.

    `days` clamps the response window. The cumulative + rolling stats
    are computed across the requested window (oldest-first).
    """
    if days < 1 or days > 5000:
        raise HTTPException(status_code=400,
                              detail="days must be 1..5000")
    cutoff = date.today() - timedelta(days=days + 7)
    with _s() as s:
        rows = s.execute(text("""
            SELECT as_of_date, instrument, signal,
                   entry_price, exit_price,
                   fwd_return_1d, fwd_return_5d,
                   regime_label, engine_a_active,
                   trend_score, note,
                   created_at, updated_at
              FROM paper_shadow_log
             WHERE source_strategy = :name
               AND as_of_date >= :cutoff
             ORDER BY as_of_date ASC
        """), {"name": name, "cutoff": cutoff}).mappings().all()
        rows = [dict(r) for r in rows]

    if not rows:
        return {
            "strategy": name,
            "n_rows": 0,
            "current": None,
            "recent": [],
            "metrics": None,
        }

    # Current = last row
    current = rows[-1]
    last10 = rows[-10:][::-1]   # newest first

    applied = _applied(rows)
    cumulative_pct = (math.prod(1 + r for r in applied if r is not None)
                         - 1.0) * 100.0 if applied else 0.0
    sharpe_full = _sharpe(applied)
    max_dd_pct = _max_dd_pct(applied)

    # Rolling windows (calendar-day backwards from latest row)
    def _rolling(window_days: int) -> dict[str, Any]:
        cut = current["as_of_date"] - timedelta(days=window_days)
        sub = [r for r in rows if r["as_of_date"] > cut]
        applied_sub = _applied(sub)
        return {
            "window_days": window_days,
            "n": len(sub),
            "sharpe": _sharpe(applied_sub),
            "cumulative_pct":
                round((math.prod(1 + r for r in applied_sub
                                       if r is not None) - 1.0) * 100.0, 4)
                if applied_sub else 0.0,
            "max_dd_pct": round(_max_dd_pct(applied_sub), 4),
        }

    # Activity split
    n_long = sum(1 for r in rows if r["signal"] == "LONG")
    n_flat = sum(1 for r in rows if r["signal"] == "FLAT")
    n_filtered_stress = sum(
        1 for r in rows
        if r["signal"] == "FLAT" and r.get("regime_label") == "STRESS")
    n_total = len(rows)

    # Per-regime perf (1d returns weighted by signal)
    regimes = {}
    for r in rows:
        reg = r.get("regime_label") or "UNKNOWN"
        regimes.setdefault(reg, []).append(r)
    regime_perf = []
    for reg, rs in regimes.items():
        applied_r = _applied(rs)
        regime_perf.append({
            "regime": reg,
            "n_days": len(rs),
            "n_long": sum(1 for r in rs if r["signal"] == "LONG"),
            "sharpe": _sharpe(applied_r),
            "cumulative_pct":
                round((math.prod(1 + r for r in applied_r
                                       if r is not None) - 1.0) * 100.0, 4)
                if applied_r else 0.0,
        })

    # Hit rate on LONG entries
    hit_rate = _hit_rate(rows)

    # Recent series for charting
    series = [
        {"date": r["as_of_date"].isoformat()
                  if hasattr(r["as_of_date"], "isoformat")
                  else str(r["as_of_date"]),
         "signal": r["signal"],
         "fwd_return_1d": (float(r["fwd_return_1d"])
                              if r["fwd_return_1d"] is not None else None),
         "regime": r.get("regime_label")}
        for r in rows
    ]

    # Equity curve (cumulative product of 1+applied)
    equity_curve = []
    eq = 1.0
    for r, a in zip(rows, applied):
        eq *= (1 + a) if a is not None else 1.0
        equity_curve.append({
            "date": r["as_of_date"].isoformat()
                      if hasattr(r["as_of_date"], "isoformat")
                      else str(r["as_of_date"]),
            "equity": round(eq, 6),
        })

    return {
        "strategy": name,
        "n_rows": n_total,
        "current": {
            "as_of_date": current["as_of_date"].isoformat()
                if hasattr(current["as_of_date"], "isoformat")
                else str(current["as_of_date"]),
            "signal": current["signal"],
            "regime": current.get("regime_label"),
            "trend_score": (float(current["trend_score"])
                              if current.get("trend_score") is not None
                              else None),
            "engine_a_active": bool(current.get("engine_a_active")),
            "note": current.get("note"),
        },
        "recent": [
            {
                "as_of_date": r["as_of_date"].isoformat()
                    if hasattr(r["as_of_date"], "isoformat")
                    else str(r["as_of_date"]),
                "signal": r["signal"],
                "regime": r.get("regime_label"),
                "fwd_return_1d": (float(r["fwd_return_1d"])
                                    if r["fwd_return_1d"] is not None
                                    else None),
                "fwd_return_5d": (float(r["fwd_return_5d"])
                                    if r["fwd_return_5d"] is not None
                                    else None),
                "trend_score": (float(r["trend_score"])
                                  if r.get("trend_score") is not None
                                  else None),
            } for r in last10
        ],
        "metrics": {
            "cumulative_pct": round(cumulative_pct, 4),
            "sharpe_full": sharpe_full,
            "max_dd_pct": round(max_dd_pct, 4),
            "hit_rate_on_long_pct": (round(hit_rate * 100, 2)
                                          if hit_rate is not None else None),
            "n_total": n_total,
            "n_long": n_long,
            "n_flat": n_flat,
            "n_filtered_stress": n_filtered_stress,
            "active_pct": round((n_long / n_total) * 100, 2)
                if n_total else 0.0,
            "filtered_stress_pct": round(
                (n_filtered_stress / n_total) * 100, 2)
                if n_total else 0.0,
            "rolling": [_rolling(30), _rolling(60), _rolling(90)],
            "by_regime": regime_perf,
            "advisory_only": True,
            "execution_changed": False,
        },
        "equity_curve": equity_curve,
        "series": series,
    }


@router.get("/strategy/{name}/divergence")
async def divergence(name: str = DEFAULT_STRATEGY) -> dict[str, Any]:
    """Compare shadow strategy 1d returns to Engine A and Engine B
    daily aggregates over the same dates. Read-only."""
    with _s() as s:
        rows = s.execute(text("""
            SELECT as_of_date, signal, fwd_return_1d
              FROM paper_shadow_log
             WHERE source_strategy = :name
               AND fwd_return_1d IS NOT NULL
             ORDER BY as_of_date
        """), {"name": name}).mappings().all()
        rows = [dict(r) for r in rows]
        if not rows:
            return {"strategy": name, "n": 0,
                    "vs_engine_a": None, "vs_engine_b": None}
        dates = [r["as_of_date"] for r in rows]
        a = s.execute(text("""
            SELECT entry_date, SUM(net_ret_pct) / 100.0 AS r
              FROM paper_trade_log
             WHERE engine = 'A' AND status = 'closed'
               AND entry_date = ANY(:dates)
             GROUP BY entry_date
        """), {"dates": dates}).mappings().all()
        a_map = {row["entry_date"]: float(row["r"]) for row in a
                  if row["r"] is not None}
        b = s.execute(text("""
            SELECT entry_date, SUM(net_ret_pct) / 100.0 AS r
              FROM paper_trade_log
             WHERE engine = 'B' AND status = 'closed'
               AND entry_date = ANY(:dates)
             GROUP BY entry_date
        """), {"dates": dates}).mappings().all()
        b_map = {row["entry_date"]: float(row["r"]) for row in b
                  if row["r"] is not None}

    diff_a = []
    diff_b = []
    for r in rows:
        sig = r["signal"]
        sret = float(r["fwd_return_1d"]) if sig == "LONG" else 0.0
        d = r["as_of_date"]
        a_r = a_map.get(d, 0.0)
        b_r = b_map.get(d, 0.0)
        diff_a.append(sret - a_r)
        diff_b.append(sret - b_r)

    def _stats(diffs):
        if not diffs:
            return None
        mu = sum(diffs) / len(diffs)
        try:
            sd = statistics.stdev(diffs)
        except statistics.StatisticsError:
            sd = 0.0
        return {
            "n": len(diffs),
            "mean_bps": round(mu * 1e4, 2),
            "stdev_bps": round(sd * 1e4, 2),
            "cumulative_pct": round(
                (math.prod(1 + d for d in diffs) - 1.0) * 100.0, 4),
        }

    return {
        "strategy": name,
        "n": len(rows),
        "vs_engine_a": _stats(diff_a),
        "vs_engine_b": _stats(diff_b),
        "advisory_only": True,
    }
