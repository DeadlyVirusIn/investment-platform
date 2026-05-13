"""Finnhub options-chain adapter (Phase Opt-B3a).

Implements `BaseOptionsAdapter` against Finnhub's `/stock/option-chain`
endpoint. Designed for Finnhub's *free tier* characteristics:

  * EOD-fresh quotes (no real-time intraday on free tier)
  * Greeks / IV typically absent → adapter yields `None` for those
    fields and the chain-ingest layer fills them via stdlib BSM
    (`apps/api/src/options/data_provider/greeks.py`)
  * Strict 60 req/min cap → token-bucket rate limiter, default 1.0 QPS
  * `contractName` is already OCC-formatted → used verbatim as
    `option_symbol`

Discipline (mirrors ThetaData adapter):
  * Pure data adapter. NEVER writes to DB. NEVER triggers any worker job.
  * `health_check()` is a side-effect-free probe.
  * Missing API key → return empty `ChainSnapshotResult` with
    `partial=True, partial_reason="no api key"`. Do NOT raise.
  * No silent synthesis: empty / missing fields → `None`. Greeks are
    only filled later by the explicit `_enrich_with_greeks` BSM path,
    which records `provider_version="finnhub-free-tier"` so consumers
    can discriminate exchange-native vs locally-derived Greeks.

NEVER imports execution / equity / V2 / strategy modules.
"""

from __future__ import annotations

import datetime
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

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
    PartialChainWarning,
    ProviderError,
    ProviderUnavailable,
)


PROVIDER_NAME = "finnhub"
PROVIDER_VERSION_FREE = "finnhub-free-tier"

DEFAULT_BASE_URL = "https://finnhub.io/api/v1"
DEFAULT_TIMEOUT_SECONDS = 15
DEFAULT_MAX_RETRIES = 1
DEFAULT_RATE_LIMIT_QPS = 1.0          # 60 req/min — Finnhub free tier cap

OPTION_CHAIN_PATH = "/stock/option-chain"
HEALTH_PROBE_SYMBOL = "SPY"


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FinnhubOptionsConfig:
    base_url: str = DEFAULT_BASE_URL
    api_key: str | None = None
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    max_retries: int = DEFAULT_MAX_RETRIES
    rate_limit_qps: float = DEFAULT_RATE_LIMIT_QPS


def _config_from_settings() -> FinnhubOptionsConfig:
    """Build config from app settings. Tolerates missing keys (returns
    cfg with `api_key=None` so adapter can graceful-degrade)."""
    from apps.api.src.config import settings

    api_key = (getattr(settings, "FINNHUB_API_KEY", "") or "").strip()
    return FinnhubOptionsConfig(
        base_url=DEFAULT_BASE_URL,
        api_key=api_key or None,
        timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
        max_retries=DEFAULT_MAX_RETRIES,
        rate_limit_qps=DEFAULT_RATE_LIMIT_QPS,
    )


# ---------------------------------------------------------------------------
# Rate limiter (mirrors ThetaData implementation; same single-thread bucket)
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
# Helpers
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


def _parse_expiry(raw: str | None) -> datetime.date | None:
    if not raw:
        return None
    try:
        return datetime.date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _parse_last_trade(raw: str | None) -> datetime.datetime | None:
    """Finnhub free-tier emits 'YYYY-MM-DD HH:MM:SS' (no TZ — assume UTC)."""
    if not raw:
        return None
    raw = raw.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            naive = datetime.datetime.strptime(raw, fmt)
            return naive.replace(tzinfo=datetime.timezone.utc)
        except ValueError:
            continue
    return None


def _quote_age_seconds(
    *, last_trade: datetime.datetime | None,
    snapshot_at: datetime.datetime,
) -> int:
    """Age of the quote vs the snapshot moment. If `last_trade` is
    unknown or in the future relative to the snapshot, fall back to 0."""
    if last_trade is None:
        return 0
    delta = (snapshot_at - last_trade).total_seconds()
    if delta < 0:
        return 0
    if delta > 60 * 60 * 24 * 365:    # absurd → treat as unknown
        return 0
    return int(delta)


def _mid(bid: Decimal | None, ask: Decimal | None) -> Decimal | None:
    if bid is None or ask is None:
        return None
    return (bid + ask) / Decimal("2")


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class FinnhubOptionsAdapter(BaseOptionsAdapter):
    """Finnhub `/stock/option-chain` adapter.

    Free-tier characteristics are explicit in the constructor docstring;
    behavior is identical on paid plans except that Greeks/IV will arrive
    populated and the BSM enrichment in the chain-ingest layer becomes a
    no-op for those fields.
    """

    name = PROVIDER_NAME

    def __init__(
        self,
        config: FinnhubOptionsConfig | None = None,
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
    def _build_client(cfg: FinnhubOptionsConfig) -> httpx.Client:
        return httpx.Client(
            base_url=cfg.base_url.rstrip("/"),
            headers={"Accept": "application/json"},
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
        """Lightweight probe. Returns True iff the chain endpoint
        responds 200 with a JSON body containing the `data` key.

        Pure observation. No DB writes. No retries. No raises (returns
        False on any error).
        """
        if not self.config.api_key:
            logger.info("finnhub: health_check → False (api key missing)")
            return False
        try:
            self._rate_limiter.wait()
            resp = self._client.get(
                OPTION_CHAIN_PATH,
                params={"symbol": HEALTH_PROBE_SYMBOL,
                        "token": self.config.api_key},
            )
            if resp.status_code != 200:
                logger.warning(
                    "finnhub: health_check non-200 url={} status={} body~{}",
                    safe_url(resp.url), resp.status_code,
                    redact_token(resp.text[:120]),
                )
                return False
            body = resp.json()
            return isinstance(body, dict) and "data" in body
        except Exception as exc:        # noqa: BLE001 — pure probe
            logger.warning("finnhub: health_check failed: {}",
                           redact_token(str(exc)))
            return False

    def get_chain_snapshot(
        self,
        *,
        symbol: str,
        timestamp: datetime.datetime,
    ) -> ChainSnapshotResult:
        # Graceful degrade — no key → empty partial chain (NEVER raise,
        # NEVER synthesize). Mirror of ThetaData adapter's behavior so
        # the ingest orchestrator records `status="skipped_unavailable"`.
        if not self.config.api_key:
            return ChainSnapshotResult(
                quotes=(),
                provider=PROVIDER_NAME,
                fetched_at_utc=datetime.datetime.now(datetime.timezone.utc),
                snapshot_at_utc=timestamp,
                partial=True,
                partial_reason="no api key",
                n_raw_quotes=0,
                notes=("finnhub_no_api_key",),
            )

        try:
            body = self._raw_chain_pull(symbol=symbol)
        except (httpx.ConnectError, httpx.ConnectTimeout, ConnectionError) as exc:
            # `from None` instead of `from exc` so the exception chain
            # does not preserve a raw URL with the token in the traceback.
            raise ProviderUnavailable(
                redact_token(f"finnhub connect error: {exc}")) from None
        except (httpx.ReadTimeout, httpx.WriteTimeout, TimeoutError) as exc:
            raise ProviderUnavailable(
                redact_token(f"finnhub timeout: {exc}")) from None
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else None
            # safe_url() strips query string → token never appears in our msg.
            # `from None` discards the chained httpx exception (whose repr
            # contains the raw URL including the token).
            url = safe_url(exc.request.url) if exc.request else ""
            if status in (401, 403):
                raise ProviderError(
                    f"finnhub auth failed (HTTP {status}) url={url}") from None
            if status == 429:
                raise ProviderUnavailable(
                    f"finnhub rate limited (HTTP 429) url={url}") from None
            raise ProviderError(
                f"finnhub http error status={status} url={url}") from None
        except httpx.HTTPError as exc:
            raise ProviderError(
                redact_token(f"finnhub http error: {exc}")) from None

        fetched_at = datetime.datetime.now(datetime.timezone.utc)

        quotes_raw = list(self._iter_quotes_from_body(
            body=body, symbol=symbol, snapshot_at=timestamp,
        ))

        # No quotes → partial-empty result. Honest signal upstream.
        if not quotes_raw:
            return ChainSnapshotResult(
                quotes=(),
                provider=PROVIDER_NAME,
                fetched_at_utc=fetched_at,
                snapshot_at_utc=timestamp,
                partial=True,
                partial_reason="finnhub returned 0 contracts",
                n_raw_quotes=0,
                notes=("finnhub_empty_chain",),
            )

        # Detect whether ANY quote arrived with provider Greeks. Used to
        # tag the snapshot result so downstream knows BSM fallback fired.
        any_provider_greeks = any(
            (q.delta is not None or q.iv is not None) for q in quotes_raw
        )
        notes: tuple[str, ...] = ()
        if not any_provider_greeks:
            notes = ("greeks_provider_unavailable_bsm_fallback_will_run",)

        return ChainSnapshotResult(
            quotes=tuple(quotes_raw),
            provider=PROVIDER_NAME,
            fetched_at_utc=fetched_at,
            snapshot_at_utc=timestamp,
            partial=False,
            partial_reason=None,
            n_raw_quotes=len(quotes_raw),
            notes=notes,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _raw_chain_pull(self, *, symbol: str) -> dict[str, Any]:
        """Single GET to `/stock/option-chain`. Raises on HTTP/transport
        error so the caller can map to ProviderError / Unavailable.

        Finnhub auth is via `?token=` query param (their API does not
        accept Authorization headers). The outer get_chain_snapshot()
        error path uses safe_url() to strip the query before logging,
        so the token never appears in any emitted message even on a
        raise_for_status() failure path.
        """
        self._rate_limiter.wait()
        resp = self._client.get(
            OPTION_CHAIN_PATH,
            params={"symbol": symbol, "token": self.config.api_key},
        )
        resp.raise_for_status()
        body = resp.json()
        if not isinstance(body, dict):
            raise ProviderError(
                f"finnhub returned non-dict body for {symbol}")
        return body

    def _iter_quotes_from_body(
        self,
        *,
        body: dict[str, Any],
        symbol: str,
        snapshot_at: datetime.datetime,
    ):
        """Generator yielding normalized `OptionChainQuote` rows from the
        raw Finnhub payload. Skips malformed rows silently (logs once
        per skip)."""
        data = body.get("data") or []
        if not isinstance(data, list):
            return

        for expiry_block in data:
            if not isinstance(expiry_block, dict):
                continue
            expiry = _parse_expiry(expiry_block.get("expirationDate"))
            if expiry is None:
                continue
            options = expiry_block.get("options") or {}
            if not isinstance(options, dict):
                continue

            for side_key, option_type in (("CALL", "CALL"), ("PUT", "PUT")):
                rows = options.get(side_key) or []
                if not isinstance(rows, list):
                    continue
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    q = self._normalize_row(
                        row=row,
                        symbol=symbol,
                        expiry=expiry,
                        option_type=option_type,
                        snapshot_at=snapshot_at,
                    )
                    if q is not None:
                        yield q

    def _normalize_row(
        self,
        *,
        row: dict[str, Any],
        symbol: str,
        expiry: datetime.date,
        option_type: str,
        snapshot_at: datetime.datetime,
    ) -> OptionChainQuote | None:
        strike = _to_decimal(row.get("strike"))
        if strike is None:
            return None
        contract_name = row.get("contractName") or row.get("symbol") or ""
        if not contract_name:
            return None

        bid = _to_decimal(row.get("bid"))
        ask = _to_decimal(row.get("ask"))
        last = _to_decimal(row.get("lastPrice"))
        mid = _mid(bid, ask)

        last_trade = _parse_last_trade(row.get("lastTradeDateTime"))
        age = _quote_age_seconds(last_trade=last_trade, snapshot_at=snapshot_at)

        return OptionChainQuote(
            snapshot_at_utc=snapshot_at,
            underlying=symbol.upper(),
            expiry=expiry,
            strike=strike,
            option_type=option_type,
            option_symbol=str(contract_name),
            bid=bid,
            ask=ask,
            mid=mid,
            last=last,
            volume=_to_int(row.get("volume")),
            open_interest=_to_int(row.get("openInterest")),
            delta=_to_decimal(row.get("delta")),
            gamma=_to_decimal(row.get("gamma")),
            theta=_to_decimal(row.get("theta")),
            vega=_to_decimal(row.get("vega")),
            iv=_to_decimal(row.get("impliedVolatility")),
            quote_age_seconds=age,
            provider=PROVIDER_NAME,
            provider_version=PROVIDER_VERSION_FREE,
            underlying_price=None,         # ingest layer fills from price_bar
            interest_rate=None,            # BSM uses default 0.05
            dividend_yield=None,           # BSM uses 0.0
        )


# Re-export PartialChainWarning so callers can `except` it without
# importing base_adapter directly.
__all__ = [
    "FinnhubOptionsAdapter",
    "FinnhubOptionsConfig",
    "PROVIDER_NAME",
    "PROVIDER_VERSION_FREE",
]
