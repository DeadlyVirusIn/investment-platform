"""refresh_company_names — populate asset.name from Polygon (Phase 2).

Backfills + nightly-refreshes the human company name for every asset whose
name is NULL, using Polygon's bulk reference-tickers list (one map covers
the universe; per-symbol details endpoint is the straggler fallback).

No static maps, no manual maintenance: names come straight from Polygon.
Null-safe — when POLYGON_API_KEY is absent or a symbol has no name, the row
is left NULL and the UI falls back to the ticker. Idempotent: only rows with
a NULL name are touched, so reruns are cheap and order-independent.
"""

from __future__ import annotations

from loguru import logger


# Cap per-symbol fallback lookups so a run can't stall on the free-tier
# rate limit. Bulk map already covers the vast majority of the universe.
_FALLBACK_CAP = 50


async def refresh_company_names() -> None:
    from sqlalchemy import select, update

    from apps.api.src.db import SessionLocal
    from apps.api.src.db.models import Asset
    from apps.api.src.providers import polygon

    if not polygon.is_available():
        logger.warning("POLYGON_API_KEY not set — skipping refresh_company_names")
        return

    # Which symbols still need a name?
    with SessionLocal() as session:
        rows = session.execute(
            select(Asset.id, Asset.symbol).where(Asset.name.is_(None))
        ).all()
    if not rows:
        logger.info("refresh_company_names: no assets missing a name")
        return
    need = {sym.upper(): aid for aid, sym in rows if sym}
    logger.info("refresh_company_names: {} assets missing a name", len(need))

    # Bulk map first (cheap, covers most).
    name_map = polygon.fetch_ticker_name_map()
    logger.info("refresh_company_names: bulk map returned {} names", len(name_map))

    resolved: dict[str, str] = {}
    for sym in need:
        nm = name_map.get(sym)
        if nm:
            resolved[sym] = nm

    # Per-symbol fallback for stragglers (capped).
    missing = [s for s in need if s not in resolved]
    for sym in missing[:_FALLBACK_CAP]:
        nm = polygon.fetch_ticker_name(sym)
        if nm:
            resolved[sym] = nm

    if not resolved:
        logger.warning("refresh_company_names: resolved 0 names this run")
        return

    written = 0
    with SessionLocal() as session:
        for sym, nm in resolved.items():
            aid = need.get(sym)
            if not aid:
                continue
            res = session.execute(
                update(Asset)
                .where(Asset.id == aid, Asset.name.is_(None))
                .values(name=nm)
            )
            written += res.rowcount or 0
        session.commit()

    logger.info(
        "refresh_company_names complete: resolved={} written={} still_missing={}",
        len(resolved), written, len(need) - len(resolved),
    )
