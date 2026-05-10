"""FastAPI application entry-point for the investment-intelligence platform."""

from __future__ import annotations

import datetime
import sys
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from apps.api.src.api.actions import router as actions_router
from apps.api.src.api.catalysts import router as catalysts_router
from apps.api.src.api.ml_research import router as ml_research_router
from apps.api.src.api.ml_replay import router as ml_replay_router
from apps.api.src.api.catalyst_backfill import (
    router as catalyst_backfill_router,
    replay_router as replay_readiness_router,
)
from apps.api.src.api.ml_shadow import router as ml_shadow_router
from apps.api.src.api.analytics import (
    router as alpha_analytics_router,
    health_router as alpha_health_router,
    replay_router as alpha_replay_router,
)
from apps.api.src.api.alpha_rules import (
    router as alpha_rules_router,
    thresholds_router as alpha_thresholds_router,
)
from apps.api.src.api.gates import router as gates_router
from apps.api.src.api.paper_runs import router as paper_runs_router
from apps.api.src.api.alpha_calibration import (
    router as alpha_calibration_router,
)
from apps.api.src.api.alpha_context import (
    router as alpha_context_router,
)
from apps.api.src.api.alpha_similarity import (
    router as alpha_similarity_router,
)
from apps.api.src.api.ml_hybrid import router as ml_hybrid_router
from apps.api.src.api.scheduler_health import router as scheduler_health_router
from apps.api.src.api.shadow import router as shadow_router
from apps.api.src.api.engine_b_transition import router as engine_b_transition_router
from apps.api.src.api.b2_v2_comparison import router as b2_v2_comparison_router
from apps.api.src.api.v2_promotion import router as v2_promotion_router
from apps.api.src.options.routes_readonly import router as options_readonly_router
from apps.api.src.api.options_shadow import router as options_shadow_router
from apps.api.src.api.auth_me import router as auth_me_router
from apps.api.src.api.research import router as research_router
from apps.api.src.api.safe_gate_evolution import (
    router as safe_gate_evolution_router,
)
from apps.api.src.api.ranked_signals import router as ranked_signals_router
from apps.api.src.api.scorecard import router as scorecard_router
from apps.api.src.api.alerts import router as alerts_router
from apps.api.src.api.asset import router as asset_router
from apps.api.src.api.assets import router as assets_router
from apps.api.src.api.market_events import router as market_events_router
from apps.api.src.api.event_features import router as event_features_router
from apps.api.src.api.backtest import router as backtest_router
from apps.api.src.api.briefing import router as briefing_router
from apps.api.src.api.briefing_narrative import router as briefing_narrative_router
from apps.api.src.api.dashboard import router as dashboard_router
from apps.api.src.api.diagnostics import router as diagnostics_router
from apps.api.src.api.diagnostics_pending import (
    router as diagnostics_pending_router,
)
from apps.api.src.api.factors import router as factors_router
from apps.api.src.api.intelligence import router as intelligence_router
from apps.api.src.api.jobs import router as jobs_router
from apps.api.src.api.news import router as news_router
from apps.api.src.api.pnl import router as pnl_router
from apps.api.src.api.paper import router as paper_router
from apps.api.src.api.paper_executed import router as paper_executed_router
from apps.api.src.api.performance_paper import router as performance_paper_router
from apps.api.src.api.performance_paper import options_router as performance_options_router
from apps.api.src.api.cross_signal import router as cross_signal_router
from apps.api.src.api.alpha_lab import router as alpha_lab_router
from apps.api.src.api.ml_insights import router as ml_insights_router
from apps.api.src.api.operator import router as operator_router
from apps.api.src.api.performance import router as performance_router
from apps.api.src.api.portfolio import router as portfolio_router
from apps.api.src.api.recommendations import router as recommendations_router
from apps.api.src.api.regime import router as regime_router
from apps.api.src.api.settings import router as settings_router
from apps.api.src.api.stock_engine import router as stock_engine_router
from apps.api.src.api.stock_engine_analytics import (
    router as stock_engine_analytics_router,
)
from apps.api.src.api.universe import router as universe_router
from apps.api.src.api.watchlist import router as watchlist_router
from apps.api.src.api.insights import router as insights_router
from apps.api.src.api.agent_workflows import (
    router as agent_workflows_router,
)
from apps.api.src.config import settings

# ---------------------------------------------------------------------------
# Lifespan – logging only; routers are registered at module scope below.
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    logger.remove()
    # loguru levels are case-sensitive; compose defaults to lowercase
    # `info`, so normalize before passing.
    logger.add(
        sys.stderr,
        level=(settings.LOG_LEVEL or "INFO").upper(),
        colorize=True,
    )
    logger.info("Starting investment-platform API v{}", settings.APP_VERSION)
    # Log effective ML hybrid + promotion config at startup so operators
    # can confirm env passthrough is working.
    _ml_keys = (
        "ML_HYBRID_ENABLED", "ML_HYBRID_MODE",
        "ML_HYBRID_REQUIRE_CALIBRATION", "ML_HYBRID_REQUIRE_BASELINE_BEAT",
        "ML_HYBRID_ALLOW_BLOCK", "ML_HYBRID_MIN_CONFIDENCE",
        "ML_HYBRID_MAX_STALE_DAYS", "ML_HYBRID_MIN_DATA_CONFIDENCE",
        "ML_HYBRID_MIN_MULTIPLIER",
        "ML_PROMOTION_MIN_ADVICE", "ML_PROMOTION_MIN_OUTCOMES",
        "ML_PROMOTION_MAX_ECE", "ML_PROMOTION_MIN_DELTA_SHARPE",
        "ML_PROMOTION_MAX_FALSE_AVOID_RATE",
        "ML_PROMOTION_REQUIRED_HEALTHY_DAYS",
        "ML_PROMOTION_REQUIRE_OPERATOR_APPROVAL",
        "ML_PROMOTION_MAX_MISSED_WINNER_RATE",
        "ML_CAN_AFFECT_TRADES",
    )
    cfg = {k: getattr(settings, k, "MISSING") for k in _ml_keys}
    logger.info("ML effective config: {}", cfg)
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
# Routers (module scope – introspectable without lifespan boot)
# ---------------------------------------------------------------------------

for _router in (
    portfolio_router,
    watchlist_router,
    asset_router,
    assets_router,
    market_events_router,
    event_features_router,
    recommendations_router,
    briefing_router,
    alerts_router,
    jobs_router,
    performance_router,
    paper_router,
    paper_executed_router,
    performance_paper_router,
    performance_options_router,
    cross_signal_router,
    alpha_lab_router,
    ml_insights_router,
    backtest_router,
    universe_router,
    regime_router,
    factors_router,
    stock_engine_router,
    stock_engine_analytics_router,
    dashboard_router,
    pnl_router,
    diagnostics_router,
    diagnostics_pending_router,
    settings_router,
    news_router,
    intelligence_router,
    briefing_narrative_router,
    actions_router,
    scorecard_router,
    ranked_signals_router,
    operator_router,
    catalysts_router,
    ml_research_router,
    ml_replay_router,
    catalyst_backfill_router,
    replay_readiness_router,
    ml_shadow_router,
    alpha_analytics_router,
    alpha_health_router,
    alpha_replay_router,
    alpha_rules_router,
    alpha_thresholds_router,
    gates_router,
    paper_runs_router,
    alpha_calibration_router,
    alpha_context_router,
    alpha_similarity_router,
    ml_hybrid_router,
    scheduler_health_router,
    shadow_router,
    engine_b_transition_router,
    b2_v2_comparison_router,
    v2_promotion_router,
    options_readonly_router,
    options_shadow_router,
    auth_me_router,
    safe_gate_evolution_router,
    insights_router,
    agent_workflows_router,
):
    app.include_router(_router, prefix="/api")


# ---------------------------------------------------------------------------
# Phase 11W (Phase B) — Research Intelligence read-only router.
# Mounted ONLY when RESEARCH_RO_ENABLED is True. When False (production
# default), every /api/research/* path 404s. GET-only by design.
# ---------------------------------------------------------------------------
if settings.RESEARCH_RO_ENABLED:
    app.include_router(research_router, prefix="/api")


# ---------------------------------------------------------------------------
# Phase 11W (Phase E) — admin-only manual research run.
# Mounted ONLY when RESEARCH_RO_ENABLED AND RESEARCH_MANUAL_RUN_ENABLED
# AND RESEARCH_ADMIN_TOKEN is non-empty. When any precondition fails,
# the POST /api/research/runs/manual route is not registered →
# requests 404. NEVER scheduled. NEVER touches execution.
# ---------------------------------------------------------------------------
if (
    settings.RESEARCH_RO_ENABLED
    and settings.RESEARCH_MANUAL_RUN_ENABLED
    and bool((settings.RESEARCH_ADMIN_TOKEN or "").strip())
):
    from apps.api.src.api.research_manual import (
        router as research_manual_router,
    )
    app.include_router(research_manual_router, prefix="/api")


# ---------------------------------------------------------------------------
# Phase F5 — admin-only insight cache maintenance.
# Mounted ONLY when AGENT_INSIGHTS_ADMIN_MAINTENANCE_ENABLED=true AND
# RESEARCH_ADMIN_TOKEN is non-empty. When either precondition fails,
# DELETE /api/insights/cache is not registered → requests 404.
# Default deployments cannot expose this surface.
# ---------------------------------------------------------------------------
if (
    settings.AGENT_INSIGHTS_ADMIN_MAINTENANCE_ENABLED
    and bool((settings.RESEARCH_ADMIN_TOKEN or "").strip())
):
    from apps.api.src.api.insights import (
        admin_router as insights_admin_router,
    )
    app.include_router(insights_admin_router, prefix="/api")


# ---------------------------------------------------------------------------
# Built-in health route
# ---------------------------------------------------------------------------


@app.get("/api/health", tags=["meta"])
async def health() -> dict[str, object]:
    return {
        "status": "ok",
        "version": settings.APP_VERSION,
        "time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Script entry-point (used by pyproject [scripts])
# ---------------------------------------------------------------------------


def main() -> None:
    import uvicorn

    uvicorn.run("apps.api.src.main:app", host="0.0.0.0", port=8000, reload=False)
