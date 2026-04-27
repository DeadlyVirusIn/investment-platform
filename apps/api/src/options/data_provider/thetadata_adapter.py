"""ThetaData provider adapter (Phase 11C).

Implements `BaseOptionsAdapter`. v1 ships with the contract + a stub
HTTP layer; the actual ThetaData REST integration is wired here when
the operator's API key + network access are available.

Hard-isolated from V2 / equity / strategy / execution. Stdlib only at
import time; HTTP client (httpx / requests) imported lazily inside the
fetch method to keep the module load light.
"""

from __future__ import annotations

import datetime
import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

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

# Frozen module constants — change only with revision-history doc update
DEFAULT_BASE_URL = "http://127.0.0.1:25510"      # ThetaData Terminal default
DEFAULT_TIMEOUT_SECONDS = 10
DEFAULT_QUOTE_AGE_TOLERANCE_SECONDS = 60   # quotes older than this rejected at ingest layer


@dataclass(frozen=True)
class ThetaDataConfig:
    base_url: str = DEFAULT_BASE_URL
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    quote_age_tolerance_seconds: int = DEFAULT_QUOTE_AGE_TOLERANCE_SECONDS


class ThetaDataAdapter(BaseOptionsAdapter):
    """ThetaData REST adapter.

    v1 contract impl. The fetch path is structured but the actual HTTP
    call is stubbed via `_raw_chain_pull` — substituted in tests with
    a deterministic mock; will be wired to ThetaData's REST API once
    the operator confirms credentials + network access.
    """

    name = PROVIDER_NAME

    def __init__(self, config: ThetaDataConfig | None = None) -> None:
        self.config = config or ThetaDataConfig(
            base_url=os.environ.get("THETADATA_BASE_URL", DEFAULT_BASE_URL),
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
            # Already a typed provider error — propagate as-is
            raise
        except ConnectionError as exc:
            logger.warning(
                "thetadata: provider unavailable for {} @ {}: {}",
                symbol, timestamp, exc,
            )
            raise ProviderUnavailable(str(exc)) from exc
        except TimeoutError as exc:
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
                or Decimal("0.05"),     # 5% default if provider omits
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
        try:
            self._raw_health_check()
            return True
        except Exception as exc:
            logger.warning("thetadata health check failed: {}", exc)
            return False

    # ------------------------------------------------------------------
    # Internal — stub HTTP layer; substituted in tests
    # ------------------------------------------------------------------

    def _raw_chain_pull(
        self,
        *,
        symbol: str,
        timestamp: datetime.datetime,
    ) -> dict[str, Any]:
        """Lazy-import the HTTP client; perform actual REST call.

        v1 returns a NotImplementedError sentinel that flags
        operator-side wiring as the next step. Tests substitute this
        method with a deterministic mock returning the expected dict
        shape.

        Returns dict with keys:
          rows: list[dict]   per-row chain entries (provider-shape)
          partial: bool
          partial_reason: str | None
          underlying_price: float | None
          interest_rate: float | None
          dividend_yield: float | None
        """
        raise NotImplementedError(
            "ThetaData REST integration pending operator wiring "
            "(THETADATA_BASE_URL + auth). Tests substitute this method."
        )

    def _raw_health_check(self) -> None:
        """Lazy-import HTTP client + ping ThetaData /v2/system/health."""
        raise NotImplementedError(
            "ThetaData health check pending operator wiring."
        )

    # ------------------------------------------------------------------
    # Internal — normalization
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
                    option_symbol=str(r.get("option_symbol")
                                       or _occ(symbol, r)),
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
    """Construct OCC symbol from row fields if provider doesn't supply.
    Format: ROOT YYMMDD C/P STRIKE×1000 zero-padded to 8 digits."""
    expiry = _to_date(row["expiry"])
    strike = Decimal(str(row["strike"]))
    cp = "C" if str(row["option_type"]).upper() in ("C", "CALL") else "P"
    strike_milli = int(strike * 1000)
    return f"{symbol.upper()}{expiry.strftime('%y%m%d')}{cp}{strike_milli:08d}"
