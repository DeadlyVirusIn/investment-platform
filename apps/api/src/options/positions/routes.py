"""Phase C — Position Intelligence HTTP routes.

GET-only surface. Read-only. No execution endpoints exist.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from apps.api.src.db import get_session
from apps.api.src.options.positions.service import (
    compute_intelligence_all,
    compute_intelligence_for_trade,
    intelligence_to_dict,
)


router = APIRouter(prefix="/options/positions", tags=["options-positions"])


@router.get("/intelligence")
def list_position_intelligence(
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Canonical AI-trade-management payload across every open paper trade.

    Honest empty state when 0 positions exist — `items: []` with a
    helpful `message` so the UI can render explanatory copy.
    """
    items = compute_intelligence_all(session)
    return {
        "count": len(items),
        "guidance_legend": {
            "hold":              "No action — theta + breakeven carry the thesis.",
            "take_profit":       "Captured ≥ 50% of max profit — exit asymmetric from here.",
            "stop_loss":         "Down ≥ 50% of max loss — close to preserve capital.",
            "expiring":          "DTE ≤ 3 — pin-risk + gamma accelerating.",
            "catalyst_caution":  "Named high-importance event within 5 days.",
            "roll":              "DTE ≤ 7 and in profit — roll out to keep edge.",
            "review":            "Mixed signals — operator review.",
        },
        "message": (
            None if items
            else "No open paper positions yet. When the canary fires, "
                 "every open position will appear here with its own AI "
                 "trade-management intelligence."
        ),
        "items": [intelligence_to_dict(i) for i in items],
    }


@router.get("/intelligence/{trade_id}")
def get_position_intelligence(
    trade_id: int,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    item = compute_intelligence_for_trade(session, trade_id)
    if item is None:
        raise HTTPException(status_code=404, detail="trade not found")
    return intelligence_to_dict(item)
