"""Unit tests for agents.narrator.build_prompt — pure / no I/O.

Covers every AgentKind. Asserts banner presence, source
endpoint string, UUID redaction, forbidden-term absence, and
that imports do not pull in execution / LLM modules.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from apps.api.src.domain.agents import narrator, safety
from apps.api.src.domain.agents.registry import (
    AgentKind, BANNER, REGISTRY,
)


_ALL_KINDS = list(AgentKind)


# Realistic payload shapes per kind — values are arbitrary but
# match the keys actually returned by the matching endpoint.
def _payload_for(kind: AgentKind) -> dict:
    if kind is AgentKind.TRADE_QUALITY:
        return {
            "trade_id": "42eecbbf-3cc6-4229-8efc-086310914e2b",
            "portfolio_id": "7e00ce27-8157-42df-8cb7-30cd8c22e25a",
            "symbol": "NVDA",
            "side": "sell",
            "is_open": False,
            "fill_ts": "2026-05-05T00:00:00+00:00",
            "entry_price": 199.300003,
            "qty": 0.4763492593,
            "held_days": 4,
            "current_price": None,
            "realized_pnl": -5.063591,
            "exit_reason": "exit_cycle: stop_loss(-0.0545 <= -0.04)",
            "score": 69,
            "grade": "C",
            "thesis": "stopped_out",
            "completeness": "full",
            "components": {
                "entry": 20, "return": 7,
                "hold": 15, "exit_or_status": 17,
                "completeness": 10,
            },
            "reasons": [
                "Entry: favorable fill for SELL.",
                "Realized return: -5.33 percent.",
            ],
        }
    if kind is AgentKind.RISK_COMMENTARY:
        return {
            "snapshot_date": "2026-05-05T00:00:00+00:00",
            "mark_unavailable": False,
            "nav": 115392.97,
            "cash": 527.27,
            "exposure_value": 114865.70,
            "exposure_pct": 0.9954,
            "open_positions_count": 38,
            "unrealized_pnl": 3392.97,
            "realized_pnl_total": -10.1272,
            "max_drawdown_pct": -0.0266,
            "live_trades_count": 24,
            "replay_trades_count": 18,
            "concentration_by_symbol": [
                {"symbol": "VTI", "n_open": 4,
                 "notional_usd": 10389.78,
                 "unrealized_pnl": 171.49,
                 "mark_unavailable": False},
            ],
            "concentration_by_portfolio": [
                {"portfolio_id":
                    "166b12ed-4b6d-4ec8-854d-234baa7d029a",
                 "portfolio_name": "Replay Recovery Account",
                 "n_open": 10,
                 "notional_usd": 102584.89},
            ],
            "top_5_notional": [],
        }
    if kind is AgentKind.EXIT_REVIEW:
        return {
            "n_closed": 2,
            "n_winners": 0,
            "n_losers": 2,
            "win_rate": 0.0,
            "realized_pnl_total": -10.1272,
            "avg_win_dollars": None,
            "avg_loss_dollars": -5.0636,
            "avg_hold_days": 4.0,
            "tp_sl_effectiveness": {
                "tp_count": 0, "sl_count": 2,
                "tp_total_pnl": 0.0,
                "sl_total_pnl": -10.1272,
            },
            "small_sample_warning": (
                "Only 2 closed trades so far — statistics are "
                "directional, not reliable."
            ),
        }
    if kind is AgentKind.OPTIONS_THESIS:
        return {
            "id": "ev-uuid",
            "rule_id": "long_call_atm",
            "underlying": "AMZN",
            "as_of_date": "2026-05-04",
            "qualified": True,
            "total_score": 71,
            "components": [],
            "penalties": [],
            "flags": [],
            "model_version": "v1",
        }
    raise ValueError(f"unhandled kind: {kind}")


# -----------------------------------------------------------------
# Per-kind builds and shape assertions
# -----------------------------------------------------------------

@pytest.mark.parametrize("kind", _ALL_KINDS)
def test_build_prompt_contains_banner(kind):
    prompt = narrator.build_prompt(kind, _payload_for(kind))
    assert BANNER in prompt


@pytest.mark.parametrize("kind", _ALL_KINDS)
def test_build_prompt_contains_source_endpoint(kind):
    prompt = narrator.build_prompt(kind, _payload_for(kind))
    assert REGISTRY[kind].source_endpoint in prompt


@pytest.mark.parametrize("kind", _ALL_KINDS)
def test_build_prompt_contains_kind_label(kind):
    prompt = narrator.build_prompt(kind, _payload_for(kind))
    assert REGISTRY[kind].label in prompt


@pytest.mark.parametrize("kind", _ALL_KINDS)
def test_build_prompt_no_forbidden_execution_terms(kind):
    prompt = narrator.build_prompt(kind, _payload_for(kind))
    # validate_no_forbidden_terms must not raise on the output.
    safety.validate_no_forbidden_terms(prompt)


@pytest.mark.parametrize("kind", _ALL_KINDS)
def test_build_prompt_strips_raw_uuids(kind):
    prompt = narrator.build_prompt(kind, _payload_for(kind))
    uuid_pattern = re.compile(
        r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
        r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
    )
    assert not uuid_pattern.search(prompt), (
        "raw UUID leaked into prompt — scrubber failed"
    )


# -----------------------------------------------------------------
# Numeric fidelity
# -----------------------------------------------------------------

def test_trade_quality_preserves_payload_numbers_verbatim():
    payload = _payload_for(AgentKind.TRADE_QUALITY)
    prompt = narrator.build_prompt(
        AgentKind.TRADE_QUALITY, payload,
    )
    # JSON facts block contains payload values exactly.
    for v in [69, "C", "stopped_out", "full"]:
        assert str(v) in prompt
    # Realized pnl printed with full precision in JSON block.
    assert "-5.063591" in prompt


def test_options_thesis_includes_extra_disclaimer():
    prompt = narrator.build_prompt(
        AgentKind.OPTIONS_THESIS,
        _payload_for(AgentKind.OPTIONS_THESIS),
    )
    assert "execution_allowed=false" in prompt


def test_missing_required_field_is_called_out_not_silenced():
    payload = {"score": 72}  # only 1 of 6 required fields
    prompt = narrator.build_prompt(
        AgentKind.TRADE_QUALITY, payload,
    )
    assert "Missing payload fields" in prompt
    # Each missing field name must appear so the future LLM can
    # state it as unavailable.
    for f in ("grade", "thesis", "completeness",
              "components", "reasons"):
        assert f in prompt


# -----------------------------------------------------------------
# Regression: payload UUIDs must NOT appear in the prompt
# -----------------------------------------------------------------

def test_regression_uuids_redacted_from_all_paths():
    payload = _payload_for(AgentKind.RISK_COMMENTARY)
    # portfolio_id lives nested in concentration_by_portfolio.
    portfolio_uuid = (
        payload["concentration_by_portfolio"][0]["portfolio_id"]
    )
    prompt = narrator.build_prompt(
        AgentKind.RISK_COMMENTARY, payload,
    )
    assert portfolio_uuid not in prompt
    assert "[redacted]" in prompt


def test_uuid_in_string_field_redacted():
    payload = _payload_for(AgentKind.TRADE_QUALITY)
    payload["exit_reason"] = (
        "exit_cycle: stop_loss for "
        "42eecbbf-3cc6-4229-8efc-086310914e2b"
    )
    prompt = narrator.build_prompt(
        AgentKind.TRADE_QUALITY, payload,
    )
    assert "42eecbbf" not in prompt
    assert "[redacted-uuid]" in prompt


# -----------------------------------------------------------------
# Hard input contract
# -----------------------------------------------------------------

def test_build_prompt_rejects_non_agentkind_input():
    with pytest.raises(TypeError):
        narrator.build_prompt("trade_quality", {})  # str, not enum


def test_build_prompt_rejects_non_dict_payload():
    with pytest.raises(TypeError):
        narrator.build_prompt(
            AgentKind.TRADE_QUALITY, [1, 2, 3],
        )


# -----------------------------------------------------------------
# Source-level safety: narrator does not import execution / LLM
# -----------------------------------------------------------------

_FORBIDDEN_IMPORT_TOKENS = (
    # Execution paths
    "paper_trading.paper_execution",
    "paper_trading.paper_service",
    "options.paper.engine",
    "options.pending_replay",
    "scripts.run_paper_exit_cycle",
    "scripts.run_options_paper_exec",
    "submit_trade",
    "_build_legs_payload",
    "replay_recovery_manifest",
    # LLM / agent frameworks (Phase F1 has no LLM call)
    "import anthropic",
    "from anthropic",
    "import openai",
    "from openai",
    "import autogen",
    "from autogen",
    "import langchain",
    "from langchain",
    # Network primitives
    "import requests",
    "import httpx",
    "from urllib.request",
    "import socket",
)


def test_narrator_source_has_no_forbidden_imports():
    src = inspect.getsource(narrator)
    for tok in _FORBIDDEN_IMPORT_TOKENS:
        assert tok not in src, (
            f"narrator.py must not reference {tok!r}"
        )


def test_safety_source_has_no_forbidden_imports():
    src = inspect.getsource(safety)
    for tok in _FORBIDDEN_IMPORT_TOKENS:
        assert tok not in src, (
            f"safety.py must not reference {tok!r}"
        )


def test_agents_package_has_no_endpoint_module():
    """Phase F1 explicitly does NOT add an endpoint. Verify no
    insights router file was committed alongside the scaffolding."""
    api_dir = (
        Path(narrator.__file__).resolve()
        .parents[3]   # apps/api/src
        / "api"
    )
    insights_files = list(api_dir.glob("insights*.py"))
    assert insights_files == [], (
        f"Phase F1 must not add an insights endpoint; found "
        f"{insights_files}"
    )


# -----------------------------------------------------------------
# Smoke: build_prompt is idempotent (same input → same output)
# -----------------------------------------------------------------

@pytest.mark.parametrize("kind", _ALL_KINDS)
def test_build_prompt_is_deterministic(kind):
    payload = _payload_for(kind)
    a = narrator.build_prompt(kind, payload)
    b = narrator.build_prompt(kind, payload)
    assert a == b
