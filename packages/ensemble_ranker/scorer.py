"""Phase 1 ranker — product of signal_strength × confidence, clamped.

Deterministic. Pure. No correlation, no regime, no family weights, no
scorecard feedback. Five-line contract.
"""

from __future__ import annotations

import math
from typing import Iterable

from loguru import logger

from packages.signal_schema.ranked_signal import RankedSignal
from packages.signal_schema.signal import Signal


def _clamped(v) -> float:
    """Coerce to non-negative float. NaN/None/negative → 0.0 with warn log."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        logger.warning("[ranker] invalid score input {!r}; clamping to 0", v)
        return 0.0
    if math.isnan(f):
        logger.warning("[ranker] NaN score input; clamping to 0")
        return 0.0
    if f < 0:
        logger.warning("[ranker] negative score input {} clamped to 0", f)
        return 0.0
    return f


def rank(signals: Iterable[Signal]) -> list[RankedSignal]:
    """Return signals sorted by score desc. One RankedSignal per input."""
    out: list[RankedSignal] = []
    for s in signals:
        score = _clamped(s.signal_strength) * _clamped(s.confidence)
        out.append(RankedSignal(
            asset_id=s.asset_id,
            symbol=s.symbol,
            score=score,
            contributing=[s],
        ))
    return sorted(out, key=lambda r: -r.score)
