"""Shadow strategy V2 — TSMOM 60d + persist-3 MA200 stress filter.

Parallel to current B2 (`tsmom_60_no_stress`). NEVER replaces B2.
Reads regime labels from `research_backfill_persist3_v1` rows in
context_daily (status='diagnostic').

Same TSMOM 60d signal computation as B2; only the stress flag input
differs.

NEVER writes to paper_trade_log, decision_log, or any production
execution surface. Idempotent on (as_of_date, instrument,
source_strategy='tsmom_60_no_stress_v2_persist3').
"""

from __future__ import annotations

from datetime import date

from apps.api.src.research.shadow_strategy import (
    INSTRUMENT_DEFAULT, ShadowDecision, _tsmom_60_signal,
)


SOURCE_STRATEGY_V2 = "tsmom_60_no_stress_v2_persist3"
REGIME_LOGIC_VERSION_V2 = "research_backfill_persist3_v1"


def compute_decision_v2(
    *,
    as_of_date: date,
    closes_thru_today,
    stress_regime_persist3: bool,
    directional_regime_persist3: bool,
    engine_a_active: bool,
    instrument: str = INSTRUMENT_DEFAULT,
) -> ShadowDecision:
    """V2 decision: TSMOM 60d * NOT(persist3 stress).

    Caller passes regime flags computed under the persist3 logic
    version.
    """
    base_signal, mom = _tsmom_60_signal(closes_thru_today)

    note_parts: list[str] = []
    if stress_regime_persist3:
        signal = "FLAT"
        note_parts.append("filtered: persist3_stress=True")
    else:
        signal = base_signal
        if base_signal == "LONG":
            note_parts.append(f"tsmom_60 mom={mom:.4f}")
        else:
            note_parts.append("tsmom_60 momentum non-positive")

    regime = (
        "STRESS" if stress_regime_persist3
        else "DIRECTIONAL" if directional_regime_persist3
        else "NEUTRAL"
    )

    last_close = (float(closes_thru_today[-1])
                    if len(closes_thru_today) else None)

    return ShadowDecision(
        as_of_date=as_of_date,
        instrument=instrument,
        source_strategy=SOURCE_STRATEGY_V2,
        signal=signal,
        entry_price=last_close if signal == "LONG" else None,
        regime_label=regime,
        engine_a_active=bool(engine_a_active),
        trend_score=mom,
        note="; ".join(note_parts),
    )
