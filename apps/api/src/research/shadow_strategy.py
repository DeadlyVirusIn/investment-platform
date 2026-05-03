"""Shadow strategy compute — pure functions + idempotent upsert.

Contract:
  • NEVER writes to paper_trade_log, decision_log, or any production
    execution table.
  • NEVER mutates risk parameters or scheduler state.
  • NEVER affects ML pipeline.
  • Idempotent per (as_of_date, instrument, source_strategy):
    re-running upsert with same input is a no-op.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session


SOURCE_STRATEGY = "tsmom_60_no_stress"
INSTRUMENT_DEFAULT = "ES"
TSMOM_HORIZON = 60


def engine_b_signal_proxy(*, directional_regime: bool) -> str:
    """Research-proxy for Engine B's directional decision.

    Real Engine B requires (directional_regime AND credit_stable AND
    rates_calm). For backtest comparison we approximate using only
    directional_regime, which is PIT-safe in research_backfill_v1.

    Production Engine B execution remains independent of this proxy —
    this function is consumed only by the shadow logger / router.
    """
    return "LONG" if bool(directional_regime) else "FLAT"


# ---------------------------------------------------------------------------
# Pure compute
# ---------------------------------------------------------------------------

def _tsmom_60_signal(closes: Sequence[float]) -> tuple[str, float | None]:
    """Returns (signal, momentum_value).

    signal: 'LONG' if 60d momentum > 0 else 'FLAT'.
    """
    cl = [float(c) for c in closes if c is not None]
    if len(cl) < TSMOM_HORIZON + 1:
        return "FLAT", None
    a = cl[-(TSMOM_HORIZON + 1)]
    b = cl[-1]
    if a == 0:
        return "FLAT", None
    mom = b / a - 1.0
    return ("LONG" if mom > 0 else "FLAT"), mom


@dataclass(frozen=True)
class ShadowDecision:
    as_of_date: date
    instrument: str
    source_strategy: str
    signal: str             # LONG | FLAT
    entry_price: float | None
    regime_label: str | None
    engine_a_active: bool
    trend_score: float | None
    note: str

    def to_dict(self) -> dict:
        return {
            "as_of_date": self.as_of_date.isoformat()
                if hasattr(self.as_of_date, "isoformat") else str(self.as_of_date),
            "instrument": self.instrument,
            "source_strategy": self.source_strategy,
            "signal": self.signal,
            "entry_price": self.entry_price,
            "regime_label": self.regime_label,
            "engine_a_active": self.engine_a_active,
            "trend_score": (round(self.trend_score, 6)
                              if self.trend_score is not None else None),
            "note": self.note,
        }


def compute_decision(
    *,
    as_of_date: date,
    closes_thru_today: Sequence[float],
    stress_regime: bool,
    directional_regime: bool,
    engine_a_active: bool,
    instrument: str = INSTRUMENT_DEFAULT,
) -> ShadowDecision:
    """Pure decision: TSMOM 60d * NOT stress."""
    base_signal, mom = _tsmom_60_signal(closes_thru_today)

    note_parts: list[str] = []
    if stress_regime:
        signal = "FLAT"
        note_parts.append("filtered: stress_regime=True")
    else:
        signal = base_signal
        if base_signal == "LONG":
            note_parts.append(f"tsmom_60 mom={mom:.4f}")
        else:
            note_parts.append("tsmom_60 momentum non-positive")

    regime = (
        "STRESS" if stress_regime
        else "DIRECTIONAL" if directional_regime
        else "NEUTRAL"
    )

    last_close = (float(closes_thru_today[-1])
                    if len(closes_thru_today) else None)

    return ShadowDecision(
        as_of_date=as_of_date,
        instrument=instrument,
        source_strategy=SOURCE_STRATEGY,
        signal=signal,
        entry_price=last_close if signal == "LONG" else None,
        regime_label=regime,
        engine_a_active=bool(engine_a_active),
        trend_score=mom,
        note="; ".join(note_parts),
    )


# ---------------------------------------------------------------------------
# Idempotent upsert
# ---------------------------------------------------------------------------

UPSERT_SQL = text("""
INSERT INTO paper_shadow_log (
    as_of_date, instrument, source_strategy, signal,
    entry_price, regime_label, engine_a_active,
    trend_score, note,
    engine_b_signal, b2_signal, divergence_flag,
    mode_at_decision, routed_signal
)
VALUES (
    :as_of_date, :instrument, :source_strategy, :signal,
    :entry_price, :regime_label, :engine_a_active,
    :trend_score, :note,
    :engine_b_signal, :b2_signal, :divergence_flag,
    :mode_at_decision, :routed_signal
)
ON CONFLICT (as_of_date, instrument, source_strategy)
DO UPDATE SET
    signal           = EXCLUDED.signal,
    entry_price      = EXCLUDED.entry_price,
    regime_label     = EXCLUDED.regime_label,
    engine_a_active  = EXCLUDED.engine_a_active,
    trend_score      = EXCLUDED.trend_score,
    note             = EXCLUDED.note,
    engine_b_signal  = EXCLUDED.engine_b_signal,
    b2_signal        = EXCLUDED.b2_signal,
    divergence_flag  = EXCLUDED.divergence_flag,
    mode_at_decision = EXCLUDED.mode_at_decision,
    routed_signal    = EXCLUDED.routed_signal,
    updated_at       = now()
""")


def upsert_decision(
    session: Session,
    d: ShadowDecision,
    *,
    engine_b_signal: str | None = None,
    b2_signal: str | None = None,
    mode_at_decision: str | None = None,
    routed_signal: str | None = None,
) -> None:
    """Upsert a shadow decision row. Idempotent per natural key.

    Optional B-vs-B2 columns default to NULL (preserves backwards
    compatibility for callers that haven't been updated).
    """
    div_flag = (engine_b_signal is not None and b2_signal is not None
                  and str(engine_b_signal).upper() != str(b2_signal).upper())
    session.execute(UPSERT_SQL, {
        "as_of_date":       d.as_of_date,
        "instrument":       d.instrument,
        "source_strategy":  d.source_strategy,
        "signal":           d.signal,
        "entry_price":      d.entry_price,
        "regime_label":     d.regime_label,
        "engine_a_active":  bool(d.engine_a_active),
        "trend_score":      (None if d.trend_score is None
                                else float(d.trend_score)),
        "note":             d.note[:500] if d.note else None,
        "engine_b_signal":  engine_b_signal,
        "b2_signal":        b2_signal,
        "divergence_flag":  bool(div_flag),
        "mode_at_decision": mode_at_decision,
        "routed_signal":    routed_signal,
    })


# ---------------------------------------------------------------------------
# Forward-return back-fill (1d / 5d realized)
# ---------------------------------------------------------------------------

BACKFILL_SQL = text("""
UPDATE paper_shadow_log
   SET fwd_return_1d      = :ret1d,
       fwd_return_5d      = :ret5d,
       exit_price         = :exit_price,
       divergence_outcome = CASE
            WHEN engine_b_signal IS NULL OR b2_signal IS NULL
                THEN divergence_outcome
            WHEN engine_b_signal = b2_signal
                THEN 0.0
            WHEN engine_b_signal = 'LONG' AND b2_signal = 'FLAT'
                THEN :ret1d
            WHEN engine_b_signal = 'FLAT' AND b2_signal = 'LONG'
                THEN -1.0 * :ret1d
            ELSE divergence_outcome
        END,
       updated_at         = now()
 WHERE as_of_date      = :as_of_date
   AND instrument      = :instrument
   AND source_strategy = :source_strategy
""")


def backfill_forward_returns(
    session: Session,
    *,
    as_of_date: date,
    instrument: str,
    source_strategy: str,
    fwd_return_1d: float | None,
    fwd_return_5d: float | None,
    exit_price: float | None,
) -> int:
    """Update an existing row with realized forward returns.

    Also computes `divergence_outcome` = realized B return − realized B2
    return on the same as_of_date. Positive = B beat B2 on this day;
    negative = B2 beat B.
    """
    res = session.execute(BACKFILL_SQL, {
        "as_of_date": as_of_date,
        "instrument": instrument,
        "source_strategy": source_strategy,
        "ret1d": fwd_return_1d,
        "ret5d": fwd_return_5d,
        "exit_price": exit_price,
    })
    return res.rowcount or 0
