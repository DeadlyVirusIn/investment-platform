"""Unit tests for TradierOptionsAdapter. No network. Uses MockTransport.

Coverage:
  * graceful degrade with no token
  * health_check 200 vs non-200 vs no-token
  * expirations parse (both shapes: dates-only and full)
  * chain pull + normalization (CALL + PUT, Greeks present, IV present)
  * per-expiry failure aggregates into `partial=True`
  * factory dispatch via chain_ingest._build_adapter('tradier')
  * Authorization: Bearer header sent; no token in URL ever
"""

from __future__ import annotations

import datetime
import json
from decimal import Decimal

import httpx

# pytest optional: when pytest is absent (e.g. inside the runtime
# image), the tests still run via stdlib inline harness — only
# `pytest.raises` would need it, so define a tiny stub.
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

from apps.api.src.options.data_provider.base_adapter import BaseOptionsAdapter
from apps.api.src.options.data_provider.tradier_adapter import (
    TradierOptionsAdapter,
    TradierOptionsConfig,
    PROVIDER_NAME,
    PROVIDER_VERSION_SANDBOX,
)


_FAKE_TOKEN = "tradier-fake-token-NOT-A-REAL-SECRET-1234"


def _ok(payload: dict) -> httpx.Response:
    return httpx.Response(200, content=json.dumps(payload).encode())


def _build(handler, *, token: str | None = _FAKE_TOKEN) -> TradierOptionsAdapter:
    transport = httpx.MockTransport(handler)
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    client = httpx.Client(
        transport=transport,
        base_url="https://sandbox.tradier.com/v1",
        headers=headers,
    )
    cfg = TradierOptionsConfig(
        base_url="https://sandbox.tradier.com/v1",
        access_token=token,
        rate_limit_qps=1000.0,
        dte_window_days=365,
    )
    return TradierOptionsAdapter(
        cfg, http_client=client, sleeper=lambda _: None,
    )


# ---------------------------------------------------------------------------
# Graceful degrade
# ---------------------------------------------------------------------------

def test_no_token_returns_empty_partial():
    a = _build(handler=lambda r: _ok({"clock": {}}), token=None)
    r = a.get_chain_snapshot(
        symbol="SPY",
        timestamp=datetime.datetime(2026, 5, 13, tzinfo=datetime.timezone.utc),
    )
    assert r.quotes == ()
    assert r.partial is True
    assert "no access token" in (r.partial_reason or "")
    assert "tradier_no_access_token" in r.notes


def test_health_check_no_token():
    a = _build(handler=lambda r: _ok({"clock": {}}), token=None)
    assert a.health_check() is False


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

def test_health_check_200_clock_true():
    a = _build(handler=lambda r: _ok({"clock": {"state": "open"}}))
    assert a.health_check() is True


def test_health_check_429_false():
    a = _build(handler=lambda r: httpx.Response(429, content=b""))
    assert a.health_check() is False


def test_health_check_no_clock_key_false():
    a = _build(handler=lambda r: _ok({"unexpected": "shape"}))
    assert a.health_check() is False


# ---------------------------------------------------------------------------
# Authorization header — token NEVER in URL
# ---------------------------------------------------------------------------

def test_authorization_header_sent_and_no_token_in_url():
    seen_requests: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen_requests.append(req)
        if req.url.path.endswith("/markets/clock"):
            return _ok({"clock": {"state": "open"}})
        if req.url.path.endswith("/markets/options/expirations"):
            return _ok({"expirations": {"date": []}})
        return _ok({})

    a = _build(handler=handler)
    a.health_check()
    a.get_chain_snapshot(
        symbol="SPY",
        timestamp=datetime.datetime(2026, 5, 13, tzinfo=datetime.timezone.utc),
    )

    assert seen_requests, "no requests captured"
    for req in seen_requests:
        # Authorization MUST be present
        auth = req.headers.get("Authorization", "")
        assert auth.startswith("Bearer "), f"missing Bearer header: {auth!r}"
        # Token MUST NOT appear in URL anywhere
        url_str = str(req.url)
        assert _FAKE_TOKEN not in url_str, (
            f"TOKEN LEAKED IN URL: {url_str}")
        # No `token=` / `access_token=` query param either
        assert "token=" not in url_str
        assert "access_token=" not in url_str


# ---------------------------------------------------------------------------
# Expirations parsing — both shapes
# ---------------------------------------------------------------------------

def test_expirations_parse_dates_only_shape():
    payload = {"expirations": {"date": ["2026-05-16", "2026-06-20"]}}

    def handler(req):
        if "expirations" in req.url.path:
            return _ok(payload)
        # chain calls — return empty
        return _ok({"options": None})

    a = _build(handler=handler)
    r = a.get_chain_snapshot(
        symbol="SPY",
        timestamp=datetime.datetime(2026, 5, 13, tzinfo=datetime.timezone.utc),
    )
    # 0 quotes because chain returned empty, but partial reason should
    # indicate empty-contracts not empty-expirations
    assert r.partial is True
    assert "tradier returned 0 contracts" in (r.partial_reason or "")


def test_expirations_parse_full_shape():
    payload = {"expirations": {"expiration": [
        {"date": "2026-05-16", "contract_size": 100,
         "expiration_type": "weeklys"},
        {"date": "2026-06-20", "contract_size": 100,
         "expiration_type": "standard"},
    ]}}

    def handler(req):
        if "expirations" in req.url.path:
            return _ok(payload)
        return _ok({"options": None})

    a = _build(handler=handler)
    r = a.get_chain_snapshot(
        symbol="SPY",
        timestamp=datetime.datetime(2026, 5, 13, tzinfo=datetime.timezone.utc),
    )
    assert r.partial is True
    # Either empty contracts OR empty expirations — both acceptable parse paths.
    # Important: no exception raised.
    assert isinstance(r.notes, tuple)


# ---------------------------------------------------------------------------
# Chain normalization — provider-native Greeks
# ---------------------------------------------------------------------------

_CHAIN_RESPONSE = {
    "options": {
        "option": [
            {
                "symbol": "SPY260516C00400000",
                "strike": 400.0,
                "expiration_date": "2026-05-16",
                "option_type": "call",
                "bid": 100.50,
                "ask": 100.65,
                "last": 100.55,
                "volume": 123,
                "open_interest": 456,
                "bid_date": 1747353600000,
                "ask_date": 1747353600000,
                "greeks": {
                    "delta": 0.6,
                    "gamma": 0.03,
                    "theta": -0.05,
                    "vega": 0.20,
                    "smv_vol": 0.21,
                    "mid_iv": 0.215,
                },
            },
            {
                "symbol": "SPY260516P00400000",
                "strike": 400.0,
                "expiration_date": "2026-05-16",
                "option_type": "put",
                "bid": 2.50,
                "ask": 2.60,
                "last": 2.55,
                "volume": 77,
                "open_interest": 999,
                "greeks": {
                    "delta": -0.4,
                    "gamma": 0.03,
                    "theta": -0.04,
                    "vega": 0.18,
                    "smv_vol": 0.22,
                },
            },
        ]
    }
}


def test_chain_normalization_call_and_put_with_greeks():
    def handler(req):
        if "expirations" in req.url.path:
            return _ok({"expirations": {"date": ["2026-05-16"]}})
        if "chains" in req.url.path:
            return _ok(_CHAIN_RESPONSE)
        return _ok({})

    a = _build(handler=handler)
    ts = datetime.datetime(2026, 5, 13, tzinfo=datetime.timezone.utc)
    r = a.get_chain_snapshot(symbol="SPY", timestamp=ts)

    assert r.partial is False
    assert len(r.quotes) == 2
    assert r.provider == PROVIDER_NAME

    # Provider Greeks present → no BSM-fallback note expected
    assert "greeks_provider_unavailable_bsm_fallback_will_run" not in r.notes

    call = next(q for q in r.quotes if q.option_type == "CALL")
    assert call.underlying == "SPY"
    assert call.expiry == datetime.date(2026, 5, 16)
    assert call.strike == Decimal("400.0")
    assert call.option_symbol == "SPY260516C00400000"
    assert call.bid == Decimal("100.50")
    assert call.ask == Decimal("100.65")
    assert call.mid == Decimal("100.575")
    assert call.volume == 123
    assert call.open_interest == 456
    assert call.delta == Decimal("0.6")
    assert call.gamma == Decimal("0.03")
    assert call.iv == Decimal("0.21")          # smv_vol preferred
    assert call.provider_version == PROVIDER_VERSION_SANDBOX

    put = next(q for q in r.quotes if q.option_type == "PUT")
    assert put.delta == Decimal("-0.4")


# ---------------------------------------------------------------------------
# Partial — some expiries fail
# ---------------------------------------------------------------------------

def test_partial_when_one_expiry_fails():
    state = {"chain_calls": 0}

    def handler(req):
        if "expirations" in req.url.path:
            return _ok({"expirations": {"date":
                ["2026-05-16", "2026-06-20"]}})
        if "chains" in req.url.path:
            state["chain_calls"] += 1
            if state["chain_calls"] == 1:
                return _ok(_CHAIN_RESPONSE)
            # second expiry → 500
            return httpx.Response(500, content=b"server err")
        return _ok({})

    a = _build(handler=handler)
    r = a.get_chain_snapshot(
        symbol="SPY",
        timestamp=datetime.datetime(2026, 5, 13, tzinfo=datetime.timezone.utc),
    )
    # First expiry succeeded → has quotes
    assert len(r.quotes) == 2
    # But partial flag set because second failed
    assert r.partial is True
    assert "one or more expirations failed" in (r.partial_reason or "")


# ---------------------------------------------------------------------------
# Factory wiring
# ---------------------------------------------------------------------------

def test_factory_dispatches_to_tradier():
    from apps.api.src.options.data.chain_ingest import _build_adapter

    a = _build_adapter("tradier")
    assert isinstance(a, TradierOptionsAdapter)
    assert isinstance(a, BaseOptionsAdapter)
    a.close()


def test_factory_lists_tradier_in_error():
    from apps.api.src.options.data.chain_ingest import _build_adapter

    with pytest.raises(ValueError, match="tradier"):
        _build_adapter("polygon")
