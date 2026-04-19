"""Unit tests for alert engine threshold logic (pure functions)."""

from __future__ import annotations

import datetime as dt

from apps.api.src.domain.alerts.alert_engine import _d, _within_cooldown


def test_d_handles_various_inputs() -> None:
    from decimal import Decimal
    assert _d(None) is None
    assert _d("150.25") == Decimal("150.25")
    assert _d(150) == Decimal("150")
    assert _d(Decimal("42")) == Decimal("42")


def test_within_cooldown_none_is_false() -> None:
    now = dt.datetime(2026, 4, 19, 12, tzinfo=dt.timezone.utc)
    assert _within_cooldown(None, now) is False


def test_within_cooldown_recent_true() -> None:
    now = dt.datetime(2026, 4, 19, 12, tzinfo=dt.timezone.utc)
    prev = now - dt.timedelta(hours=2)
    assert _within_cooldown(prev, now) is True


def test_within_cooldown_stale_false() -> None:
    now = dt.datetime(2026, 4, 19, 12, tzinfo=dt.timezone.utc)
    prev = now - dt.timedelta(hours=25)
    assert _within_cooldown(prev, now) is False
