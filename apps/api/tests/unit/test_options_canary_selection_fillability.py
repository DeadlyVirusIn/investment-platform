"""P6D.12 — selector fillability gate parity with the paper engine.

The canary selector (`_load_promotable_requests`) now rejects any candidate
whose legs would fail the engine's `compute_fill` liquidity gate
(OI >= MIN_OPEN_INTEREST=500, spread <= $0.10, quote age <= 60s, valid
bid/ask). These cases lock the per-leg gate behaviour the selector relies on
— the same path the paper engine enforces at open, so selector-promotable ==
engine-fillable. No thresholds are duplicated here; they come from
options.data.liquidity_filter.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from apps.api.src.options.data_provider.base_adapter import OptionChainQuote
from apps.api.src.options.paper.fills import compute_fill

EXPIRY = dt.date(2026, 7, 17)
NOW = dt.datetime(2026, 6, 5, 14, 15, tzinfo=dt.timezone.utc)


def _q(bid: str, ask: str, oi: int, age: int = 2) -> OptionChainQuote:
    b, a = Decimal(bid), Decimal(ask)
    return OptionChainQuote(
        snapshot_at_utc=NOW, underlying="QQQ", expiry=EXPIRY,
        strike=Decimal("700"), option_type="PUT", option_symbol="QQQ_TEST",
        bid=b, ask=a, mid=(b + a) / 2, last=b, volume=100,
        open_interest=oi, delta=Decimal("-0.30"), gamma=Decimal("0.02"),
        theta=Decimal("-0.05"), vega=Decimal("0.10"), iv=Decimal("0.20"),
        quote_age_seconds=age, provider="tradier",
    )


def test_thin_open_interest_excluded():
    # Mirrors the P6D.10 failure: long leg OI 301 < MIN_OPEN_INTEREST(500).
    assert compute_fill(_q("11.61", "11.68", 301), side="BUY").accepted is False


def test_liquid_legs_included():
    # Both an OTM long (BUY) and the short (SELL) clear the gate.
    assert compute_fill(_q("11.61", "11.68", 1000), side="BUY").accepted is True
    assert compute_fill(_q("11.86", "11.94", 40497), side="SELL").accepted is True


def test_stale_quote_excluded():
    # quote_age_seconds 120 > MAX_QUOTE_AGE_SECONDS(60).
    assert compute_fill(_q("11.61", "11.68", 1000, age=120), side="BUY").accepted is False


def test_wide_spread_excluded():
    # spread 0.20 > MAX_BID_ASK_SPREAD_DOLLARS($0.10).
    assert compute_fill(_q("11.50", "11.70", 1000), side="BUY").accepted is False
