"""Engine A — P15 mean reversion on stress regime. READ-ONLY ADAPTER.

Wraps frozen logic from scripts/run_phase15_mean_reversion.py + Phase 21
stress-regime gate. Does not alter thresholds. Any change requires new
decision_version.
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.api.src.data.features.registry import get_registry
from apps.api.src.data.context.production import ProductionContext

DECISION_VERSION = "engineA-v1.0.0"
HOLD_BARS = 10


@dataclass(frozen=True)
class EngineAInputs:
    p15_entry: bool       # output of frozen P15 entry: ATR10/ATR50>1.2 & vol & z<-1
    stress_regime: bool   # output of production context classifier


@dataclass(frozen=True)
class EngineADecision:
    fire: bool
    reason: str
    decision_version: str
    hold_bars: int


def decide_engine_a(inputs: EngineAInputs) -> EngineADecision:
    """Read-only adapter. Enforces production-feature requirement via registry."""
    reg = get_registry()
    reg.require_production_feature("p15_entry")
    reg.require_production_context("stress_regime")

    if inputs.p15_entry and inputs.stress_regime:
        return EngineADecision(
            fire=True,
            reason="stress_regime=True AND p15_entry=True",
            decision_version=DECISION_VERSION,
            hold_bars=HOLD_BARS,
        )
    return EngineADecision(
        fire=False,
        reason=(f"p15_entry={inputs.p15_entry} "
                f"stress_regime={inputs.stress_regime}"),
        decision_version=DECISION_VERSION,
        hold_bars=HOLD_BARS,
    )
