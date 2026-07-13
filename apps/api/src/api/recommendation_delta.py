"""Wave 1C — "What changed?" delta API.

Mounted ONLY when settings.REC_DELTA_ENABLED. One public read route
returning the bounded, redacted delta contract (see
docs/architecture/RECOMMENDATION_DELTA_CONTRACT.md). The service reads
stored rows only; the response never contains recommendation UUIDs,
snapshot hashes, git SHAs, job ids, raw preflight checks, raw family-score
maps, provider errors, or owner identity.
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from apps.api.src.db import get_session
from apps.api.src.domain.recommendations.delta import get_delta

router = APIRouter(prefix="/recommendations", tags=["recommendation-delta"])

_SYMBOL = re.compile(r"^[A-Za-z][A-Za-z0-9.\-]{0,9}$")


@router.get("/{symbol}/delta")
def recommendation_delta(
    symbol: str, db: Session = Depends(get_session)
) -> dict[str, Any]:
    # Symbol-shape gate: rejects enumeration probes / path junk before any
    # query runs; comparison is always within one canonical asset.
    if not _SYMBOL.fullmatch(symbol):
        raise HTTPException(status_code=404, detail="unknown symbol")
    result = get_delta(db, symbol)
    if result is None:
        raise HTTPException(status_code=404, detail="unknown symbol")
    return result
