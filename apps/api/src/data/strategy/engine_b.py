"""Engine B — credit_stable AND rates_calm on directional regime.

READ-ONLY ADAPTER. Frozen Phase 22 logic.
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.api.src.data.features.registry import get_registry

DECISION_VERSION = "engineB-v1.0.0"
HOLD_BARS = 1


@dataclass(frozen=True)
class EngineBInputs:
    directional_regime: bool
    credit_stable: bool
    rates_calm: bool


@dataclass(frozen=True)
class EngineBDecision:
    fire: bool
    reason: str
    decision_version: str
    hold_bars: int


def decide_engine_b(inputs: EngineBInputs) -> EngineBDecision:
    reg = get_registry()
    reg.require_production_feature("credit_stable")
    reg.require_production_feature("rates_calm")
    reg.require_production_context("directional_regime")

    if (inputs.directional_regime
        and inputs.credit_stable and inputs.rates_calm):
        return EngineBDecision(
            fire=True,
            reason="directional_regime + credit_stable + rates_calm",
            decision_version=DECISION_VERSION,
            hold_bars=HOLD_BARS,
        )
    return EngineBDecision(
        fire=False,
        reason=(f"directional_regime={inputs.directional_regime} "
                f"credit_stable={inputs.credit_stable} "
                f"rates_calm={inputs.rates_calm}"),
        decision_version=DECISION_VERSION,
        hold_bars=HOLD_BARS,
    )
