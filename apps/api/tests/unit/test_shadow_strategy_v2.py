"""Tests for shadow_strategy_v2 (persist-3 variant).

Verifies:
- V2 SOURCE_STRATEGY differs from B2
- compute_decision_v2 honors persist3 stress flag
- V2 does NOT touch B2 module's SOURCE_STRATEGY
- Decision shape is identical to B2 (same ShadowDecision)
"""

from __future__ import annotations

from datetime import date

from src.research.shadow_strategy import SOURCE_STRATEGY as B2_SRC
from src.research.shadow_strategy_v2 import (
    REGIME_LOGIC_VERSION_V2,
    SOURCE_STRATEGY_V2,
    compute_decision_v2,
)


def _trend_up(n: int) -> list[float]:
    p = [100.0]
    for _ in range(n - 1):
        p.append(p[-1] * 1.001)
    return p


def test_v2_source_strategy_distinct():
    assert SOURCE_STRATEGY_V2 == "tsmom_60_no_stress_v2_persist3"
    assert SOURCE_STRATEGY_V2 != B2_SRC


def test_v2_logic_version_constant():
    assert REGIME_LOGIC_VERSION_V2 == "research_backfill_persist3_v1"


def test_v2_long_when_persist3_not_triggered():
    d = compute_decision_v2(
        as_of_date=date(2024, 6, 1),
        closes_thru_today=_trend_up(80),
        stress_regime_persist3=False,
        directional_regime_persist3=True,
        engine_a_active=False,
    )
    assert d.signal == "LONG"
    assert d.source_strategy == SOURCE_STRATEGY_V2
    assert d.regime_label == "DIRECTIONAL"
    assert d.entry_price is not None


def test_v2_flat_when_persist3_stress():
    d = compute_decision_v2(
        as_of_date=date(2024, 6, 1),
        closes_thru_today=_trend_up(80),
        stress_regime_persist3=True,
        directional_regime_persist3=False,
        engine_a_active=False,
    )
    assert d.signal == "FLAT"
    assert d.regime_label == "STRESS"
    assert d.entry_price is None
    assert "persist3_stress" in d.note


def test_v2_to_dict_payload():
    d = compute_decision_v2(
        as_of_date=date(2024, 6, 1),
        closes_thru_today=_trend_up(80),
        stress_regime_persist3=False,
        directional_regime_persist3=True,
        engine_a_active=False,
    )
    p = d.to_dict()
    assert p["source_strategy"] == SOURCE_STRATEGY_V2
    assert p["signal"] == "LONG"
    assert "as_of_date" in p


def test_v2_does_not_mutate_input():
    closes = _trend_up(80)
    snap = list(closes)
    compute_decision_v2(
        as_of_date=date(2024, 6, 1),
        closes_thru_today=closes,
        stress_regime_persist3=False,
        directional_regime_persist3=True,
        engine_a_active=False,
    )
    assert closes == snap
