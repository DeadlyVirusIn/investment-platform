"""Phase Opt-B3a — unit tests for FinnhubOptionsAdapter.

Pure unit tests. NEVER hit Finnhub network. Use httpx.MockTransport so
tests run deterministically and offline.

Coverage:
  * graceful degrade when api_key is missing
  * health_check True/False on 200 vs non-200
  * happy-path normalization of a representative response shape
  * empty `data` array → partial=True, partial_reason populated
  * factory dispatch via chain_ingest._build_adapter('finnhub')
"""

from __future__ import annotations

import datetime
import json
from decimal import Decimal

import httpx

# pytest optional: stub when running under stdlib-only harness
try:
    import pytest        # type: ignore
except ImportError:                                    # pragma: no cover
    import re as _re
    class _Pytest:
        class raises:
            def __init__(self, exc, match=None):
                self.exc, self.match = exc, match
            def __enter__(self): return self
            def __exit__(self, t, v, tb):
                if t is None:
                    raise AssertionError(f"expected {self.exc} not raised")
                if not issubclass(t, self.exc): return False
                if self.match and not _re.search(self.match, str(v)):
                    raise AssertionError(
                        f"match {self.match!r} not in {v!r}")
                return True
    pytest = _Pytest()                                 # type: ignore

from apps.api.src.options.data_provider.base_adapter import (
    BaseOptionsAdapter,
    PartialChainWarning,                          # noqa: F401 — re-export check
)
from apps.api.src.options.data_provider.finnhub_adapter import (
    FinnhubOptionsAdapter,
    FinnhubOptionsConfig,
    PROVIDER_NAME,
    PROVIDER_VERSION_FREE,
)


def _ok(payload: dict) -> httpx.Response:
    return httpx.Response(200, content=json.dumps(payload).encode())


def _build_adapter(handler, *, api_key: str | None = "test-key") -> FinnhubOptionsAdapter:
    transport = httpx.MockTransport(handler)
    client = httpx.Client(
        transport=transport,
        base_url="https://finnhub.io/api/v1",
        headers={"Accept": "application/json"},
    )
    cfg = FinnhubOptionsConfig(api_key=api_key, rate_limit_qps=1000.0)
    # rate_limit_qps high so the limiter never sleeps in tests
    return FinnhubOptionsAdapter(
        cfg, http_client=client, sleeper=lambda _: None,
    )


# ---------------------------------------------------------------------------
# Graceful degrade
# ---------------------------------------------------------------------------

def test_no_api_key_returns_empty_partial_chain() -> None:
    """Adapter must NEVER raise when key is missing — returns empty
    partial result so the ingest layer can record skipped_unavailable."""
    a = _build_adapter(handler=lambda r: _ok({"data": []}), api_key=None)
    r = a.get_chain_snapshot(
        symbol="SPY",
        timestamp=datetime.datetime(2026, 5, 13, tzinfo=datetime.timezone.utc),
    )
    assert r.quotes == ()
    assert r.partial is True
    assert "no api key" in (r.partial_reason or "")
    assert "finnhub_no_api_key" in r.notes
    assert r.provider == PROVIDER_NAME


def test_health_check_returns_false_when_no_key() -> None:
    a = _build_adapter(handler=lambda r: _ok({"data": []}), api_key=None)
    assert a.health_check() is False


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

def test_health_check_true_when_200_and_data_key_present() -> None:
    a = _build_adapter(handler=lambda r: _ok({"data": []}))
    assert a.health_check() is True


def test_health_check_false_on_non_200() -> None:
    a = _build_adapter(handler=lambda r: httpx.Response(429, content=b""))
    assert a.health_check() is False


def test_health_check_false_when_data_key_absent() -> None:
    a = _build_adapter(handler=lambda r: _ok({"unexpected": "shape"}))
    assert a.health_check() is False


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

_SAMPLE = {
    "code": "SPY",
    "exchange": "US",
    "data": [
        {
            "expirationDate": "2026-06-19",
            "options": {
                "CALL": [
                    {
                        "contractName": "SPY260619C00500000",
                        "strike": 500.0,
                        "bid": 12.30,
                        "ask": 12.40,
                        "lastPrice": 12.35,
                        "volume": 1234,
                        "openInterest": 5678,
                        "lastTradeDateTime": "2026-05-12 19:30:00",
                        # Greeks/IV missing — typical free tier shape
                    }
                ],
                "PUT": [
                    {
                        "contractName": "SPY260619P00500000",
                        "strike": 500.0,
                        "bid": 6.10,
                        "ask": 6.20,
                        "lastPrice": 6.15,
                        "volume": 999,
                        "openInterest": 4321,
                        "lastTradeDateTime": "2026-05-12 19:29:00",
                    }
                ],
            },
        }
    ],
}


def test_get_chain_snapshot_normalizes_call_and_put() -> None:
    a = _build_adapter(handler=lambda r: _ok(_SAMPLE))
    ts = datetime.datetime(2026, 5, 13, tzinfo=datetime.timezone.utc)
    r = a.get_chain_snapshot(symbol="SPY", timestamp=ts)

    assert len(r.quotes) == 2
    assert r.partial is False
    assert r.provider == PROVIDER_NAME
    # Greeks all None on this fixture → BSM fallback flag should fire
    assert "greeks_provider_unavailable_bsm_fallback_will_run" in r.notes

    call = next(q for q in r.quotes if q.option_type == "CALL")
    assert call.underlying == "SPY"
    assert call.expiry == datetime.date(2026, 6, 19)
    assert call.strike == Decimal("500.0")
    assert call.option_symbol == "SPY260619C00500000"
    assert call.bid == Decimal("12.30")
    assert call.ask == Decimal("12.40")
    assert call.mid == Decimal("12.35")
    assert call.volume == 1234
    assert call.open_interest == 5678
    assert call.delta is None
    assert call.iv is None
    assert call.provider_version == PROVIDER_VERSION_FREE
    assert call.snapshot_at_utc == ts


def test_empty_data_array_yields_partial_empty() -> None:
    a = _build_adapter(handler=lambda r: _ok({"data": []}))
    r = a.get_chain_snapshot(
        symbol="ZZZ",
        timestamp=datetime.datetime(2026, 5, 13, tzinfo=datetime.timezone.utc),
    )
    assert r.quotes == ()
    assert r.partial is True
    assert "0 contracts" in (r.partial_reason or "")


# ---------------------------------------------------------------------------
# Factory wiring
# ---------------------------------------------------------------------------

def test_chain_ingest_factory_dispatches_to_finnhub() -> None:
    """Importing chain_ingest's private factory and calling it with
    'finnhub' must yield an instance of FinnhubOptionsAdapter."""
    from apps.api.src.options.data.chain_ingest import _build_adapter

    a = _build_adapter("finnhub")
    assert isinstance(a, FinnhubOptionsAdapter)
    assert isinstance(a, BaseOptionsAdapter)
    a.close()


def test_chain_ingest_factory_unknown_provider_raises() -> None:
    from apps.api.src.options.data.chain_ingest import _build_adapter

    with pytest.raises(ValueError, match="supported: 'thetadata', 'finnhub'"):
        _build_adapter("polygon")
