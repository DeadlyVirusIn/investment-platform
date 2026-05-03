"""Worker job: live daily pipeline orchestrator.

Invokes apps.api.src.domain.ops.daily_runner.run_daily_pipeline with
run_date = today (UTC). Cron scheduler calls this once per weekday.
"""

from __future__ import annotations

import datetime as dt

from loguru import logger

from apps.api.src.domain.ops.daily_runner import AlreadyRan, run_daily_pipeline


async def run_daily_pipeline_job() -> None:
    today = dt.datetime.now(dt.timezone.utc).date()
    try:
        result = run_daily_pipeline(today)
    except AlreadyRan as exc:
        logger.warning("[daily_job] {}", exc)
        return
    logger.info(
        "[daily_job] run_date={} status={} stage_failed={} alerts={}",
        result.run_date, result.status, result.stage_failed, len(result.alerts),
    )
