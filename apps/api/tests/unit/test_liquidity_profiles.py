"""Phase Opt-B3a — provider-aware LIQUIDITY_PROFILES tests.

Mandatory gating tests per Section-5 approval matrix:
  * provider profile resolution
  * unknown-provider fallback (FAIL-CLOSED to strict)
  * tradier-sandbox acceptance of representative quotes
  * thetadata strict behavior preserved
  * provider_version mismatch handling (None / empty / typo)
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from apps.api.src.options.data.liquidity_filter import (
    LIQUIDITY_PROFILES,
    MAX_BID_ASK_SPREAD_DOLLARS,
    MAX_QUOTE_AGE_SECONDS,
    MIN_OPEN_INTEREST,
    LiquidityProfile,
    evaluate_quote,
    resolve_profile,
)
from apps.api.src.options.data_provider.base_adapter import OptionChainQuote


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _quote(
    *,
    bid="1.00", ask="1.10", oi=200, age_s=1500,
    provider_version="tradier-sandbox",
) -> OptionChainQuote:
    """Build a representative chain quote for filter testing."""
    return OptionChainQuote(
        snapshot_at_utc=dt.datetime(2026, 5, 13, tzinfo=dt.timezone.utc),
        underlying="SPY",
        expiry=dt.date(2026, 6, 19),
        strike=Decimal("500"),
        option_type="CALL",
        option_symbol="SPY260619C00500000",
        bid=Decimal(bid) if bid is not None else None,
        ask=Decimal(ask) if ask is not None else None,
        mid=None,
        last=None,
        volume=10,
        open_interest=oi,
        delta=Decimal("0.4"), gamma=Decimal("0.02"),
        theta=Decimal("-0.03"), vega=Decimal("0.10"),
        iv=Decimal("0.21"),
        quote_age_seconds=age_s,
        provider="tradier",
        provider_version=provider_version,
    )


# ---------------------------------------------------------------------------
# 1. Provider profile resolution
# ---------------------------------------------------------------------------

def test_thetadata_profile_resolves():
    p = resolve_profile("thetadata")
    assert p.name == "thetadata"
    assert p.min_open_interest == 500
    assert p.max_spread_dollars == Decimal("0.10")
    assert p.max_quote_age_seconds == 60


def test_tradier_sandbox_profile_resolves():
    p = resolve_profile("tradier-sandbox")
    assert p.name == "tradier-sandbox"
    assert p.min_open_interest == 100
    assert p.max_spread_dollars == Decimal("0.50")
    assert p.max_quote_age_seconds == 1800


def test_tradier_prod_profile_resolves():
    p = resolve_profile("tradier-prod")
    assert p.name == "tradier-prod"
    assert p.min_open_interest == 250
    assert p.max_spread_dollars == Decimal("0.25")
    assert p.max_quote_age_seconds == 300


def test_finnhub_free_tier_profile_resolves():
    p = resolve_profile("finnhub-free-tier")
    assert p.name == "finnhub-free-tier"
    assert p.min_open_interest == 100
    assert p.max_spread_dollars == Decimal("0.50")
    assert p.max_quote_age_seconds == 86400


def test_all_four_known_profiles_present():
    expected = {"thetadata", "tradier-sandbox", "tradier-prod",
                "finnhub-free-tier"}
    assert set(LIQUIDITY_PROFILES.keys()) == expected
    for k, v in LIQUIDITY_PROFILES.items():
        assert isinstance(v, LiquidityProfile)
        assert v.name == k


# ---------------------------------------------------------------------------
# 2. Unknown-provider FAIL-CLOSED fallback
# ---------------------------------------------------------------------------

def test_unknown_provider_returns_strict_default():
    p = resolve_profile("polygon-pro-tier-2027")     # not registered
    assert p.name == "strict_default_fail_closed"
    assert p.min_open_interest == MIN_OPEN_INTEREST          # 500
    assert p.max_spread_dollars == MAX_BID_ASK_SPREAD_DOLLARS  # 0.10
    assert p.max_quote_age_seconds == MAX_QUOTE_AGE_SECONDS  # 60


def test_none_provider_returns_strict_default():
    p = resolve_profile(None)
    assert p.name == "strict_default_fail_closed"
    assert p.min_open_interest == MIN_OPEN_INTEREST


def test_empty_string_provider_returns_strict_default():
    p = resolve_profile("")
    assert p.name == "strict_default_fail_closed"
    assert p.max_quote_age_seconds == MAX_QUOTE_AGE_SECONDS


def test_typo_returns_strict_default():
    """A common-typo case must FAIL CLOSED to strict, not silently pass."""
    p = resolve_profile("tradier_sandbox")           # underscore typo
    assert p.name == "strict_default_fail_closed"
    p2 = resolve_profile("tradier-Sandbox")          # case typo
    assert p2.name == "strict_default_fail_closed"


# ---------------------------------------------------------------------------
# 3. Tradier-sandbox profile acceptance behavior
# ---------------------------------------------------------------------------

def test_tradier_sandbox_accepts_typical_research_quote():
    """A quote with 200 OI, $0.10 spread, 1500s age — typical sandbox
    research-quality contract — must be accepted under tradier-sandbox
    profile and rejected under thetadata strict."""
    q = _quote(bid="1.00", ask="1.10", oi=200, age_s=1500)
    p = resolve_profile("tradier-sandbox")

    accepted_reason = evaluate_quote(
        q,
        min_open_interest=p.min_open_interest,
        max_spread_dollars=p.max_spread_dollars,
        max_quote_age_seconds=p.max_quote_age_seconds,
    )
    assert accepted_reason is None, f"sandbox should accept: {accepted_reason}"

    strict = resolve_profile("thetadata")
    rejected_reason = evaluate_quote(
        q,
        min_open_interest=strict.min_open_interest,
        max_spread_dollars=strict.max_spread_dollars,
        max_quote_age_seconds=strict.max_quote_age_seconds,
    )
    assert rejected_reason in ("LOW_OPEN_INTEREST", "STALE_QUOTE"), (
        f"thetadata should reject (OI=200<500 OR age=1500s>60s); got: {rejected_reason}")


def test_tradier_sandbox_still_rejects_zero_bid():
    """Loose profile must NOT bypass inherent gates (bid > 0)."""
    q = _quote(bid="0.00", ask="0.05", oi=500, age_s=900)
    p = resolve_profile("tradier-sandbox")
    reason = evaluate_quote(
        q,
        min_open_interest=p.min_open_interest,
        max_spread_dollars=p.max_spread_dollars,
        max_quote_age_seconds=p.max_quote_age_seconds,
    )
    assert reason == "BID_NONPOSITIVE"


def test_tradier_sandbox_still_rejects_wide_spread_above_cap():
    q = _quote(bid="1.00", ask="2.00", oi=500, age_s=900)   # $1 spread > $0.50 cap
    p = resolve_profile("tradier-sandbox")
    reason = evaluate_quote(
        q,
        min_open_interest=p.min_open_interest,
        max_spread_dollars=p.max_spread_dollars,
        max_quote_age_seconds=p.max_quote_age_seconds,
    )
    assert reason == "WIDE_SPREAD"


def test_tradier_sandbox_still_rejects_stale_above_cap():
    q = _quote(bid="1.00", ask="1.10", oi=500, age_s=2000)  # 2000s > 1800s
    p = resolve_profile("tradier-sandbox")
    reason = evaluate_quote(
        q,
        min_open_interest=p.min_open_interest,
        max_spread_dollars=p.max_spread_dollars,
        max_quote_age_seconds=p.max_quote_age_seconds,
    )
    assert reason == "STALE_QUOTE"


# ---------------------------------------------------------------------------
# 4. Thetadata strict behavior preserved
# ---------------------------------------------------------------------------

def test_thetadata_accepts_real_time_tight_spread_high_oi():
    """The exact 'good' quote shape that locked-v1 was tuned for
    must still pass under thetadata profile."""
    q = _quote(bid="1.00", ask="1.05", oi=600, age_s=30,
               provider_version="thetadata")
    p = resolve_profile("thetadata")
    reason = evaluate_quote(
        q,
        min_open_interest=p.min_open_interest,
        max_spread_dollars=p.max_spread_dollars,
        max_quote_age_seconds=p.max_quote_age_seconds,
    )
    assert reason is None


def test_thetadata_rejects_at_boundary_oi_499():
    q = _quote(bid="1.00", ask="1.05", oi=499, age_s=30,
               provider_version="thetadata")
    p = resolve_profile("thetadata")
    assert evaluate_quote(
        q,
        min_open_interest=p.min_open_interest,
        max_spread_dollars=p.max_spread_dollars,
        max_quote_age_seconds=p.max_quote_age_seconds,
    ) == "LOW_OPEN_INTEREST"


def test_thetadata_rejects_at_boundary_age_61():
    q = _quote(bid="1.00", ask="1.05", oi=500, age_s=61,
               provider_version="thetadata")
    p = resolve_profile("thetadata")
    assert evaluate_quote(
        q,
        min_open_interest=p.min_open_interest,
        max_spread_dollars=p.max_spread_dollars,
        max_quote_age_seconds=p.max_quote_age_seconds,
    ) == "STALE_QUOTE"


def test_thetadata_rejects_spread_over_dollar_10():
    q = _quote(bid="1.00", ask="1.11", oi=500, age_s=30,
               provider_version="thetadata")
    p = resolve_profile("thetadata")
    assert evaluate_quote(
        q,
        min_open_interest=p.min_open_interest,
        max_spread_dollars=p.max_spread_dollars,
        max_quote_age_seconds=p.max_quote_age_seconds,
    ) == "WIDE_SPREAD"


# ---------------------------------------------------------------------------
# 5. Provider_version mismatch handling — fail-closed boundary tests
# ---------------------------------------------------------------------------

def test_strict_default_constants_unchanged():
    """Module constants (used as fail-closed defaults) must still match
    the original locked v1 values."""
    assert MIN_OPEN_INTEREST == 500
    assert MAX_BID_ASK_SPREAD_DOLLARS == Decimal("0.10")
    assert MAX_QUOTE_AGE_SECONDS == 60


def test_unknown_provider_with_loose_quote_is_rejected():
    """A quote that would pass under tradier-sandbox MUST be rejected
    when provider_version is unknown — proves fail-closed."""
    q = _quote(bid="1.00", ask="1.30", oi=200, age_s=1000,
               provider_version="brand-new-untagged-adapter")
    p = resolve_profile(q.provider_version)        # → strict default
    reason = evaluate_quote(
        q,
        min_open_interest=p.min_open_interest,
        max_spread_dollars=p.max_spread_dollars,
        max_quote_age_seconds=p.max_quote_age_seconds,
    )
    # Any of: LOW_OI (200<500), WIDE_SPREAD ($0.30>$0.10), STALE (1000s>60s)
    assert reason in ("LOW_OPEN_INTEREST", "WIDE_SPREAD", "STALE_QUOTE")


def test_resolve_profile_idempotent_returns_same_dataclass():
    """Multiple calls with same key return equivalent profiles."""
    p1 = resolve_profile("tradier-sandbox")
    p2 = resolve_profile("tradier-sandbox")
    assert p1 == p2
    # Also frozen dataclass equality
    assert p1.name == p2.name
    assert p1.min_open_interest == p2.min_open_interest
