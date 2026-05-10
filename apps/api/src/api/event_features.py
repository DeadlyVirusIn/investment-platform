"""Phase 10 — Event features route.

Exposes:
    GET /api/event-features?symbols=AAPL,MSFT,NVDA

Returns structured advisory features derived from market events.
NEVER an automatic trade trigger — features inform rationale +
confidence only.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from apps.api.src.domain.event_features.service import (
    get_event_features_for_symbols,
)

router = APIRouter(tags=["event-features"])


@router.get("/event-features")
def event_features(
    symbols: str = Query(default="", max_length=512),
) -> dict[str, Any]:
    sym_list = [s for s in (symbols or "").split(",") if s.strip()]
    return get_event_features_for_symbols(sym_list)
