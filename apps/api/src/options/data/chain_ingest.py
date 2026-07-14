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
import json
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Iterable

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
from apps.api.src.options.data_provider.finnhub_adapter import (
    FinnhubOptionsAdapter,
)
from apps.api.src.options.data_provider.tradier_adapter import (
    TradierOptionsAdapter,
)


# Default universe. ETFs were the v1 frozen set
# (docs/research/OPTIONS_STRATEGY_UNIVERSE.md). Phase: add liquid
# single-name equities so Options Practice isn't ETF-only — Tradier
# verified to return full chains for these (e.g. AAPL ~1378 quotes).
# Conservative, deeply-liquid names with tight option markets.
# New names surface in the UI only after the nightly chain→shadow→
# candidate pipeline processes them.
_ETF_UNIVERSE: tuple[str, ...] = ("SPY", "QQQ", "IWM", "GLD", "TLT")
_EQUITY_UNIVERSE: tuple[str, ...] = (
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL",
    "META", "TSLA", "AMD", "NFLX", "JPM",
)
DEFAULT_UNIVERSE: tuple[str, ...] = _ETF_UNIVERSE + _EQUITY_UNIVERSE


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
    # Phase Opt-B3a — filter provenance: which liquidity profile
    # admitted these contracts? Stamped from
    # liquidity_filter.resolve_profile(provider_version).
    profile_name: str | None = None
    provider: str | None = None
    provider_version: str | None = None


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
    """Provider-name → adapter instance.

    Phase Opt-B3a — three providers wired:
      * 'tradier'   — sandbox or production; provider-native Greeks/IV;
                      Bearer-header auth; chosen as initial low-cost
                      activation path (sandbox tier).
      * 'finnhub'   — kept for legacy/free-tier paths; adapter exists
                      but free tier blocks /stock/option-chain (403).
      * 'thetadata' — paid OPRA-direct path; future upgrade route.
    """
    if provider_name == "thetadata":
        return ThetaDataAdapter()
    if provider_name == "finnhub":
        return FinnhubOptionsAdapter()
    if provider_name == "tradier":
        return TradierOptionsAdapter()
    raise ValueError(
        f"unknown options data provider {provider_name!r}; "
        f"supported: 'thetadata', 'finnhub', 'tradier'"
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

    # Phase Opt-B3a — resolve liquidity profile from provider tagging.
    # Sample provider_version off the first quote (all quotes from a
    # single snapshot share the same provider tag by adapter contract).
    # Adapters emitting empty result.quotes still produce a result
    # object with `result.provider` set — fall back to strict-default
    # in that case (FAIL-CLOSED).
    sample_provider_version: str | None = (
        result.quotes[0].provider_version if result.quotes else None
    )
    sample_provider: str | None = (
        result.quotes[0].provider if result.quotes else result.provider
    )
    from apps.api.src.options.data.liquidity_filter import resolve_profile
    profile = resolve_profile(sample_provider_version)

    # Apply liquidity filter under the resolved profile
    filtered: FilterResult = filter_chain(
        enriched,
        require_iv=require_iv,
        require_greeks=require_greeks,
        min_open_interest=profile.min_open_interest,
        max_spread_dollars=profile.max_spread_dollars,
        max_quote_age_seconds=profile.max_quote_age_seconds,
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
        profile_name=profile.name,
        provider=sample_provider,
        provider_version=sample_provider_version,
    )
    logger.info(
        "options chain ingest {} @ {} status={} provider={} "
        "provider_version={} profile={} provider_quotes={} filtered={} "
        "inserted={} skipped_existing={} rejects={}",
        underlying, snapshot_at, status,
        sample_provider, sample_provider_version, profile.name,
        n_provider, filtered.n_accepted, inserted, skipped,
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


# ---------------------------------------------------------------------------
# Ingest-run telemetry (options_chain_ingest_run)
#
# Phase Opt-Obs-Fix1 — restore the run-summary telemetry the
# admin-observability `options_chains` freshness card reads from. The
# 14:15 market-hours handler writes options_chain_snapshot rows but the
# run-summary writer was dropped during a worker rebuild (registry
# drift), leaving the card anchored to a dead table (last row 05-28) and
# falsely reading 'stale' while the data table was fresh. This writes one
# row per ingest_universe() invocation, mirroring envelope_generation_run.
# ---------------------------------------------------------------------------

# Per-symbol statuses that mean "this underlying produced no usable rows".
_ERROR_STATUSES = ("error", "partial_then_failed", "skipped_unavailable")

_INGEST_RUN_INSERT_SQL = text(
    """
    INSERT INTO options_chain_ingest_run
      (started_at, finished_at, provider, universe,
       rows_inserted, rows_dedup, rows_filtered_out,
       n_symbols_ok, n_symbols_partial, n_symbols_error,
       classification, error_summary, duration_sec)
    VALUES
      (:started_at, :finished_at, :provider, :universe,
       :rows_inserted, :rows_dedup, :rows_filtered_out,
       :n_symbols_ok, :n_symbols_partial, :n_symbols_error,
       :classification, CAST(:error_summary AS JSONB), :duration_sec)
    """
)


def build_ingest_run_record(
    summaries: list[IngestSummary],
    *,
    started_at: datetime.datetime,
    finished_at: datetime.datetime,
    universe: tuple[str, ...],
    provider_default: str,
) -> dict[str, Any]:
    """Aggregate per-underlying IngestSummary list → one ingest-run row.

    Pure (no DB / no clock). Classification taxonomy mirrors migration
    089:  'success' | 'partial' | 'no_new_data' | 'error'. ('flags_off'
    is emitted by the caller's skip path, not here.)
      * success    — at least one row inserted, no partial symbols.
      * partial    — rows inserted but >=1 underlying came back partial.
      * no_new_data— provider returned quotes but all were deduped /
                     filtered (0 inserted) — a healthy idempotent re-run.
      * error      — provider returned nothing AND >=1 underlying errored.
    """
    n_ok = sum(1 for s in summaries if s.status == "ok")
    n_partial = sum(1 for s in summaries if s.status == "partial")
    n_error = sum(1 for s in summaries if s.status in _ERROR_STATUSES)

    rows_inserted = sum(s.n_inserted for s in summaries)
    rows_dedup = sum(s.n_skipped_existing for s in summaries)
    rows_filtered_out = sum(
        max(0, s.n_provider_quotes - s.n_filtered) for s in summaries
    )
    total_provider = sum(s.n_provider_quotes for s in summaries)

    provider = next(
        (s.provider for s in summaries if s.provider), provider_default,
    )
    provider_version = next(
        (s.provider_version for s in summaries if s.provider_version), None,
    )

    if rows_inserted > 0:
        classification = "partial" if n_partial > 0 else "success"
    elif total_provider == 0 and n_error > 0:
        classification = "error"
    elif n_partial > 0:
        classification = "partial"
    else:
        # provider gave quotes but nothing new landed → healthy idempotent
        # re-run; or genuinely empty universe — both are 'no_new_data'.
        classification = "no_new_data"

    notes = {s.underlying: s.note for s in summaries if s.note}
    reject_totals: dict[str, int] = {}
    for s in summaries:
        for key, val in (s.reject_counts or {}).items():
            reject_totals[key] = reject_totals.get(key, 0) + int(val)

    error_summary: dict[str, Any] | None = None
    if notes or reject_totals or provider_version:
        error_summary = {
            "provider_version": provider_version,
            "reject_counts": reject_totals or None,
            "notes": notes or None,
        }

    duration_sec = round((finished_at - started_at).total_seconds(), 3)

    return {
        "started_at": started_at,
        "finished_at": finished_at,
        "provider": provider,
        "universe": list(universe),
        "rows_inserted": rows_inserted,
        "rows_dedup": rows_dedup,
        "rows_filtered_out": rows_filtered_out,
        "n_symbols_ok": n_ok,
        "n_symbols_partial": n_partial,
        "n_symbols_error": n_error,
        "classification": classification,
        "error_summary": error_summary,
        "duration_sec": duration_sec,
    }


def persist_ingest_run(
    record: dict[str, Any],
    *,
    session_factory=SessionLocal,
) -> None:
    """Append-only INSERT of one ingest-run telemetry row. Defensive: the
    caller wraps this so a telemetry-write failure never breaks ingest."""
    params = dict(record)
    params["error_summary"] = (
        json.dumps(record["error_summary"])
        if record.get("error_summary") is not None else None
    )
    with session_factory() as session:
        session.execute(_INGEST_RUN_INSERT_SQL, params)
        session.commit()
