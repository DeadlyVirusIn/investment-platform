"""P6D.37B — exit-specific fillability profile (compute_exit_fill).

Exits keep every SANITY gate (bid/ask present, bid>0, ask>bid, age,
NO_MID) and parameterize the OPPORTUNITY gates: min OI (0 disables) and
a relative spread cap max(floor, pct × mid) replacing the entry gate's
absolute cap. DEFAULTS ARE INERT — byte-identical to compute_fill's
entry gate — locked here by parity cases. The quote shapes mirror the
live trade-3 blocker (06-10: spread $0.11/$0.12 on ~$12.3–12.6 mids,
~0.9–1.0% relative width) so the production failure mode stays pinned.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from apps.api.src.options.data_provider.base_adapter import OptionChainQuote
from apps.api.src.options.paper.fills import (
    compute_exit_fill,
    compute_fill,
    exit_max_spread_dollars,
)

EXPIRY = dt.date(2026, 7, 17)
NOW = dt.datetime(2026, 6, 11, 14, 15, tzinfo=dt.timezone.utc)

# Rollout values (what env flips to) — NOT the inert defaults.
EXIT_PCT = Decimal("0.015")
EXIT_FLOOR = Decimal("0.10")


def _q(bid: str | None, ask: str | None, oi: int, age: int = 2,
       mid: str | None = "auto") -> OptionChainQuote:
    b = None if bid is None else Decimal(bid)
    a = None if ask is None else Decimal(ask)
    if mid == "auto":
        m = (b + a) / 2 if (b is not None and a is not None) else None
    else:
        m = None if mid is None else Decimal(mid)
    return OptionChainQuote(
        snapshot_at_utc=NOW, underlying="QQQ", expiry=EXPIRY,
        strike=Decimal("675"), option_type="PUT", option_symbol="QQQ_TEST",
        bid=b, ask=a, mid=m, last=b, volume=100,
        open_interest=oi, delta=Decimal("-0.30"), gamma=Decimal("0.02"),
        theta=Decimal("-0.05"), vega=Decimal("0.10"), iv=Decimal("0.20"),
        quote_age_seconds=age, provider="thetadata",
    )


# ---------------------------------------------------------------------------
# INERT DEFAULTS — compute_exit_fill() with no overrides == compute_fill()
# ---------------------------------------------------------------------------

def test_inert_defaults_match_entry_gate_accept():
    q = _q("9.69", "9.78", 26528)          # trade 3 short leg at entry
    entry, exit_ = compute_fill(q, side="BUY"), compute_exit_fill(q, side="BUY")
    assert entry.accepted and exit_.accepted
    assert entry.fill_price == exit_.fill_price
    assert entry.slippage_per_contract == exit_.slippage_per_contract


def test_inert_defaults_match_entry_gate_wide_spread_reject():
    # Trade-3 live blocker shape: spread $0.11 > $0.10 absolute cap.
    q = _q("12.52", "12.63", 26996)
    assert compute_fill(q, side="BUY").accepted is False
    r = compute_exit_fill(q, side="BUY")
    assert r.accepted is False and r.reason == "WIDE_SPREAD"


def test_inert_defaults_match_entry_gate_low_oi_reject():
    q = _q("11.61", "11.68", 301)
    assert compute_fill(q, side="BUY").accepted is False
    r = compute_exit_fill(q, side="BUY")
    assert r.accepted is False and r.reason == "LOW_OPEN_INTEREST"


# ---------------------------------------------------------------------------
# RELATIVE SPREAD CAP — max(floor, pct × mid)
# ---------------------------------------------------------------------------

def test_exit_cap_formula():
    # mid 12.575 × 0.015 = 0.188625 > floor → relative term wins.
    q = _q("12.52", "12.63", 26996)
    assert exit_max_spread_dollars(
        q, max_spread_pct=EXIT_PCT, max_spread_floor=EXIT_FLOOR,
    ) == Decimal("12.575") * EXIT_PCT
    # Cheap option: mid 0.50 × 0.015 = 0.0075 < floor → floor wins.
    cheap = _q("0.45", "0.55", 1000)
    assert exit_max_spread_dollars(
        cheap, max_spread_pct=EXIT_PCT, max_spread_floor=EXIT_FLOOR,
    ) == EXIT_FLOOR
    # pct=0 → floor regardless of mid (inert).
    assert exit_max_spread_dollars(
        q, max_spread_pct=Decimal("0"), max_spread_floor=EXIT_FLOOR,
    ) == EXIT_FLOOR


def test_trade3_wide_spread_unblocked_by_exit_profile():
    # BOTH live trade-3 legs on the 06-10 snapshot.
    short = _q("12.52", "12.63", 26996)   # spread 0.11, BUY to close
    wing = _q("12.27", "12.39", 1276)     # spread 0.12, SELL to close
    for q, side in ((short, "BUY"), (wing, "SELL")):
        r = compute_exit_fill(q, side=side, max_spread_pct=EXIT_PCT,
                              max_spread_floor=EXIT_FLOOR)
        assert r.accepted, r.reason
        # Slippage stays capped at $0.05 even on the wider spread.
        assert r.slippage_per_contract == Decimal("0.05")
    # SELL fill floored at bid (conservative model unchanged).
    r = compute_exit_fill(wing, side="SELL", max_spread_pct=EXIT_PCT,
                          max_spread_floor=EXIT_FLOOR)
    assert r.fill_price >= wing.bid


def test_spread_exactly_at_relative_cap_passes():
    # Round numbers: mid 20.00 → cap = 20.00 × 0.015 = 0.30; spread 0.30.
    q = _q("19.85", "20.15", 5000)
    assert (q.ask - q.bid) == Decimal("0.30")
    r = compute_exit_fill(q, side="BUY", max_spread_pct=EXIT_PCT,
                          max_spread_floor=EXIT_FLOOR)
    assert r.accepted  # boundary == passes (gate is strict >)


def test_spread_above_relative_cap_still_rejects():
    # mid ~2.00 → cap = max(0.10, 0.03) = 0.10; spread 0.20 rejects.
    q = _q("1.90", "2.10", 5000)
    r = compute_exit_fill(q, side="BUY", max_spread_pct=EXIT_PCT,
                          max_spread_floor=EXIT_FLOOR)
    assert r.accepted is False and r.reason == "WIDE_SPREAD"


# ---------------------------------------------------------------------------
# OI IGNORED ON EXITS (min_open_interest=0) — entry unchanged
# ---------------------------------------------------------------------------

def test_oi_ignored_on_exit_when_disabled():
    q = _q("11.61", "11.68", 10)   # OI 10 — far below entry's 500
    r = compute_exit_fill(q, side="SELL", min_open_interest=0)
    assert r.accepted
    # Same quote still rejected at ENTRY (parity untouched).
    assert compute_fill(q, side="SELL").accepted is False


def test_oi_zero_passes_exit_when_disabled():
    q = _q("11.61", "11.68", 0)
    assert compute_exit_fill(q, side="BUY", min_open_interest=0).accepted


# ---------------------------------------------------------------------------
# SANITY GATES KEPT on exits, regardless of profile
# ---------------------------------------------------------------------------

def test_crossed_quote_rejected_on_exit():
    q = _q("12.63", "12.52", 5000)   # ask < bid (crossed)
    r = compute_exit_fill(q, side="BUY", min_open_interest=0,
                          max_spread_pct=EXIT_PCT)
    assert r.accepted is False and r.reason == "ASK_NOT_GREATER_BID"


def test_nonpositive_bid_rejected_on_exit():
    q = _q("0.00", "0.10", 5000)
    r = compute_exit_fill(q, side="SELL", min_open_interest=0,
                          max_spread_pct=EXIT_PCT)
    assert r.accepted is False and r.reason == "BID_NONPOSITIVE"


def test_missing_bid_ask_rejected_on_exit():
    q = _q(None, None, 5000, mid=None)
    r = compute_exit_fill(q, side="BUY", min_open_interest=0,
                          max_spread_pct=EXIT_PCT)
    assert r.accepted is False and r.reason == "MISSING_BID_OR_ASK"


def test_stale_quote_rejected_on_exit():
    q = _q("12.52", "12.63", 26996, age=61)
    r = compute_exit_fill(q, side="BUY", min_open_interest=0,
                          max_spread_pct=EXIT_PCT)
    assert r.accepted is False and r.reason == "STALE_QUOTE"


def test_missing_mid_with_bid_ask_uses_fallback_for_cap():
    # mid=None but bid/ask present: cap derives from (bid+ask)/2; the
    # fill itself then rejects NO_MID downstream (fill model unchanged —
    # compute_exit_fill must never invent a fill price).
    q = _q("12.52", "12.63", 26996, mid=None)
    assert exit_max_spread_dollars(
        q, max_spread_pct=EXIT_PCT, max_spread_floor=EXIT_FLOOR,
    ) == Decimal("12.575") * EXIT_PCT
    r = compute_exit_fill(q, side="BUY", min_open_interest=0,
                          max_spread_pct=EXIT_PCT)
    assert r.accepted is False and r.reason == "FILL_NO_MID"
