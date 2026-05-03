"""Production context labels — stress_regime, directional_regime.

IMMUTABLE PER VERSION. Do not modify logic without bumping version AND
promoting via registry review process.
"""

from __future__ import annotations

from dataclasses import dataclass

LOGIC_VERSION = "v1.0.0"


@dataclass(frozen=True)
class ProductionContext:
    stress_regime: bool
    directional_regime: bool
    gates_favorable_count: int
    logic_version: str
    logic_fingerprint: str


def classify_production_context(gates_favorable: int) -> ProductionContext:
    """Phase 21 frozen logic: stress <= 1, directional >= 2.

    gates_favorable counts the number of true production gates:
      rates_calm, vrp_supportive, credit_stable, liquidity_expanding
    """
    stress = gates_favorable <= 1
    directional = gates_favorable >= 2
    return ProductionContext(
        stress_regime=stress,
        directional_regime=directional,
        gates_favorable_count=gates_favorable,
        logic_version=LOGIC_VERSION,
        logic_fingerprint=f"stress:gates<=1|directional:gates>=2:{LOGIC_VERSION}",
    )
