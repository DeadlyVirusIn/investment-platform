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


def compute_entry_fill(
    quote: OptionChainQuote,
    *,
    side: str,
    wing_min_oi: int = MIN_OPEN_INTEREST,
    slippage_cap: Decimal = DEFAULT_SLIPPAGE_CAP_DOLLARS,
) -> FillResult:
    """Conservative fill for OPENING a leg, with a role-aware OI floor.

    P6D.37C — at entry the OI gate is role-aware: SELL (risk) legs
    always keep the strict MIN_OPEN_INTEREST (500); BUY legs use
    `wing_min_oi`. side==BUY is exactly the protective hedge wing for
    every strategy the engine admits (DEFINED_RISK_STRATEGIES are all
    credit structures — SPCS/SCCS/IC), so no separate role field is
    needed. The DEFAULT is INERT (wing_min_oi == MIN_OPEN_INTEREST →
    byte-identical to compute_fill). Both the canary selector and the
    engine open path MUST call this same helper — that is what keeps
    selector-promotable == engine-fillable (P6D.12 parity) under the
    role-aware threshold. All other gates (spread, age, bid/ask
    sanity) and the fill-price math are compute_fill's, unchanged.
    """
    min_oi = wing_min_oi if side == "BUY" else MIN_OPEN_INTEREST
    return compute_fill(
        quote,
        side=side,
        slippage_cap=slippage_cap,
        enforce_liquidity=True,
        min_open_interest=min_oi,
    )


def exit_max_spread_dollars(
    quote: OptionChainQuote,
    *,
    max_spread_pct: Decimal,
    max_spread_floor: Decimal,
) -> Decimal:
    """Effective EXIT spread cap: max(floor, pct × mid).

    P6D.37B — the entry gate's absolute $0.10 cap cannot scale with
    option price (a $0.12 spread on a $12 mid is the same ~1% relative
    width the trade was opened at), so exits use a relative cap with an
    absolute floor. pct <= 0 → floor only (inert). mid falls back to
    (bid+ask)/2 when the quote's mid is missing; with no usable mid the
    floor applies (compute_fill rejects NO_MID downstream anyway).
    """
    mid = quote.mid
    if mid is None and quote.bid is not None and quote.ask is not None:
        mid = (quote.bid + quote.ask) / Decimal("2")
    if max_spread_pct <= 0 or mid is None or mid <= 0:
        return max_spread_floor
    rel = mid * max_spread_pct
    return rel if rel > max_spread_floor else max_spread_floor


def compute_exit_fill(
    quote: OptionChainQuote,
    *,
    side: str,
    slippage_cap: Decimal = DEFAULT_SLIPPAGE_CAP_DOLLARS,
    min_open_interest: int = MIN_OPEN_INTEREST,
    max_spread_pct: Decimal = Decimal("0"),
    max_spread_floor: Decimal = MAX_BID_ASK_SPREAD_DOLLARS,
    max_quote_age_seconds: int = MAX_QUOTE_AGE_SECONDS,
) -> FillResult:
    """Conservative fill for CLOSING a leg, under the EXIT profile.

    P6D.37B — exits keep every SANITY gate (bid/ask present, bid > 0,
    ask > bid, quote age, NO_MID) but parameterize the OPPORTUNITY
    gates: `min_open_interest` (0 disables — a held position's close
    is not an entry decision) and a relative spread cap
    max(max_spread_floor, max_spread_pct × mid) instead of the entry
    gate's absolute cap. The DEFAULTS are INERT — identical to
    compute_fill's entry gate (OI>=500, $0.10 absolute, age<=60s) —
    so behavior only changes when the caller passes the exit settings.
    Fill-price math (mid ± min(half-spread, cap), SELL floored at bid)
    is compute_fill's, unchanged.
    """
    return compute_fill(
        quote,
        side=side,
        slippage_cap=slippage_cap,
        enforce_liquidity=True,
        min_open_interest=min_open_interest,
        max_spread=exit_max_spread_dollars(
            quote, max_spread_pct=max_spread_pct,
            max_spread_floor=max_spread_floor,
        ),
        max_quote_age_seconds=max_quote_age_seconds,
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
