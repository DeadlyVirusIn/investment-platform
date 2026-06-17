"""BP27 — Polygon DailyPriceProvider unit tests (mocked httpx)."""

from __future__ import annotations

import asyncio
import datetime as dt

import httpx
import pytest

from apps.api.src.domain.prices.canonical import source_priority
from apps.api.src.domain.prices.providers.base import NoDataError, ProviderError
from apps.api.src.domain.prices.providers.polygon import PolygonProvider

S, E = dt.date(2022, 1, 3), dt.date(2022, 1, 10)


class _FakeClient:
    def __init__(self, resp): self._r = resp
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False
    async def get(self, url, params=None): return self._r


def _patch(monkeypatch, status, body):
    resp = httpx.Response(status, json=body)
    import apps.api.src.domain.prices.providers.polygon as mod
    monkeypatch.setattr(mod.httpx, "AsyncClient", lambda *a, **k: _FakeClient(resp))


def test_success_mapping(monkeypatch):
    body = {"status": "OK", "results": [
        {"t": 1641186000000, "o": 177.83, "h": 182.88, "l": 177.71,
         "c": 182.01, "v": 104677470},
        {"t": 1641272400000, "o": 182.63, "h": 182.94, "l": 179.12,
         "c": 179.70, "v": 99310438},
    ]}
    _patch(monkeypatch, 200, body)
    bars = asyncio.run(PolygonProvider("k").fetch_daily_bars("aapl", S, E))
    assert len(bars) == 2
    b = bars[0]
    assert b.symbol == "AAPL"
    assert b.date_iso == "2022-01-03"          # epoch-ms -> UTC trading day
    assert str(b.open) == "177.83"
    assert str(b.close) == "182.01"            # raw close (adjusted=false)
    assert b.adjusted_close is None            # Polygon supplies no total-return adj
    assert b.volume == 104677470


def test_404_is_nodata(monkeypatch):
    _patch(monkeypatch, 404, {})
    with pytest.raises(NoDataError):
        asyncio.run(PolygonProvider("k").fetch_daily_bars("X", S, E))


def test_empty_results_is_nodata(monkeypatch):
    _patch(monkeypatch, 200, {"status": "OK", "results": []})
    with pytest.raises(NoDataError):
        asyncio.run(PolygonProvider("k").fetch_daily_bars("X", S, E))


def test_http_error_is_provider_error(monkeypatch):
    _patch(monkeypatch, 500, {"error": "boom"})
    with pytest.raises(ProviderError):
        asyncio.run(PolygonProvider("k").fetch_daily_bars("X", S, E))


def test_missing_key_is_provider_error():
    with pytest.raises(ProviderError):
        asyncio.run(PolygonProvider("").fetch_daily_bars("X", S, E))


def test_priority_below_total_return_sources():
    assert source_priority("polygon") == 40
    assert PolygonProvider("k").priority == 40
    assert PolygonProvider("k").name == "polygon"
    # Polygon must NOT outrank the total-return adjusted_close authorities.
    assert source_priority("polygon") < source_priority("yahoo") < source_priority("tiingo")


def test_chain_excludes_polygon(monkeypatch):
    from apps.api.src.config import settings
    monkeypatch.setattr(settings, "POLYGON_API_KEY", "pk", raising=False)
    monkeypatch.setattr(settings, "TIINGO_API_KEY", "tk", raising=False)
    from apps.worker.src.jobs.ingest_prices_daily import _provider_chain
    chain = _provider_chain()
    # BP27B: Polygon is reserved for the gap-backfill driver, NOT the daily chain.
    assert [p.name for p in chain] == ["tiingo", "yahoo"]


def test_polygon_does_not_overwrite_complete_tiingo():
    from decimal import Decimal
    from types import SimpleNamespace
    from apps.api.src.domain.prices.reconcile import should_upsert, ExistingBar
    poly = SimpleNamespace(source="polygon", adjusted_close=None, volume=1000)
    tiingo = ExistingBar(source="tiingo", open=Decimal("179"), close=Decimal("182.01"),
                         adjusted_close=Decimal("177.96"), volume=1000)
    # Lower priority + existing complete (total-return) -> Polygon must NOT overwrite.
    assert should_upsert(poly, tiingo) is False
    # Gap date (no existing row) -> Polygon fills it (raw).
    assert should_upsert(poly, None) is True
