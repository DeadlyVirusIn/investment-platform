"""Phase 11W (incident fix) — run_daily_loop.sh source-level guards.

Pins the orchestration order: engine pipeline must run BEFORE the
market-data precheck and BEFORE paper_daily, so context_daily is
fresh when downstream stages execute. Also pins the absence of
exploratory-mode / strategy-relaxation language."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def script_text() -> str:
    return Path("scripts/run_daily_loop.sh").read_text(encoding="utf-8")


def test_engine_pipeline_step_is_present(script_text: str):
    assert "scripts.run_engine_pipeline" in script_text


def test_engine_pipeline_runs_before_market_data_readiness(script_text: str):
    pos_engine = script_text.find("scripts.run_engine_pipeline")
    pos_precheck = script_text.find("scripts.check_market_data_ready")
    assert 0 < pos_engine < pos_precheck, (
        "engine_pipeline must run BEFORE check_market_data_ready"
    )


def test_engine_pipeline_runs_before_paper_daily(script_text: str):
    pos_engine = script_text.find("scripts.run_engine_pipeline")
    pos_paper = script_text.find("scripts.run_paper_daily")
    assert 0 < pos_engine < pos_paper, (
        "engine_pipeline must run BEFORE run_paper_daily"
    )


def test_no_exploratory_mode_added(script_text: str):
    """Hard guard: this incident fix must NOT introduce any
    exploratory-mode invocation in the daily loop."""
    forbidden = (
        "EXPLORATORY_PAPER_ENABLED",
        "exploratory_mode",
        "--exploratory",
    )
    for tok in forbidden:
        assert tok not in script_text, (
            f"forbidden exploratory-mode token {tok!r} in daily loop"
        )


def test_no_gate_relaxation_or_threshold_change(script_text: str):
    forbidden = (
        "MIN_GATE_SCORE", "RATE_THRESHOLD", "VRP_THRESHOLD",
        "force_trade", "--force-trade", "--bypass-gates",
    )
    for tok in forbidden:
        assert tok not in script_text, (
            f"forbidden strategy-relaxation token {tok!r} in daily loop"
        )


def test_engine_pipeline_uses_iso_date_arg(script_text: str):
    """Date arg must be an explicit ISO date string, never a
    timezone-relative bareword."""
    assert "--as-of" in script_text
    assert "ENGINE_AS_OF" in script_text
