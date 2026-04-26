"""B2 vs V2 head-to-head comparison API.

Read-only. NEVER mutates state. NEVER changes thresholds. NEVER
triggers execution. NEVER touches promotion or routing.

Endpoints:
    GET /api/b2-v2/comparison    full bundle (verdict + metrics + tail + stability)
    GET /api/b2-v2/timeline      joined per-day rows for charting

Both endpoints SELECT only.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.db import SessionLocal
from apps.api.src.research.b2_v2_comparison import compute_all
from apps.api.src.research.shadow_strategy import (
    SOURCE_STRATEGY as B2_SOURCE_STRATEGY,
)
from apps.api.src.research.shadow_strategy_v2 import SOURCE_STRATEGY_V2


router = APIRouter(prefix="/b2-v2", tags=["b2-v2-comparison"])


_JOIN_SQL = text(
    """
    SELECT
      b2.as_of_date,
      b2.instrument,
      b2.signal           AS b2_signal,
      v2.signal           AS v2_signal,
      b2.regime_label     AS b2_regime,
      v2.regime_label     AS v2_regime,
      b2.fwd_return_1d    AS fwd_return_1d,
      b2.fwd_return_5d    AS fwd_return_5d,
      b2.trend_score      AS b2_trend,
      v2.trend_score      AS v2_trend
    FROM paper_shadow_log b2
    INNER JOIN paper_shadow_log v2
      ON  b2.as_of_date  = v2.as_of_date
      AND b2.instrument  = v2.instrument
    WHERE b2.source_strategy = :b2_src
      AND v2.source_strategy = :v2_src
      AND b2.instrument      = :instrument
      AND b2.as_of_date     >= :cutoff
    ORDER BY b2.as_of_date ASC
    """
)


def _s() -> Session:
    return SessionLocal()


def _fetch_rows(
    s: Session,
    *,
    instrument: str,
    cutoff: date,
) -> list[dict]:
    rs = s.execute(
        _JOIN_SQL,
        {
            "b2_src": B2_SOURCE_STRATEGY,
            "v2_src": SOURCE_STRATEGY_V2,
            "instrument": instrument,
            "cutoff": cutoff,
        },
    ).mappings().all()
    out: list[dict] = []
    for r in rs:
        d = dict(r)
        # Coerce numeric fields (sqlalchemy may return Decimal)
        for k in ("fwd_return_1d", "fwd_return_5d", "b2_trend", "v2_trend"):
            v = d.get(k)
            d[k] = float(v) if v is not None else None
        out.append(d)
    return out


@router.get("/comparison")
async def comparison_bundle(
    days: int = 365,
    instrument: str = "SPY",
) -> dict[str, Any]:
    """Full B2 vs V2 comparison bundle. SELECT only."""
    if days < 1 or days > 5000:
        raise HTTPException(status_code=400, detail="days must be 1..5000")
    cutoff = date.today() - timedelta(days=days + 7)
    with _s() as s:
        rows = _fetch_rows(s, instrument=instrument, cutoff=cutoff)
    bundle = compute_all(rows)
    bundle["params"] = {
        "days": days,
        "instrument": instrument,
        "cutoff": cutoff.isoformat(),
        "b2_source_strategy": B2_SOURCE_STRATEGY,
        "v2_source_strategy": SOURCE_STRATEGY_V2,
    }
    return bundle


@router.get("/timeline")
async def comparison_timeline(
    days: int = 365,
    instrument: str = "SPY",
) -> dict[str, Any]:
    """Joined per-day rows (for charting). SELECT only."""
    if days < 1 or days > 5000:
        raise HTTPException(status_code=400, detail="days must be 1..5000")
    cutoff = date.today() - timedelta(days=days + 7)
    with _s() as s:
        rows = _fetch_rows(s, instrument=instrument, cutoff=cutoff)
    out_rows: list[dict] = []
    for r in rows:
        b2_sig = r.get("b2_signal")
        v2_sig = r.get("v2_signal")
        ret = r.get("fwd_return_1d")
        b2_ret = (float(ret) if b2_sig == "LONG" else 0.0) if ret is not None else None
        v2_ret = (float(ret) if v2_sig == "LONG" else 0.0) if ret is not None else None
        delta = (v2_ret - b2_ret) if (b2_ret is not None and v2_ret is not None) else None
        cls = None
        if b2_sig != v2_sig and b2_sig in ("LONG", "FLAT") and v2_sig in ("LONG", "FLAT"):
            cls = (
                "B2_FLAT_V2_LONG" if (b2_sig == "FLAT" and v2_sig == "LONG")
                else "B2_LONG_V2_FLAT"
            )
        out_rows.append(
            {
                "as_of_date": r["as_of_date"].isoformat()
                if hasattr(r["as_of_date"], "isoformat") else r["as_of_date"],
                "instrument": r["instrument"],
                "b2_signal": b2_sig,
                "v2_signal": v2_sig,
                "b2_regime": r.get("b2_regime"),
                "v2_regime": r.get("v2_regime"),
                "fwd_return_1d": ret,
                "b2_return": b2_ret,
                "v2_return": v2_ret,
                "delta": delta,
                "divergence_class": cls,
            }
        )
    return {
        "n_rows": len(out_rows),
        "instrument": instrument,
        "rows": out_rows,
    }
