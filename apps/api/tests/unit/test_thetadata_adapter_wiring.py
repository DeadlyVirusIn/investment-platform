"""Phase 11O.1 - Adapter wiring unit tests.

Constructor + auth-mode + parsing + retry + rate-limit + failure-mapping
behaviour using `httpx.MockTransport`. NEVER hits the network.
"""

from __future__ import annotations

import datetime
import json
import re
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from apps.api.src.options.data_provider.base_adapter import (
    PartialChainWarning,
    ProviderError,
    ProviderUnavailable,
)
from apps.api.src.options.data_provider import thetadata_adapter as ta_mod
from apps.api.src.options.data_provider.thetadata_adapter import (
    AUTH_BASIC,
    AUTH_BEARER,
    AUTH_NONE,
    HEALTH_PATH,
    QUOTE_PATH,
    ThetaDataAdapter,
    ThetaDataConfig,
    ThetaDataConfigError,
    _RateLimiter,
    _config_from_settings,
    _validate_config,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

EXPIRY = "2026-06-18"
SNAP = datetime.datetime(2026, 4, 27, 14, 0, tzinfo=datetime.timezone.utc)


def _ok_quote_payload() -> dict:
    return {
        "underlying_price": 442.50,
        "interest_rate": 0.05,
        "dividend_yield": 0.0,
        "rows": [
            {
                "expiry": EXPIRY, "strike": 440, "option_type": "PUT",
                "option_symbol": "SPY260618P00440000",
                "bid": 1.20, "ask": 1.25, "mid": 1.225, "last": 1.20,
                "volume": 100, "open_interest": 1000,
                "delta": -0.30, "gamma": 0.02, "theta": -0.05,
                "vega": 0.10, "iv": 0.20, "quote_age_seconds": 2,
            },
        ],
        "partial": False,
        "partial_reason": None,
    }


def _build_adapter(
    *,
    transport: httpx.MockTransport,
    cfg: ThetaDataConfig | None = None,
    sleeper=lambda _s: None,
    clock=None,
) -> ThetaDataAdapter:
    base = (cfg.base_url if cfg else "http://127.0.0.1:25510")
    client = httpx.Client(
        transport=transport, base_url=base.rstrip("/"),
        headers={"Accept": "application/json"},
        timeout=cfg.timeout_seconds if cfg else 30,
    )
    real_cfg = cfg or ThetaDataConfig(
        base_url=base, max_retries=0, rate_limit_qps=1000.0,
    )
    return ThetaDataAdapter(
        config=real_cfg, http_client=client,
        clock=clock, sleeper=sleeper,
    )


# ---------------------------------------------------------------------------
# Config / construction
# ---------------------------------------------------------------------------

def test_adapter_requires_base_url():
    with pytest.raises(ThetaDataConfigError, match="THETADATA_BASE_URL"):
        _validate_config(ThetaDataConfig(base_url=""))


def test_adapter_rejects_non_http_scheme():
    with pytest.raises(ThetaDataConfigError, match="http://"):
        _validate_config(ThetaDataConfig(base_url="ftp://x"))


def test_adapter_picks_bearer_auth_when_api_key_set():
    cfg = ThetaDataConfig(base_url="http://x", api_key="abc123")
    assert cfg.auth_mode() == AUTH_BEARER


def test_adapter_picks_basic_auth_when_username_password_set():
    cfg = ThetaDataConfig(
        base_url="http://x", username="u", password="p",
    )
    assert cfg.auth_mode() == AUTH_BASIC


def test_adapter_picks_no_auth_when_neither_set():
    cfg = ThetaDataConfig(base_url="http://x")
    assert cfg.auth_mode() == AUTH_NONE


def test_adapter_rejects_mixed_auth_modes():
    with pytest.raises(ThetaDataConfigError, match="ONE auth mode"):
        _validate_config(ThetaDataConfig(
            base_url="http://x", api_key="k",
            username="u", password="p",
        ))


def test_adapter_rejects_partial_basic_auth():
    with pytest.raises(ThetaDataConfigError, match="must be set together"):
        _validate_config(ThetaDataConfig(
            base_url="http://x", username="u",
        ))


def test_adapter_rejects_zero_timeout():
    with pytest.raises(ThetaDataConfigError, match="TIMEOUT"):
        _validate_config(ThetaDataConfig(
            base_url="http://x", timeout_seconds=0,
        ))


def test_adapter_rejects_negative_retries():
    with pytest.raises(ThetaDataConfigError, match="MAX_RETRIES"):
        _validate_config(ThetaDataConfig(
            base_url="http://x", max_retries=-1,
        ))


def test_adapter_rejects_zero_rate_limit():
    with pytest.raises(ThetaDataConfigError, match="RATE_LIMIT"):
        _validate_config(ThetaDataConfig(
            base_url="http://x", rate_limit_qps=0,
        ))


def test_config_from_settings_reads_keys():
    s = SimpleNamespace(
        THETADATA_BASE_URL="http://example/",
        THETADATA_API_KEY="k",
        THETADATA_USERNAME=None,
        THETADATA_PASSWORD=None,
        THETADATA_TIMEOUT_SECONDS=15,
        THETADATA_MAX_RETRIES=1,
        THETADATA_RATE_LIMIT_QPS=2.0,
    )
    cfg = _config_from_settings(s)
    assert cfg.base_url == "http://example/"
    assert cfg.api_key == "k"
    assert cfg.timeout_seconds == 15
    assert cfg.auth_mode() == AUTH_BEARER


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

def test_adapter_health_check_returns_ok_on_200():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == HEALTH_PATH
        return httpx.Response(200, json={"status": "ok"})

    adapter = _build_adapter(transport=httpx.MockTransport(handler))
    detail = adapter.health_check_detail()
    assert detail["ok"] is True
    assert detail["status_code"] == 200
    assert detail["latency_ms"] is not None
    assert detail["base_url_host"] == "127.0.0.1"
    assert adapter.health_check() is True


def test_adapter_health_check_returns_failure_on_401():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="unauthorized")
    adapter = _build_adapter(transport=httpx.MockTransport(handler))
    detail = adapter.health_check_detail()
    assert detail["ok"] is False
    assert detail["status_code"] == 401
    assert "401" in detail["reason"]


def test_adapter_health_check_returns_failure_on_5xx():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="bad gateway")
    adapter = _build_adapter(transport=httpx.MockTransport(handler))
    detail = adapter.health_check_detail()
    assert detail["ok"] is False
    assert detail["status_code"] == 502


def test_adapter_health_check_returns_failure_on_timeout():
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("fake timeout")
    adapter = _build_adapter(transport=httpx.MockTransport(handler))
    detail = adapter.health_check_detail()
    assert detail["ok"] is False
    assert "connection refused" in detail["reason"] \
        or "timeout" in detail["reason"]


def test_adapter_health_check_returns_failure_on_connect_refused():
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")
    adapter = _build_adapter(transport=httpx.MockTransport(handler))
    detail = adapter.health_check_detail()
    assert detail["ok"] is False
    assert "connection refused" in detail["reason"]


# ---------------------------------------------------------------------------
# Chain pull parsing
# ---------------------------------------------------------------------------

def test_adapter_get_chain_snapshot_parses_quote_rows():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == QUOTE_PATH
        assert req.url.params.get("root") == "SPY"
        return httpx.Response(200, json=_ok_quote_payload())
    adapter = _build_adapter(transport=httpx.MockTransport(handler))
    result = adapter.get_chain_snapshot(symbol="SPY", timestamp=SNAP)
    assert result.partial is False
    assert len(result.quotes) == 1
    q = result.quotes[0]
    assert q.underlying == "SPY"
    assert q.option_type == "PUT"
    assert q.strike == Decimal("440")
    assert q.bid == Decimal("1.20")
    assert q.option_symbol == "SPY260618P00440000"
    assert result.underlying_price == Decimal("442.50")


def test_adapter_get_chain_snapshot_emits_partial_warning():
    payload = _ok_quote_payload()
    payload["partial"] = True
    payload["partial_reason"] = "expiry-2026-07-18 unavailable"

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)
    adapter = _build_adapter(transport=httpx.MockTransport(handler))
    with pytest.raises(PartialChainWarning) as exc_info:
        adapter.get_chain_snapshot(symbol="SPY", timestamp=SNAP)
    assert exc_info.value.result is not None
    assert exc_info.value.result.partial is True


def test_adapter_get_chain_snapshot_raises_provider_unavailable_on_conn_refused():
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")
    cfg = ThetaDataConfig(
        base_url="http://127.0.0.1:25510",
        max_retries=0, rate_limit_qps=1000.0,
    )
    adapter = _build_adapter(
        transport=httpx.MockTransport(handler), cfg=cfg,
    )
    with pytest.raises(ProviderUnavailable):
        adapter.get_chain_snapshot(symbol="SPY", timestamp=SNAP)


def test_adapter_get_chain_snapshot_raises_provider_error_on_4xx():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="not found")
    adapter = _build_adapter(transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderError, match="404"):
        adapter.get_chain_snapshot(symbol="SPY", timestamp=SNAP)


def test_adapter_get_chain_snapshot_raises_provider_error_on_non_json():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not-json-body")
    adapter = _build_adapter(transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderError, match="non-JSON"):
        adapter.get_chain_snapshot(symbol="SPY", timestamp=SNAP)


def test_adapter_get_chain_snapshot_raises_provider_error_on_missing_rows():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"underlying_price": 100})
    adapter = _build_adapter(transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderError, match="missing 'rows'"):
        adapter.get_chain_snapshot(symbol="SPY", timestamp=SNAP)


# ---------------------------------------------------------------------------
# Retry behaviour
# ---------------------------------------------------------------------------

def test_adapter_retries_only_on_5xx():
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503, text="busy")
        return httpx.Response(200, json=_ok_quote_payload())
    cfg = ThetaDataConfig(
        base_url="http://127.0.0.1:25510",
        max_retries=2, rate_limit_qps=1000.0,
    )
    adapter = _build_adapter(
        transport=httpx.MockTransport(handler), cfg=cfg,
    )
    result = adapter.get_chain_snapshot(symbol="SPY", timestamp=SNAP)
    assert calls["n"] == 2
    assert len(result.quotes) == 1


def test_adapter_no_retry_on_4xx():
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(404, text="missing")
    cfg = ThetaDataConfig(
        base_url="http://127.0.0.1:25510",
        max_retries=5, rate_limit_qps=1000.0,
    )
    adapter = _build_adapter(
        transport=httpx.MockTransport(handler), cfg=cfg,
    )
    with pytest.raises(ProviderError):
        adapter.get_chain_snapshot(symbol="SPY", timestamp=SNAP)
    assert calls["n"] == 1


def test_adapter_5xx_exhausted_retries_raises_provider_unavailable():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="busy")
    cfg = ThetaDataConfig(
        base_url="http://127.0.0.1:25510",
        max_retries=1, rate_limit_qps=1000.0,
    )
    adapter = _build_adapter(
        transport=httpx.MockTransport(handler), cfg=cfg,
    )
    with pytest.raises(ProviderUnavailable, match="server error"):
        adapter.get_chain_snapshot(symbol="SPY", timestamp=SNAP)


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

def test_rate_limiter_sleeps_when_called_too_fast():
    sleeps: list[float] = []

    def fake_sleep(s: float) -> None:
        sleeps.append(s)

    times = iter([0.0, 0.05, 0.05])  # second call within min_interval

    def fake_clock() -> float:
        return next(times)

    rl = _RateLimiter(qps=10.0, clock=fake_clock)
    rl._sleep = fake_sleep
    rl.wait()  # first call sets last
    rl.wait()  # second call sleeps remainder
    assert len(sleeps) == 1
    assert sleeps[0] > 0


def test_adapter_respects_rate_limit():
    sleeps: list[float] = []

    def slow_sleep(s: float) -> None:
        sleeps.append(s)

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_ok_quote_payload())
    cfg = ThetaDataConfig(
        base_url="http://127.0.0.1:25510",
        max_retries=0, rate_limit_qps=1.0,
    )
    adapter = _build_adapter(
        transport=httpx.MockTransport(handler),
        cfg=cfg, sleeper=slow_sleep,
    )
    adapter.get_chain_snapshot(symbol="SPY", timestamp=SNAP)
    adapter.get_chain_snapshot(symbol="QQQ", timestamp=SNAP)
    # Second call should have sleep > 0 (1 qps allowed once per second)
    assert any(s > 0 for s in sleeps)


# ---------------------------------------------------------------------------
# Boundary / static scans
# ---------------------------------------------------------------------------

def test_adapter_never_imports_broker_or_live_or_execution_modules():
    src = Path(ta_mod.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "from broker_", "import broker_",
        "from live_", "import live_",
        "from execution_", "import execution_",
        "order_router",
    ):
        assert forbidden not in src, (
            f"forbidden import token {forbidden!r} in adapter"
        )


def test_adapter_never_writes_to_db():
    src = Path(ta_mod.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "INSERT INTO", "UPDATE ", "DELETE FROM",
        "session.execute", "session.commit",
    ):
        assert forbidden not in src, (
            f"adapter must be read-only: token {forbidden!r}"
        )


def test_adapter_does_not_register_into_REGISTRY():
    from apps.worker.src.jobs.registry import REGISTRY
    assert all("options" not in k.lower() for k in REGISTRY.keys())


def test_adapter_does_not_modify_eval_runner():
    """Static guard: 11O.1 must NOT add code to the runner core."""
    runner = Path(
        "apps/api/src/options/paper/eval_runner.py"
    ).read_text(encoding="utf-8")
    for forbidden in (
        "thetadata_adapter", "ThetaDataAdapter",
    ):
        # eval_runner imports ingest_universe (which itself uses the
        # adapter), but must not import ThetaDataAdapter directly.
        assert forbidden not in runner, (
            f"eval_runner should not reference {forbidden!r} directly"
        )
