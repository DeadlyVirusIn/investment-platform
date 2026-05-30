"""Unit tests for TradierOptionsAdapter underlying-spot fetch (Layer 1).

Covers the /markets/quotes spot path added so ChainSnapshotResult.
underlying_price is populated (enabling Greeks enrichment + moneyness).
Mocks the httpx client — no network. Non-fatal fallback is the core
contract: any error/malformed payload returns None (never raises).
"""

from __future__ import annotations

from decimal import Decimal

import httpx

from apps.api.src.options.data_provider.tradier_adapter import (
    TradierOptionsAdapter,
    TradierOptionsConfig,
)


class _FakeResp:
    def __init__(self, body, status: int = 200):
        self._body = body
        self.status_code = status
        self.url = "https://api.tradier.com/v1/markets/quotes"

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}", request=None, response=None,
            )

    def json(self):
        return self._body


class _FakeClient:
    """Returns a canned response, or raises a canned exception, on .get()."""

    def __init__(self, resp_or_exc):
        self._r = resp_or_exc

    def get(self, path, params=None):
        if isinstance(self._r, Exception):
            raise self._r
        return self._r

    def close(self):
        pass


def _adapter(client: _FakeClient) -> TradierOptionsAdapter:
    cfg = TradierOptionsConfig(
        access_token="test-token",
        base_url="https://api.tradier.com/v1",
    )
    # sleeper no-ops the rate limiter so tests don't actually sleep.
    return TradierOptionsAdapter(
        config=cfg, http_client=client, sleeper=lambda *_a, **_k: None,
    )


def test_spot_success_uses_last():
    a = _adapter(_FakeClient(_FakeResp(
        {"quotes": {"quote": {"last": 756.48, "close": 750.0}}})))
    assert a._fetch_underlying_spot(symbol="SPY") == Decimal("756.48")


def test_spot_falls_back_to_close_when_last_nonpositive():
    a = _adapter(_FakeClient(_FakeResp(
        {"quotes": {"quote": {"last": 0, "close": 750.0}}})))
    assert a._fetch_underlying_spot(symbol="SPY") == Decimal("750.0")


def test_spot_quote_as_list_takes_first():
    a = _adapter(_FakeClient(_FakeResp(
        {"quotes": {"quote": [{"last": 290.43}, {"last": 1.0}]}})))
    assert a._fetch_underlying_spot(symbol="IWM") == Decimal("290.43")


def test_spot_malformed_body_returns_none():
    a = _adapter(_FakeClient(_FakeResp({"unexpected": True})))
    assert a._fetch_underlying_spot(symbol="SPY") is None


def test_spot_non_dict_body_returns_none():
    a = _adapter(_FakeClient(_FakeResp(["not", "a", "dict"])))
    assert a._fetch_underlying_spot(symbol="SPY") is None


def test_spot_http_error_returns_none():
    a = _adapter(_FakeClient(httpx.ConnectError("boom")))
    assert a._fetch_underlying_spot(symbol="SPY") is None


def test_spot_all_fields_missing_returns_none():
    a = _adapter(_FakeClient(_FakeResp(
        {"quotes": {"quote": {"last": 0, "close": 0, "prevclose": None}}})))
    assert a._fetch_underlying_spot(symbol="SPY") is None
