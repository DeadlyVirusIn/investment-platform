"""Liquidity filter for options chain quotes (Phase 11C).

Pure functions. NEVER imports V2 / equity / strategy / execution code.
NEVER writes to DB.

Filter rules (locked v1, frozen module constants):
  * open_interest >= MIN_OPEN_INTEREST (500)
  * (ask − bid) <= MAX_BID_ASK_SPREAD_DOLLARS ($0.10)
  * bid > 0
  * ask > bid
  * Optional: require IV present
  * Optional: require all 4 Greeks present
  * quote_age_seconds <= MAX_QUOTE_AGE_SECONDS (60)
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from apps.api.src.options.data_provider.base_adapter import OptionChainQuote


# Frozen module constants (mirror docs/research/OPTIONS_STRATEGY_UNIVERSE.md locks)
MIN_OPEN_INTEREST = 500
MAX_BID_ASK_SPREAD_DOLLARS = Decimal("0.10")
MAX_QUOTE_AGE_SECONDS = 60


# Reasons surfaced when a quote is rejected (kept frozen for downstream
# pattern-matching in monitoring / red-flag logic later)
REJECT_LOW_OPEN_INTEREST = "LOW_OPEN_INTEREST"
REJECT_WIDE_SPREAD = "WIDE_SPREAD"
REJECT_BID_NONPOSITIVE = "BID_NONPOSITIVE"
REJECT_ASK_NOT_GREATER_BID = "ASK_NOT_GREATER_BID"
REJECT_MISSING_IV = "MISSING_IV"
REJECT_MISSING_GREEKS = "MISSING_GREEKS"
REJECT_STALE_QUOTE = "STALE_QUOTE"
REJECT_MISSING_BID_OR_ASK = "MISSING_BID_OR_ASK"


@dataclass(frozen=True)
class FilterResult:
    accepted: tuple[OptionChainQuote, ...]
    rejected: tuple[tuple[OptionChainQuote, str], ...]   # (quote, reason)
    n_input: int
    n_accepted: int
    n_rejected: int
    reject_counts: dict[str, int]


def evaluate_quote(
    quote: OptionChainQuote,
    *,
    require_iv: bool = False,
    require_greeks: bool = False,
    min_open_interest: int = MIN_OPEN_INTEREST,
    max_spread_dollars: Decimal = MAX_BID_ASK_SPREAD_DOLLARS,
    max_quote_age_seconds: int = MAX_QUOTE_AGE_SECONDS,
) -> str | None:
    """Return None if quote passes; else the reject-reason code."""
    if quote.bid is None or quote.ask is None:
        return REJECT_MISSING_BID_OR_ASK
    if quote.bid <= 0:
        return REJECT_BID_NONPOSITIVE
    if quote.ask <= quote.bid:
        return REJECT_ASK_NOT_GREATER_BID
    if (quote.ask - quote.bid) > max_spread_dollars:
        return REJECT_WIDE_SPREAD
    if (quote.open_interest or 0) < min_open_interest:
        return REJECT_LOW_OPEN_INTEREST
    if quote.quote_age_seconds > max_quote_age_seconds:
        return REJECT_STALE_QUOTE
    if require_iv and quote.iv is None:
        return REJECT_MISSING_IV
    if require_greeks and any(
        g is None for g in (quote.delta, quote.gamma, quote.theta, quote.vega)
    ):
        return REJECT_MISSING_GREEKS
    return None


def filter_chain(
    quotes: Iterable[OptionChainQuote],
    *,
    require_iv: bool = False,
    require_greeks: bool = False,
    min_open_interest: int = MIN_OPEN_INTEREST,
    max_spread_dollars: Decimal = MAX_BID_ASK_SPREAD_DOLLARS,
    max_quote_age_seconds: int = MAX_QUOTE_AGE_SECONDS,
) -> FilterResult:
    """Apply liquidity filter to a chain of quotes. Pure; deterministic."""
    accepted: list[OptionChainQuote] = []
    rejected: list[tuple[OptionChainQuote, str]] = []
    counts: dict[str, int] = {}
    n_input = 0
    for q in quotes:
        n_input += 1
        reason = evaluate_quote(
            q,
            require_iv=require_iv,
            require_greeks=require_greeks,
            min_open_interest=min_open_interest,
            max_spread_dollars=max_spread_dollars,
            max_quote_age_seconds=max_quote_age_seconds,
        )
        if reason is None:
            accepted.append(q)
        else:
            rejected.append((q, reason))
            counts[reason] = counts.get(reason, 0) + 1
    return FilterResult(
        accepted=tuple(accepted),
        rejected=tuple(rejected),
        n_input=n_input,
        n_accepted=len(accepted),
        n_rejected=len(rejected),
        reject_counts=counts,
    )
