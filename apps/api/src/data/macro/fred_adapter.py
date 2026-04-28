"""Phase 11P.2 - FRED REST adapter.

Thin httpx client. Fetches a single FRED series for a date window and
returns a pandas Series indexed by date. Append-only consumer:
NEVER writes to any DB table directly. The macro backfill script
persists the returned data under explicit operator commit.

Auth model:
  * FRED REST requires an API key (`?api_key=...`). When `api_key` is
    missing the adapter raises `FredConfigError` at construction.

Retry / rate limit:
  * Retries on 5xx and connection errors only. NEVER retries 4xx.
  * Token-bucket rate limiter (`FRED_RATE_LIMIT_QPS`).

NEVER imports broker / live / execution / V2 / equity engine modules.
"""

from __future__ import annotations

import datetime as dt
import time
from dataclasses import dataclass
from typing import Any

import httpx
import pandas as pd
from loguru import logger


DEFAULT_BASE_URL = "https://api.stlouisfed.org/fred"
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_MAX_RETRIES = 3
DEFAULT_RATE_LIMIT_QPS = 1.0

OBSERVATIONS_PATH = "/series/observations"


class FredError(Exception):
    """Base FRED error."""


class FredConfigError(FredError):
    """Construction-time validation failure."""


class FredUnavailable(FredError):
    """5xx / network error after retries."""


class FredAPIError(FredError):
    """4xx (auth, missing series, malformed request)."""


@dataclass(frozen=True)
class FredConfig:
    base_url: str
    api_key: str
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    max_retries: int = DEFAULT_MAX_RETRIES
    rate_limit_qps: float = DEFAULT_RATE_LIMIT_QPS


def _validate_config(cfg: FredConfig) -> None:
    if not cfg.base_url:
        raise FredConfigError("[config] FRED_BASE_URL must be set")
    scheme = httpx.URL(cfg.base_url).scheme
    if scheme not in ("http", "https"):
        raise FredConfigError(
            "[config] FRED_BASE_URL must use http:// or https:// "
            f"(got: {scheme!r})"
        )
    if not cfg.api_key:
        raise FredConfigError(
            "[config] FRED_API_KEY must be set when running the macro "
            "backfill against FRED"
        )
    if cfg.timeout_seconds <= 0:
        raise FredConfigError(
            "[config] FRED_TIMEOUT_SECONDS must be > 0"
        )
    if cfg.max_retries < 0:
        raise FredConfigError(
            "[config] FRED_MAX_RETRIES must be >= 0"
        )
    if cfg.rate_limit_qps <= 0:
        raise FredConfigError(
            "[config] FRED_RATE_LIMIT_QPS must be > 0"
        )


def _config_from_settings(settings_obj=None) -> FredConfig:
    from apps.api.src.config import settings as default_settings
    s = settings_obj if settings_obj is not None else default_settings
    return FredConfig(
        base_url=getattr(s, "FRED_BASE_URL", None) or DEFAULT_BASE_URL,
        api_key=getattr(s, "FRED_API_KEY", None) or "",
        timeout_seconds=int(
            getattr(s, "FRED_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)
        ),
        max_retries=int(
            getattr(s, "FRED_MAX_RETRIES", DEFAULT_MAX_RETRIES)
        ),
        rate_limit_qps=float(
            getattr(s, "FRED_RATE_LIMIT_QPS", DEFAULT_RATE_LIMIT_QPS)
        ),
    )


class _RateLimiter:
    """Trivial token-bucket: at most qps requests per second."""

    def __init__(self, qps: float, *, clock=None) -> None:
        self.qps = max(0.001, float(qps))
        self.min_interval = 1.0 / self.qps
        self._clock = clock or time.monotonic
        self._sleep = time.sleep
        self._last_call: float | None = None

    def wait(self) -> None:
        now = self._clock()
        if self._last_call is None:
            self._last_call = now
            return
        delta = now - self._last_call
        if delta < self.min_interval:
            self._sleep(self.min_interval - delta)
            now = self._clock()
        self._last_call = now


class FredAdapter:
    """Read-only FRED client.

    Methods:
      fetch_series(series_id, start, end) -> pandas.Series
      health_check() -> dict
    """

    def __init__(
        self,
        config: FredConfig | None = None,
        *,
        http_client: httpx.Client | None = None,
        clock=None,
        sleeper=None,
    ) -> None:
        cfg = config or _config_from_settings()
        _validate_config(cfg)
        self.config = cfg
        self._owned_client = http_client is None
        self._client = http_client or self._build_client(cfg)
        self._rate_limiter = _RateLimiter(cfg.rate_limit_qps, clock=clock)
        if sleeper is not None:
            self._rate_limiter._sleep = sleeper  # type: ignore[assignment]

    @staticmethod
    def _build_client(cfg: FredConfig) -> httpx.Client:
        return httpx.Client(
            base_url=cfg.base_url.rstrip("/"),
            headers={"Accept": "application/json"},
            timeout=cfg.timeout_seconds,
        )

    def close(self) -> None:
        if self._owned_client:
            self._client.close()

    # ------------------------------------------------------------------

    def fetch_series(
        self,
        series_id: str,
        *,
        start: dt.date,
        end: dt.date,
    ) -> pd.Series:
        params = {
            "series_id": series_id,
            "api_key": self.config.api_key,
            "file_type": "json",
            "observation_start": start.isoformat(),
            "observation_end": end.isoformat(),
        }
        attempt = 0
        while True:
            self._rate_limiter.wait()
            try:
                resp = self._client.get(OBSERVATIONS_PATH, params=params)
            except (httpx.ConnectError, httpx.ConnectTimeout,
                    httpx.ReadTimeout, httpx.WriteTimeout) as exc:
                if attempt >= self.config.max_retries:
                    raise FredUnavailable(
                        f"network error fetching {series_id}: {exc}"
                    ) from exc
                attempt += 1
                continue

            sc = resp.status_code
            if 200 <= sc < 300:
                try:
                    payload = resp.json()
                except Exception as exc:  # noqa: BLE001
                    raise FredAPIError(
                        f"non-JSON FRED response for {series_id}: {exc}"
                    ) from exc
                return _payload_to_series(payload, series_id)
            if 400 <= sc < 500:
                raise FredAPIError(
                    f"FRED returned {sc} for {series_id}: "
                    f"{resp.text[:200]!r}"
                )
            if 500 <= sc < 600:
                if attempt >= self.config.max_retries:
                    raise FredUnavailable(
                        f"FRED server error {sc} for {series_id}: "
                        f"{resp.text[:200]!r}"
                    )
                attempt += 1
                continue
            raise FredAPIError(
                f"FRED unhandled status {sc} for {series_id}"
            )

    def health_check(self) -> dict[str, Any]:
        host = httpx.URL(self.config.base_url).host or self.config.base_url
        result: dict[str, Any] = {
            "ok": False, "status_code": None, "host": host,
            "latency_ms": None, "reason": None,
        }
        t0 = time.monotonic()
        try:
            # Cheapest possible probe: ask for a tiny known series with
            # a 1-day window. FRED returns 200 even when no observations
            # land in the window (empty observations array).
            resp = self._client.get(
                OBSERVATIONS_PATH,
                params={
                    "series_id": "DGS10",
                    "api_key": self.config.api_key,
                    "file_type": "json",
                    "observation_start": "2024-01-02",
                    "observation_end": "2024-01-02",
                },
                timeout=2.0,
            )
            result["latency_ms"] = int((time.monotonic() - t0) * 1000)
            result["status_code"] = resp.status_code
            if 200 <= resp.status_code < 300:
                result["ok"] = True
            else:
                result["reason"] = (
                    f"HTTP {resp.status_code}: {resp.text[:160]!r}"
                )
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            result["reason"] = f"connection refused: {exc}"
        except (httpx.ReadTimeout, httpx.WriteTimeout, TimeoutError):
            result["reason"] = "timeout after 2000ms"
        except Exception as exc:  # noqa: BLE001
            result["reason"] = f"unexpected error: {exc}"
        if result["latency_ms"] is None:
            result["latency_ms"] = int((time.monotonic() - t0) * 1000)
        return result


def _payload_to_series(payload: dict, series_id: str) -> pd.Series:
    obs = payload.get("observations") if isinstance(payload, dict) else None
    if obs is None:
        raise FredAPIError(
            f"FRED payload missing 'observations' for {series_id}"
        )
    rows: list[tuple[dt.date, float]] = []
    for o in obs:
        date_s = o.get("date")
        val_s = o.get("value")
        if not date_s or val_s in (None, "", "."):
            continue
        try:
            d = dt.date.fromisoformat(date_s)
            v = float(val_s)
        except (ValueError, TypeError):
            continue
        rows.append((d, v))
    if not rows:
        # An empty result is valid for some series + windows; return an
        # empty Series rather than raising.
        return pd.Series(dtype="float64", name=series_id)
    idx = pd.to_datetime([r[0] for r in rows])
    s = pd.Series(
        [r[1] for r in rows], index=idx, name=series_id, dtype="float64",
    )
    return s.sort_index()
