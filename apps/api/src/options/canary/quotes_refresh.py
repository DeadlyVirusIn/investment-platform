"""P6D.34C — targeted intraday quote refresh for OPEN canary positions.

Before the lifecycle cycle evaluates exit decisions, refresh the option
chain for each DISTINCT underlying that currently has an open (unreleased)
canary position. This keeps the decision quotes' effective age (P6D.34A)
under the freshness gate (OPTIONS_CANARY_MAX_DECISION_AGE_SECONDS) so
TP / DTE-management closes act on current prices instead of hours-old
snapshots.

STRICTLY read-only with respect to portfolio / trade state — the only
write this module triggers is chain ingestion (an append-only
options_chain_snapshot market-data insert via
chain_ingest.ingest_chain_snapshot, natural-key deduped). Per-underlying
failures are captured and reported, NEVER raised — a refresh failure must
never block the lifecycle cycle (decisions then simply see stale quotes
and HOLD_STALE_QUOTES).
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
                "canary quote refresh failed underlying={} pid={}: {}",
                underlying, portfolio_id, exc,
            )

    return {"refreshed": refreshed, "failed": failed, "skipped": None}
