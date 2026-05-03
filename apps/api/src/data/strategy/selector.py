"""Selector — routes decisions between Engine A and Engine B.

Frozen Phase 21 logic. NO overlap between engines.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from apps.api.src.data.context.production import ProductionContext
from apps.api.src.data.strategy.engine_a import (
    EngineAInputs, EngineADecision, decide_engine_a,
)
from apps.api.src.data.strategy.engine_b import (
    EngineBInputs, EngineBDecision, decide_engine_b,
)

DECISION_VERSION = "selector-v1.0.0"


@dataclass(frozen=True)
class SelectorInputs:
    p15_entry: bool
    credit_stable: bool
    rates_calm: bool
    production_context: ProductionContext


@dataclass(frozen=True)
class SelectorOutput:
    engine: Literal["A", "B", "none"]
    fire: bool
    engine_a_decision: EngineADecision
    engine_b_decision: EngineBDecision
    reason: str
    decision_version: str


def select(inputs: SelectorInputs) -> SelectorOutput:
    ctx = inputs.production_context
    a_dec = decide_engine_a(EngineAInputs(
        p15_entry=inputs.p15_entry, stress_regime=ctx.stress_regime,
    ))
    b_dec = decide_engine_b(EngineBInputs(
        directional_regime=ctx.directional_regime,
        credit_stable=inputs.credit_stable, rates_calm=inputs.rates_calm,
    ))

    # Non-overlapping selector: stress -> A only, directional -> B only
    if ctx.stress_regime and a_dec.fire:
        return SelectorOutput(
            engine="A", fire=True,
            engine_a_decision=a_dec, engine_b_decision=b_dec,
            reason=a_dec.reason, decision_version=DECISION_VERSION,
        )
    if ctx.directional_regime and b_dec.fire:
        return SelectorOutput(
            engine="B", fire=True,
            engine_a_decision=a_dec, engine_b_decision=b_dec,
            reason=b_dec.reason, decision_version=DECISION_VERSION,
        )
    return SelectorOutput(
        engine="none", fire=False,
        engine_a_decision=a_dec, engine_b_decision=b_dec,
        reason=f"stress={ctx.stress_regime} directional={ctx.directional_regime} "
               f"a_fire={a_dec.fire} b_fire={b_dec.fire}",
        decision_version=DECISION_VERSION,
    )
