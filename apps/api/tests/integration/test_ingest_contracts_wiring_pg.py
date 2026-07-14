"""Honest Numbers — ingest_symbol wired to dataset contracts (flag-gated).

Pins:
  * flag OFF (default): legacy validate_batch path, report.contract is None;
  * flag ON: quarantined rows never reach price_bar; ABORT writes nothing
    and sets failure_reason; stale/future/duplicate rules surface in the
    structured report; full provider outage keeps the legacy failure shape.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from apps.api.src.config import settings
from apps.api.src.db.models import Asset, PriceBar
from apps.api.src.domain.prices.canonical import RawProviderBar
from apps.api.src.domain.prices.providers.base import NoDataError
from apps.api.src.domain.prices.service import ingest_symbol

pytestmark = pytest.mark.integration

END = dt.date(2026, 7, 9)
START = dt.date(2026, 7, 1)


class FakeProvider:
    name = "fake-test"

    def __init__(self, raws):
        self._raws = raws

    async def fetch_daily_bars(self, symbol, start, end):
        if self._raws is None:
            raise NoDataError("fake outage")
        return self._raws


def _raw(date: str, close: str = "100", open_: str = "100",
         high: str = "101", low: str = "99") -> RawProviderBar:
    return RawProviderBar(
        symbol="CTRT", date_iso=date,
        open=Decimal(open_), high=Decimal(high), low=Decimal(low),
        close=Decimal(close), adjusted_close=Decimal(close), volume=1000,
    )


def _clean() -> list[RawProviderBar]:
    return [_raw(f"2026-07-0{d}") for d in (6, 7, 8)]


def _bar_count(session: Session) -> int:
    return session.scalar(
        select(func.count()).select_from(PriceBar)
        .join(Asset, Asset.id == PriceBar.asset_id)
        .where(Asset.symbol == "CTRT")
    )


@pytest.fixture(autouse=True)
def _flag_on(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "INGEST_CONTRACTS_ENABLED", True)
    yield



async def test_flag_off_is_legacy_path(pg_session: Session, monkeypatch) -> None:
    monkeypatch.setattr(settings, "INGEST_CONTRACTS_ENABLED", False)
    report = await ingest_symbol(
        pg_session, "CTRT", providers=[FakeProvider(_clean())],
        start_date=START, end_date=END,
    )
    assert report.contract is None            # seam absent when flag off
    assert report.bars_written == 3



async def test_quarantined_row_never_written(pg_session: Session) -> None:
    # 11 clean weekday bars + 1 malformed = 8.3% rejects, below the 10%
    # abort threshold — the single bad row must quarantine, not abort.
    clean = [_raw(d) for d in (
        "2026-06-22", "2026-06-23", "2026-06-24", "2026-06-25", "2026-06-26",
        "2026-06-29", "2026-06-30", "2026-07-01", "2026-07-02", "2026-07-06",
        "2026-07-07",
    )]
    raws = clean + [_raw("2026-07-03", close="-4", open_="-4")]
    report = await ingest_symbol(
        pg_session, "CTRT", providers=[FakeProvider(raws)],
        start_date=dt.date(2026, 6, 20), end_date=END,
    )
    assert report.contract is not None
    assert report.contract["verdict"] == "quarantine_and_continue"
    assert report.bars_written == 11          # pipeline survived
    assert _bar_count(pg_session) == 11       # bad row absent from price_bar



async def test_abort_threshold_writes_nothing(pg_session: Session) -> None:
    raws = [_raw(f"2026-07-0{d}", close="-1", open_="-1") for d in (1, 2, 3, 6, 7)]
    raws.append(_raw("2026-07-08"))
    report = await ingest_symbol(
        pg_session, "CTRT", providers=[FakeProvider(raws)],
        start_date=START, end_date=END,
    )
    assert report.contract["verdict"] == "abort_dataset"
    assert report.failure_reason and "contract abort" in report.failure_reason
    assert report.bars_written == 0
    assert _bar_count(pg_session) == 0        # fail closed: zero rows


async def test_stale_provider_flagged_but_written(pg_session: Session) -> None:
    raws = [_raw("2026-06-22"), _raw("2026-06-23")]
    report = await ingest_symbol(
        pg_session, "CTRT", providers=[FakeProvider(raws)],
        start_date=dt.date(2026, 6, 20), end_date=END,
    )
    assert any(f.startswith("stale_provider")
               for f in report.contract["dataset_flags"])
    assert report.bars_written == 2           # stale != invalid



async def test_future_rows_quarantined(pg_session: Session) -> None:
    raws = _clean() + [_raw("2026-07-20")]
    report = await ingest_symbol(
        pg_session, "CTRT", providers=[FakeProvider(raws)],
        start_date=START, end_date=dt.date(2026, 7, 25),
    )
    assert any(i["rule"] == "future_dated" for i in report.contract["issues"])
    assert report.bars_written == 3



async def test_duplicate_dates_single_write(pg_session: Session) -> None:
    raws = _clean() + [_raw("2026-07-08", close="200", open_="200",
                            high="201", low="199")]
    report = await ingest_symbol(
        pg_session, "CTRT", providers=[FakeProvider(raws)],
        start_date=START, end_date=END,
    )
    assert report.bars_written == 3
    assert _bar_count(pg_session) == 3



async def test_full_outage_keeps_legacy_failure_shape(pg_session: Session) -> None:
    report = await ingest_symbol(
        pg_session, "CTRT", providers=[FakeProvider(None)],
        start_date=START, end_date=END,
    )
    assert report.failure_reason == "all providers failed or empty"
    assert report.contract is None            # contract never evaluated
    assert _bar_count(pg_session) == 0


async def test_retry_after_abort_yields_clean_writes_only(pg_session: Session) -> None:
    """An aborted batch writes zero rows; a subsequent clean retry writes
    only the clean batch — no mixed/partial state can accumulate."""
    corrupt = [_raw(f"2026-07-0{d}", close="-1", open_="-1") for d in (1, 2, 3, 6, 7)]
    corrupt.append(_raw("2026-07-08"))
    first = await ingest_symbol(
        pg_session, "CTRT", providers=[FakeProvider(corrupt)],
        start_date=START, end_date=END,
    )
    assert first.contract["verdict"] == "abort_dataset"
    assert _bar_count(pg_session) == 0            # nothing partial persisted

    retry = await ingest_symbol(
        pg_session, "CTRT", providers=[FakeProvider(_clean())],
        start_date=START, end_date=END,
    )
    assert retry.contract["verdict"] == "accept"
    assert retry.bars_written == 3
    assert _bar_count(pg_session) == 3            # exactly the clean batch


async def test_report_has_no_provider_payload_or_secrets(pg_session: Session) -> None:
    import json as _json

    raws = _clean() + [_raw("2026-07-02", close="-9", open_="-9")]
    report = await ingest_symbol(
        pg_session, "CTRT", providers=[FakeProvider(raws)],
        start_date=START, end_date=END,
    )
    encoded = _json.dumps(report.contract).lower()
    # bounded structured fields only — never raw provider rows or creds
    assert "password" not in encoded and "api_key" not in encoded
    assert "rawproviderbar" not in encoded
    assert len(encoded) < 20_000
