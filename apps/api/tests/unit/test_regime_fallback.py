"""Phase 1 — bounded regime fallback in stock-engine candidate generation.

Pins:
  1. `_trading_days_between` counts weekdays only, exclusive of start.
  2. `_resolve_regime_with_fallback` returns the exact row when present.
  3. Returns the most recent prior row when within
     REGIME_FALLBACK_MAX_TRADING_DAYS trading days.
  4. Returns None when the latest prior is older than the bound —
     `regime_off` will then still fire by design.
  5. Returns None when no prior row exists at all.
  6. `_regime_off` still rejects when fallback returned a row whose
     market_trend is "downtrend" (logic NOT changed).
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from apps.api.src.db.models import RegimeSnapshot
from apps.api.src.domain.stock_engine.decision_engine import (
    REGIME_FALLBACK_MAX_TRADING_DAYS,
    _resolve_regime_with_fallback,
    _trading_days_between,
)
from apps.api.src.domain.stock_engine.eligibility import (
    DecisionContext,
    _regime_off,
)


# ---------------------------------------------------------------------------
# _trading_days_between
# ---------------------------------------------------------------------------
def test_trading_days_between_same_day():
    d = dt.date(2026, 5, 4)  # Mon
    assert _trading_days_between(d, d) == 0


def test_trading_days_between_consecutive_weekdays():
    # Fri 2026-05-01 → Mon 2026-05-04: weekend in between
    fri = dt.date(2026, 5, 1)
    mon = dt.date(2026, 5, 4)
    assert _trading_days_between(fri, mon) == 1


def test_trading_days_between_skips_weekends():
    # Fri 2026-05-01 → Wed 2026-05-06: Mon, Tue, Wed = 3 trading days
    fri = dt.date(2026, 5, 1)
    wed = dt.date(2026, 5, 6)
    assert _trading_days_between(fri, wed) == 3


def test_trading_days_between_end_before_start_returns_zero():
    assert _trading_days_between(
        dt.date(2026, 5, 4), dt.date(2026, 5, 1),
    ) == 0


# ---------------------------------------------------------------------------
# _resolve_regime_with_fallback
# ---------------------------------------------------------------------------
def _stub_regime(d: dt.date, trend: str = "uptrend") -> RegimeSnapshot:
    return RegimeSnapshot(
        as_of_date=d,
        benchmark_symbol="SPY",
        market_trend=trend,
        vol_regime="normal",
        breadth_regime=None,
        sma50_over_sma200=True,
        realized_vol_20d=Decimal("0.10"),
        atr_pctile_1y=Decimal("0.50"),
    )


def test_fallback_returns_exact_row_when_present():
    session = MagicMock()
    today = dt.date(2026, 5, 4)
    today_row = _stub_regime(today)
    session.get.return_value = today_row
    result = _resolve_regime_with_fallback(session, today)
    assert result is today_row
    # No prior-row query needed when exact hit.
    session.execute.assert_not_called()


def test_fallback_uses_prior_row_within_bound():
    session = MagicMock()
    today = dt.date(2026, 5, 4)               # Mon
    prior = _stub_regime(dt.date(2026, 5, 1)) # Fri (1 trading day back)
    session.get.return_value = None
    session.execute.return_value.scalar_one_or_none.return_value = prior
    result = _resolve_regime_with_fallback(session, today)
    assert result is prior


def test_fallback_rejects_prior_row_beyond_bound():
    session = MagicMock()
    today = dt.date(2026, 5, 11)              # Mon
    # 5 trading days behind (Mon..Fri previous week then weekend)
    prior = _stub_regime(dt.date(2026, 5, 1))
    age = _trading_days_between(prior.as_of_date, today)
    assert age > REGIME_FALLBACK_MAX_TRADING_DAYS, (
        f"setup must exceed bound (got age={age})"
    )
    session.get.return_value = None
    session.execute.return_value.scalar_one_or_none.return_value = prior
    result = _resolve_regime_with_fallback(session, today)
    assert result is None


def test_fallback_returns_none_when_no_prior_exists():
    session = MagicMock()
    session.get.return_value = None
    session.execute.return_value.scalar_one_or_none.return_value = None
    result = _resolve_regime_with_fallback(session, dt.date(2026, 5, 4))
    assert result is None


def test_regime_off_still_fires_on_downtrend_fallback():
    """Even when fallback is used, market_trend='downtrend' MUST still
    flip regime_off=True. Phase 1 does not soften that gate."""
    fallback_row = _stub_regime(dt.date(2026, 5, 1), trend="downtrend")
    ctx = DecisionContext(
        regime=fallback_row,
        universe_asset_ids=set(),
        atr_p90=None,
    )
    factor_row = MagicMock()
    assert _regime_off(ctx, factor_row) is True


def test_regime_off_passes_when_fallback_is_uptrend():
    fallback_row = _stub_regime(dt.date(2026, 5, 1), trend="uptrend")
    ctx = DecisionContext(
        regime=fallback_row,
        universe_asset_ids=set(),
        atr_p90=None,
    )
    factor_row = MagicMock()
    assert _regime_off(ctx, factor_row) is False


def test_regime_off_passes_when_fallback_is_sideways():
    fallback_row = _stub_regime(dt.date(2026, 5, 1), trend="sideways")
    ctx = DecisionContext(
        regime=fallback_row,
        universe_asset_ids=set(),
        atr_p90=None,
    )
    factor_row = MagicMock()
    assert _regime_off(ctx, factor_row) is False


def test_constant_default_is_three_trading_days():
    """Pin the bound so tightening it later requires an explicit test
    update + commit message."""
    assert REGIME_FALLBACK_MAX_TRADING_DAYS == 3
