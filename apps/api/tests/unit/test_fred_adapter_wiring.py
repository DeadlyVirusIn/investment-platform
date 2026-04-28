"""Phase 11P.2 - FRED adapter wiring unit tests."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from types import SimpleNamespace

import httpx
import pandas as pd
import pytest

from apps.api.src.data.macro import fred_adapter as fred_mod
from apps.api.src.data.macro.fred_adapter import (
    DEFAULT_RATE_LIMIT_QPS,
    FredAPIError,
    FredAdapter,
    FredConfig,
    FredConfigError,
    FredUnavailable,
    OBSERVATIONS_PATH,
    _RateLimiter,
    _config_from_settings,
    _validate_config,
)


def _ok_payload() -> dict:
    return {
        "observations": [
            {"date": "2024-01-02", "value": "4.05"},
            {"date": "2024-01-03", "value": "4.07"},
            {"date": "2024-01-04", "value": "."},
            {"date": "2024-01-05", "value": "4.09"},
        ],
    }


def _build_adapter(
    transport: httpx.MockTransport,
    cfg: FredConfig | None = None,
    sleeper=lambda _s: None,
) -> FredAdapter:
    real_cfg = cfg or FredConfig(
        base_url="https://api.stlouisfed.org/fred",
        api_key="test_key",
        max_retries=0, rate_limit_qps=1000.0,
    )
    client = httpx.Client(
        transport=transport,
        base_url=real_cfg.base_url.rstrip("/"),
        headers={"Accept": "application/json"},
        timeout=real_cfg.timeout_seconds,
    )
    return FredAdapter(
        config=real_cfg, http_client=client, sleeper=sleeper,
    )


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------

def test_fred_requires_base_url():
    with pytest.raises(FredConfigError, match="FRED_BASE_URL"):
        _validate_config(FredConfig(base_url="", api_key="k"))


def test_fred_requires_api_key():
    with pytest.raises(FredConfigError, match="FRED_API_KEY"):
        _validate_config(FredConfig(base_url="https://x", api_key=""))


def test_fred_rejects_non_http_scheme():
    with pytest.raises(FredConfigError, match="http://"):
        _validate_config(FredConfig(
            base_url="ftp://x", api_key="k",
        ))


def test_fred_rejects_zero_timeout():
    with pytest.raises(FredConfigError, match="TIMEOUT"):
        _validate_config(FredConfig(
            base_url="https://x", api_key="k", timeout_seconds=0,
        ))


def test_fred_rejects_negative_retries():
    with pytest.raises(FredConfigError, match="MAX_RETRIES"):
        _validate_config(FredConfig(
            base_url="https://x", api_key="k", max_retries=-1,
        ))


def test_fred_rejects_zero_qps():
    with pytest.raises(FredConfigError, match="RATE_LIMIT"):
        _validate_config(FredConfig(
            base_url="https://x", api_key="k", rate_limit_qps=0,
        ))


def test_config_from_settings_reads_keys():
    s = SimpleNamespace(
        FRED_BASE_URL="https://api.stlouisfed.org/fred/",
        FRED_API_KEY="k",
        FRED_TIMEOUT_SECONDS=15,
        FRED_MAX_RETRIES=1,
        FRED_RATE_LIMIT_QPS=2.0,
    )
    cfg = _config_from_settings(s)
    assert cfg.base_url == "https://api.stlouisfed.org/fred/"
    assert cfg.api_key == "k"
    assert cfg.timeout_seconds == 15
    assert cfg.max_retries == 1
    assert cfg.rate_limit_qps == 2.0


# ---------------------------------------------------------------------------
# Fetch series
# ---------------------------------------------------------------------------

def test_fetch_series_parses_observations():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path.endswith(OBSERVATIONS_PATH)
        assert req.url.params.get("series_id") == "DGS10"
        return httpx.Response(200, json=_ok_payload())

    adapter = _build_adapter(httpx.MockTransport(handler))
    s = adapter.fetch_series(
        "DGS10", start=dt.date(2024, 1, 2), end=dt.date(2024, 1, 5),
    )
    assert isinstance(s, pd.Series)
    # 3 valid rows (one filtered out due to value=".")
    assert len(s) == 3
    assert s.name == "DGS10"
    assert float(s.iloc[0]) == 4.05


def test_fetch_series_empty_observations_returns_empty_series():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"observations": []})
    adapter = _build_adapter(httpx.MockTransport(handler))
    s = adapter.fetch_series(
        "X", start=dt.date(2024, 1, 1), end=dt.date(2024, 1, 2),
    )
    assert s.empty
    assert s.name == "X"


def test_fetch_series_4xx_raises_api_error():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="bad request")
    adapter = _build_adapter(httpx.MockTransport(handler))
    with pytest.raises(FredAPIError, match="400"):
        adapter.fetch_series(
            "DGS10", start=dt.date(2024, 1, 1),
            end=dt.date(2024, 1, 2),
        )


def test_fetch_series_5xx_retries_then_succeeds():
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503, text="busy")
        return httpx.Response(200, json=_ok_payload())

    cfg = FredConfig(
        base_url="https://x", api_key="k",
        max_retries=2, rate_limit_qps=1000.0,
    )
    adapter = _build_adapter(httpx.MockTransport(handler), cfg=cfg)
    s = adapter.fetch_series(
        "DGS10", start=dt.date(2024, 1, 2),
        end=dt.date(2024, 1, 5),
    )
    assert calls["n"] == 2
    assert len(s) == 3


def test_fetch_series_5xx_exhausted_raises_unavailable():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="busy")
    cfg = FredConfig(
        base_url="https://x", api_key="k",
        max_retries=1, rate_limit_qps=1000.0,
    )
    adapter = _build_adapter(httpx.MockTransport(handler), cfg=cfg)
    with pytest.raises(FredUnavailable, match="server error"):
        adapter.fetch_series(
            "DGS10", start=dt.date(2024, 1, 1),
            end=dt.date(2024, 1, 2),
        )


def test_fetch_series_no_retry_on_4xx():
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(404, text="not found")
    cfg = FredConfig(
        base_url="https://x", api_key="k",
        max_retries=5, rate_limit_qps=1000.0,
    )
    adapter = _build_adapter(httpx.MockTransport(handler), cfg=cfg)
    with pytest.raises(FredAPIError):
        adapter.fetch_series(
            "DGS10", start=dt.date(2024, 1, 1),
            end=dt.date(2024, 1, 2),
        )
    assert calls["n"] == 1


def test_fetch_series_connection_error_unavailable():
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")
    cfg = FredConfig(
        base_url="https://x", api_key="k",
        max_retries=0, rate_limit_qps=1000.0,
    )
    adapter = _build_adapter(httpx.MockTransport(handler), cfg=cfg)
    with pytest.raises(FredUnavailable):
        adapter.fetch_series(
            "DGS10", start=dt.date(2024, 1, 1),
            end=dt.date(2024, 1, 2),
        )


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

def test_health_check_ok():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"observations": []})
    adapter = _build_adapter(httpx.MockTransport(handler))
    detail = adapter.health_check()
    assert detail["ok"] is True
    assert detail["status_code"] == 200


def test_health_check_401():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="unauthorized")
    adapter = _build_adapter(httpx.MockTransport(handler))
    detail = adapter.health_check()
    assert detail["ok"] is False
    assert detail["status_code"] == 401


def test_health_check_connect_refused():
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")
    adapter = _build_adapter(httpx.MockTransport(handler))
    detail = adapter.health_check()
    assert detail["ok"] is False
    assert "connection refused" in detail["reason"]


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

def test_rate_limiter_sleeps_when_called_too_fast():
    sleeps: list[float] = []
    times = iter([0.0, 0.05, 0.05])

    rl = _RateLimiter(qps=10.0, clock=lambda: next(times))
    rl._sleep = sleeps.append
    rl.wait()
    rl.wait()
    assert len(sleeps) == 1
    assert sleeps[0] > 0


# ---------------------------------------------------------------------------
# Static / boundary
# ---------------------------------------------------------------------------

def test_fred_adapter_no_forbidden_imports():
    src = Path(fred_mod.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "from broker_", "import broker_",
        "from live_", "import live_",
        "from execution_", "import execution_",
        "order_router",
    ):
        assert forbidden not in src, (
            f"forbidden import token {forbidden!r}"
        )


def test_fred_adapter_no_db_writes():
    src = Path(fred_mod.__file__).read_text(encoding="utf-8")
    for forbidden in ("INSERT INTO", "UPDATE ", "DELETE FROM"):
        assert forbidden not in src, (
            f"FRED adapter must be read-only: {forbidden!r}"
        )
