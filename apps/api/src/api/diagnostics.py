"""Diagnostics export + share-text endpoints. Read-only."""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from apps.api.src.db import get_session
from apps.api.src.domain.diagnostics.exporter import build_diagnostic_bundle
from apps.api.src.domain.diagnostics.share_text import (
    build_share_payload,
    render_share_text,
)

router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])


@router.get("/export")
def export_bundle(
    from_date: dt.date = Query(..., alias="from"),
    to_date: dt.date = Query(..., alias="to"),
    portfolio_id: str | None = Query(None),
    symbols: list[str] | None = Query(None),
    include_factors: bool = Query(True),
    include_candidates: bool = Query(True),
    include_pnl: bool = Query(True),
    include_jobs: bool = Query(True),
    format: str = Query("zip", pattern="^(zip)$"),
    session: Session = Depends(get_session),
) -> Response:
    _ = format  # only zip supported in this batch
    if to_date < from_date:
        return Response(
            content='{"detail":"to must be >= from"}',
            status_code=400, media_type="application/json",
        )
    blob, manifest = build_diagnostic_bundle(
        session,
        from_date=from_date, to_date=to_date,
        portfolio_id=portfolio_id,
        symbols=symbols,
        include_factors=include_factors,
        include_candidates=include_candidates,
        include_pnl=include_pnl,
        include_jobs=include_jobs,
    )
    fname = f"diagnostics_{from_date.isoformat()}_{to_date.isoformat()}.zip"
    headers = {
        "Content-Disposition": f'attachment; filename="{fname}"',
        "X-Bundle-Manifest": ",".join(manifest["files"]),
    }
    return Response(
        content=blob, media_type="application/zip", headers=headers,
    )


@router.get("/share-text")
def share_text(
    portfolio_id: str | None = Query(None),
    as_of: dt.date | None = Query(None),
    format: str = Query("text", pattern="^(text|json)$"),
    session: Session = Depends(get_session),
) -> Response:
    payload = build_share_payload(
        session, portfolio_id=portfolio_id, as_of=as_of,
    )
    if format == "json":
        import json
        return Response(
            content=json.dumps(payload, indent=2, default=str),
            media_type="application/json",
        )
    text = render_share_text(payload)
    return Response(content=text, media_type="text/plain")
