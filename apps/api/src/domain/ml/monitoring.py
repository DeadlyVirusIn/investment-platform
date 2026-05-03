"""ML-sizing live monitoring — alert conditions.

Two conditions tracked:
  1. Daily Sharpe delta < ML_ALERT_SHARPE_DELTA_BP for N consecutive days
     → regression alert; recommend rollback.
  2. Production running drawdown exceeds parallel-shadow DD by more than
     ML_ALERT_DD_EXCESS_PCT → drawdown excess alert.

Input = list of daily JSONL headers (from sizing_log_writer). Paper-trade
PnL snapshot lookup is injected via a callable, keeping this module
side-effect-free.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from loguru import logger

from apps.api.src.config import settings


@dataclass
class Alert:
    code: str                 # "sharpe_regression" | "dd_excess"
    severity: str             # "warn" | "critical"
    message: str
    details: dict


def _load_headers(days: int) -> list[dict]:
    """Load last `days` daily headers from artifacts/ml_sizing/*.jsonl."""
    path = Path("artifacts/ml_sizing")
    if not path.exists():
        return []
    files = sorted(path.glob("*.jsonl"))[-days:]
    headers: list[dict] = []
    for p in files:
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("kind") == "daily_header":
                    headers.append(rec)
                    break
    return headers


def check_sharpe_regression(
    daily_production_return: Callable[[dt.date], float | None],
    daily_shadow_return: Callable[[dt.date], float | None],
    n_days: int | None = None,
    threshold_bp: float | None = None,
) -> Alert | None:
    """Alert if sharpe delta < threshold_bp for N consecutive days.

    `daily_production_return` / `daily_shadow_return` are callables so the
    caller can plug in paper_trade PnL or equity-snapshot queries without
    this module importing DB code.

    threshold_bp is in basis points (negative). Example: -5.0 means -0.0005.
    """
    n_days = n_days or settings.ML_ALERT_SHARPE_CONSEC_DAYS
    threshold_bp = threshold_bp if threshold_bp is not None else settings.ML_ALERT_SHARPE_DELTA_BP
    threshold = threshold_bp / 10000.0

    headers = _load_headers(n_days)
    if len(headers) < n_days:
        return None

    breach: list[dict] = []
    for h in headers:
        d = dt.date.fromisoformat(h["as_of_date"])
        pr = daily_production_return(d)
        sh = daily_shadow_return(d)
        if pr is None or sh is None:
            continue
        delta = pr - sh
        if delta < threshold:
            breach.append({"date": str(d), "delta_bp": round(delta * 10000, 2)})
        else:
            breach.clear()   # reset streak on any non-breach day

    if len(breach) >= n_days:
        return Alert(
            code="sharpe_regression",
            severity="critical",
            message=(
                f"Production return lagged shadow by >{abs(threshold_bp)}bp "
                f"for {n_days} consecutive days. Consider rollback: "
                f"set ENABLE_ML_SIZING=0."
            ),
            details={"breach_days": breach},
        )
    return None


def check_drawdown_excess(
    production_dd_pct: float,
    shadow_dd_pct: float,
    threshold_pct: float | None = None,
) -> Alert | None:
    """Alert if production drawdown exceeds shadow drawdown by threshold_pct."""
    threshold_pct = threshold_pct if threshold_pct is not None else settings.ML_ALERT_DD_EXCESS_PCT
    excess = production_dd_pct - shadow_dd_pct  # both negative; more negative = worse
    if excess < -threshold_pct:
        return Alert(
            code="dd_excess",
            severity="critical",
            message=(
                f"Production drawdown worse than shadow by "
                f"{abs(excess):.2f}pp (> {threshold_pct}pp). "
                "Consider rollback: set ENABLE_ML_SIZING=0."
            ),
            details={
                "production_dd_pct": production_dd_pct,
                "shadow_dd_pct": shadow_dd_pct,
                "excess_pct": excess,
            },
        )
    return None


def raise_alerts(alerts: list[Alert]) -> None:
    """Emit alerts to logger. Caller may forward to alerting subsystem."""
    for a in alerts:
        logger.log(
            "ERROR" if a.severity == "critical" else "WARNING",
            "[ml_monitor] {} {}",
            a.code.upper(), a.message,
        )
