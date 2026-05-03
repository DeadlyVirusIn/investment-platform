"""Unit tests for paper-trading validation helpers."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

from apps.api.src.domain.paper_trading.paper_service import (
    _confidence_bucket,
    compute_paper_max_drawdown,
)


@dataclass
class _Snap:
    snapshot_date: dt.datetime
    total_equity: Decimal


BASE = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)


def test_max_drawdown_empty_returns_none() -> None:
    out = compute_paper_max_drawdown([])
    assert out["max_drawdown_pct"] is None
    assert out["max_drawdown_duration_days"] is None


def test_max_drawdown_single_point_returns_none() -> None:
    out = compute_paper_max_drawdown([_Snap(BASE, Decimal("1000"))])
    assert out["max_drawdown_pct"] is None


def test_max_drawdown_none_when_monotonic_up() -> None:
    snaps = [
        _Snap(BASE, Decimal("1000")),
        _Snap(BASE + dt.timedelta(days=1), Decimal("1050")),
        _Snap(BASE + dt.timedelta(days=2), Decimal("1100")),
    ]
    out = compute_paper_max_drawdown(snaps)
    assert out["max_drawdown_pct"] is None


def test_max_drawdown_simple_20pct() -> None:
    snaps = [
        _Snap(BASE, Decimal("1000")),
        _Snap(BASE + dt.timedelta(days=5), Decimal("1200")),
        _Snap(BASE + dt.timedelta(days=10), Decimal("960")),
        _Snap(BASE + dt.timedelta(days=15), Decimal("1300")),
    ]
    out = compute_paper_max_drawdown(snaps)
    # peak 1200 → trough 960 → -20%
    assert out["max_drawdown_pct"] == Decimal("-0.2")
    assert out["max_drawdown_duration_days"] == 5
    assert out["peak_equity"] == Decimal("1200")
    assert out["trough_equity"] == Decimal("960")


def test_confidence_bucket_boundaries() -> None:
    assert _confidence_bucket(None) == "Unknown"
    assert _confidence_bucket(Decimal("0")) == "Low (0-30)"
    assert _confidence_bucket(Decimal("29.99")) == "Low (0-30)"
    assert _confidence_bucket(Decimal("30")) == "Medium (30-60)"
    assert _confidence_bucket(Decimal("59.99")) == "Medium (30-60)"
    assert _confidence_bucket(Decimal("60")) == "High (60-100)"
    assert _confidence_bucket(Decimal("100")) == "High (60-100)"
