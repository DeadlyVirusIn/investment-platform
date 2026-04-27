"""Conservative fill price logic for the paper-trading engine (Phase 11E).

Rules (frozen for v1):
  * BUY  (open or close)  → fill_price = mid + slippage_per_contract
  * SELL (open or close)  → fill_price = mid − slippage_per_contract
  * NEVER use last price as a fill source.
  * If mid is None (missing bid/ask), the fill is rejected.
  * Reject if quote fails liquidity gate (OI, spread, age).

Pure functions; stdlib + Decimal only. No DB. No I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

from apps.api.src.options.data.liquidity_filter import (
    MAX_BID_ASK_SPREAD_DOLLARS,
    MAX_QUOTE_AGE_SECONDS,
    MIN_OPEN_INTEREST,
    REJECT_LOW_OPEN_INTEREST,
    REJECT_MISSING_BID_OR_ASK,
    REJECT_STALE_QUOTE,
    REJECT_WIDE_SPREAD,
    evaluate_quote,
)
from apps.api.src.options.data_provider.base_adapter import OptionChainQuote


# Frozen module constants (v1 fill model)
FILL_MODEL_VERSION = "v1.conservative"

# Fill slippage per contract (single-side) is min(half-spread, cap).
# Cap protects against degenerate widths slipping through filter.
DEFAULT_SLIPPAGE_CAP_DOLLARS = Decimal("0.05")

# Per-contract commission charged at OPEN and again at CLOSE.
DEFAULT_COMMISSION_PER_CONTRACT = Decimal("0.65")
DEFAULT_EXCHANGE_FEE_PER_CONTRACT = Decimal("0.05")
DEFAULT_FEE_PER_CONTRACT = (
    DEFAULT_COMMISSION_PER_CONTRACT + DEFAULT_EXCHANGE_FEE_PER_CONTRACT
)


@dataclass(frozen=True)
class FillResult:
    accepted: bool
    fill_price: Decimal | None       # per-contract dollars (positive)
    slippage_per_contract: Decimal   # signed: positive added on BUY, subtracted on SELL
    reason: str | None               # populated when accepted=False
    quote_age_seconds: int | None    # for audit


REJECT_NO_MID = "FILL_NO_MID"


def slippage_per_contract(
    quote: OptionChainQuote,
    *,
    cap: Decimal = DEFAULT_SLIPPAGE_CAP_DOLLARS,
) -> Decimal:
    """Half the bid-ask spread, clipped to cap. Per single contract."""
    if quote.bid is None or quote.ask is None:
        return Decimal("0")
    half = (quote.ask - quote.bid) / Decimal("2")
    if half < 0:
        half = Decimal("0")
    return half if half <= cap else cap


def compute_fill(
    quote: OptionChainQuote,
    *,
    side: str,
    slippage_cap: Decimal = DEFAULT_SLIPPAGE_CAP_DOLLARS,
    enforce_liquidity: bool = True,
    min_open_interest: int = MIN_OPEN_INTEREST,
    max_spread: Decimal = MAX_BID_ASK_SPREAD_DOLLARS,
    max_quote_age_seconds: int = MAX_QUOTE_AGE_SECONDS,
) -> FillResult:
    """Compute conservative fill price for one contract.

    side: "BUY" pays mid + slip; "SELL" receives mid − slip.
    """
    if side not in ("BUY", "SELL"):
        raise ValueError(f"side must be BUY or SELL, got {side!r}")

    if enforce_liquidity:
        liq_reason = evaluate_quote(
            quote,
            min_open_interest=min_open_interest,
            max_spread_dollars=max_spread,
            max_quote_age_seconds=max_quote_age_seconds,
        )
        if liq_reason is not None:
            return FillResult(
                accepted=False, fill_price=None,
                slippage_per_contract=Decimal("0"),
                reason=liq_reason,
                quote_age_seconds=quote.quote_age_seconds,
            )

    if quote.mid is None or quote.bid is None or quote.ask is None:
        return FillResult(
            accepted=False, fill_price=None,
            slippage_per_contract=Decimal("0"),
            reason=REJECT_NO_MID,
            quote_age_seconds=quote.quote_age_seconds,
        )

    slip = slippage_per_contract(quote, cap=slippage_cap)
    if side == "BUY":
        price = quote.mid + slip
    else:
        price = quote.mid - slip
        # SELL fill must remain ≥ bid (cannot get worse than the bid)
        if price < quote.bid:
            price = quote.bid
    if price < 0:
        price = Decimal("0")
    return FillResult(
        accepted=True,
        fill_price=price,
        slippage_per_contract=slip,
        reason=None,
        quote_age_seconds=quote.quote_age_seconds,
    )


def fees_for(
    qty: int,
    *,
    fee_per_contract: Decimal = DEFAULT_FEE_PER_CONTRACT,
) -> Decimal:
    """Total fees in dollars for a single fill (open OR close) of qty contracts.
    The engine charges fees at both the open AND the close.
    """
    return Decimal(qty) * fee_per_contract


def total_fees_for_legs(
    legs_qty: Sequence[int],
    *,
    fee_per_contract: Decimal = DEFAULT_FEE_PER_CONTRACT,
) -> Decimal:
    """Round-trip (open + close) total fees across all legs."""
    return Decimal(2) * sum(
        (Decimal(q) * fee_per_contract for q in legs_qty),
        start=Decimal("0"),
    )
