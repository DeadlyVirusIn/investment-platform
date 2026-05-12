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
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException
from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.src.config import settings
from apps.api.src.db import SessionLocal
from apps.api.src.db.models import (
    Asset,
    PaperPosition,
    Recommendation,
)
from apps.api.src.ml.intraday.observation_writer import (
    derive_observation as derive_intraday_observation,
    write_observation as write_intraday_observation,
)
from apps.api.src.providers import polygon

router = APIRouter(prefix="/market", tags=["market"])

# Phase 16 v1 — separate router for the recommendation-keyed overlay
# endpoint so the URL reads /api/recommendations/{id}/intraday-context
# rather than /api/market/.... Both routers live in this module so the
# in-memory cache + derivation stay co-located.
recommendations_overlay_router = APIRouter(
    prefix="/recommendations", tags=["market", "recommendations"]
)


# Symbols the macro tape tracks. Phase 15h.5 scope: SPY/QQQ/DIA
# (broad-market ETFs) only. VIX/TNX deferred — Polygon Indices is a
# separate paid subscription not currently active. See arch doc §2.
MACRO_TAPE_SYMBOLS: list[str] = ["SPY", "QQQ", "DIA"]
# Hard cap on the per-cycle Polygon symbol set when the overlay
# resolver expands the tape with active paper holdings. Per
# INTRADAY_CONTEXT_OVERLAY.md §4 governance rule 7.
OVERLAY_SYMBOL_CAP: int = 100

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
# Phase 16 v1 — intraday context overlay (ephemeral)
# Architecture: docs/research/INTRADAY_CONTEXT_OVERLAY.md
#
# In-memory only. No DB writes. Latest-snapshot-per-recommendation
# only — overwritten each poll cycle. Cleared on container restart.
# ---------------------------------------------------------------------------


@dataclass
class _OverlayEntry:
    recommendation_id: str
    symbol: str
    intraday_change_pct: float | None
    vs_recommendation_entry_pct: float | None
    vs_macro_drift_pct: float | None
    context_label: str           # aligned | drift | stress | quiet
    derived_at: float            # epoch seconds (server clock)
    quote_ts: float | None       # source-reported delayed ts
    source: str                  # "polygon"
    delay_minutes: int           # 15


# Keyed by recommendation_id. Replaced wholesale each cycle.
_overlay_cache: dict[str, _OverlayEntry] = {}


# Thresholds (per arch doc §1; v1 uses fixed-percent draft until
# σ-based tuning lands in a follow-up).
OVERLAY_DRIFT_THRESHOLD_PCT: float = 0.5    # |entry move| in this band -> drift
OVERLAY_STRESS_THRESHOLD_PCT: float = 1.5   # < -this -> stress
OVERLAY_QUIET_THRESHOLD_PCT: float = 0.2    # |intraday_change| < this -> quiet


def derive_intraday_context(
    recommendation_id: str,
    symbol: str,
    price: float | None,
    prev_close: float | None,
    macro_intraday_pct: float | None,
    quote_ts: float | None,
    source: str = "polygon",
    delay_minutes: int = 15,
    derived_at: float | None = None,
) -> _OverlayEntry:
    """Pure function — derive an intraday context entry for one symbol.

    Inputs are scalars (no ORM coupling) so this is trivially testable.

    `prev_close` is used as the recommendation entry-reference proxy for
    v1: the recommendation cron runs at 22:30 ET against the day's close,
    so the prior session's close IS the entry reference for the current
    active recommendation. When the symbol opens with a meaningful
    intraday move vs prev_close, that's the recommendation thesis under
    pressure (or supported).

    `macro_intraday_pct` is the same metric for SPY (or whichever
    benchmark the caller chooses) so we can compute relative drift.

    Returns an _OverlayEntry. context_label is one of:
      - "stress"  : symbol -1.5%+ vs entry (thesis under pressure)
      - "drift"   : symbol moved 0.5–1.5% in either direction
      - "aligned" : symbol within ±0.5% of entry, with non-quiet macro
      - "quiet"   : both symbol and macro moves are tiny (<0.2%)
    """
    derived_at = derived_at if derived_at is not None else time.time()

    # Compute intraday change vs prev_close (used as entry proxy for v1).
    if price is None or prev_close is None or float(prev_close) == 0:
        intraday_change_pct: float | None = None
        vs_entry_pct: float | None = None
    else:
        intraday_change_pct = (float(price) - float(prev_close)) / float(prev_close) * 100.0
        # v1: entry-reference proxy = prev_close (recommendation cron
        # ran against last night's close at 22:30 ET).
        vs_entry_pct = intraday_change_pct

    if intraday_change_pct is None or macro_intraday_pct is None:
        vs_macro_drift_pct: float | None = None
    else:
        vs_macro_drift_pct = intraday_change_pct - macro_intraday_pct

    # Label assignment — earliest matching wins.
    if intraday_change_pct is None:
        label = "quiet"
    elif (
        abs(intraday_change_pct) < OVERLAY_QUIET_THRESHOLD_PCT
        and (macro_intraday_pct is None
             or abs(macro_intraday_pct) < OVERLAY_QUIET_THRESHOLD_PCT)
    ):
        label = "quiet"
    elif vs_entry_pct is not None and vs_entry_pct < -OVERLAY_STRESS_THRESHOLD_PCT:
        label = "stress"
    elif vs_entry_pct is not None and abs(vs_entry_pct) >= OVERLAY_DRIFT_THRESHOLD_PCT:
        label = "drift"
    else:
        label = "aligned"

    return _OverlayEntry(
        recommendation_id=recommendation_id,
        symbol=symbol,
        intraday_change_pct=intraday_change_pct,
        vs_recommendation_entry_pct=vs_entry_pct,
        vs_macro_drift_pct=vs_macro_drift_pct,
        context_label=label,
        derived_at=derived_at,
        quote_ts=quote_ts,
        source=source,
        delay_minutes=delay_minutes,
    )


def resolve_active_overlay_targets(session: Session) -> dict[str, str]:
    """Return {recommendation_id: symbol} for active overlay targets.

    v1 scope: open paper positions only. For each open paper position,
    find the most recent recommendation for that asset (across all
    accounts, since this is single-operator). If no recommendation
    exists for an open position, that position is skipped — the
    overlay needs a recommendation to bind to.

    Macro symbols (SPY/QQQ/DIA) are NOT included here because they
    are not bound to a recommendation; they live in the tape cache
    instead. The macro intraday change pct is computed at poll time
    from the tape itself.
    """
    targets: dict[str, str] = {}
    rows = session.execute(
        select(Asset.id, Asset.symbol)
        .join(PaperPosition, PaperPosition.asset_id == Asset.id)
        .where(PaperPosition.is_open.is_(True))
        .distinct()
    ).all()
    for asset_id, symbol in rows:
        # Most-recent recommendation for this asset.
        rec = session.execute(
            select(Recommendation.id)
            .where(Recommendation.asset_id == asset_id)
            .order_by(Recommendation.generated_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if rec is None:
            continue
        targets[str(rec)] = str(symbol)
        if len(targets) >= OVERLAY_SYMBOL_CAP:
            logger.warning(
                "intraday_overlay: hit OVERLAY_SYMBOL_CAP={} — truncating",
                OVERLAY_SYMBOL_CAP,
            )
            break
    return targets


async def _refresh_overlay_cache(client: httpx.AsyncClient) -> None:
    """Resolve active overlay targets, fetch their snapshots, derive
    context, and replace _overlay_cache wholesale.

    Called from _poll_once after the macro tape cache refresh succeeds.
    Honors the INTRADAY_OVERLAY_ENABLED feature flag.
    """
    global _overlay_cache
    if not settings.INTRADAY_OVERLAY_ENABLED:
        return  # flag off — leave _overlay_cache empty/stale silently

    # Resolve which (rec_id, symbol) pairs need an overlay this cycle.
    with SessionLocal() as session:
        targets = resolve_active_overlay_targets(session)
    if not targets:
        _overlay_cache = {}
        logger.debug("intraday_overlay: no active targets")
        return

    # Macro benchmark for vs_macro_drift_pct — use SPY's intraday
    # change from the tape cache. None when SPY isn't priced this cycle.
    macro_intraday_pct: float | None = None
    for q in _cache.quotes:
        if q.get("symbol") == "SPY":
            macro_intraday_pct = q.get("change_pct")
            break

    # Determine symbols we need beyond what's already in the tape cache.
    cached_symbols = {q.get("symbol"): q for q in _cache.quotes}
    target_symbols = set(targets.values())
    missing_symbols = sorted(target_symbols - set(cached_symbols.keys()))

    # Fetch missing symbols in one bulk Polygon call.
    fetched_for_overlay: dict[str, dict] = {}
    if missing_symbols:
        try:
            extra = await polygon.fetch_tape_snapshot(client, missing_symbols)
            for q in extra:
                fetched_for_overlay[q["symbol"]] = q
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "intraday_overlay: missing-symbol fetch failed — {}", exc
            )
            # Soft-fail: existing tape data still serves macro symbols;
            # overlay just won't have entries for the missing ones.

    # Build the new cache.
    new_cache: dict[str, _OverlayEntry] = {}
    for rec_id, sym in targets.items():
        snap = cached_symbols.get(sym) or fetched_for_overlay.get(sym)
        if snap is None:
            continue  # symbol unavailable from upstream this cycle
        entry = derive_intraday_context(
            recommendation_id=rec_id,
            symbol=sym,
            price=snap.get("price"),
            prev_close=snap.get("prev_close"),
            macro_intraday_pct=macro_intraday_pct,
            quote_ts=snap.get("quote_ts"),
            source=snap.get("source", "polygon"),
            delay_minutes=snap.get("delay_minutes", 15),
        )
        new_cache[rec_id] = entry
    _overlay_cache = new_cache
    logger.debug(
        "intraday_overlay: refreshed {} entries (cap {}, missing fetched {})",
        len(new_cache), OVERLAY_SYMBOL_CAP, len(fetched_for_overlay),
    )


# ---------------------------------------------------------------------------
# Phase 16 Phase 2 — Intraday ML shadow observation writes
# ---------------------------------------------------------------------------


async def _write_intraday_observations(client: httpx.AsyncClient) -> None:
    """Persist one row per (recommendation_id, 15-min slot) into
    `intraday_observation`. Sole runtime writer of that table. No-op
    when INTRADAY_ML_SHADOW_ENABLED=false.

    Called from _poll_once AFTER the macro tape + overlay caches are
    refreshed. Reuses the SAME (rec_id, symbol) target set as the
    overlay so we cover exactly the active paper holdings.

    Coverage path (v1.1):
      1. Macro tape cache already holds SPY/QQQ/DIA snapshots.
      2. For target symbols NOT in the macro tape (e.g. HR), we
         bulk-fetch their snapshots from Polygon in ONE call.
      3. Cap the merged set at OVERLAY_SYMBOL_CAP (100) per arch
         doc §4 governance rule 7.

    All exceptions are logged + swallowed — observation persistence
    must never fail the tape cycle. The next cycle 90s later
    re-attempts via the natural retry loop.
    """
    if not settings.INTRADAY_ML_SHADOW_ENABLED:
        return
    if not _cache.quotes:
        return  # no tape data this cycle; nothing to bind to

    # Reuse the resolver from the overlay layer (single source of truth
    # for "what should we be observing now").
    with SessionLocal() as session:
        targets = resolve_active_overlay_targets(session)
        if not targets:
            logger.debug("intraday_shadow: no active targets")
            return

        # Lookup recommendations + actions + convictions in one batch.
        rec_meta: dict[str, tuple[str, float | None]] = {}
        rows = session.execute(
            select(
                Recommendation.id,
                Recommendation.action,
                Recommendation.conviction,
            ).where(Recommendation.id.in_(list(targets.keys())))
        ).all()
        for rec_id, action, conv in rows:
            rec_meta[str(rec_id)] = (
                str(action or "hold").lower(),
                float(conv) if conv is not None else None,
            )

        # Position state per asset_id (reverse lookup: target symbol → asset_id
        # is via the rec; cheaper to flag any open position by symbol set).
        pos_rows = session.execute(
            select(Asset.symbol)
            .join(PaperPosition, PaperPosition.asset_id == Asset.id)
            .where(PaperPosition.is_open.is_(True))
            .distinct()
        ).all()
        open_symbols: set[str] = {str(s) for (s,) in pos_rows}

        # Macro benchmark for vs_macro_drift_pct.
        macro_pct: dict[str, float | None] = {"SPY": None, "QQQ": None, "DIA": None}
        for q in _cache.quotes:
            sym = q.get("symbol")
            if sym in macro_pct:
                macro_pct[sym] = q.get("change_pct")

        # Start with snapshots already in the macro tape cache.
        cached_symbols: dict[str, dict] = {q.get("symbol"): q for q in _cache.quotes}

        # v1.1 — fetch snapshots for target symbols NOT in macro tape.
        # Single bulk Polygon call covers all missing symbols at once.
        target_symbols = set(targets.values())
        missing_symbols = sorted(s for s in target_symbols if s not in cached_symbols)
        # Honor the 100-symbol governance cap (arch doc §4 rule 7).
        if len(missing_symbols) > OVERLAY_SYMBOL_CAP:
            logger.warning(
                "intraday_shadow: hit OVERLAY_SYMBOL_CAP={} for missing fetch "
                "({} requested); truncating",
                OVERLAY_SYMBOL_CAP, len(missing_symbols),
            )
            missing_symbols = missing_symbols[:OVERLAY_SYMBOL_CAP]

        fetched_extras: dict[str, dict] = {}
        if missing_symbols:
            try:
                extras = await polygon.fetch_tape_snapshot(client, missing_symbols)
                for q in extras:
                    fetched_extras[q["symbol"]] = q
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "intraday_shadow: missing-symbol fetch failed — {}", exc,
                )
                # Soft-fail: macro-tape symbols still get observations.

        all_snapshots: dict[str, dict] = {**cached_symbols, **fetched_extras}

        written = 0
        skipped_no_meta = 0
        skipped_no_snap = 0
        for rec_id, sym in targets.items():
            meta = rec_meta.get(rec_id)
            if meta is None:
                skipped_no_meta += 1
                continue
            action_type, prior_conv = meta
            snap = all_snapshots.get(sym)
            if snap is None:
                skipped_no_snap += 1
                continue
            position_state = "open_long" if sym in open_symbols else "flat"
            quote_ts_epoch = snap.get("quote_ts")
            quote_ts_dt = (
                datetime.fromtimestamp(float(quote_ts_epoch), tz=timezone.utc)
                if quote_ts_epoch else None
            )
            row = derive_intraday_observation(
                recommendation_id=rec_id,
                symbol=sym,
                observed_at=datetime.now(tz=timezone.utc),
                price=snap.get("price"),
                prev_close=snap.get("prev_close"),
                day_open=None,           # not yet exposed in tape cache
                day_high=None,           # ditto
                day_low=None,            # ditto
                spy_change_pct=macro_pct.get("SPY"),
                qqq_change_pct=macro_pct.get("QQQ"),
                dia_change_pct=macro_pct.get("DIA"),
                prior_eod_conviction=prior_conv,
                action_type=action_type,
                position_state=position_state,
                entry_reference_price=snap.get("prev_close"),  # v1 proxy
                atr_60d_pct=None,        # deferred to Phase 3 prep
                vol_60d_pct=None,        # deferred to Phase 3 prep
                sector_id=None,          # deferred to Phase 3 prep
                source=snap.get("source", "polygon"),
                delay_minutes=int(snap.get("delay_minutes", 15)),
                quote_ts=quote_ts_dt,
            )
            try:
                write_intraday_observation(session, row)
                written += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "intraday_shadow: write failed for {}: {}", rec_id, exc,
                )
        logger.debug(
            "intraday_shadow: wrote {} obs "
            "(macro={}, missing_fetched={}, skipped meta={}, snap={})",
            written, len(cached_symbols), len(fetched_extras),
            skipped_no_meta, skipped_no_snap,
        )


# ---------------------------------------------------------------------------
# Background poller
# ---------------------------------------------------------------------------


async def _poll_once(client: httpx.AsyncClient) -> None:
    """Run one refresh cycle. Updates _cache in place. After a successful
    macro tape refresh, also fetches minute-bar history per symbol (used
    by the UI to render sparklines) and triggers the intraday overlay
    refresh (no-op when INTRADAY_OVERLAY_ENABLED=false)."""
    try:
        quotes = await polygon.fetch_tape_snapshot(client, MACRO_TAPE_SYMBOLS)
        # Fetch ~30min minute-bar history per symbol for sparkline rendering.
        # Sequential per symbol — 3 symbols, ~150ms each, well within
        # the 90s poll budget. Soft-fail per symbol; missing history just
        # omits the sparkline for that one.
        for q in quotes:
            sym = q.get("symbol")
            if not sym:
                continue
            history = await polygon.fetch_intraday_history(client, sym, limit=30)
            if history:
                q["history"] = history
        _cache.quotes = quotes
        _cache.fetched_at = time.time()
        _cache.last_error = None
        _cache.consecutive_errors = 0
        logger.debug(
            "market_tape: refreshed {} quotes from polygon (with history)",
            len(quotes),
        )
    except Exception as exc:  # noqa: BLE001 — provider errors classified at edge
        _cache.last_error = f"{type(exc).__name__}: {exc}"
        _cache.consecutive_errors += 1
        logger.warning(
            "market_tape: poll failed (#{}) — {}",
            _cache.consecutive_errors, _cache.last_error,
        )
        return  # don't run the overlay on a failed tape cycle

    # Phase 16 v1 — overlay refresh AFTER successful tape refresh.
    # No-op when INTRADAY_OVERLAY_ENABLED=false.
    try:
        await _refresh_overlay_cache(client)
    except Exception as exc:  # noqa: BLE001 — never fail the tape cycle
        logger.warning("intraday_overlay: refresh failed — {}", exc)

    # Phase 16 Phase 2 — durable intraday observation writes AFTER the
    # tape + overlay refresh. No-op when INTRADAY_ML_SHADOW_ENABLED=false.
    # See docs/research/INTRADAY_ML_SHADOW.md.
    try:
        await _write_intraday_observations(client)
    except Exception as exc:  # noqa: BLE001 — never fail the tape cycle
        logger.warning("intraday_shadow: observation write failed — {}", exc)


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
            # Intraday 1-min closes (chronological) for sparkline render.
            "history": q.get("history") or [],
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


# ---------------------------------------------------------------------------
# Phase 16 v1 — Intraday context overlay endpoint
# ---------------------------------------------------------------------------


@recommendations_overlay_router.get("/{recommendation_id}/intraday-context")
def get_intraday_context(recommendation_id: str) -> dict:
    """Return the in-memory intraday context entry for a recommendation.

    404 when:
      - INTRADAY_OVERLAY_ENABLED is False
      - The recommendation_id is not in the current overlay cache
        (no open paper position bound to it, or the macro tape cycle
        hasn't completed yet)

    Per arch doc §6: reads only from the in-memory _overlay_cache.
    No DB hit on the request path. No upstream call.
    """
    if not settings.INTRADAY_OVERLAY_ENABLED:
        raise HTTPException(status_code=404, detail="overlay disabled")

    # Tape staleness check — if the underlying tape hasn't refreshed
    # in STALE_AFTER_SECONDS, the overlay cache is also implicitly
    # stale even if entries exist. Surface that to the caller.
    age = time.time() - _cache.fetched_at if _cache.fetched_at > 0 else None
    tape_is_stale = age is None or age > STALE_AFTER_SECONDS

    entry = _overlay_cache.get(recommendation_id)
    if entry is None:
        raise HTTPException(
            status_code=404,
            detail="no overlay entry for recommendation_id",
        )

    return {
        "recommendation_id": entry.recommendation_id,
        "symbol": entry.symbol,
        "intraday_change_pct": entry.intraday_change_pct,
        "vs_recommendation_entry_pct": entry.vs_recommendation_entry_pct,
        "vs_macro_drift_pct": entry.vs_macro_drift_pct,
        "context_label": entry.context_label,
        "derived_at": _ts_to_iso(entry.derived_at),
        "quote_ts": _ts_to_iso(entry.quote_ts),
        "source": entry.source,
        "delay_minutes": entry.delay_minutes,
        "stale": tape_is_stale,
    }
