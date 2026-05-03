"""Scheduled job: write daily factor_snapshot rows for the stock-swing universe.

Idempotent — unique on ``(as_of_date, asset_id)``. Safe to re-run; existing
rows are overwritten via ON CONFLICT DO UPDATE.
"""

from __future__ import annotations

import datetime as dt

from loguru import logger
from sqlalchemy.dialects.postgresql import insert as pg_insert

from apps.api.src.db import SessionLocal
from apps.api.src.db.models import FactorSnapshot
from apps.api.src.domain.features.stock_factor_engine import (
    compute_universe_snapshots,
)

DEFAULT_UNIVERSE = "stock_swing_v1"


async def compute_factor_snapshots(
    as_of: dt.date | None = None,
    universe_name: str = DEFAULT_UNIVERSE,
) -> None:
    target = as_of or dt.date.today()

    with SessionLocal() as session:
        rows = compute_universe_snapshots(session, universe_name, target)
        if not rows:
            logger.warning(
                "compute_factor_snapshots: empty universe '{}' on {}",
                universe_name, target,
            )
            return

        written = 0
        for row in rows:
            stmt = (
                pg_insert(FactorSnapshot)
                .values(
                    as_of_date=row.as_of_date,
                    asset_id=row.asset_id,
                    residual_momentum_20d=row.residual_momentum_20d,
                    residual_momentum_60d=row.residual_momentum_60d,
                    sector_relative_rank=row.sector_relative_rank,
                    trend_strength_20d=row.trend_strength_20d,
                    price_vs_200sma=row.price_vs_200sma,
                    atr_percent_14=row.atr_percent_14,
                    earnings_proximity_days=row.earnings_proximity_days,
                    avg_dollar_volume_20d=row.avg_dollar_volume_20d,
                    feature_set_hash=row.feature_set_hash,
                    enough_data=row.enough_data,
                    stale_data=row.stale_data,
                )
                .on_conflict_do_update(
                    index_elements=["as_of_date", "asset_id"],
                    set_={
                        "residual_momentum_20d": row.residual_momentum_20d,
                        "residual_momentum_60d": row.residual_momentum_60d,
                        "sector_relative_rank": row.sector_relative_rank,
                        "trend_strength_20d": row.trend_strength_20d,
                        "price_vs_200sma": row.price_vs_200sma,
                        "atr_percent_14": row.atr_percent_14,
                        "earnings_proximity_days": row.earnings_proximity_days,
                        "avg_dollar_volume_20d": row.avg_dollar_volume_20d,
                        "feature_set_hash": row.feature_set_hash,
                        "enough_data": row.enough_data,
                        "stale_data": row.stale_data,
                    },
                )
            )
            session.execute(stmt)
            written += 1
        session.commit()

    logger.info(
        "compute_factor_snapshots {}: universe={} assets={} written={}",
        target, universe_name, len(rows), written,
    )
