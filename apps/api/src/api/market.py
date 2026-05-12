"""Market tape API — Phase 15h.5.

Serves /api/market/tape from an in-memory cache populated by a
background poller. The poller calls Polygon's bulk-snapshot endpoint
every REFRESH_SECONDS for the macro tape symbols (SPY/QQQ/DIA per
the Phase 15h.5 brief).

Honest discipline (per docs/research/MARKET_QUOTE_PROVIDER_EVAL.md):
- Quotes are 15-min delayed (Polygon Stocks Starter tier).
- No fake fallback. If Polygon is unreachable, the endpoint returns
  the previous successful cache (with `error` populated) until the
  cache exceeds STALE_AFTER_SECONDS, after which `stale: true` and
  the UI hides the tape behind its disabled-state strip.
- No per-request upstream call from the API. The endpoint reads
  cache only — p95 latency well under 50 ms.

The poller lifecycle is owned by the FastAPI lifespan in main.py.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter
from loguru import logger

from apps.api.src.providers import polygon

router = APIRouter(prefix="/market", tags=["market"])


# Symbols the macro tape tracks. Phase 15h.5 scope: SPY/QQQ/DIA
# (broad-market ETFs) only. VIX/TNX deferred — Polygon Indices is a
# separate paid subscription not currently active. See arch doc §2.
MACRO_TAPE_SYMBOLS: list[str] = ["SPY", "QQQ", "DIA"]

# Poll cadence — middle of the user-approved 60–120s window.
REFRESH_SECONDS: float = 90.0
# Cache is treated as stale (and the UI shown its disabled state)
# once the most recent successful refresh is older than this.
STALE_AFTER_SECONDS: float = 300.0
# How long the poller backs off after a transport / upstream failure
# before retrying. Multiplied by the failure streak, capped.
ERROR_BACKOFF_BASE_SECONDS: float = 15.0
ERROR_BACKOFF_MAX_SECONDS: float = 300.0


@dataclass
class _Cache:
    quotes: list[dict] = field(default_factory=list)
    fetched_at: float = 0.0      # epoch seconds — last SUCCESSFUL refresh
    last_error: str | None = None
    consecutive_errors: int = 0


_cache: _Cache = _Cache()
_poll_task: asyncio.Task | None = None


# ---------------------------------------------------------------------------
# Background poller
# ---------------------------------------------------------------------------


async def _poll_once(client: httpx.AsyncClient) -> None:
    """Run one refresh cycle. Updates _cache in place."""
    try:
        quotes = await polygon.fetch_tape_snapshot(client, MACRO_TAPE_SYMBOLS)
        _cache.quotes = quotes
        _cache.fetched_at = time.time()
        _cache.last_error = None
        _cache.consecutive_errors = 0
        logger.debug(
            "market_tape: refreshed {} quotes from polygon", len(quotes)
        )
    except Exception as exc:  # noqa: BLE001 — provider errors classified at edge
        _cache.last_error = f"{type(exc).__name__}: {exc}"
        _cache.consecutive_errors += 1
        logger.warning(
            "market_tape: poll failed (#{}) — {}",
            _cache.consecutive_errors, _cache.last_error,
        )


async def _poll_loop() -> None:
    """Long-running poller. Sleeps REFRESH_SECONDS between cycles, with
    exponential backoff after consecutive failures."""
    async with httpx.AsyncClient() as client:
        while True:
            await _poll_once(client)
            if _cache.consecutive_errors > 0:
                # Exponential backoff: 15s → 30s → 60s → 120s → 240s → 300s cap
                delay = min(
                    ERROR_BACKOFF_BASE_SECONDS * (2 ** (_cache.consecutive_errors - 1)),
                    ERROR_BACKOFF_MAX_SECONDS,
                )
            else:
                delay = REFRESH_SECONDS
            await asyncio.sleep(delay)


def start_market_tape_poller() -> None:
    """Idempotent — safe to call multiple times. Owned by lifespan."""
    global _poll_task
    if _poll_task is not None and not _poll_task.done():
        return
    if not polygon.is_available():
        logger.warning(
            "market_tape: POLYGON_API_KEY not set — poller NOT started; "
            "/api/market/tape will return stale=true"
        )
        return
    _poll_task = asyncio.create_task(_poll_loop(), name="market_tape_poller")
    logger.info("market_tape: poller started ({}s cadence, symbols={})",
                REFRESH_SECONDS, MACRO_TAPE_SYMBOLS)


def stop_market_tape_poller() -> None:
    """Lifespan teardown."""
    global _poll_task
    if _poll_task is not None:
        _poll_task.cancel()
        _poll_task = None
        logger.info("market_tape: poller stopped")


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


def _ts_to_iso(epoch: float | None) -> str | None:
    if epoch is None or epoch <= 0:
        return None
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )


@router.get("/tape")
def get_tape() -> dict:
    """Return the cached delayed market tape.

    Response shape mirrors docs/research/MARKET_QUOTE_PROVIDER_EVAL.md §7
    with one simplification: only the macro tape is exposed for now
    (per Phase 15h.5 scope).
    """
    age = time.time() - _cache.fetched_at if _cache.fetched_at > 0 else None
    is_stale = age is None or age > STALE_AFTER_SECONDS

    quotes_out: list[dict] = []
    for q in _cache.quotes:
        quotes_out.append({
            "symbol": q.get("symbol"),
            "price": q.get("price"),
            "prev_close": q.get("prev_close"),
            "change_abs": q.get("change_abs"),
            "change_pct": q.get("change_pct"),
            "quote_ts": _ts_to_iso(q.get("quote_ts")),
            "source": q.get("source", "polygon"),
            "delay_minutes": q.get("delay_minutes", 15),
        })

    return {
        "stale": is_stale,
        "fetched_at": _ts_to_iso(_cache.fetched_at),
        "max_delay_minutes": 15 if quotes_out and not is_stale else None,
        "source": "polygon" if quotes_out else None,
        "symbols_tracked": MACRO_TAPE_SYMBOLS,
        "quotes": quotes_out if not is_stale else [],
        "error": _cache.last_error,
    }
