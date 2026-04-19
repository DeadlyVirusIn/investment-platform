"""Worker entry-point – starts the DB-backed tick-loop scheduler."""

from __future__ import annotations

import asyncio
import sys

from loguru import logger

from apps.api.src.config import settings
from apps.worker.src.scheduler.tick_loop import run


def main() -> None:
    logger.remove()
    logger.add(sys.stderr, level=settings.LOG_LEVEL, colorize=True)
    logger.info("Investment-platform worker starting")
    asyncio.run(run())


if __name__ == "__main__":
    main()
