"""FastAPI application entry-point for the investment-intelligence platform."""

from __future__ import annotations

import datetime
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from apps.api.src.config import settings


# ---------------------------------------------------------------------------
# Routers – imported inside lifespan to allow clean error reporting on start
# ---------------------------------------------------------------------------

def _include_routers(app: FastAPI) -> None:
    from apps.api.src.api.alerts import router as alerts_router
    from apps.api.src.api.asset import router as asset_router
    from apps.api.src.api.briefing import router as briefing_router
    from apps.api.src.api.jobs import router as jobs_router
    from apps.api.src.api.performance import router as performance_router
    from apps.api.src.api.portfolio import router as portfolio_router
    from apps.api.src.api.recommendations import router as recommendations_router
    from apps.api.src.api.watchlist import router as watchlist_router

    for router in (
        portfolio_router,
        watchlist_router,
        asset_router,
        recommendations_router,
        briefing_router,
        alerts_router,
        jobs_router,
        performance_router,
    ):
        app.include_router(router, prefix="/api")


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    import sys

    logger.remove()
    logger.add(sys.stderr, level=settings.LOG_LEVEL, colorize=True)
    logger.info("Starting investment-platform API v{}", settings.APP_VERSION)
    _include_routers(app)
    yield
    logger.info("Shutting down investment-platform API")


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Investment Intelligence Platform",
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Built-in health routes (no router file needed for these two)
# ---------------------------------------------------------------------------

@app.get("/api/health", tags=["meta"])
async def health() -> dict[str, object]:
    return {
        "status": "ok",
        "version": settings.APP_VERSION,
        "time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


@app.get("/api/jobs/health", tags=["meta"])
async def jobs_health_top() -> dict[str, object]:
    """Top-level jobs health alias (also served from /api/jobs/health via the jobs router)."""
    return {
        "jobs": [],
        "last_checked": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Script entry-point (used by pyproject [scripts])
# ---------------------------------------------------------------------------

def main() -> None:
    import uvicorn

    uvicorn.run("apps.api.src.main:app", host="0.0.0.0", port=8000, reload=False)
