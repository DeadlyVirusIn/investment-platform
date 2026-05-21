"""Phase 11V - turnover_diagnostic unit tests."""

from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from apps.api.src.ml import turnover_diagnostic as td_mod
from apps.api.src.ml.turnover_diagnostic import (
    REPORT_VERSION,
    _holding_age_days,
    _portfolio_max_open,
    diagnose_portfolio,
    predict_next_cycle,
)
from apps.api.src.domain.paper_trading.auto_trader import AutoTradeConfig


# ---------------------------------------------------------------------------
# Frozen constants
# ---------------------------------------------------------------------------

def test_report_version_frozen():
    assert REPORT_VERSION == "turnover-diagnostic-v1.0.0"


# ---------------------------------------------------------------------------
# _portfolio_max_open
# ---------------------------------------------------------------------------

def _portfolio_stub(*, config_json: str | None = None, name: str = "p1"):
    p = MagicMock()
    p.id = "pid-1"
    p.name = name
    p.config_json = config_json
    return p


def test_portfolio_max_open_falls_back_to_default():
    p = _portfolio_stub()
    assert _portfolio_max_open(p) == 30  # DEFAULT_MAX_OPEN_POSITIONS


def test_portfolio_max_open_uses_config_when_present():
    p = _portfolio_stub(
        config_json=json.dumps({"max_open_positions": 25})
    )
    assert _portfolio_max_open(p) == 25


def test_portfolio_max_open_falls_back_on_bad_json():
    p = _portfolio_stub(config_json="not json")
    assert _portfolio_max_open(p) == 30


def test_portfolio_max_open_falls_back_when_key_missing():
    p = _portfolio_stub(config_json=json.dumps({"other": 1}))
    assert _portfolio_max_open(p) == 30


# ---------------------------------------------------------------------------
# _holding_age_days
# ---------------------------------------------------------------------------

def test_holding_age_returns_floor_of_delta_days():
    opened = dt.datetime(2026, 4, 1, 12, 0, tzinfo=dt.timezone.utc)
    asof = dt.datetime(2026, 4, 30, 11, 59, tzinfo=dt.timezone.utc)
    # 28 days, 23h59m → 28 days floor
    assert _holding_age_days(opened, asof) == 28


def test_holding_age_clamps_negative_to_zero():
    opened = dt.datetime(2026, 4, 30, tzinfo=dt.timezone.utc)
    asof = dt.datetime(2026, 4, 1, tzinfo=dt.timezone.utc)
    assert _holding_age_days(opened, asof) == 0


def test_holding_age_requires_tz_aware():
    opened = dt.datetime(2026, 4, 1)
    asof = dt.datetime(2026, 4, 30, tzinfo=dt.timezone.utc)
    with pytest.raises(ValueError):
        _holding_age_days(opened, asof)


# ---------------------------------------------------------------------------
# predict_next_cycle (pure)
# ---------------------------------------------------------------------------

def test_predict_next_cycle_full():
    diag = {
        "free_slots": 2,
        "pending_exits_count": 3,
        "expected_slots_after_next_run": 5,
    }
    out = predict_next_cycle(diag)
    assert out == {
        "will_close_old_positions": True,
        "close_count": 3,
        "free_slots_after": 5,
        "buys_possible_after": 5,
    }


def test_predict_next_cycle_no_pending_exits():
    diag = {
        "free_slots": 0,
        "pending_exits_count": 0,
        "expected_slots_after_next_run": 0,
    }
    out = predict_next_cycle(diag)
    assert out["will_close_old_positions"] is False
    assert out["close_count"] == 0
    assert out["buys_possible_after"] == 0


# ---------------------------------------------------------------------------
# diagnose_portfolio — input validation
# ---------------------------------------------------------------------------

def test_diagnose_requires_tz_aware_as_of():
    p = _portfolio_stub()
    s = MagicMock()
    with pytest.raises(ValueError):
        diagnose_portfolio(
            s, p,
            as_of=dt.datetime(2026, 4, 28),
            lookback_days=30,
        )


def test_diagnose_requires_positive_lookback():
    p = _portfolio_stub()
    s = MagicMock()
    with pytest.raises(ValueError):
        diagnose_portfolio(
            s, p,
            as_of=dt.datetime(2026, 4, 28, tzinfo=dt.timezone.utc),
            lookback_days=0,
        )


# ---------------------------------------------------------------------------
# Source-level guards
# ---------------------------------------------------------------------------

def test_module_has_no_db_writes():
    src = Path(td_mod.__file__).read_text(encoding="utf-8")
    for tok in (
        "INSERT INTO", "UPDATE ", "DELETE FROM",
        "session.commit", "session.add(",
    ):
        assert tok not in src, f"forbidden token {tok!r}"


def test_module_does_not_import_execution_paths():
    src = Path(td_mod.__file__).read_text(encoding="utf-8")
    for tok in (
        "submit_trade", "auto_trade_portfolio",
        "live_", "broker_", "order_router",
    ):
        assert tok not in src, f"forbidden import {tok!r}"


def test_module_does_not_change_default_max_open_positions():
    """The diagnostic must IMPORT DEFAULT_MAX_OPEN_POSITIONS from
    paper_execution, not redefine it."""
    src = Path(td_mod.__file__).read_text(encoding="utf-8")
    assert "from apps.api.src.domain.paper_trading.paper_execution" in src
    assert "DEFAULT_MAX_OPEN_POSITIONS = " not in src.replace(
        "from apps.api.src.domain.paper_trading.paper_execution import",
        "",
    )
