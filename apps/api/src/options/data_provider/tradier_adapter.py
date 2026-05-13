"""Tradier options-chain adapter (Phase Opt-B3a).

Implements `BaseOptionsAdapter` against the Tradier API. Designed
primarily for the sandbox tier (https://sandbox.tradier.com/v1)
which provides:

  * ~15-min delayed quotes (appropriate for shadow-eval cadence)
  * provider-native Greeks + IV (no BSM fallback required)
  * 60 req/min cap — token-bucket rate limiter at 1.0 QPS default
  * Bearer-header auth (token NEVER in URL → safe under redaction
    layer + safe_url())

Production tier (https://api.tradier.com/v1) uses the same adapter
shape — caller just changes `TRADIER_BASE_URL`.

Endpoint flow per `get_chain_snapshot()`:
  1. GET /markets/options/expirations → list of expiry dates
  2. Filter to expiries within `TRADIER_DTE_WINDOW_DAYS`
  3. For each: GET /markets/options/chains?expiration=&greeks=true
  4. Normalize each option → `OptionChainQuote`

Discipline (mirrors other adapters):
  * Pure data adapter. NEVER writes DB. NEVER triggers worker jobs.
  * Missing token → return empty `ChainSnapshotResult(partial=True)`.
    Do NOT raise.
  * Per-expiry failures aggregate into `partial=True, notes=(...)`
    rather than aborting whole snapshot.
  * Token NEVER appears in URLs (uses Authorization header).
  * All error paths route through `redact_token` + `safe_url`.
"""

from __future__ import annotations

import datetime
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

import httpx

from apps.api.src.options.data_provider._redact import (
    redact_token,
    safe_logger as logger,
    safe_url,
)
from apps.api.src.options.data_provider.base_adapter import (
    BaseOptionsAdapter,
    ChainSnapshotResult,
    OptionChainQuote,
    ProviderError,
    ProviderUnavailable,
)


PROVIDER_NAME = "tradier"
PROVIDER_VERSION_SANDBOX = "tradier-sandbox"
PROVIDER_VERSION_PROD = "tradier-prod"

DEFAULT_BASE_URL = "https://sandbox.tradier.com/v1"
DEFAULT_TIMEOUT_SECONDS = 15
DEFAULT_RATE_LIMIT_QPS = 1.0
DEFAULT_DTE_WINDOW_DAYS = 60

HEALTH_PATH = "/markets/clock"
EXPIRATIONS_PATH = "/markets/options/expirations"
CHAINS_PATH = "/markets/options/chains"


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TradierOptionsConfig:
    base_url: str = DEFAULT_BASE_URL
    access_token: str | None = None
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    rate_limit_qps: float = DEFAULT_RATE_LIMIT_QPS
    dte_window_days: int = DEFAULT_DTE_WINDOW_DAYS

    @property
    def provider_version(self) -> str:
        return (PROVIDER_VERSION_PROD
                if "sandbox" not in self.base_url
                else PROVIDER_VERSION_SANDBOX)


def _config_from_settings() -> TradierOptionsConfig:
    from apps.api.src.config import settings

    token = (getattr(settings, "TRADIER_ACCESS_TOKEN", "") or "").strip()
    base = (getattr(settings, "TRADIER_BASE_URL", "") or "").strip() or DEFAULT_BASE_URL
    qps = float(getattr(settings, "TRADIER_RATE_LIMIT_QPS", DEFAULT_RATE_LIMIT_QPS) or DEFAULT_RATE_LIMIT_QPS)
    dte = int(getattr(settings, "TRADIER_DTE_WINDOW_DAYS", DEFAULT_DTE_WINDOW_DAYS) or DEFAULT_DTE_WINDOW_DAYS)
    timeout = int(getattr(settings, "TRADIER_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS) or DEFAULT_TIMEOUT_SECONDS)
    return TradierOptionsConfig(
        base_url=base,
        access_token=token or None,
        timeout_seconds=timeout,
        rate_limit_qps=qps,
        dte_window_days=dte,
    )


# ---------------------------------------------------------------------------
# Rate limiter (shared single-thread bucket pattern)
# ---------------------------------------------------------------------------

class _RateLimiter:
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


# ---------------------------------------------------------------------------
# Coercion helpers
# ---------------------------------------------------------------------------

def _to_decimal(v: Any) -> Decimal | None:
    if v is None or v == "":
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None


def _to_int(v: Any) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return None


def _parse_iso_date(raw: str | None) -> datetime.date | None:
    if not raw:
        return None
    try:
        return datetime.date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _parse_epoch_ms(raw: Any) -> datetime.datetime | None:
    """Tradier emits `bid_date` / `ask_date` as epoch milliseconds (int)."""
    if raw is None:
        return None
    try:
        ms = int(raw)
    except (TypeError, ValueError):
        return None
    if ms <= 0:
        return None
    try:
        return datetime.datetime.fromtimestamp(ms / 1000.0, tz=datetime.timezone.utc)
    except (OSError, OverflowError, ValueError):
        return None


def _quote_age_seconds(
    *, bid_date: datetime.datetime | None,
    ask_date: datetime.datetime | None,
    snapshot_at: datetime.datetime,
) -> int:
    """Age of the freshest of bid_date / ask_date vs snapshot moment."""
    freshest: datetime.datetime | None = None
    for d in (bid_date, ask_date):
        if d is None:
            continue
        if freshest is None or d > freshest:
            freshest = d
    if freshest is None:
        return 0
    delta = (snapshot_at - freshest).total_seconds()
    if delta < 0:
        return 0
    if delta > 60 * 60 * 24 * 365:
        return 0
    return int(delta)


def _mid(bid: Decimal | None, ask: Decimal | None) -> Decimal | None:
    if bid is None or ask is None:
        return None
    return (bid + ask) / Decimal("2")


def _as_list(value: Any) -> list:
    """Tradier returns single-element collections as dicts, multi-element
    as lists. Normalize both into a list."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class TradierOptionsAdapter(BaseOptionsAdapter):
    """Tradier (sandbox or production) options chain adapter."""

    name = PROVIDER_NAME

    def __init__(
        self,
        config: TradierOptionsConfig | None = None,
        *,
        http_client: httpx.Client | None = None,
        clock=None,
        sleeper=None,
    ) -> None:
        cfg = config or _config_from_settings()
        self.config = cfg
        self._owned_client = http_client is None
        self._client = http_client or self._build_client(cfg)
        self._rate_limiter = _RateLimiter(cfg.rate_limit_qps, clock=clock)
        if sleeper is not None:
            self._rate_limiter._sleep = sleeper  # type: ignore[assignment]

    @staticmethod
    def _build_client(cfg: TradierOptionsConfig) -> httpx.Client:
        headers: dict[str, str] = {"Accept": "application/json"}
        if cfg.access_token:
            # Authorization header — NEVER URL query string
            headers["Authorization"] = f"Bearer {cfg.access_token}"
        return httpx.Client(
            base_url=cfg.base_url.rstrip("/"),
            headers=headers,
            timeout=cfg.timeout_seconds,
        )

    def close(self) -> None:
        if self._owned_client:
            try:
                self._client.close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # BaseOptionsAdapter contract
    # ------------------------------------------------------------------

    def health_check(self) -> bool:
        """GET /markets/clock — cheap probe. Returns True iff 200 and
        body contains `clock` key.

        Pure observation. No raises. No retries.
        """
        if not self.config.access_token:
            logger.info("tradier: health_check false (access_token missing)")
            return False
        try:
            self._rate_limiter.wait()
            resp = self._client.get(HEALTH_PATH)
            if resp.status_code != 200:
                logger.warning(
                    "tradier: health_check non-200 url={} status={}",
                    safe_url(resp.url), resp.status_code,
                )
                return False
            body = resp.json()
            return isinstance(body, dict) and "clock" in body
        except Exception as exc:        # noqa: BLE001 — pure probe
            logger.warning("tradier: health_check error: {}",
                           redact_token(str(exc)))
            return False

    def get_chain_snapshot(
        self,
        *,
        symbol: str,
        timestamp: datetime.datetime,
    ) -> ChainSnapshotResult:
        # Graceful degrade — no token → empty partial.
        if not self.config.access_token:
            return ChainSnapshotResult(
                quotes=(),
                provider=PROVIDER_NAME,
                fetched_at_utc=datetime.datetime.now(datetime.timezone.utc),
                snapshot_at_utc=timestamp,
                partial=True,
                partial_reason="no access token",
                n_raw_quotes=0,
                notes=("tradier_no_access_token",),
            )

        # 1. Expirations list
        try:
            expirations = self._fetch_expirations(symbol=symbol)
        except (httpx.ConnectError, httpx.ConnectTimeout, ConnectionError) as exc:
            raise ProviderUnavailable(
                redact_token(f"tradier connect error: {exc}")) from exc
        except (httpx.ReadTimeout, httpx.WriteTimeout, TimeoutError) as exc:
            raise ProviderUnavailable(
                redact_token(f"tradier timeout: {exc}")) from exc
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else None
            url = safe_url(exc.request.url) if exc.request else ""
            if status in (401, 403):
                raise ProviderError(
                    f"tradier auth failed (HTTP {status}) url={url}") from None
            if status == 429:
                raise ProviderUnavailable(
                    f"tradier rate limited (HTTP 429) url={url}") from None
            raise ProviderError(
                f"tradier http error status={status} url={url}") from None
        except httpx.HTTPError as exc:
            raise ProviderError(
                redact_token(f"tradier http error: {exc}")) from None

        fetched_at = datetime.datetime.now(datetime.timezone.utc)

        # 2. Filter by DTE window
        snapshot_date = timestamp.date()
        max_date = snapshot_date + datetime.timedelta(
            days=self.config.dte_window_days)
        eligible = [d for d in expirations
                    if d is not None and snapshot_date <= d <= max_date]

        if not eligible:
            return ChainSnapshotResult(
                quotes=(),
                provider=PROVIDER_NAME,
                fetched_at_utc=fetched_at,
                snapshot_at_utc=timestamp,
                partial=True,
                partial_reason=(
                    f"no expirations within {self.config.dte_window_days}-day window"
                ),
                n_raw_quotes=0,
                notes=("tradier_empty_eligible_expirations",),
            )

        # 3. Per-expiry chain pulls
        all_quotes: list[OptionChainQuote] = []
        per_expiry_status: list[str] = []
        any_provider_greeks = False

        for expiry in eligible:
            try:
                body = self._fetch_chain(symbol=symbol, expiration=expiry)
                quotes = list(self._iter_quotes_from_body(
                    body=body,
                    symbol=symbol,
                    snapshot_at=timestamp,
                ))
                all_quotes.extend(quotes)
                per_expiry_status.append(f"{expiry}:ok({len(quotes)})")
                if any(q.delta is not None or q.iv is not None for q in quotes):
                    any_provider_greeks = True
            except (httpx.HTTPError, ProviderError, ProviderUnavailable) as exc:
                per_expiry_status.append(
                    f"{expiry}:err({type(exc).__name__})")
                logger.warning(
                    "tradier: chain pull failed for {} {} — {}",
                    symbol, expiry, redact_token(str(exc)),
                )

        if not all_quotes:
            return ChainSnapshotResult(
                quotes=(),
                provider=PROVIDER_NAME,
                fetched_at_utc=fetched_at,
                snapshot_at_utc=timestamp,
                partial=True,
                partial_reason="tradier returned 0 contracts across eligible expiries",
                n_raw_quotes=0,
                notes=tuple(per_expiry_status) or ("tradier_empty_chain",),
            )

        notes: tuple[str, ...] = ()
        if not any_provider_greeks:
            notes = ("greeks_provider_unavailable_bsm_fallback_will_run",)
        partial = any(":err" in s for s in per_expiry_status)
        partial_reason = (
            "one or more expirations failed" if partial else None
        )

        return ChainSnapshotResult(
            quotes=tuple(all_quotes),
            provider=PROVIDER_NAME,
            fetched_at_utc=fetched_at,
            snapshot_at_utc=timestamp,
            partial=partial,
            partial_reason=partial_reason,
            n_raw_quotes=len(all_quotes),
            notes=notes,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _fetch_expirations(self, *, symbol: str) -> list[datetime.date]:
        """GET /markets/options/expirations → list of date objects."""
        self._rate_limiter.wait()
        resp = self._client.get(
            EXPIRATIONS_PATH,
            params={"symbol": symbol, "strikes": "false",
                    "includeAllRoots": "true"},
        )
        resp.raise_for_status()
        body = resp.json()
        if not isinstance(body, dict):
            return []
        block = body.get("expirations") or {}
        if not isinstance(block, dict):
            return []
        # Two shapes: {"date": [...]} OR {"expiration": [{date:...}, ...]}
        raw_dates = block.get("date")
        if raw_dates is None:
            exps = _as_list(block.get("expiration"))
            raw_dates = [e.get("date") for e in exps if isinstance(e, dict)]
        if not isinstance(raw_dates, list):
            raw_dates = [raw_dates]
        out: list[datetime.date] = []
        for r in raw_dates:
            d = _parse_iso_date(r if isinstance(r, str) else None)
            if d is not None:
                out.append(d)
        return out

    def _fetch_chain(self, *, symbol: str,
                     expiration: datetime.date) -> dict[str, Any]:
        """GET /markets/options/chains?greeks=true."""
        self._rate_limiter.wait()
        resp = self._client.get(
            CHAINS_PATH,
            params={"symbol": symbol,
                    "expiration": expiration.isoformat(),
                    "greeks": "true"},
        )
        resp.raise_for_status()
        body = resp.json()
        if not isinstance(body, dict):
            raise ProviderError(
                f"tradier returned non-dict body url={safe_url(resp.url)}")
        return body

    def _iter_quotes_from_body(
        self,
        *,
        body: dict[str, Any],
        symbol: str,
        snapshot_at: datetime.datetime,
    ) -> Iterable[OptionChainQuote]:
        opts = body.get("options")
        if not isinstance(opts, dict):
            return
        rows = _as_list(opts.get("option"))
        for row in rows:
            if not isinstance(row, dict):
                continue
            q = self._normalize_row(
                row=row, symbol=symbol, snapshot_at=snapshot_at)
            if q is not None:
                yield q

    def _normalize_row(
        self,
        *,
        row: dict[str, Any],
        symbol: str,
        snapshot_at: datetime.datetime,
    ) -> OptionChainQuote | None:
        strike = _to_decimal(row.get("strike"))
        if strike is None:
            return None
        option_symbol = str(row.get("symbol") or "")
        if not option_symbol:
            return None
        expiry = _parse_iso_date(row.get("expiration_date"))
        if expiry is None:
            return None

        raw_type = str(row.get("option_type") or "").strip().lower()
        if raw_type == "call":
            option_type = "CALL"
        elif raw_type == "put":
            option_type = "PUT"
        else:
            return None

        bid = _to_decimal(row.get("bid"))
        ask = _to_decimal(row.get("ask"))
        last = _to_decimal(row.get("last"))
        mid = _mid(bid, ask)

        bid_date = _parse_epoch_ms(row.get("bid_date"))
        ask_date = _parse_epoch_ms(row.get("ask_date"))
        age = _quote_age_seconds(
            bid_date=bid_date, ask_date=ask_date, snapshot_at=snapshot_at)

        greeks = row.get("greeks") or {}
        if not isinstance(greeks, dict):
            greeks = {}
        # Prefer smv_vol (ORATS-derived stable mark IV), fall back to mid_iv
        iv_raw = greeks.get("smv_vol")
        if iv_raw in (None, "", 0, 0.0):
            iv_raw = greeks.get("mid_iv")

        return OptionChainQuote(
            snapshot_at_utc=snapshot_at,
            underlying=symbol.upper(),
            expiry=expiry,
            strike=strike,
            option_type=option_type,
            option_symbol=option_symbol,
            bid=bid,
            ask=ask,
            mid=mid,
            last=last,
            volume=_to_int(row.get("volume")),
            open_interest=_to_int(row.get("open_interest")),
            delta=_to_decimal(greeks.get("delta")),
            gamma=_to_decimal(greeks.get("gamma")),
            theta=_to_decimal(greeks.get("theta")),
            vega=_to_decimal(greeks.get("vega")),
            iv=_to_decimal(iv_raw),
            quote_age_seconds=age,
            provider=PROVIDER_NAME,
            provider_version=self.config.provider_version,
            underlying_price=None,
            interest_rate=None,
            dividend_yield=None,
        )


__all__ = [
    "TradierOptionsAdapter",
    "TradierOptionsConfig",
    "PROVIDER_NAME",
    "PROVIDER_VERSION_SANDBOX",
    "PROVIDER_VERSION_PROD",
]
