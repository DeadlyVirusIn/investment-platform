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
from apps.api.src.options.paper.fills import compute_entry_fill, compute_fill

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


# ---------------------------------------------------------------------------
# P6D.37C — role-aware wing OI threshold (compute_entry_fill).
# SELL (risk) legs ALWAYS keep MIN_OPEN_INTEREST=500; BUY (hedge wing)
# legs use wing_min_oi. Inert default (500) == compute_fill exactly.
# ---------------------------------------------------------------------------

def test_entry_fill_inert_default_matches_strict_gate():
    # Default wing_min_oi=500 reproduces the current rejection: the
    # P6D.10 wing shape (BUY, OI 300) still rejects.
    r = compute_entry_fill(_q("11.61", "11.68", 300), side="BUY")
    assert r.accepted is False and r.reason == "LOW_OPEN_INTEREST"
    # And accepts exactly what compute_fill accepts.
    a = compute_entry_fill(_q("11.61", "11.68", 1000), side="BUY")
    b = compute_fill(_q("11.61", "11.68", 1000), side="BUY")
    assert a.accepted and a.fill_price == b.fill_price


def test_wing_oi_300_passes_at_wing_min_oi_100():
    r = compute_entry_fill(_q("11.61", "11.68", 300), side="BUY",
                           wing_min_oi=100)
    assert r.accepted is True


def test_wing_oi_boundary_100_passes_99_rejects():
    assert compute_entry_fill(
        _q("11.61", "11.68", 100), side="BUY", wing_min_oi=100,
    ).accepted is True
    r = compute_entry_fill(_q("11.61", "11.68", 99), side="BUY",
                           wing_min_oi=100)
    assert r.accepted is False and r.reason == "LOW_OPEN_INTEREST"


def test_short_leg_oi_499_still_rejects_regardless_of_wing_setting():
    # SELL leg ignores wing_min_oi entirely — strict 500 floor holds.
    r = compute_entry_fill(_q("11.86", "11.94", 499), side="SELL",
                           wing_min_oi=100)
    assert r.accepted is False and r.reason == "LOW_OPEN_INTEREST"
    assert compute_entry_fill(
        _q("11.86", "11.94", 500), side="SELL", wing_min_oi=100,
    ).accepted is True


def test_wing_setting_does_not_loosen_other_gates():
    # Wide spread + stale age still reject a BUY wing at wing_min_oi=100.
    assert compute_entry_fill(
        _q("11.50", "11.70", 5000), side="BUY", wing_min_oi=100,
    ).accepted is False
    assert compute_entry_fill(
        _q("11.61", "11.68", 5000, age=120), side="BUY", wing_min_oi=100,
    ).accepted is False
