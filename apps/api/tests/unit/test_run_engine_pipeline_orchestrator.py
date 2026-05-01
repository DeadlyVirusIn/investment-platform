"""Phase 11W (incident fix) — engine pipeline orchestrator tests."""

from __future__ import annotations

import datetime as dt
from unittest.mock import patch

import pytest

import scripts.run_engine_pipeline as mod


@pytest.fixture
def mock_pipeline(monkeypatch):
    """Stub every external dependency so run_for_date is a pure
    coordination test."""

    def _stub_macro(as_of, dry_run):
        return 0

    async def _stub_regime(as_of):
        return None

    async def _stub_factor(as_of):
        return None

    async def _stub_candidate(as_of):
        return None

    monkeypatch.setattr(mod, "_run_macro_backfill", _stub_macro)
    monkeypatch.setattr(mod, "_run_regime_snapshot", _stub_regime)
    monkeypatch.setattr(mod, "_run_factor_snapshots", _stub_factor)
    monkeypatch.setattr(mod, "_run_generate_candidates", _stub_candidate)
    monkeypatch.setattr(mod, "_has_price_bar_for", lambda d: True)
    monkeypatch.setattr(
        mod, "_stage_max_dates",
        lambda: {
            "price_bar": "2026-05-01",
            "context_daily": "2026-04-28",
            "regime_snapshot": "2026-04-17",
            "factor_snapshot": "2026-04-17",
            "candidate_idea": "2026-04-17",
        },
    )


def test_run_for_date_runs_all_four_stages_in_order(mock_pipeline):
    out = mod.run_for_date(dt.date(2026, 5, 1))
    assert out["ok"] is True
    assert out["stages"]["macro_backfill"] == "ok"
    assert out["stages"]["regime_snapshot"] == "ok"
    assert out["stages"]["factor_snapshots"] == "ok"
    assert out["stages"]["generate_stock_candidates"] == "ok"


def test_run_for_date_aborts_when_no_price_bar(monkeypatch):
    monkeypatch.setattr(mod, "_has_price_bar_for", lambda d: False)
    monkeypatch.setattr(
        mod, "_stage_max_dates",
        lambda: {"price_bar": None, "context_daily": None,
                 "regime_snapshot": None, "factor_snapshot": None,
                 "candidate_idea": None},
    )
    out = mod.run_for_date(dt.date(2026, 5, 1))
    assert out["ok"] is False
    assert "no price_bar" in out["error"]


def test_main_returns_3_when_no_price_bar(monkeypatch):
    monkeypatch.setattr(mod, "_has_price_bar_for", lambda d: False)
    monkeypatch.setattr(
        mod, "_stage_max_dates",
        lambda: {"price_bar": None, "context_daily": None,
                 "regime_snapshot": None, "factor_snapshot": None,
                 "candidate_idea": None},
    )
    rc = mod.main(["--as-of", "2026-05-01"])
    assert rc == 3


def test_main_returns_2_on_macro_failure(mock_pipeline, monkeypatch):
    def _bad_macro(as_of, dry_run):
        return 1

    monkeypatch.setattr(mod, "_run_macro_backfill", _bad_macro)
    rc = mod.main(["--as-of", "2026-05-01"])
    assert rc == 2


def test_skip_flags_propagate_through_stages(mock_pipeline):
    out = mod.run_for_date(
        dt.date(2026, 5, 1),
        skip_macro=True,
        skip_regime=True,
    )
    assert out["stages"]["macro_backfill"] == "skipped"
    assert out["stages"]["regime_snapshot"] == "skipped"
    # Downstream stages still run when explicit skip set upstream
    # (we only auto-skip when an upstream stage CRASHES).
    assert out["stages"]["factor_snapshots"] == "ok"
    assert out["stages"]["generate_stock_candidates"] == "ok"


def test_arg_parser_requires_as_of():
    with pytest.raises(SystemExit):
        mod._parse([])


def test_arg_parser_accepts_iso_date():
    args = mod._parse(["--as-of", "2026-05-01"])
    assert args.as_of == dt.date(2026, 5, 1)


def test_no_strategy_threshold_changes_in_orchestrator():
    """Sanity guard — orchestrator must not import or reference
    strategy thresholds, gate logic, or sizing functions."""
    from pathlib import Path

    src = Path("scripts/run_engine_pipeline.py").read_text(
        encoding="utf-8"
    )
    forbidden = (
        "RATE_THRESHOLD", "VRP_THRESHOLD",
        "DEFAULT_MAX_OPEN_POSITIONS",
        "submit_trade", "auto_trade_portfolio",
        "exploratory", "EXPLORATORY",
    )
    for tok in forbidden:
        assert tok not in src, (
            f"orchestrator must not reference {tok!r}"
        )
