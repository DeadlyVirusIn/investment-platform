"""Deterministic edge validation — Step 2 hard gate before ML training.

Computes Sharpe of deterministic engine on historical_label rows and
compares against (a) SPY buy-hold and (b) random-symbol baseline.

PASS iff:
    engine_sharpe >= max(spy_sharpe + 0.2, random_sharpe + 0.4)
    AND engine_max_dd_pct >= -25

Writes gate-state JSON to artifacts/ml_gate.json. Training CLI reads it.

Usage::

    python -m scripts.validate_edge
    python -m scripts.validate_edge --spy-symbol SPY
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import random
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean, stdev

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.src.db import SessionLocal
from apps.api.src.db.models import HistoricalLabel, PriceBar, Asset
from apps.api.src.domain.stock_engine.scoring import MODEL_VERSION

GATE_PATH = Path("artifacts/ml_gate.json")
SHARPE_UPLIFT_VS_SPY = 0.2
SHARPE_UPLIFT_VS_RANDOM = 0.4
MAX_DD_FLOOR_PCT = -25.0
TRADING_DAYS = 252


# ---------------------------------------------------------------------------
# Metric helpers
# ---------------------------------------------------------------------------


def _sharpe(daily_returns: list[float]) -> float:
    if len(daily_returns) < 5:
        return 0.0
    m = mean(daily_returns)
    s = stdev(daily_returns) if len(daily_returns) > 1 else 0.0
    if s == 0:
        return 0.0
    return (m / s) * math.sqrt(TRADING_DAYS)


def _max_drawdown_pct(daily_returns: list[float]) -> float:
    if not daily_returns:
        return 0.0
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    for r in daily_returns:
        equity *= (1.0 + r)
        if equity > peak:
            peak = equity
        dd = (equity - peak) / peak
        if dd < max_dd:
            max_dd = dd
    return max_dd * 100.0


def _annualized_return(daily_returns: list[float]) -> float:
    if not daily_returns:
        return 0.0
    equity = 1.0
    for r in daily_returns:
        equity *= (1.0 + r)
    years = len(daily_returns) / TRADING_DAYS
    if years <= 0:
        return 0.0
    return (equity ** (1.0 / years) - 1.0) * 100.0


# ---------------------------------------------------------------------------
# Strategy PnL from historical_label
# ---------------------------------------------------------------------------


def _engine_daily_returns(
    session: Session, engine_version: str,
) -> tuple[list[float], int, float]:
    """Daily portfolio returns from engine Buy signals.

    Simple model: each day, take equal-weight position across ALL Buy
    labels resolved on that day. Daily return = mean(forward_return_pct) / 100
    spread over n_bars (divide by n_bars to get bar-level contribution).

    Returns (daily_returns, trade_count, hit_rate_pct).
    """
    rows = list(
        session.execute(
            select(HistoricalLabel).where(
                HistoricalLabel.engine_version == engine_version,
                HistoricalLabel.action == "Buy",
            )
        ).scalars().all()
    )
    if not rows:
        return [], 0, 0.0

    # Group by as_of_date, compute mean return; amortize over n_bars as
    # naive daily sleeve.
    by_day: dict[dt.date, list[float]] = defaultdict(list)
    hits = 0
    for r in rows:
        ret = float(r.forward_return_pct) / 100.0
        n = max(1, r.barrier_n_bars)
        daily_equiv = ret / n
        by_day[r.as_of_date].append(daily_equiv)
        if r.label == 1:
            hits += 1

    # Expand each trade over its n_bars horizon (approximate)
    daily_returns: list[float] = []
    sorted_days = sorted(by_day.keys())
    for d in sorted_days:
        daily_returns.append(sum(by_day[d]) / max(1, len(by_day[d])))

    return daily_returns, len(rows), (hits / len(rows) * 100.0)


def _spy_daily_returns(
    session: Session, symbol: str, start: dt.date, end: dt.date,
) -> list[float]:
    asset = session.execute(
        select(Asset).where(Asset.symbol == symbol)
    ).scalar_one_or_none()
    if asset is None:
        logger.warning("[validate_edge] benchmark symbol {} missing", symbol)
        return []
    stmt = (
        select(PriceBar)
        .where(
            PriceBar.asset_id == asset.id,
            PriceBar.timeframe == "1d",
            PriceBar.ts >= dt.datetime.combine(start, dt.time(0, 0, 0)),
            PriceBar.ts <= dt.datetime.combine(end, dt.time(23, 59, 59)),
        )
        .order_by(PriceBar.ts.asc())
    )
    bars = list(session.execute(stmt).scalars().all())
    closes = [float(b.close) for b in bars if b.close is not None]
    rets = []
    for i in range(1, len(closes)):
        if closes[i - 1] > 0:
            rets.append(closes[i] / closes[i - 1] - 1.0)
    return rets


def _random_daily_returns(
    session: Session, engine_version: str, seed: int = 42,
) -> list[float]:
    """Random-symbol baseline: for each Buy day, pick a random universe
    symbol's realized forward return instead of the engine's pick."""
    rows = list(
        session.execute(
            select(HistoricalLabel).where(
                HistoricalLabel.engine_version == engine_version,
            )
        ).scalars().all()
    )
    if not rows:
        return []

    by_day: dict[dt.date, list[HistoricalLabel]] = defaultdict(list)
    for r in rows:
        by_day[r.as_of_date].append(r)

    rng = random.Random(seed)
    daily_returns: list[float] = []
    for d in sorted(by_day.keys()):
        pool = by_day[d]
        pick = rng.choice(pool)
        n = max(1, pick.barrier_n_bars)
        daily_returns.append((float(pick.forward_return_pct) / 100.0) / n)
    return daily_returns


# ---------------------------------------------------------------------------
# Regime-stratified Sharpe
# ---------------------------------------------------------------------------


def _stratified_sharpe(
    session: Session, engine_version: str,
) -> dict[str, float]:
    rows = list(
        session.execute(
            select(HistoricalLabel).where(
                HistoricalLabel.engine_version == engine_version,
                HistoricalLabel.action == "Buy",
            )
        ).scalars().all()
    )
    buckets: dict[str, dict[dt.date, list[float]]] = {
        "uptrend_normal":   defaultdict(list),
        "uptrend_high":     defaultdict(list),
        "sideways_normal":  defaultdict(list),
        "sideways_high":    defaultdict(list),
        "downtrend_normal": defaultdict(list),
        "downtrend_high":   defaultdict(list),
    }
    for r in rows:
        trend = (r.market_trend or "unknown").lower()
        vol = (r.vol_regime or "unknown").lower()
        # Map trend to canonical label
        if "up" in trend:
            t = "uptrend"
        elif "down" in trend:
            t = "downtrend"
        else:
            t = "sideways"
        v = "high" if vol == "high" else "normal"
        key = f"{t}_{v}"
        if key not in buckets:
            continue
        ret = float(r.forward_return_pct) / 100.0
        n = max(1, r.barrier_n_bars)
        buckets[key][r.as_of_date].append(ret / n)

    out = {}
    for name, by_day in buckets.items():
        daily = [
            sum(by_day[d]) / max(1, len(by_day[d]))
            for d in sorted(by_day.keys())
        ]
        out[name] = {
            "sharpe": round(_sharpe(daily), 3),
            "days": len(daily),
        }
    return out


# ---------------------------------------------------------------------------
# Gate writer
# ---------------------------------------------------------------------------


def _write_gate(state: dict) -> None:
    GATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    GATE_PATH.write_text(json.dumps(state, indent=2, default=str))
    logger.info("[validate_edge] gate written → {}", GATE_PATH)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate deterministic edge.")
    parser.add_argument("--spy-symbol", default="SPY")
    parser.add_argument("--engine-version", default=MODEL_VERSION)
    args = parser.parse_args()

    with SessionLocal() as session:
        eng_rets, trade_count, hit_rate = _engine_daily_returns(
            session, args.engine_version,
        )
        if not eng_rets:
            logger.error(
                "[validate_edge] no engine Buy labels for engine_version={}",
                args.engine_version,
            )
            _write_gate({
                "status": "CLOSED",
                "reason": "no_buy_labels",
                "engine_version": args.engine_version,
            })
            sys.exit(2)

        # Date range from labeled data.
        date_rows = session.execute(
            select(HistoricalLabel.as_of_date).where(
                HistoricalLabel.engine_version == args.engine_version,
            )
        ).all()
        all_days = [d[0] for d in date_rows]
        start, end = min(all_days), max(all_days)

        spy_rets = _spy_daily_returns(session, args.spy_symbol, start, end)
        rand_rets = _random_daily_returns(session, args.engine_version)

        eng_sharpe = _sharpe(eng_rets)
        spy_sharpe = _sharpe(spy_rets)
        rand_sharpe = _sharpe(rand_rets)
        eng_dd = _max_drawdown_pct(eng_rets)
        eng_ann = _annualized_return(eng_rets)
        strat = _stratified_sharpe(session, args.engine_version)

        logger.info(
            "[validate_edge] engine sharpe={:.3f} dd={:.2f}% ann={:.2f}% trades={} hit_rate={:.1f}%",
            eng_sharpe, eng_dd, eng_ann, trade_count, hit_rate,
        )
        logger.info(
            "[validate_edge] spy sharpe={:.3f}  random sharpe={:.3f}",
            spy_sharpe, rand_sharpe,
        )
        logger.info("[validate_edge] regime_stratified_sharpe={}", strat)

        req_spy = spy_sharpe + SHARPE_UPLIFT_VS_SPY
        req_rand = rand_sharpe + SHARPE_UPLIFT_VS_RANDOM
        req = max(req_spy, req_rand)

        reasons: list[str] = []
        if eng_sharpe < req:
            reasons.append(
                f"sharpe_insufficient: {eng_sharpe:.3f} < required {req:.3f} "
                f"(spy+{SHARPE_UPLIFT_VS_SPY}={req_spy:.3f}, "
                f"random+{SHARPE_UPLIFT_VS_RANDOM}={req_rand:.3f})"
            )
        if eng_dd < MAX_DD_FLOOR_PCT:
            reasons.append(
                f"drawdown_excessive: {eng_dd:.2f}% < floor {MAX_DD_FLOOR_PCT}%"
            )

        status = "OPEN" if not reasons else "CLOSED"
        payload = {
            "status": status,
            "engine_version": args.engine_version,
            "engine_sharpe": round(eng_sharpe, 4),
            "spy_sharpe": round(spy_sharpe, 4),
            "random_sharpe": round(rand_sharpe, 4),
            "engine_max_dd_pct": round(eng_dd, 4),
            "engine_annualized_return_pct": round(eng_ann, 4),
            "trade_count": trade_count,
            "hit_rate_pct": round(hit_rate, 2),
            "regime_stratified_sharpe": strat,
            "required_sharpe": round(req, 4),
            "reasons": reasons,
            "date_range": [str(start), str(end)],
            "validated_at": dt.datetime.utcnow().isoformat(),
        }
        _write_gate(payload)

        logger.info("=" * 72)
        if status == "OPEN":
            logger.info("[validate_edge] PASS")
            logger.info("[validate_edge] ML gate: OPEN → apps/ml/* may proceed")
        else:
            logger.error("[validate_edge] FAIL")
            for r in reasons:
                logger.error("  - {}", r)
            logger.error("[validate_edge] ML gate: CLOSED → training BLOCKED")
            logger.error(
                "[validate_edge] Next action: fix deterministic engine, "
                "DO NOT train ML."
            )
        logger.info("=" * 72)

        sys.exit(0 if status == "OPEN" else 1)


if __name__ == "__main__":
    main()
