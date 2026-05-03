"""Integration tests for the price-ingestion service against real Postgres.

Providers are replaced with in-memory stubs so tests stay deterministic and
don't hit Tiingo/Yahoo. The canonical → validate → reconcile → upsert path is
exercised end-to-end against the PriceBar table.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.src.db.models import Asset, PriceBar
from apps.api.src.domain.prices.canonical import RawProviderBar, source_priority
from apps.api.src.domain.prices.providers.base import (
    DailyPriceProvider,
    NoDataError,
    ProviderError,
)
from apps.api.src.domain.prices.service import (
    ingest_symbol,
    ingest_symbols,
    resolve_start_date,
)

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Stub providers
# ---------------------------------------------------------------------------


@dataclass
class StubProvider:
    name: str
    priority: int
    bars: dict[str, list[RawProviderBar]] = field(default_factory=dict)
    raise_exc: Exception | None = None
    empty: bool = False
    called: list[tuple[str, dt.date, dt.date]] = field(default_factory=list)

    async def fetch_daily_bars(self, symbol, start_date, end_date):
        self.called.append((symbol.upper(), start_date, end_date))
        if self.raise_exc:
            raise self.raise_exc
        if self.empty:
            raise NoDataError(f"{self.name} empty for {symbol}")
        return list(self.bars.get(symbol.upper(), []))


def _raw(date: str, o="100", h="102", low="99", c="101", adj="101", vol=1000, sym="AAPL"):
    return RawProviderBar(
        symbol=sym, date_iso=date,
        open=Decimal(o), high=Decimal(h), low=Decimal(low), close=Decimal(c),
        adjusted_close=Decimal(adj) if adj else None, volume=vol,
    )


# ---------------------------------------------------------------------------
# Success path — Tiingo only
# ---------------------------------------------------------------------------


async def test_tiingo_success_writes_bars(pg_session: Session) -> None:
    tiingo = StubProvider("tiingo", source_priority("tiingo"), {
        "AAPL": [_raw("2026-01-02"), _raw("2026-01-03")],
    })
    yahoo = StubProvider("yahoo", source_priority("yahoo"))

    report = await ingest_symbol(
        pg_session, "AAPL",
        providers=[tiingo, yahoo],
        start_date=dt.date(2026, 1, 1),
        end_date=dt.date(2026, 1, 5),
    )
    pg_session.commit()

    assert report.provider_used == "tiingo"
    assert report.bars_fetched == 2
    assert report.bars_written == 2
    assert yahoo.called == []   # yahoo never touched on success

    rows = list(pg_session.scalars(select(PriceBar).where(PriceBar.provider == "tiingo")))
    assert len(rows) == 2


# ---------------------------------------------------------------------------
# Fallback — Tiingo failure → Yahoo
# ---------------------------------------------------------------------------


async def test_tiingo_failure_falls_back_to_yahoo(pg_session: Session) -> None:
    tiingo = StubProvider("tiingo", source_priority("tiingo"),
                          raise_exc=ProviderError("http 500"))
    yahoo = StubProvider("yahoo", source_priority("yahoo"),
                         {"MSFT": [_raw("2026-01-02", sym="MSFT")]})

    report = await ingest_symbol(
        pg_session, "MSFT",
        providers=[tiingo, yahoo],
        start_date=dt.date(2026, 1, 1),
        end_date=dt.date(2026, 1, 5),
    )
    pg_session.commit()

    assert report.provider_used == "yahoo"
    assert report.provider_attempted == ["tiingo", "yahoo"]
    assert report.bars_written == 1
    assert any("tiingo" in w for w in report.warnings)


async def test_tiingo_empty_triggers_yahoo(pg_session: Session) -> None:
    tiingo = StubProvider("tiingo", source_priority("tiingo"), empty=True)
    yahoo = StubProvider("yahoo", source_priority("yahoo"),
                         {"NVDA": [_raw("2026-01-02", sym="NVDA")]})

    report = await ingest_symbol(
        pg_session, "NVDA",
        providers=[tiingo, yahoo],
        start_date=dt.date(2026, 1, 1),
        end_date=dt.date(2026, 1, 5),
    )
    pg_session.commit()
    assert report.provider_used == "yahoo"
    assert report.bars_written == 1


async def test_both_providers_fail_records_failure(pg_session: Session) -> None:
    tiingo = StubProvider("tiingo", source_priority("tiingo"), empty=True)
    yahoo = StubProvider("yahoo", source_priority("yahoo"), empty=True)
    report = await ingest_symbol(
        pg_session, "ZZZ",
        providers=[tiingo, yahoo],
        start_date=dt.date(2026, 1, 1),
        end_date=dt.date(2026, 1, 5),
    )
    pg_session.commit()
    assert report.provider_used is None
    assert report.failure_reason is not None


# ---------------------------------------------------------------------------
# Validation: bad rows are rejected, good rows accepted
# ---------------------------------------------------------------------------


async def test_bad_rows_rejected_good_rows_written(pg_session: Session) -> None:
    good = _raw("2026-01-02")
    bad = _raw("2026-01-03", h="50", low="100")   # high < low
    tiingo = StubProvider("tiingo", source_priority("tiingo"), {
        "AAPL": [good, bad],
    })
    report = await ingest_symbol(
        pg_session, "AAPL",
        providers=[tiingo],
        start_date=dt.date(2026, 1, 1),
        end_date=dt.date(2026, 1, 5),
    )
    pg_session.commit()
    assert report.bars_fetched == 2
    assert report.bars_rejected == 1
    assert report.bars_written == 1


# ---------------------------------------------------------------------------
# Duplicates in single payload
# ---------------------------------------------------------------------------


async def test_payload_dupes_are_collapsed(pg_session: Session) -> None:
    d1 = _raw("2026-01-02", adj=None, vol=None)
    d2 = _raw("2026-01-02", adj="101", vol=1000)    # more complete
    tiingo = StubProvider("tiingo", source_priority("tiingo"), {"AAPL": [d1, d2]})
    report = await ingest_symbol(
        pg_session, "AAPL",
        providers=[tiingo],
        start_date=dt.date(2026, 1, 1),
        end_date=dt.date(2026, 1, 5),
    )
    pg_session.commit()
    assert report.bars_fetched == 2
    assert report.bars_written == 1     # payload-dedupe collapsed
    stored = list(pg_session.scalars(select(PriceBar).where(PriceBar.provider == "tiingo")))
    assert len(stored) == 1
    assert stored[0].adjusted_close is not None


# ---------------------------------------------------------------------------
# Source-priority overwrite rules
# ---------------------------------------------------------------------------


async def test_yahoo_does_not_overwrite_complete_tiingo(pg_session: Session) -> None:
    tiingo = StubProvider("tiingo", source_priority("tiingo"),
                          {"AAPL": [_raw("2026-01-02", c="100")]})
    await ingest_symbol(
        pg_session, "AAPL", providers=[tiingo],
        start_date=dt.date(2026, 1, 1), end_date=dt.date(2026, 1, 5),
    )
    pg_session.commit()

    yahoo = StubProvider("yahoo", source_priority("yahoo"),
                         {"AAPL": [_raw("2026-01-02", o="100", h="999", low="99", c="999")]})
    report = await ingest_symbol(
        pg_session, "AAPL", providers=[yahoo],
        start_date=dt.date(2026, 1, 1), end_date=dt.date(2026, 1, 5),
    )
    pg_session.commit()

    # Tiingo row must remain with its original close (not overwritten by yahoo 999)
    tiingo_row = pg_session.scalars(
        select(PriceBar).where(PriceBar.provider == "tiingo")
    ).first()
    assert Decimal(str(tiingo_row.close)) == Decimal("100")
    # Yahoo may or may not insert its own row — but shouldn't touch tiingo row
    # skipped counter should reflect at least one skip
    assert report.bars_skipped >= 1


async def test_tiingo_overwrites_yahoo(pg_session: Session) -> None:
    yahoo = StubProvider("yahoo", source_priority("yahoo"),
                         {"AAPL": [_raw("2026-01-02", o="100", h="200", low="99", c="200")]})
    await ingest_symbol(
        pg_session, "AAPL", providers=[yahoo],
        start_date=dt.date(2026, 1, 1), end_date=dt.date(2026, 1, 5),
    )
    pg_session.commit()

    tiingo = StubProvider("tiingo", source_priority("tiingo"),
                          {"AAPL": [_raw("2026-01-02", o="100", h="160", low="99", c="150")]})
    report = await ingest_symbol(
        pg_session, "AAPL", providers=[tiingo],
        start_date=dt.date(2026, 1, 1), end_date=dt.date(2026, 1, 5),
    )
    pg_session.commit()
    assert report.bars_skipped == 0


# ---------------------------------------------------------------------------
# Incremental lookback buffer
# ---------------------------------------------------------------------------


async def test_resolve_start_uses_5day_lookback(pg_session: Session) -> None:
    asset = Asset(symbol="INC", asset_class="equity", exchange="NASDAQ", currency="USD")
    pg_session.add(asset)
    pg_session.flush()
    pg_session.add(PriceBar(
        asset_id=asset.id, timeframe="1d",
        ts=dt.datetime(2026, 1, 20, tzinfo=dt.timezone.utc),
        open=Decimal("100"), high=Decimal("102"), low=Decimal("99"),
        close=Decimal("101"), adjusted_close=Decimal("101"),
        volume=1000, provider="tiingo",
    ))
    pg_session.commit()

    start = resolve_start_date(
        pg_session, asset.id,
        incremental_floor=dt.date(2025, 1, 1),
    )
    # 20th minus 5 days = 15th
    assert start == dt.date(2026, 1, 15)


async def test_resolve_start_respects_floor(pg_session: Session) -> None:
    asset = Asset(symbol="FLR", asset_class="equity", exchange="NASDAQ", currency="USD")
    pg_session.add(asset)
    pg_session.flush()
    pg_session.commit()

    start = resolve_start_date(
        pg_session, asset.id,
        incremental_floor=dt.date(2025, 7, 1),
    )
    assert start == dt.date(2025, 7, 1)


# ---------------------------------------------------------------------------
# SPY always included
# ---------------------------------------------------------------------------


async def test_spy_always_included(pg_session: Session) -> None:
    tiingo = StubProvider("tiingo", source_priority("tiingo"), {
        "AAPL": [_raw("2026-01-02")],
        "SPY": [_raw("2026-01-02", sym="SPY")],
    })
    report = await ingest_symbols(
        pg_session, ["AAPL"],     # caller did NOT pass SPY
        providers=[tiingo],
        start_date=dt.date(2026, 1, 1), end_date=dt.date(2026, 1, 5),
        incremental=False,
    )
    symbols = {r.symbol for r in report.symbols}
    assert "SPY" in symbols
    assert "AAPL" in symbols


# ---------------------------------------------------------------------------
# Deterministic repeat runs
# ---------------------------------------------------------------------------


async def test_repeat_run_is_deterministic(pg_session: Session) -> None:
    bars = [_raw("2026-01-02"), _raw("2026-01-03")]
    tiingo = StubProvider("tiingo", source_priority("tiingo"), {"AAPL": bars})
    await ingest_symbol(pg_session, "AAPL", providers=[tiingo],
                        start_date=dt.date(2026, 1, 1), end_date=dt.date(2026, 1, 5))
    pg_session.commit()
    first = list(pg_session.scalars(select(PriceBar)))
    first_count = len(first)

    await ingest_symbol(pg_session, "AAPL", providers=[tiingo],
                        start_date=dt.date(2026, 1, 1), end_date=dt.date(2026, 1, 5))
    pg_session.commit()
    second = list(pg_session.scalars(select(PriceBar)))
    assert len(second) == first_count     # no duplicate rows from rerun
