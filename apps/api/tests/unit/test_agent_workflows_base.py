"""Unit tests for the agent_workflows framework base + registry."""

from __future__ import annotations

import pytest

from apps.api.src.domain.agent_workflows import (
    AGENT_REGISTRY, get_agent, list_agent_names,
)
from apps.api.src.domain.agent_workflows.base import (
    AGENT_BANNER, Agent, AgentMode, AgentOutput,
)


# ---------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------

def test_registry_contains_all_four_agents():
    names = set(list_agent_names())
    assert names == {
        "trade_quality", "risk", "exit_analysis", "signal_validation",
    }


def test_get_agent_unknown_raises():
    with pytest.raises(KeyError):
        get_agent("not_a_real_agent")


def test_each_agent_declares_inputs():
    for agent in AGENT_REGISTRY.values():
        ins = agent.inputs()
        assert isinstance(ins, dict)
        assert ins, f"{agent.name} declares no inputs"
        for k, v in ins.items():
            assert isinstance(k, str) and k
            assert isinstance(v, str) and v


def test_each_agent_has_description_and_deterministic_mode():
    for agent in AGENT_REGISTRY.values():
        assert agent.description, f"{agent.name} missing description"
        assert agent.mode == AgentMode.DETERMINISTIC


# ---------------------------------------------------------------------
# AgentOutput envelope
# ---------------------------------------------------------------------

def test_agent_output_defaults_to_read_only():
    out = AgentOutput(
        agent="x",
        mode=AgentMode.DETERMINISTIC,
        generated_at="2026-05-07T00:00:00+00:00",
        output={"k": 1},
    )
    assert out.execution_linked is False
    assert out.banner == AGENT_BANNER
    assert out.warnings == []


# ---------------------------------------------------------------------
# Validate gate
# ---------------------------------------------------------------------

class _BadAgent(Agent):
    name = "_bad"
    description = "test only"

    def inputs(self) -> dict[str, str]:
        return {"x": "y"}

    def run(self, *, db=None, **params) -> AgentOutput:
        return self.envelope(output={"k": 1})


def test_validate_rejects_execution_linked_true():
    a = _BadAgent()
    bad = AgentOutput(
        agent="_bad",
        mode=AgentMode.DETERMINISTIC,
        generated_at="2026-05-07T00:00:00+00:00",
        output={"k": 1},
        execution_linked=True,
    )
    with pytest.raises(ValueError):
        a.validate(bad)


def test_validate_rejects_banner_mismatch():
    a = _BadAgent()
    bad = AgentOutput(
        agent="_bad",
        mode=AgentMode.DETERMINISTIC,
        generated_at="2026-05-07T00:00:00+00:00",
        output={"k": 1},
        banner="Wrong banner",
    )
    with pytest.raises(ValueError):
        a.validate(bad)


def test_validate_rejects_agent_name_mismatch():
    a = _BadAgent()
    bad = AgentOutput(
        agent="not_bad",
        mode=AgentMode.DETERMINISTIC,
        generated_at="2026-05-07T00:00:00+00:00",
        output={"k": 1},
    )
    with pytest.raises(ValueError):
        a.validate(bad)


def test_validate_passes_for_clean_envelope():
    a = _BadAgent()
    out = a.run()
    a.validate(out)


# ---------------------------------------------------------------------
# Source-level safety: no execution-path imports
# ---------------------------------------------------------------------

def test_framework_does_not_import_execution_modules():
    import inspect
    from apps.api.src.domain.agent_workflows import base, registry

    forbidden = (
        "paper_trading.paper_execution",
        "paper_trading.paper_service",
        "options.paper.engine",
        "submit_trade",
        "_build_legs_payload",
        "import autogen", "from autogen",
        "import langchain", "from langchain",
    )
    for mod in (base, registry):
        src = inspect.getsource(mod)
        for tok in forbidden:
            assert tok not in src, (
                f"{mod.__name__} must not reference {tok!r}"
            )
