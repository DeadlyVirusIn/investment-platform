"""ThetaData provider adapter (Phase 11C, wired in Phase 11O.1).

Implements `BaseOptionsAdapter`. The HTTP layer is a thin httpx client
backed by `THETADATA_*` settings keys. The adapter expects ThetaData
(or the operator's proxy in front of it) to return normalized JSON of
the shape:

    GET {base_url}/v2/snapshot/option/quote?root={symbol}
        -> 200 {
            "underlying_price": 442.50,
            "interest_rate":    0.05,
            "dividend_yield":   0.0,
            "rows": [
              {"expiry": "2026-06-18", "strike": 440,
               "option_type": "PUT",
               "bid": 1.20, "ask": 1.25, "mid": 1.225, "last": 1.20,
               "volume": 100, "open_interest": 1000,
               "delta": -0.30, "gamma": 0.02, "theta": -0.05,
               "vega": 0.10, "iv": 0.20, "quote_age_seconds": 2,
               "option_symbol": "SPY260618P00440000"},
              ...
            ],
            "partial": false,
            "partial_reason": null
        }

NEVER imports broker / live / execution / V2 / equity / strategy
modules. NEVER triggers a worker job. Pure read.
"""

from __future__ import annotations

import datetime
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx
from loguru import logger

from apps.api.src.options.data_provider.base_adapter import (
    BaseOptionsAdapter,
    ChainSnapshotResult,
    OptionChainQuote,
    PartialChainWarning,
    ProviderError,
    ProviderUnavailable,
)


PROVIDER_NAME = "thetadata"
PROVIDER_VERSION = "rest-v1"

DEFAULT_BASE_URL = "http://127.0.0.1:25510"
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_MAX_RETRIES = 2
DEFAULT_RATE_LIMIT_QPS = 5.0
DEFAULT_QUOTE_AGE_TOLERANCE_SECONDS = 60

HEALTH_PATH = "/v2/system/status"
QUOTE_PATH = "/v2/snapshot/option/quote"

AUTH_NONE = "none"
AUTH_BEARER = "bearer"
AUTH_BASIC = "basic"


@dataclass(frozen=True)
class ThetaDataConfig:
    base_url: str
    api_key: str | None = None
    username: str | None = None
    password: str | None = None
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    max_retries: int = DEFAULT_MAX_RETRIES
    rate_limit_qps: float = DEFAULT_RATE_LIMIT_QPS
    quote_age_tolerance_seconds: int = DEFAULT_QUOTE_AGE_TOLERANCE_SECONDS

    def auth_mode(self) -> str:
        if self.api_key:
            return AUTH_BEARER
        if self.username and self.password:
            return AUTH_BASIC
        return AUTH_NONE


class _RateLimiter:
    """Trivial single-threaded token-bucket: at most qps requests per
    second. Sleeps inline when the bucket is empty."""

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


class ThetaDataAdapter(BaseOptionsAdapter):
    """ThetaData REST adapter.

    Constructor validates `base_url` + auth selection. `http_client` is
    injectable so tests can plug in `httpx.MockTransport`.
    """

    name = PROVIDER_NAME

    def __init__(
        self,
        config: ThetaDataConfig | None = None,
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

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_client(cfg: ThetaDataConfig) -> httpx.Client:
        headers: dict[str, str] = {"Accept": "application/json"}
        auth: httpx.Auth | None = None
        if cfg.auth_mode() == AUTH_BEARER:
            headers["Authorization"] = f"Bearer {cfg.api_key}"
        elif cfg.auth_mode() == AUTH_BASIC:
            auth = httpx.BasicAuth(
                cfg.username or "", cfg.password or "",
            )
        return httpx.Client(
            base_url=cfg.base_url.rstrip("/"),
            headers=headers,
            auth=auth,
            timeout=cfg.timeout_seconds,
        )

    # ------------------------------------------------------------------
    # Public BaseOptionsAdapter contract
    # ------------------------------------------------------------------

    def get_chain_snapshot(
        self,
        *,
        symbol: str,
        timestamp: datetime.datetime,
    ) -> ChainSnapshotResult:
        try:
            raw = self._raw_chain_pull(symbol=symbol, timestamp=timestamp)
        except ProviderError:
            raise
        except (httpx.ConnectError, httpx.ConnectTimeout, ConnectionError) as exc:
            logger.warning(
                "thetadata: provider unavailable for {} @ {}: {}",
                symbol, timestamp, exc,
            )
            raise ProviderUnavailable(str(exc)) from exc
        except (httpx.ReadTimeout, httpx.WriteTimeout, TimeoutError) as exc:
            logger.warning(
                "thetadata: provider timeout for {} @ {}: {}",
                symbol, timestamp, exc,
            )
            raise ProviderUnavailable(f"timeout: {exc}") from exc
        except Exception as exc:
            logger.error(
                "thetadata: unexpected error for {} @ {}: {}",
                symbol, timestamp, exc,
            )
            raise ProviderError(str(exc)) from exc

        quotes = self._normalize(raw, symbol=symbol, snapshot_at=timestamp)
        partial = bool(raw.get("partial", False))
        partial_reason = raw.get("partial_reason") if partial else None
        result = ChainSnapshotResult(
            quotes=tuple(quotes),
            provider=PROVIDER_NAME,
            fetched_at_utc=datetime.datetime.now(datetime.timezone.utc),
            snapshot_at_utc=timestamp,
            partial=partial,
            partial_reason=partial_reason,
            n_raw_quotes=len(raw.get("rows", [])),
            underlying_price=_to_dec(raw.get("underlying_price")),
            interest_rate=_to_dec(raw.get("interest_rate"))
                or Decimal("0.05"),
            dividend_yield=_to_dec(raw.get("dividend_yield"))
                or Decimal("0.0"),
        )
        if partial:
            logger.warning(
                "thetadata: partial chain for {} @ {} ({})",
                symbol, timestamp, partial_reason,
            )
            raise PartialChainWarning(
                partial_reason or "partial chain", result=result,
            )
        return result

    def health_check(self) -> bool:
        """Legacy contract (BaseOptionsAdapter). True when reachable."""
        return self.health_check_detail()["ok"]

    def health_check_detail(self) -> dict[str, Any]:
        """Phase 11O.1 — rich health check used by `--check-provider`.
        NEVER raises; surfaces all failures via the dict."""
        host = httpx.URL(self.config.base_url).host or self.config.base_url
        result: dict[str, Any] = {
            "ok": False,
            "status_code": None,
            "auth_mode": self.config.auth_mode(),
            "base_url_host": host,
            "latency_ms": None,
            "reason": None,
        }
        t0 = time.monotonic()
        try:
            resp = self._client.get(HEALTH_PATH, timeout=1.0)
            result["latency_ms"] = int((time.monotonic() - t0) * 1000)
            result["status_code"] = resp.status_code
            if 200 <= resp.status_code < 300:
                result["ok"] = True
            else:
                result["reason"] = (
                    f"HTTP {resp.status_code}: {resp.text[:120]!r}"
                )
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            result["reason"] = f"connection refused: {exc}"
        except (httpx.ReadTimeout, httpx.WriteTimeout, TimeoutError):
            result["reason"] = "timeout after 1000ms"
        except Exception as exc:  # noqa: BLE001
            result["reason"] = f"unexpected error: {exc}"
        result["latency_ms"] = (
            result["latency_ms"]
            if result["latency_ms"] is not None
            else int((time.monotonic() - t0) * 1000)
        )
        return result


# ---------------------------------------------------------------------------
# Phase Opt-B1 — classified pre-flight health probe
# ---------------------------------------------------------------------------


def classify_thetadata_preflight(settings_obj: Any) -> dict[str, Any]:
    """Distinguish 5 distinct health states for the operator dashboard.

    Returns a dict with EXACTLY these keys:
      - state:    "key_missing" | "auth_failed" | "unreachable" |
                  "rate_limited" | "healthy"
      - sentence: one short calm operator-facing sentence
      - http_status: int | None  (for healthy/auth_failed/rate_limited)
      - latency_ms:  int | None
      - reason:      raw upstream reason (verbose; for diagnostics card)

    NEVER raises. NEVER calls upstream when key/config is missing
    (saves the network round-trip + avoids leaking that the
    deployment exists to a misconfigured probe).

    Rule order matters:
      1. key_missing wins (config-only, no network call)
      2. unreachable beats everything network (connection refused / timeout)
      3. auth_failed (HTTP 401/403)
      4. rate_limited (HTTP 429)
      5. healthy (HTTP 2xx)
      6. default to unreachable for any other HTTP / unknown error
    """
    # 1. Config-level — key/credentials missing
    api_key = (getattr(settings_obj, "THETADATA_API_KEY", "") or "").strip()
    username = (getattr(settings_obj, "THETADATA_USERNAME", "") or "").strip()
    password = (getattr(settings_obj, "THETADATA_PASSWORD", "") or "").strip()
    if not api_key and not (username and password):
        return {
            "state": "key_missing",
            "sentence": (
                "ThetaData credentials not configured "
                "(THETADATA_API_KEY unset)."
            ),
            "http_status": None,
            "latency_ms": None,
            "reason": "no api_key and no username/password in env",
        }

    # 2-5. Network probe via the existing detail check
    base_url = getattr(settings_obj, "THETADATA_BASE_URL", DEFAULT_BASE_URL)
    cfg = ThetaDataConfig(
        base_url=base_url,
        api_key=api_key or None,
        username=username or None,
        password=password or None,
        timeout_seconds=2,  # short for dashboard; not for chain pulls
        max_retries=0,
    )
    try:
        adapter = ThetaDataAdapter(cfg)
    except Exception as exc:  # noqa: BLE001
        return {
            "state": "unreachable",
            "sentence": "ThetaData adapter could not be constructed.",
            "http_status": None,
            "latency_ms": None,
            "reason": f"adapter init failed: {exc}",
        }
    try:
        detail = adapter.health_check_detail()
    finally:
        try:
            adapter.close()
        except Exception:  # noqa: BLE001
            pass

    sc = detail.get("status_code")
    raw_reason = detail.get("reason")
    latency_ms = detail.get("latency_ms")

    if detail.get("ok") and sc and 200 <= sc < 300:
        return {
            "state": "healthy",
            "sentence": (
                f"ThetaData reachable at {detail.get('base_url_host')} "
                f"({latency_ms}ms)."
            ),
            "http_status": sc,
            "latency_ms": latency_ms,
            "reason": None,
        }
    if sc in (401, 403):
        return {
            "state": "auth_failed",
            "sentence": (
                f"ThetaData rejected credentials ({sc}). Check API key / "
                "username + password."
            ),
            "http_status": sc,
            "latency_ms": latency_ms,
            "reason": raw_reason,
        }
    if sc == 429:
        return {
            "state": "rate_limited",
            "sentence": (
                "ThetaData returned 429 Too Many Requests. Reduce poll "
                "rate or wait."
            ),
            "http_status": sc,
            "latency_ms": latency_ms,
            "reason": raw_reason,
        }
    # Default — any non-2xx / no status_code / connection failure
    return {
        "state": "unreachable",
        "sentence": (
            f"ThetaData unreachable at {detail.get('base_url_host')}: "
            f"{raw_reason or 'no response'}"
        ),
        "http_status": sc,
        "latency_ms": latency_ms,
        "reason": raw_reason or "unknown",
    }

    # ------------------------------------------------------------------
    # HTTP layer
    # ------------------------------------------------------------------

    def _raw_chain_pull(
        self,
        *,
        symbol: str,
        timestamp: datetime.datetime,
    ) -> dict[str, Any]:
        params = {"root": symbol.upper()}
        attempt = 0
        last_exc: Exception | None = None
        while True:
            self._rate_limiter.wait()
            try:
                resp = self._client.get(QUOTE_PATH, params=params)
            except (httpx.ConnectError, httpx.ConnectTimeout,
                    httpx.ReadTimeout, httpx.WriteTimeout) as exc:
                last_exc = exc
                if attempt >= self.config.max_retries:
                    raise
                attempt += 1
                continue

            sc = resp.status_code
            if 200 <= sc < 300:
                try:
                    payload = resp.json()
                except Exception as exc:
                    raise ProviderError(
                        f"thetadata returned non-JSON body for {symbol}: "
                        f"{exc}"
                    ) from exc
                if not isinstance(payload, dict) or "rows" not in payload:
                    raise ProviderError(
                        f"thetadata returned unexpected payload for "
                        f"{symbol}: missing 'rows' key"
                    )
                return payload
            if 400 <= sc < 500:
                raise ProviderError(
                    f"thetadata returned {sc} for {symbol}: "
                    f"{resp.text[:200]!r}"
                )
            if 500 <= sc < 600:
                if attempt >= self.config.max_retries:
                    raise ProviderUnavailable(
                        f"thetadata server error {sc} for {symbol}: "
                        f"{resp.text[:200]!r}"
                    )
                attempt += 1
                continue
            raise ProviderError(
                f"thetadata returned unhandled status {sc} for {symbol}"
            )

    # ------------------------------------------------------------------
    # Normalization
    # ------------------------------------------------------------------

    def _normalize(
        self,
        raw: dict[str, Any],
        *,
        symbol: str,
        snapshot_at: datetime.datetime,
    ) -> list[OptionChainQuote]:
        out: list[OptionChainQuote] = []
        for r in raw.get("rows", []):
            try:
                bid = _to_dec(r.get("bid"))
                ask = _to_dec(r.get("ask"))
                mid = _to_dec(r.get("mid"))
                if mid is None and bid is not None and ask is not None:
                    mid = (bid + ask) / Decimal("2")
                opt_type = str(r["option_type"]).upper()
                if opt_type in ("C", "CALL"):
                    opt_type = "CALL"
                elif opt_type in ("P", "PUT"):
                    opt_type = "PUT"
                else:
                    logger.warning(
                        "thetadata: unknown option_type {} — skipping row",
                        opt_type,
                    )
                    continue
                quote = OptionChainQuote(
                    snapshot_at_utc=snapshot_at,
                    underlying=symbol,
                    expiry=_to_date(r["expiry"]),
                    strike=Decimal(str(r["strike"])),
                    option_type=opt_type,
                    option_symbol=str(
                        r.get("option_symbol") or _occ(symbol, r)
                    ),
                    bid=bid,
                    ask=ask,
                    mid=mid,
                    last=_to_dec(r.get("last")),
                    volume=_to_int(r.get("volume")),
                    open_interest=_to_int(r.get("open_interest")),
                    delta=_to_dec(r.get("delta")),
                    gamma=_to_dec(r.get("gamma")),
                    theta=_to_dec(r.get("theta")),
                    vega=_to_dec(r.get("vega")),
                    iv=_to_dec(r.get("iv")),
                    quote_age_seconds=int(r.get("quote_age_seconds") or 0),
                    provider=PROVIDER_NAME,
                    provider_version=PROVIDER_VERSION,
                    underlying_price=_to_dec(raw.get("underlying_price")),
                    interest_rate=_to_dec(raw.get("interest_rate")),
                    dividend_yield=_to_dec(raw.get("dividend_yield")),
                )
                out.append(quote)
            except (KeyError, ValueError, TypeError) as exc:
                logger.warning(
                    "thetadata: skipping malformed row {}: {}", r, exc,
                )
                continue
        return out

    def close(self) -> None:
        if self._owned_client:
            self._client.close()


# ---------------------------------------------------------------------------
# Settings bridge + validation
# ---------------------------------------------------------------------------

class ThetaDataConfigError(ProviderError):
    """Raised at adapter construction for invalid config."""


def _config_from_settings(settings_obj=None) -> ThetaDataConfig:
    """Build ThetaDataConfig from a Settings-like object.

    When `THETADATA_BASE_URL` is unset we fall back to
    `DEFAULT_BASE_URL` (Theta Terminal's local default) so the adapter
    constructor still succeeds with no explicit config — preserves
    Phase 11C baseline behaviour. The `assert_settings_provided`
    helper below performs a strict check for the CLI
    `--check-provider` path.
    """
    from apps.api.src.config import settings as default_settings
    s = settings_obj if settings_obj is not None else default_settings
    base = getattr(s, "THETADATA_BASE_URL", None) or DEFAULT_BASE_URL
    return ThetaDataConfig(
        base_url=base,
        api_key=getattr(s, "THETADATA_API_KEY", None) or None,
        username=getattr(s, "THETADATA_USERNAME", None) or None,
        password=getattr(s, "THETADATA_PASSWORD", None) or None,
        timeout_seconds=int(
            getattr(s, "THETADATA_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)
        ),
        max_retries=int(
            getattr(s, "THETADATA_MAX_RETRIES", DEFAULT_MAX_RETRIES)
        ),
        rate_limit_qps=float(
            getattr(s, "THETADATA_RATE_LIMIT_QPS", DEFAULT_RATE_LIMIT_QPS)
        ),
    )


def assert_settings_provided(settings_obj=None) -> None:
    """Strict check used by the CLI `--check-provider` path. Refuses
    to proceed when the operator has not explicitly set
    `THETADATA_BASE_URL`. Distinct from `_validate_config` which is
    forgiving (falls back to DEFAULT_BASE_URL) so legacy callers and
    tests that call `ThetaDataAdapter()` with no args keep working.
    """
    from apps.api.src.config import settings as default_settings
    s = settings_obj if settings_obj is not None else default_settings
    if not getattr(s, "THETADATA_BASE_URL", None):
        raise ThetaDataConfigError(
            "[config] THETADATA_BASE_URL must be set when "
            'OPTIONS_DATA_PROVIDER="thetadata"'
        )
    api_key = getattr(s, "THETADATA_API_KEY", None) or None
    user = getattr(s, "THETADATA_USERNAME", None) or None
    pwd = getattr(s, "THETADATA_PASSWORD", None) or None
    if api_key and (user or pwd):
        raise ThetaDataConfigError(
            "[config] choose ONE auth mode: api_key OR username/password"
        )
    if (user and not pwd) or (pwd and not user):
        raise ThetaDataConfigError(
            "[config] THETADATA_USERNAME and THETADATA_PASSWORD must be "
            "set together"
        )


def _validate_config(cfg: ThetaDataConfig) -> None:
    if not cfg.base_url:
        raise ThetaDataConfigError(
            "[config] THETADATA_BASE_URL must be set when "
            'OPTIONS_DATA_PROVIDER="thetadata"'
        )
    scheme = httpx.URL(cfg.base_url).scheme
    if scheme not in ("http", "https"):
        raise ThetaDataConfigError(
            "[config] THETADATA_BASE_URL must use http:// or https:// "
            f"(got: {scheme!r})"
        )
    if cfg.api_key and (cfg.username or cfg.password):
        raise ThetaDataConfigError(
            "[config] choose ONE auth mode: api_key OR username/password, "
            "not both"
        )
    if (cfg.username and not cfg.password) or (
            cfg.password and not cfg.username):
        raise ThetaDataConfigError(
            "[config] THETADATA_USERNAME and THETADATA_PASSWORD must be "
            "set together"
        )
    if cfg.timeout_seconds <= 0:
        raise ThetaDataConfigError(
            "[config] THETADATA_TIMEOUT_SECONDS must be > 0"
        )
    if cfg.max_retries < 0:
        raise ThetaDataConfigError(
            "[config] THETADATA_MAX_RETRIES must be >= 0"
        )
    if cfg.rate_limit_qps <= 0:
        raise ThetaDataConfigError(
            "[config] THETADATA_RATE_LIMIT_QPS must be > 0"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_dec(v: Any) -> Decimal | None:
    if v is None or v == "":
        return None
    try:
        return Decimal(str(v))
    except (ValueError, TypeError, ArithmeticError):
        return None


def _to_int(v: Any) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


def _to_date(v: Any) -> datetime.date:
    if isinstance(v, datetime.date) and not isinstance(v, datetime.datetime):
        return v
    if isinstance(v, datetime.datetime):
        return v.date()
    if isinstance(v, str):
        return datetime.date.fromisoformat(v)
    raise ValueError(f"cannot parse date: {v!r}")


def _occ(symbol: str, row: dict[str, Any]) -> str:
    expiry = _to_date(row["expiry"])
    strike = Decimal(str(row["strike"]))
    cp = "C" if str(row["option_type"]).upper() in ("C", "CALL") else "P"
    strike_milli = int(strike * 1000)
    return (
        f"{symbol.upper()}{expiry.strftime('%y%m%d')}"
        f"{cp}{strike_milli:08d}"
    )
