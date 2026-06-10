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


# Frozen module constants (mirror docs/research/OPTIONS_STRATEGY_UNIVERSE.md locks).
# These remain the FAIL-CLOSED defaults — used when an unknown
# provider_version is encountered (e.g., a typo, a new adapter without
# a profile entry, or a None tag). They were calibrated for OPRA-direct
# real-time quotes (ThetaData) and intentionally too strict for
# delayed/sandbox feeds — fail-closed prevents silent regression.
MIN_OPEN_INTEREST = 500
MAX_BID_ASK_SPREAD_DOLLARS = Decimal("0.10")
MAX_QUOTE_AGE_SECONDS = 60


# ---------------------------------------------------------------------------
# Phase Opt-B3a — provider-aware liquidity profiles
# ---------------------------------------------------------------------------
#
# Different providers emit quotes with structurally different freshness,
# spread, and OI characteristics. Applying a single set of thresholds
# treats sandbox/delayed feeds the same as OPRA-direct, which is wrong
# in both directions: too loose for production, too strict for research.
#
# Profile keys MUST match the `provider_version` string an adapter
# stamps onto each `OptionChainQuote` (see thetadata_adapter.py,
# tradier_adapter.py, finnhub_adapter.py). Lookup is exact-match;
# unknown keys → strict defaults (fail-closed).
#
# IMPORTANT — separation of concerns:
#   These profiles govern RESEARCH-INGEST liquidity gates only.
#   Future paper-execution / live-execution quality gates are SEPARATE
#   modules (eval_runner, fills) and MUST NOT inherit from this map.
#   Loosening here for research observability does NOT loosen
#   execution. See docs/research/OPTIONS_STRATEGY_UNIVERSE.md §3.4.

@dataclass(frozen=True)
class LiquidityProfile:
    """Resolved threshold set for a single provider_version.

    `name` is for log provenance. `min_open_interest`,
    `max_spread_dollars`, `max_quote_age_seconds` are the gate values.
    """
    name: str
    min_open_interest: int
    max_spread_dollars: Decimal
    max_quote_age_seconds: int


# Strict default — also returned by resolve() when an unknown key is
# requested. Mirror of the frozen module constants above.
_PROFILE_STRICT_DEFAULT = LiquidityProfile(
    name="strict_default_fail_closed",
    min_open_interest=MIN_OPEN_INTEREST,
    max_spread_dollars=MAX_BID_ASK_SPREAD_DOLLARS,
    max_quote_age_seconds=MAX_QUOTE_AGE_SECONDS,
)


LIQUIDITY_PROFILES: dict[str, LiquidityProfile] = {
    # ThetaData OPRA-direct, real-time. Original locked v1 — UNCHANGED.
    "thetadata": LiquidityProfile(
        name="thetadata",
        min_open_interest=500,
        max_spread_dollars=Decimal("0.10"),
        max_quote_age_seconds=60,
    ),
    # Tradier sandbox: ~15-min delayed batch quotes; wider sandbox-
    # specific spreads on placeholder strikes. Calibrated against
    # actual sandbox data (see scripts/_audit_filter_calibration.py).
    "tradier-sandbox": LiquidityProfile(
        name="tradier-sandbox",
        min_open_interest=100,
        max_spread_dollars=Decimal("0.50"),
        max_quote_age_seconds=1800,
    ),
    # Tradier production (future activation path): live consolidated
    # quotes from MBBO, tighter than sandbox but looser than OPRA-direct.
    "tradier-prod": LiquidityProfile(
        name="tradier-prod",
        min_open_interest=250,
        max_spread_dollars=Decimal("0.25"),
        max_quote_age_seconds=300,
    ),
    # Finnhub free tier: /stock/option-chain returns 403 (paid only),
    # so this profile is reserved for the future paid-tier path. EOD-
    # fresh by design; large age cap.
    "finnhub-free-tier": LiquidityProfile(
        name="finnhub-free-tier",
        min_open_interest=100,
        max_spread_dollars=Decimal("0.50"),
        max_quote_age_seconds=86400,
    ),
}


def resolve_profile(provider_version: str | None) -> LiquidityProfile:
    """Return the LiquidityProfile matching ``provider_version``.

    FAIL-CLOSED: any key not present in LIQUIDITY_PROFILES (including
    None, empty string, typos, brand-new untagged adapters) returns
    the strict default profile. This guarantees that a forgotten
    profile registration cannot silently widen ingest thresholds.
    """
    if not provider_version:
        return _PROFILE_STRICT_DEFAULT
    return LIQUIDITY_PROFILES.get(provider_version, _PROFILE_STRICT_DEFAULT)


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
    # P6D.34A — prefer the true current age (set on DB-rehydrated quotes by
    # canary.selection.latest_chain_quotes) over the stored-at-ingest age,
    # which is ~0 forever and hides hours of staleness. Fresh adapter pulls
    # leave effective_age_seconds=None → stored age applies (unchanged).
    age = (
        quote.effective_age_seconds
        if getattr(quote, "effective_age_seconds", None) is not None
        else quote.quote_age_seconds
    )
    if age > max_quote_age_seconds:
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
