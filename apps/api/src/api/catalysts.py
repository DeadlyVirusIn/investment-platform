"""Catalyst API — light read-only surface for the frontend.

Only two endpoints:
  GET /catalysts/top    — returns CatalystSummary for focus tickers
  GET /catalysts/{sym}  — returns single CatalystSummary

Never raises — service already returns neutral summaries on provider failure.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from apps.api.src.data.catalysts import get_catalyst_service

router = APIRouter(prefix="/catalysts", tags=["catalysts"])

# Focus universe — small, free-tier friendly. Mirrors frontend ticker focus.
FOCUS_DEFAULT = ["AAPL", "MSFT", "NVDA", "AMZN", "META", "TSLA", "GOOGL", "SPY"]


@router.get("/top")
async def get_top_catalysts(
    symbols: str | None = Query(
        default=None,
        description="Comma-separated symbols; defaults to focus universe.",
    ),
    limit: int = Query(default=8, ge=1, le=20),
) -> list[dict]:
    """Return catalyst summaries for a list of symbols.

    Results sorted by combined (event_risk + catalyst_score) desc so the UI
    can show the most actionable rows first.
    """
    svc = get_catalyst_service()
    if symbols:
        wanted = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    else:
        wanted = FOCUS_DEFAULT
    summaries = svc.summaries_for(wanted[:limit * 2])
    summaries.sort(
        key=lambda s: (s.event_risk_score + s.catalyst_score),
        reverse=True,
    )
    return [s.to_dict() for s in summaries[:limit]]


@router.get("/{symbol}")
async def get_catalyst_for_symbol(symbol: str) -> dict:
    svc = get_catalyst_service()
    return svc.summary_for(symbol).to_dict()
