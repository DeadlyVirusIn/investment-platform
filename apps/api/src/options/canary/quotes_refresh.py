"""P6D.34C/34D — targeted intraday quote refresh for the canary.

P6D.34C (lifecycle): before the lifecycle cycle evaluates exit decisions,
refresh the option chain for each DISTINCT underlying that currently has an
open (unreleased) canary position. This keeps the decision quotes'
effective age (P6D.34A) under the freshness gate
(OPTIONS_CANARY_MAX_DECISION_AGE_SECONDS) so TP / DTE-management closes act
on current prices instead of hours-old snapshots.

P6D.34D (promotion): before the promotion cycle runs the selector, refresh
the chain for the canary UNIVERSE underlyings (refresh_universe_quotes) so
candidate legs carry ~0 effective age and clear the promotion freshness
gate (OPTIONS_CANARY_MAX_PROMOTION_AGE_SECONDS).

STRICTLY read-only with respect to portfolio / trade state — the only
write this module triggers is chain ingestion (an append-only
options_chain_snapshot market-data insert via
chain_ingest.ingest_chain_snapshot, natural-key deduped). Per-underlying
failures are captured and reported, NEVER raised — a refresh failure must
never block a cycle (lifecycle decisions then HOLD_STALE_QUOTES; the
selector then skips stale candidates with reason 'stale_quotes').
"""

from __future__ import annotations

import datetime as dt

from loguru import logger
from sqlalchemy import text

_OPEN_UNDERLYINGS_SQL = text(
    """
    SELECT DISTINCT t.underlying
    FROM options_paper_position p
    JOIN options_paper_trade t ON t.id = p.trade_id
    WHERE p.portfolio_id = :pid AND p.released_at IS NULL
    """
)


def refresh_open_position_quotes(
    *,
    portfolio_id: str,
    session_factory,
    ingest_fn=None,
    now: dt.datetime | None = None,
) -> dict:
    """Refresh chain snapshots for every underlying with an open position.

    Returns
        {"refreshed": [underlyings], "failed": [{"underlying","error"}],
         "skipped": "no_open_positions" | None}

    * One short session for the DISTINCT-underlying read.
    * `ingest_fn` defaults to chain_ingest.ingest_chain_snapshot (lazy
      import avoids cycles). It is called per underlying with
      (underlying=, snapshot_at_utc=now, session_factory=) — the ingest
      pipeline opens/commits its own sessions via the factory.
    * Per-underlying try/except: a failing provider pull lands in
      `failed` with the error string; the function NEVER raises.
    """
    if now is None:
        now = dt.datetime.now(dt.timezone.utc)

    with session_factory() as s:
        underlyings = [r[0] for r in s.execute(
            _OPEN_UNDERLYINGS_SQL, {"pid": portfolio_id}).all()]

    if not underlyings:
        return {"refreshed": [], "failed": [], "skipped": "no_open_positions"}

    refreshed, failed = _refresh_underlyings(
        underlyings, session_factory=session_factory,
        ingest_fn=ingest_fn, now=now, context=f"pid={portfolio_id}",
    )
    return {"refreshed": refreshed, "failed": failed, "skipped": None}


def refresh_universe_quotes(
    *,
    underlyings: list[str],
    session_factory,
    ingest_fn=None,
    now: dt.datetime | None = None,
) -> dict:
    """P6D.34D — refresh chain snapshots for the canary UNIVERSE underlyings
    (promotion-cycle counterpart of refresh_open_position_quotes).

    Returns
        {"refreshed": [underlyings], "failed": [{"underlying","error"}],
         "skipped": "no_underlyings" | None}

    Same failure-tolerant per-underlying shape: a failing provider pull
    lands in `failed` with the error string; the function NEVER raises.
    """
    if now is None:
        now = dt.datetime.now(dt.timezone.utc)

    wanted = sorted({u for u in (underlyings or []) if u})
    if not wanted:
        return {"refreshed": [], "failed": [], "skipped": "no_underlyings"}

    refreshed, failed = _refresh_underlyings(
        wanted, session_factory=session_factory,
        ingest_fn=ingest_fn, now=now, context="universe",
    )
    return {"refreshed": refreshed, "failed": failed, "skipped": None}


def _refresh_underlyings(
    underlyings, *, session_factory, ingest_fn, now, context: str,
) -> tuple[list[str], list[dict]]:
    """Shared 34C/34D core: per-underlying ingest, failure-tolerant.

    `ingest_fn` defaults to chain_ingest.ingest_chain_snapshot (lazy import
    avoids cycles). Called per underlying with (underlying=,
    snapshot_at_utc=now, session_factory=) — the ingest pipeline
    opens/commits its own sessions via the factory. NEVER raises."""
    if ingest_fn is None:
        # Lazy import — chain_ingest pulls adapters/settings; keep canary
        # import graph cycle-free.
        from apps.api.src.options.data.chain_ingest import (
            ingest_chain_snapshot,
        )
        ingest_fn = ingest_chain_snapshot

    refreshed: list[str] = []
    failed: list[dict] = []
    for underlying in sorted(underlyings):
        try:
            ingest_fn(
                underlying=underlying,
                snapshot_at_utc=now,
                session_factory=session_factory,
            )
            refreshed.append(underlying)
        except Exception as exc:   # noqa: BLE001 — never raise out
            failed.append({"underlying": underlying, "error": str(exc)})
            logger.warning(
                "canary quote refresh failed underlying={} {}: {}",
                underlying, context, exc,
            )
    return refreshed, failed
