"""Phase 11V - data_collection_health unit tests."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from apps.api.src.ml import data_collection_health as dch_mod
from apps.api.src.ml.data_collection_health import (
    PRODUCTION_GATE_NAMES,
    REPORT_VERSION,
    STALE_PRICE_DAYS,
    candidate_idea_throughput,
    recommendation_throughput,
)


def test_report_version_frozen():
    assert REPORT_VERSION == "data-health-v1.0.0"


def test_stale_threshold_frozen():
    assert STALE_PRICE_DAYS == 5


def test_production_gate_names_frozen():
    assert PRODUCTION_GATE_NAMES == (
        "rates_calm", "vrp_supportive",
        "credit_stable", "liquidity_expanding",
    )


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

def test_recommendation_throughput_requires_tz_aware():
    s = MagicMock()
    with pytest.raises(ValueError):
        recommendation_throughput(
            s, as_of=dt.datetime(2026, 4, 28), lookback_days=30,
        )


def test_recommendation_throughput_requires_positive_lookback():
    s = MagicMock()
    with pytest.raises(ValueError):
        recommendation_throughput(
            s,
            as_of=dt.datetime(2026, 4, 28, tzinfo=dt.timezone.utc),
            lookback_days=0,
        )


def test_candidate_idea_throughput_requires_tz_aware():
    s = MagicMock()
    with pytest.raises(ValueError):
        candidate_idea_throughput(
            s, as_of=dt.datetime(2026, 4, 28), lookback_days=30,
        )


# ---------------------------------------------------------------------------
# Source-level guards
# ---------------------------------------------------------------------------

def test_module_has_no_db_writes():
    src = Path(dch_mod.__file__).read_text(encoding="utf-8")
    for tok in (
        "INSERT INTO", "UPDATE ", "DELETE FROM",
        "session.commit", "session.add(",
    ):
        assert tok not in src, f"forbidden token {tok!r}"


def test_module_does_not_import_execution_paths():
    src = Path(dch_mod.__file__).read_text(encoding="utf-8")
    for tok in (
        "submit_trade", "auto_trade_portfolio",
        "live_", "broker_", "order_router",
    ):
        assert tok not in src, f"forbidden import {tok!r}"


def test_module_uses_strict_le_on_context_daily_query():
    """The context_daily query must use as_of_date <= :as_of with a
    DESC order — never future dates."""
    src = Path(dch_mod.__file__).read_text(encoding="utf-8")
    assert "as_of_date <= :as_of" in src
    assert "ORDER BY as_of_date DESC" in src
    for forbidden in (
        "as_of_date >= :as_of", "as_of_date > :as_of",
        "as_of_date = :as_of",
    ):
        assert forbidden not in src, (
            f"forbidden cutoff pattern: {forbidden!r}"
        )
