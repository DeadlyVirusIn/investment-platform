"""Options chain snapshot ingest orchestrator (Phase 11C).

Pulls chain via adapter → filters → fills missing Greeks via stdlib BSM
→ INSERT-only into options_chain_snapshot. Append-only. Idempotent on
the table's natural key (snapshot_at_utc, underlying, expiry, strike,
option_type) — duplicate ingests are no-ops via ON CONFLICT DO NOTHING.

NEVER updates rows. NEVER deletes. NEVER imports V2 / equity / strategy
/ execution code.
"""

from __future__ import annotations

import dataclasses
import datetime
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterable

from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session

from apps.api.src.config import settings
from apps.api.src.db import SessionLocal
from apps.api.src.options.data.liquidity_filter import (
    FilterResult,
    filter_chain,
)
from apps.api.src.options.data_provider.base_adapter import (
    BaseOptionsAdapter,
    OptionChainQuote,
    PartialChainWarning,
    ProviderError,
    ProviderUnavailable,
)
from apps.api.src.options.data_provider.greeks import (
    fill_missing_greeks,
)
from apps.api.src.options.data_provider.thetadata_adapter import (
    ThetaDataAdapter,
)


# Default v1 universe — frozen per docs/research/OPTIONS_STRATEGY_UNIVERSE.md
DEFAULT_UNIVERSE: tuple[str, ...] = ("SPY", "QQQ", "IWM", "GLD", "TLT")


@dataclass(frozen=True)
class IngestSummary:
    underlying: str
    snapshot_at_utc: datetime.datetime
    status: str                             # "ok" | "skipped_unavailable" | "error" | "partial"
    n_provider_quotes: int = 0
    n_filtered: int = 0
    n_inserted: int = 0
    n_skipped_existing: int = 0
    reject_counts: dict[str, int] = field(default_factory=dict)
    note: str | None = None


_INSERT_SQL = text(
    """
    INSERT INTO options_chain_snapshot
      (snapshot_at_utc, underlying, expiry, strike, option_type,
       option_symbol, bid, ask, mid, last,
       volume, open_interest,
       delta, gamma, theta, vega, iv,
       quote_age_seconds, provider, provider_version)
    VALUES
      (:snapshot_at_utc, :underlying, :expiry, :strike, :option_type,
       :option_symbol, :bid, :ask, :mid, :last,
       :volume, :open_interest,
       :delta, :gamma, :theta, :vega, :iv,
       :quote_age_seconds, :provider, :provider_version)
    ON CONFLICT ON CONSTRAINT ux_options_chain_snapshot_natural_key
        DO NOTHING
    """
)


def _build_adapter(provider_name: str) -> BaseOptionsAdapter:
    """Provider-name → adapter instance. Frozen v1 = ThetaData only."""
    if provider_name == "thetadata":
        return ThetaDataAdapter()
    raise ValueError(
        f"unknown options data provider {provider_name!r}; "
        f"v1 supports 'thetadata' only"
    )


def _enrich_with_greeks(
    quote: OptionChainQuote,
    *,
    snapshot_date: datetime.date,
    spot: Decimal | None,
    rate: Decimal | None,
    div_yield: Decimal | None,
) -> OptionChainQuote:
    """Fill missing IV / Greeks via stdlib BSM. Returns a NEW frozen
    dataclass (no mutation)."""
    if spot is None:
        # Cannot compute Greeks without spot — return quote unchanged
        return quote
    g = fill_missing_greeks(
        option_type=quote.option_type,
        spot=spot,
        strike=quote.strike,
        snapshot_date=snapshot_date,
        expiry_date=quote.expiry,
        market_price=quote.mid,
        provider_iv=quote.iv,
        provider_delta=quote.delta,
        provider_gamma=quote.gamma,
        provider_theta=quote.theta,
        provider_vega=quote.vega,
        rate=rate or Decimal("0.05"),
        div_yield=div_yield or Decimal("0.0"),
    )
    return dataclasses.replace(
        quote,
        iv=Decimal(str(g.iv)) if g.iv is not None else quote.iv,
        delta=Decimal(str(g.delta)) if g.delta is not None else quote.delta,
        gamma=Decimal(str(g.gamma)) if g.gamma is not None else quote.gamma,
        theta=Decimal(str(g.theta)) if g.theta is not None else quote.theta,
        vega=Decimal(str(g.vega)) if g.vega is not None else quote.vega,
    )


def _insert_quotes(
    session: Session,
    quotes: Iterable[OptionChainQuote],
) -> tuple[int, int]:
    """Append-only INSERT with ON CONFLICT DO NOTHING.
    Returns (inserted_count, skipped_count)."""
    inserted = 0
    skipped = 0
    for q in quotes:
        result = session.execute(
            _INSERT_SQL,
            {
                "snapshot_at_utc": q.snapshot_at_utc,
                "underlying": q.underlying,
                "expiry": q.expiry,
                "strike": q.strike,
                "option_type": q.option_type,
                "option_symbol": q.option_symbol,
                "bid": q.bid,
                "ask": q.ask,
                "mid": q.mid,
                "last": q.last,
                "volume": q.volume,
                "open_interest": q.open_interest,
                "delta": q.delta,
                "gamma": q.gamma,
                "theta": q.theta,
                "vega": q.vega,
                "iv": q.iv,
                "quote_age_seconds": q.quote_age_seconds,
                "provider": q.provider,
                "provider_version": q.provider_version,
            },
        )
        if result.rowcount and result.rowcount > 0:
            inserted += 1
        else:
            skipped += 1
    session.commit()
    return inserted, skipped


def ingest_chain_snapshot(
    *,
    underlying: str,
    snapshot_at_utc: datetime.datetime | None = None,
    adapter: BaseOptionsAdapter | None = None,
    require_iv: bool = False,
    require_greeks: bool = False,
    session_factory=SessionLocal,
) -> IngestSummary:
    """Ingest one chain snapshot for one underlying.

    Pure-orchestration with explicit dependencies for testability:
      * adapter — defaults to ThetaDataAdapter via settings.OPTIONS_DATA_PROVIDER
      * session_factory — defaults to SessionLocal

    Filters per `liquidity_filter.filter_chain`. Fills missing Greeks
    via stdlib BSM. INSERTs into options_chain_snapshot append-only.
    """
    snapshot_at = snapshot_at_utc or datetime.datetime.now(datetime.timezone.utc)
    adp = adapter or _build_adapter(settings.OPTIONS_DATA_PROVIDER)

    try:
        result = adp.get_chain_snapshot(
            symbol=underlying, timestamp=snapshot_at,
        )
        partial_note = None
    except PartialChainWarning as warn:
        # Partial chain is allowed — use the rows the adapter did fetch,
        # flag the snapshot as partial. The warning carries the partial
        # ChainSnapshotResult on `warn.result`.
        partial_note = str(warn)
        if warn.result is None:
            return IngestSummary(
                underlying=underlying,
                snapshot_at_utc=snapshot_at,
                status="partial_then_failed",
                note=str(warn),
            )
        result = warn.result
    except ProviderUnavailable as exc:
        logger.warning(
            "options ingest skipped (provider unavailable) {} @ {}: {}",
            underlying, snapshot_at, exc,
        )
        return IngestSummary(
            underlying=underlying,
            snapshot_at_utc=snapshot_at,
            status="skipped_unavailable",
            note=str(exc),
        )
    except ProviderError as exc:
        logger.error(
            "options ingest error {} @ {}: {}",
            underlying, snapshot_at, exc,
        )
        return IngestSummary(
            underlying=underlying,
            snapshot_at_utc=snapshot_at,
            status="error",
            note=str(exc),
        )

    n_provider = len(result.quotes)

    # Enrich missing Greeks (when spot available)
    enriched: list[OptionChainQuote] = [
        _enrich_with_greeks(
            q,
            snapshot_date=snapshot_at.date(),
            spot=result.underlying_price,
            rate=result.interest_rate,
            div_yield=result.dividend_yield,
        )
        for q in result.quotes
    ]

    # Apply liquidity filter
    filtered: FilterResult = filter_chain(
        enriched,
        require_iv=require_iv,
        require_greeks=require_greeks,
    )

    # INSERT (append-only)
    with session_factory() as session:
        inserted, skipped = _insert_quotes(session, filtered.accepted)

    status = "partial" if (result.partial or partial_note) else "ok"
    summary = IngestSummary(
        underlying=underlying,
        snapshot_at_utc=snapshot_at,
        status=status,
        n_provider_quotes=n_provider,
        n_filtered=filtered.n_accepted,
        n_inserted=inserted,
        n_skipped_existing=skipped,
        reject_counts=dict(filtered.reject_counts),
        note=partial_note,
    )
    logger.info(
        "options chain ingest {} @ {} status={} provider={} filtered={} "
        "inserted={} skipped_existing={} rejects={}",
        underlying, snapshot_at, status, n_provider,
        filtered.n_accepted, inserted, skipped,
        filtered.reject_counts,
    )
    return summary


def ingest_universe(
    *,
    universe: tuple[str, ...] = DEFAULT_UNIVERSE,
    snapshot_at_utc: datetime.datetime | None = None,
    adapter: BaseOptionsAdapter | None = None,
    require_iv: bool = False,
    require_greeks: bool = False,
    session_factory=SessionLocal,
) -> list[IngestSummary]:
    """Ingest chain snapshots for the v1 ETF universe. One adapter call
    per underlying; failures on one underlying do not stop the others."""
    snapshot_at = snapshot_at_utc or datetime.datetime.now(datetime.timezone.utc)
    out: list[IngestSummary] = []
    for symbol in universe:
        out.append(ingest_chain_snapshot(
            underlying=symbol,
            snapshot_at_utc=snapshot_at,
            adapter=adapter,
            require_iv=require_iv,
            require_greeks=require_greeks,
            session_factory=session_factory,
        ))
    return out
