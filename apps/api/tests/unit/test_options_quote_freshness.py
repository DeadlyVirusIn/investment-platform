"""P6D.34A — effective quote-age foundation (pure tests, no DB).

Pins: effective_age_seconds math (incl. clock-skew clamp), the
OptionChainQuote field default, and evaluate_quote's preference for the
effective age over the stored-at-ingest age (which is ~0 forever on
rehydrated rows and hides hours of staleness).
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from apps.api.src.options.canary.selection import effective_age_seconds
from apps.api.src.options.data.liquidity_filter import (
    MAX_QUOTE_AGE_SECONDS,
    REJECT_STALE_QUOTE,
    evaluate_quote,
)
from apps.api.src.options.data_provider.base_adapter import OptionChainQuote

NOW = dt.datetime(2026, 6, 9, 18, 0, tzinfo=dt.timezone.utc)


def _q(*, stored_age: int = 0, effective: int | None = None,
       snapshot_at: dt.datetime = NOW) -> OptionChainQuote:
    return OptionChainQuote(
        snapshot_at_utc=snapshot_at, underlying="QQQ",
        expiry=dt.date(2026, 7, 17), strike=Decimal("675"),
        option_type="PUT", option_symbol="QQQ_TEST",
        bid=Decimal("9.69"), ask=Decimal("9.78"), mid=Decimal("9.735"),
        last=Decimal("9.69"), volume=100, open_interest=26528,
        delta=Decimal("-0.30"), gamma=Decimal("0.02"),
        theta=Decimal("-0.05"), vega=Decimal("0.10"), iv=Decimal("0.20"),
        quote_age_seconds=stored_age, provider="tradier",
        effective_age_seconds=effective,
    )


# ── effective_age_seconds math ─────────────────────────────────────────────

def test_fresh_snapshot_age_is_stored_age():
    assert effective_age_seconds(NOW, 2, NOW) == 2


def test_three_hour_old_snapshot():
    snap = NOW - dt.timedelta(hours=3)
    assert effective_age_seconds(snap, 0, NOW) == 3 * 3600


def test_elapsed_plus_stored_age_adds():
    snap = NOW - dt.timedelta(minutes=10)
    assert effective_age_seconds(snap, 30, NOW) == 600 + 30


def test_clock_skew_future_snapshot_clamps_to_zero():
    # snapshot_at_utc > now → elapsed term clamps to 0, never negative.
    snap = NOW + dt.timedelta(minutes=5)
    assert effective_age_seconds(snap, 0, NOW) == 0


def test_clock_skew_with_stored_age_keeps_stored_only():
    snap = NOW + dt.timedelta(minutes=5)
    assert effective_age_seconds(snap, 7, NOW) == 7


def test_negative_stored_age_clamped():
    assert effective_age_seconds(NOW, -50, NOW) == 0


def test_naive_timestamps_treated_as_utc():
    snap = (NOW - dt.timedelta(hours=1)).replace(tzinfo=None)
    assert effective_age_seconds(snap, 0, NOW) == 3600
    assert effective_age_seconds(
        NOW - dt.timedelta(hours=1), 0, NOW.replace(tzinfo=None)
    ) == 3600


# ── OptionChainQuote field ─────────────────────────────────────────────────

def test_field_defaults_to_none_on_adapter_path():
    # Fresh adapter pulls don't set it — stored age remains authoritative.
    assert _q(stored_age=2, effective=None).effective_age_seconds is None


# ── evaluate_quote preference ──────────────────────────────────────────────

def test_stale_effective_age_rejected_even_when_stored_is_zero():
    # The bug this phase fixes: stored 0s on a 3.5h-old snapshot.
    q = _q(stored_age=0, effective=12600)
    assert evaluate_quote(q) == REJECT_STALE_QUOTE


def test_fresh_effective_age_accepted():
    q = _q(stored_age=0, effective=MAX_QUOTE_AGE_SECONDS)
    assert evaluate_quote(q) is None


def test_none_effective_falls_back_to_stored_age():
    # Ingest-path back-compat: stored age still gates when effective absent.
    assert evaluate_quote(_q(stored_age=2, effective=None)) is None
    assert evaluate_quote(
        _q(stored_age=MAX_QUOTE_AGE_SECONDS + 1, effective=None)
    ) == REJECT_STALE_QUOTE


def test_effective_zero_overrides_stale_stored():
    # Explicit effective=0 (just-refreshed) wins over a stale stored value.
    q = _q(stored_age=999, effective=0)
    assert evaluate_quote(q) is None
