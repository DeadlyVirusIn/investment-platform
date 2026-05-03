"""Scheduled job: compute today's regime snapshot from SPY and upsert.

Idempotent — one row per ``as_of_date`` (primary key). Safe to re-run.
"""

from __future__ import annotations

import datetime as dt

from loguru import logger
from sqlalchemy.dialects.postgresql import insert as pg_insert

from apps.api.src.db import SessionLocal
from apps.api.src.db.models import RegimeSnapshot
from apps.api.src.domain.regime.regime_engine import compute_regime_for_date


async def compute_regime_snapshot(as_of: dt.date | None = None) -> None:
    target = as_of or dt.date.today()

    with SessionLocal() as session:
        result = compute_regime_for_date(session, target)
        if result is None:
            logger.warning(
                "compute_regime_snapshot: insufficient data for {} — skipping",
                target,
            )
            return

        stmt = (
            pg_insert(RegimeSnapshot)
            .values(
                as_of_date=result.as_of_date,
                benchmark_symbol=result.benchmark_symbol,
                market_trend=result.market_trend,
                vol_regime=result.vol_regime,
                breadth_regime=result.breadth_regime,
                sma50_over_sma200=result.sma50_over_sma200,
                realized_vol_20d=result.realized_vol_20d,
                atr_pctile_1y=result.atr_pctile_1y,
            )
            .on_conflict_do_update(
                index_elements=[RegimeSnapshot.as_of_date],
                set_={
                    "benchmark_symbol": result.benchmark_symbol,
                    "market_trend": result.market_trend,
                    "vol_regime": result.vol_regime,
                    "breadth_regime": result.breadth_regime,
                    "sma50_over_sma200": result.sma50_over_sma200,
                    "realized_vol_20d": result.realized_vol_20d,
                    "atr_pctile_1y": result.atr_pctile_1y,
                },
            )
        )
        session.execute(stmt)
        session.commit()

    logger.info(
        "compute_regime_snapshot upserted {}: trend={} vol={} rv20={} atrp={}",
        result.as_of_date,
        result.market_trend,
        result.vol_regime,
        result.realized_vol_20d,
        result.atr_pctile_1y,
    )
