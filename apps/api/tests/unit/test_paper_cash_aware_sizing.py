"""Unit tests for the cash-aware sizing shrink helper.

Pure function — no DB, no env unless monkey-patched.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.api.src.domain.paper_trading.paper_execution import (
    DEFAULT_CASH_BUFFER_PCT, DEFAULT_MIN_NOTIONAL_USD,
    shrink_to_cash,
)


def test_no_shrink_when_cash_covers_target():
    final, info = shrink_to_cash(
        target_usd=Decimal("100"),
        available_cash=Decimal("1000"),
    )
    assert final == Decimal("100")
    assert info["shrink_applied"] is False
    assert info["below_min"] is False


def test_shrinks_when_cash_short():
    """The reported scenario: need 1029.11, have 958.66.
    With 5% buffer, cap = 958.66 * 0.95 = 910.727 → quantize to 910.73.
    final = min(1029.11, 910.73) = 910.73."""
    final, info = shrink_to_cash(
        target_usd=Decimal("1029.11"),
        available_cash=Decimal("958.66"),
    )
    assert final == Decimal("910.73")
    assert info["shrink_applied"] is True
    assert info["below_min"] is False


def test_below_min_returns_zero():
    """Cash so low that 95%-of-cash falls below min notional."""
    final, info = shrink_to_cash(
        target_usd=Decimal("100"),
        available_cash=Decimal("10"),
        min_notional_usd=Decimal("50"),
    )
    assert final == Decimal("0")
    assert info["below_min"] is True
    assert info["shrink_applied"] is True


def test_zero_cash_returns_zero():
    final, info = shrink_to_cash(
        target_usd=Decimal("100"),
        available_cash=Decimal("0"),
    )
    assert final == Decimal("0")
    assert info["below_min"] is True


def test_negative_cash_clamped_to_zero_cap():
    final, info = shrink_to_cash(
        target_usd=Decimal("100"),
        available_cash=Decimal("-5"),
    )
    assert final == Decimal("0")
    assert info["below_min"] is True


def test_buffer_arg_overrides_default():
    final, _ = shrink_to_cash(
        target_usd=Decimal("100"),
        available_cash=Decimal("100"),
        cash_buffer_pct=Decimal("0.10"),
    )
    # cap = 100 * 0.90 = 90
    assert final == Decimal("90.00")


def test_min_notional_arg_overrides_default():
    """Custom min — final >= min keeps trade alive."""
    final, info = shrink_to_cash(
        target_usd=Decimal("100"),
        available_cash=Decimal("100"),
        min_notional_usd=Decimal("10"),
    )
    assert final == Decimal("95.00")
    assert info["below_min"] is False


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("PAPER_CASH_BUFFER_PCT", "0.10")
    monkeypatch.setenv("PAPER_MIN_NOTIONAL_USD", "1")
    final, info = shrink_to_cash(
        target_usd=Decimal("100"),
        available_cash=Decimal("100"),
    )
    # env-provided 10% buffer
    assert info["cash_buffer_pct"] == "0.10"
    assert info["min_notional_usd"] == "1"
    assert final == Decimal("90.00")


def test_env_invalid_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("PAPER_CASH_BUFFER_PCT", "not-a-number")
    final, info = shrink_to_cash(
        target_usd=Decimal("100"),
        available_cash=Decimal("100"),
    )
    assert info["cash_buffer_pct"] == str(DEFAULT_CASH_BUFFER_PCT)


def test_env_out_of_range_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("PAPER_CASH_BUFFER_PCT", "0.99")
    final, info = shrink_to_cash(
        target_usd=Decimal("100"),
        available_cash=Decimal("100"),
    )
    assert info["cash_buffer_pct"] == str(DEFAULT_CASH_BUFFER_PCT)


def test_info_contains_all_fields():
    _, info = shrink_to_cash(
        target_usd=Decimal("1029.11"),
        available_cash=Decimal("958.66"),
    )
    for k in (
        "target_usd", "available_cash", "cash_buffer_pct",
        "cap_usd", "min_notional_usd", "final_usd",
        "shrink_applied", "below_min",
    ):
        assert k in info


def test_cash_guard_not_removed():
    """Sanity: shrink output is always <= available_cash."""
    for cash, target in (
        (Decimal("100"), Decimal("1000")),
        (Decimal("0.01"), Decimal("1000")),
        (Decimal("500"), Decimal("100")),
    ):
        final, _ = shrink_to_cash(
            target_usd=target, available_cash=cash,
        )
        assert final <= cash
