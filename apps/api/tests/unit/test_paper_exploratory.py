"""SYSTEM-ALPHA-5 — exploratory evaluator + paper wrapper.

DB-free: wrapper tests use stub session that returns no active rules.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

from apps.api.src.alpha.exploratory import evaluate_exploratory
from apps.api.src.data.strategy.selector import SelectorOutput
from apps.api.src.data.strategy.engine_a import EngineADecision
from apps.api.src.data.strategy.engine_b import EngineBDecision


def _stub_selector(fire: bool = False) -> SelectorOutput:
    a = EngineADecision(fire=False, reason="stub a")
    b = EngineBDecision(fire=False, reason="stub b")
    return SelectorOutput(
        engine="none", fire=fire,
        engine_a_decision=a, engine_b_decision=b,
        reason="stub selector", decision_version="test-v0",
    )


# ---------------------------------------------------------------------------
# evaluate_exploratory
# ---------------------------------------------------------------------------

def test_strict_mode_disables_exploratory():
    r = evaluate_exploratory(
        strict_fire=False,
        context_values={"rates_calm": True, "vrp_supportive": True,
                         "credit_stable": False,
                         "liquidity_expanding": False},
        gate_mode="strict",
    )
    assert r.allowed is False
    assert "strict" in r.reason


def test_exploratory_blocks_below_min_gates():
    r = evaluate_exploratory(
        strict_fire=False,
        context_values={"rates_calm": True, "vrp_supportive": False,
                         "credit_stable": False,
                         "liquidity_expanding": False},
        gate_mode="exploratory",
        min_gates=2,
    )
    assert r.allowed is False
    assert "gates_passed" in r.reason


def test_exploratory_allows_at_two_of_four_when_safe():
    r = evaluate_exploratory(
        strict_fire=False,
        context_values={"rates_calm": True, "vrp_supportive": True,
                         "credit_stable": False,
                         "liquidity_expanding": False},
        gate_mode="exploratory",
        min_gates=2,
        risk_level="low",
        data_confidence=0.8,
        anomaly_severity=None,
    )
    assert r.allowed is True
    assert r.size_multiplier > 0
    assert r.gates_passed == 2
    assert r.gates_total == 4
    assert set(r.gates_failed) == {"credit_stable", "liquidity_expanding"}


def test_exploratory_blocks_on_critical_anomaly():
    r = evaluate_exploratory(
        strict_fire=False,
        context_values={"rates_calm": True, "vrp_supportive": True,
                         "credit_stable": False,
                         "liquidity_expanding": False},
        gate_mode="exploratory",
        anomaly_severity="critical",
        risk_level="low",
    )
    assert r.allowed is False
    assert "anomaly" in "; ".join(r.severity_blockers)


def test_exploratory_blocks_on_high_risk_when_required():
    r = evaluate_exploratory(
        strict_fire=False,
        context_values={"rates_calm": True, "vrp_supportive": True,
                         "credit_stable": True,
                         "liquidity_expanding": False},
        gate_mode="exploratory",
        risk_level="high",
        require_low_risk=True,
    )
    assert r.allowed is False
    assert any("risk_level" in s for s in r.severity_blockers)


def test_exploratory_blocks_on_low_data_confidence():
    r = evaluate_exploratory(
        strict_fire=False,
        context_values={"rates_calm": True, "vrp_supportive": True,
                         "credit_stable": False,
                         "liquidity_expanding": False},
        gate_mode="exploratory",
        risk_level="low",
        data_confidence=0.2,
        min_data_confidence=0.5,
    )
    assert r.allowed is False
    assert any("data_confidence" in s for s in r.severity_blockers)


def test_exploratory_size_multiplier_clamped_to_unit():
    r = evaluate_exploratory(
        strict_fire=False,
        context_values={"rates_calm": True, "vrp_supportive": True,
                         "credit_stable": True,
                         "liquidity_expanding": False},
        gate_mode="exploratory",
        size_multiplier=5.0,   # attacker tries to scale up
        risk_level="low",
    )
    assert r.size_multiplier <= 1.0


def test_exploratory_skipped_when_strict_already_fires():
    r = evaluate_exploratory(
        strict_fire=True,
        context_values={"rates_calm": True, "vrp_supportive": True,
                         "credit_stable": True,
                         "liquidity_expanding": True},
        gate_mode="exploratory",
    )
    assert r.allowed is False
    assert "strict mode already firing" in r.reason


# ---------------------------------------------------------------------------
# Wrapper integration — uses stub DB
# ---------------------------------------------------------------------------

@dataclass
class _Mapping:
    rows: list[dict[str, Any]]
    def mappings(self): return self
    def all(self): return list(self.rows)
    def first(self): return self.rows[0] if self.rows else None


class _StubSession:
    def execute(self, *_a, **_kw):
        return _Mapping(rows=[])   # no active rules by default
    def commit(self): pass
    def close(self): pass
    def __enter__(self): return self
    def __exit__(self, *_): pass


def test_wrapper_allows_exploratory_at_2_of_4(monkeypatch):
    from apps.api.src.config import settings
    monkeypatch.setattr(settings, "PAPER_GATE_MODE", "exploratory")
    monkeypatch.setattr(settings, "PAPER_EXPLORATORY_MIN_GATES", 2)
    monkeypatch.setattr(settings, "PAPER_EXPLORATORY_SIZE_MULTIPLIER", 0.25)
    monkeypatch.setattr(settings, "PAPER_EXPLORATORY_REQUIRE_LOW_RISK", True)
    monkeypatch.setattr(settings, "PAPER_EXPLORATORY_BLOCK_ON_ANOMALY", True)
    monkeypatch.setattr(settings, "ALPHA_RULES_ENABLED", True)
    monkeypatch.setattr(settings, "ALPHA_RULES_MODE", "advisory")
    # Clear the runtime cache so our stub session with no rules wins
    from apps.api.src.alpha import rule_runtime
    rule_runtime.invalidate_cache()

    from apps.api.src.data.strategy.paper_decision_wrapper import (
        enrich_paper_decision,
    )
    out = enrich_paper_decision(
        _StubSession(),
        _stub_selector(fire=False),
        symbol="AAPL",
        context_values={
            "rates_calm": True, "vrp_supportive": True,
            "credit_stable": False, "liquidity_expanding": False,
        },
        data_quality={"confidence": 0.9},
        risk_level="low",
    )
    assert out.exploratory_paper is True
    assert out.paper_size_multiplier == 0.25
    assert out.strict_would_block is True


def test_wrapper_respects_strict_mode(monkeypatch):
    from apps.api.src.config import settings
    monkeypatch.setattr(settings, "PAPER_GATE_MODE", "strict")
    monkeypatch.setattr(settings, "ALPHA_RULES_ENABLED", False)
    from apps.api.src.alpha import rule_runtime
    rule_runtime.invalidate_cache()

    from apps.api.src.data.strategy.paper_decision_wrapper import (
        enrich_paper_decision,
    )
    out = enrich_paper_decision(
        _StubSession(), _stub_selector(fire=False), symbol="AAPL",
        context_values={"rates_calm": True},
    )
    assert out.exploratory_paper is False
    assert out.paper_size_multiplier == 0.0


def test_wrapper_fire_path_respects_rule_size(monkeypatch):
    from apps.api.src.config import settings
    monkeypatch.setattr(settings, "ALPHA_RULES_ENABLED", True)
    monkeypatch.setattr(settings, "ALPHA_RULES_MODE", "advisory")
    from apps.api.src.alpha import rule_runtime
    rule_runtime.invalidate_cache()

    from apps.api.src.data.strategy.paper_decision_wrapper import (
        enrich_paper_decision,
    )
    out = enrich_paper_decision(
        _StubSession(), _stub_selector(fire=True), symbol="AAPL",
        context_values={"rates_calm": True, "vrp_supportive": True,
                          "credit_stable": True,
                          "liquidity_expanding": True},
        data_quality={"confidence": 0.95}, risk_level="low",
    )
    # No active rules → full size on fire
    assert out.paper_size_multiplier == 1.0
    # Strict fire → exploratory not triggered
    assert out.exploratory_paper is False
