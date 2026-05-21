"""Live mark-to-market NAV endpoint.

Phase 1a deliverable. Computes a near-real-time estimate of paper-trading
portfolio NAV using Polygon delayed quotes (15-min, Stocks Starter tier),
with graceful fallback to the most recent EOD close in `price_bar` when
Polygon is unavailable or a symbol is missing from the bulk snapshot.

Does NOT:
  - write to options_paper_* or paper_equity_snapshot
  - mutate any DB row
  - replace the canonical `/api/paper/summary` endpoint
  - alter accounting semantics

Does:
  - read `paper_portfolio.cash`           (live, mutated on every fill)
  - read `paper_position` WHERE is_open   (live)
  - call `polygon.fetch_tape_snapshot`    (one bulk HTTP request)
  - fall back to `price_bar.close`        (last EOD per symbol) when needed
  - cache the response for 30 seconds     (in-process)

UI labelling contract (Phase 1b):
  - "Live estimate · prices delayed 15 min"   for this endpoint's output
  - "Official close · <snapshot_date>"        for `/api/paper/summary` output

See: docs/research/PORTFOLIO_LIVE_MTM_AUDIT.md
     docs/research/PORTFOLIO_RECONCILIATION_FORENSIC_AUDIT.md
"""

from __future__ import annotations

import asyncio
import logging
import time
from decimal import Decimal
from typing import Any, Literal

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.src.db import get_session
from apps.api.src.db.models import (
    Asset, PaperPortfolio, PaperPosition, PriceBar,
)
from apps.api.src.providers import polygon


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/paper", tags=["paper-trading-live"])


# ---------------------------------------------------------------------------
# Cache (in-process, single instance — sufficient for one API replica).
# Concurrency lock prevents thundering-herd on cache miss.
# ---------------------------------------------------------------------------

_CACHE: dict[str, Any] = {"ts": 0.0, "payload": None}
_CACHE_TTL_SECONDS = 30
_CACHE_LOCK: asyncio.Lock = asyncio.Lock()

# Polygon HTTP budget. Reduced read timeout from 10s → 6s post-hardening
# so the EOD fallback chain kicks in faster on a degraded provider.
_POLYGON_TIMEOUT = httpx.Timeout(6.0, connect=4.0)

# Drift threshold beyond which we emit a WARN. Live vs official should
# track within ~15% on a typical session; larger gaps indicate either a
# corrupt snapshot, a price-source mismatch, or a held position outside
# the priceable universe.
_DRIFT_WARN_THRESHOLD = 0.15


FreshnessTier = Literal[
    "live",           # all symbols Polygon-priced, no fallback
    "live_partial",   # Polygon ok, some symbols on EOD fallback
    "fallback_eod",   # Polygon error/unavailable, EOD covers all
    "fallback_cost",  # at least one position on cost-basis fallback
]


def _compute_freshness_tier(
    polygon_status: str,
    n_live: int,
    n_fallback_eod: int,
    n_fallback_cost: int,
) -> FreshnessTier:
    if n_fallback_cost > 0:
        return "fallback_cost"
    if polygon_status != "ok":
        return "fallback_eod"
    if n_fallback_eod > 0:
        return "live_partial"
    return "live"


def _dec(v: Any) -> Decimal:
    if v is None:
        return Decimal("0")
    if isinstance(v, Decimal):
        return v
    return Decimal(str(v))


def _str(v: Decimal) -> str:
    return f"{v:.4f}"


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.get("/live-nav")
async def get_live_nav(
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Live MTM NAV across all active paper portfolios.

    Response shape (excerpt):
      {
        "live_estimated_nav":   "117500.0000",
        "live_cash":            "116693.1234",
        "live_holdings":        "806.8766",
        "starting_total":       "112000.0000",
        "prices_as_of_epoch":   1748234567.0,
        "polygon_status":       "ok" | "error" | "unavailable",
        "polygon_error":        null | "<short error>",
        "delay_minutes":        15,
        "n_symbols_total":      54,
        "n_symbols_priced_live":     54,
        "n_symbols_priced_fallback": 0,
        "cached_at_epoch":      1748234570.0,
        "cache_ttl_seconds":    30,
        "portfolios":           [ {...per portfolio...}, ... ]
      }

    No DB writes. 30-second in-process cache. Polygon failure does NOT
    surface as HTTP error — payload still returns with `polygon_status`
    flag and EOD fallback prices applied.
    """
    now_epoch = time.time()

    # Fast path — cache hit without lock.
    if (
        _CACHE["payload"] is not None
        and (now_epoch - _CACHE["ts"]) < _CACHE_TTL_SECONDS
    ):
        cached = dict(_CACHE["payload"])
        cached["cache_hit"] = True
        logger.debug(
            "live-nav cache hit",
            extra={"age_s": now_epoch - _CACHE["ts"]},
        )
        return cached

    # Cache miss — acquire lock and re-check (thundering-herd guard).
    async with _CACHE_LOCK:
        now_epoch = time.time()
        if (
            _CACHE["payload"] is not None
            and (now_epoch - _CACHE["ts"]) < _CACHE_TTL_SECONDS
        ):
            cached = dict(_CACHE["payload"])
            cached["cache_hit"] = True
            logger.debug("live-nav cache hit (post-lock)")
            return cached

        logger.info(
            "live-nav cache miss — refetching",
            extra={"ttl_s": _CACHE_TTL_SECONDS},
        )
        payload = await _build_live_nav_payload(session, now_epoch)
        _CACHE["ts"] = now_epoch
        _CACHE["payload"] = payload
        return payload


async def _build_live_nav_payload(
    session: Session, now_epoch: float,
) -> dict[str, Any]:
    """Compute fresh payload. Caller holds _CACHE_LOCK.

    Split out from `get_live_nav` so the lock-protected critical section
    is small and the function under test is independently exercisable.
    """
    # ---- 1. Active portfolios + their open positions + symbols --------
    rows = session.execute(
        select(
            PaperPortfolio.id,
            PaperPortfolio.name,
            PaperPortfolio.cash,
            PaperPortfolio.starting_cash,
            PaperPosition.asset_id,
            Asset.symbol,
            PaperPosition.quantity,
            PaperPosition.avg_cost,
        )
        .select_from(PaperPortfolio)
        .outerjoin(
            PaperPosition,
            (PaperPosition.portfolio_id == PaperPortfolio.id)
            & (PaperPosition.is_open.is_(True))
            & (PaperPosition.quantity > 0),
        )
        .outerjoin(Asset, Asset.id == PaperPosition.asset_id)
        .where(PaperPortfolio.is_active.is_(True))
    ).all()

    symbols = sorted({r.symbol for r in rows if r.symbol})

    # ---- 2. Polygon bulk snapshot ------------------------------------
    polygon_status: str
    polygon_error: str | None = None
    live_prices: dict[str, dict[str, Any]] = {}
    if not polygon.is_available():
        polygon_status = "unavailable"
    elif not symbols:
        polygon_status = "ok"  # no symbols to price; trivially OK
    else:
        try:
            async with httpx.AsyncClient(timeout=_POLYGON_TIMEOUT) as client:
                quotes = await polygon.fetch_tape_snapshot(client, symbols)
            for q in quotes:
                sym = q.get("symbol")
                if sym and q.get("price") is not None:
                    live_prices[sym] = q
            polygon_status = "ok"
        except Exception as exc:  # noqa: BLE001
            polygon_status = "error"
            polygon_error = f"{type(exc).__name__}: {str(exc)[:200]}"
            logger.warning("live-nav: polygon fetch failed: %s", polygon_error)

    # ---- 3. EOD fallback for symbols missing from Polygon ------------
    fallback_symbols = [s for s in symbols if s not in live_prices]
    eod_fallback: dict[str, dict[str, Any]] = {}
    if fallback_symbols:
        # One pass per symbol — small N (≤ universe size). Could be
        # rewritten as LATERAL JOIN; kept readable here.
        for sym in fallback_symbols:
            bar = session.execute(
                select(PriceBar.close, PriceBar.ts, PriceBar.provider)
                .join(Asset, Asset.id == PriceBar.asset_id)
                .where(
                    Asset.symbol == sym,
                    PriceBar.timeframe == "1d",
                    PriceBar.close.is_not(None),
                )
                .order_by(PriceBar.ts.desc())
                .limit(1)
            ).first()
            if bar is not None:
                eod_fallback[sym] = {
                    "price": _dec(bar.close),
                    "ts_epoch": bar.ts.timestamp() if bar.ts else None,
                    "provider": bar.provider,
                }

    # ---- 4. Per-portfolio aggregation --------------------------------
    portfolios: dict[str, dict[str, Any]] = {}
    for r in rows:
        p_id = r.id
        if p_id not in portfolios:
            portfolios[p_id] = {
                "id": p_id,
                "name": r.name,
                "cash": _dec(r.cash),
                "starting_cash": _dec(r.starting_cash),
                "holdings_value": Decimal("0"),
                "unrealized_pnl": Decimal("0"),
                "n_positions": 0,
                "n_priced_live": 0,
                "n_priced_fallback_eod": 0,
                "n_priced_fallback_cost": 0,
                "positions": [],
            }
        if r.asset_id is None:
            continue

        sym = r.symbol
        qty = _dec(r.quantity)
        cost = _dec(r.avg_cost)

        live_q = live_prices.get(sym)
        eod_q = eod_fallback.get(sym)

        if live_q and live_q.get("price") is not None:
            price = _dec(live_q["price"])
            price_source = "polygon"
            price_ts = live_q.get("quote_ts")
            portfolios[p_id]["n_priced_live"] += 1
        elif eod_q:
            price = _dec(eod_q["price"])
            price_source = "eod_fallback"
            price_ts = eod_q.get("ts_epoch")
            portfolios[p_id]["n_priced_fallback_eod"] += 1
        else:
            price = cost
            price_source = "cost_basis_fallback"
            price_ts = None
            portfolios[p_id]["n_priced_fallback_cost"] += 1

        mv = qty * price
        upnl = qty * (price - cost)
        portfolios[p_id]["holdings_value"] += mv
        portfolios[p_id]["unrealized_pnl"] += upnl
        portfolios[p_id]["n_positions"] += 1

        # Per-position age in seconds — frontend renders a small
        # indicator when this exceeds ~15min for live quotes, or
        # surfaces it as a stale-EOD hint for fallback symbols.
        price_age_seconds: float | None
        if price_ts is not None:
            price_age_seconds = max(0.0, now_epoch - float(price_ts))
        else:
            price_age_seconds = None

        portfolios[p_id]["positions"].append({
            "symbol": sym,
            "qty": _str(qty),
            "avg_cost": _str(cost),
            "price": _str(price),
            "price_source": price_source,
            "price_ts_epoch": price_ts,
            "price_age_seconds": (
                round(price_age_seconds, 1)
                if price_age_seconds is not None else None
            ),
            "market_value": _str(mv),
            "unrealized_pnl": _str(upnl),
        })

    # ---- 5. Aggregate envelope ---------------------------------------
    portfolios_out: list[dict[str, Any]] = []
    agg_cash = Decimal("0")
    agg_holdings = Decimal("0")
    agg_starting = Decimal("0")
    agg_unrealized = Decimal("0")
    agg_priced_live = 0
    agg_priced_fallback_eod = 0
    agg_priced_fallback_cost = 0
    for p in portfolios.values():
        live_nav = p["cash"] + p["holdings_value"]
        agg_cash += p["cash"]
        agg_holdings += p["holdings_value"]
        agg_starting += p["starting_cash"]
        agg_unrealized += p["unrealized_pnl"]
        agg_priced_live += p["n_priced_live"]
        agg_priced_fallback_eod += p["n_priced_fallback_eod"]
        agg_priced_fallback_cost += p["n_priced_fallback_cost"]
        portfolios_out.append({
            "id": p["id"],
            "name": p["name"],
            "cash": _str(p["cash"]),
            "starting_cash": _str(p["starting_cash"]),
            "holdings_value": _str(p["holdings_value"]),
            "unrealized_pnl": _str(p["unrealized_pnl"]),
            "live_nav": _str(live_nav),
            "n_positions": p["n_positions"],
            "n_priced_live": p["n_priced_live"],
            "n_priced_fallback_eod": p["n_priced_fallback_eod"],
            "n_priced_fallback_cost": p["n_priced_fallback_cost"],
            "positions": p["positions"],
        })

    # `prices_as_of_epoch` = max quote_ts across live-priced symbols.
    # When ALL prices come from EOD fallback, surface that explicitly.
    quote_ts_values = [
        q.get("quote_ts") for q in live_prices.values()
        if q.get("quote_ts")
    ]
    prices_as_of_epoch: float | None = max(quote_ts_values) if quote_ts_values else None

    # When Polygon is unavailable/error, the EOD fallback drives
    # `prices_as_of_epoch` instead. Report the freshest EOD ts.
    if prices_as_of_epoch is None and eod_fallback:
        eod_ts_values = [
            v.get("ts_epoch") for v in eod_fallback.values()
            if v.get("ts_epoch")
        ]
        if eod_ts_values:
            prices_as_of_epoch = max(eod_ts_values)

    freshness_tier = _compute_freshness_tier(
        polygon_status,
        agg_priced_live,
        agg_priced_fallback_eod,
        agg_priced_fallback_cost,
    )

    # Structured log on fallback usage (helps diagnose coverage gaps
    # and provider degradation early).
    if agg_priced_fallback_eod > 0 or agg_priced_fallback_cost > 0:
        logger.warning(
            "live-nav using fallback prices",
            extra={
                "freshness_tier": freshness_tier,
                "polygon_status": polygon_status,
                "n_priced_live": agg_priced_live,
                "n_priced_fallback_eod": agg_priced_fallback_eod,
                "n_priced_fallback_cost": agg_priced_fallback_cost,
                "n_symbols_total": len(symbols),
            },
        )

    # Drift check vs latest official snapshot. WARN when the gap is
    # large — either snapshot is corrupt, live data is stale, or a
    # held position falls outside the priceable universe.
    live_nav_value = agg_cash + agg_holdings
    official_nav_decimal = _query_latest_official_nav(session)
    drift_pct: float | None = None
    if official_nav_decimal is not None and official_nav_decimal != 0:
        drift_pct = float(
            abs(live_nav_value - official_nav_decimal) / official_nav_decimal,
        )
        if drift_pct > _DRIFT_WARN_THRESHOLD:
            logger.warning(
                "live-nav drift exceeds threshold",
                extra={
                    "live_nav": str(live_nav_value),
                    "official_nav": str(official_nav_decimal),
                    "drift_pct": drift_pct,
                    "threshold": _DRIFT_WARN_THRESHOLD,
                    "freshness_tier": freshness_tier,
                },
            )

    payload: dict[str, Any] = {
        "live_estimated_nav": _str(live_nav_value),
        "live_cash": _str(agg_cash),
        "live_holdings": _str(agg_holdings),
        "starting_total": _str(agg_starting),
        "unrealized_pnl_total": _str(agg_unrealized),
        "prices_as_of_epoch": prices_as_of_epoch,
        "polygon_status": polygon_status,
        "polygon_error": polygon_error,
        "delay_minutes": 15,
        "freshness_tier": freshness_tier,
        "official_nav_snapshot": (
            _str(official_nav_decimal)
            if official_nav_decimal is not None else None
        ),
        "drift_pct": drift_pct,
        "n_symbols_total": len(symbols),
        "n_symbols_priced_live": agg_priced_live,
        "n_symbols_priced_fallback_eod": agg_priced_fallback_eod,
        "n_symbols_priced_fallback_cost": agg_priced_fallback_cost,
        "n_portfolios_active": len(portfolios_out),
        "cached_at_epoch": now_epoch,
        "cache_ttl_seconds": _CACHE_TTL_SECONDS,
        "cache_hit": False,
        "portfolios": portfolios_out,
    }

    return payload


def _query_latest_official_nav(session: Session) -> Decimal | None:
    """Sum latest live snapshot total_equity across **active** portfolios.

    Mirrors the SELECT used by /api/paper/summary (operator.py
    `_latest_active_snapshots`). Filters to is_active portfolios so the
    drift comparison is apples-to-apples with the dashboard's "Official
    close" number. Read-only.
    """
    from apps.api.src.db.models import PaperEquitySnapshot
    rows = session.execute(
        select(
            PaperEquitySnapshot.portfolio_id,
            PaperEquitySnapshot.total_equity,
            PaperEquitySnapshot.snapshot_date,
            PaperEquitySnapshot.recorded_at,
        )
        .join(
            PaperPortfolio,
            PaperPortfolio.id == PaperEquitySnapshot.portfolio_id,
        )
        .where(
            PaperEquitySnapshot.source == "live",
            PaperPortfolio.is_active.is_(True),
        )
        .order_by(
            PaperEquitySnapshot.portfolio_id,
            PaperEquitySnapshot.snapshot_date.desc(),
            PaperEquitySnapshot.recorded_at.desc(),
        )
    ).all()
    if not rows:
        return None
    seen: set[str] = set()
    total = Decimal("0")
    for r in rows:
        if r.portfolio_id in seen:
            continue
        seen.add(r.portfolio_id)
        if r.total_equity is not None:
            total += _dec(r.total_equity)
    return total if seen else None
