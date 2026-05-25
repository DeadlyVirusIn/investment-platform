"""Phase L uncertainty marker catalog — locked.

Markers attached to a reasoning envelope to communicate honest hedges.
Per L.3-R §VII: markers must NEVER be paraphrased into "confidence"
language; they exist to surface uncertainty, not bury it.

7 locked markers. The renderer surfaces them verbatim with
operator-authored copy. The forbidden-phrase scanner (D2.4) is the
defense against drift.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class UncertaintyMarker(str, Enum):
    LIMITED_HISTORY = "limited_history"
    """Backtest sample size for this skeleton/regime combination is small."""

    LOW_SIGNAL_STRENGTH = "low_signal_strength"
    """Trigger signal fired close to its activation threshold."""

    REGIME_TRANSITION = "regime_transition"
    """Regime classification has been unstable over recent window."""

    PARTIAL_DATA = "partial_data"
    """One or more input data sources were stale or incomplete at decision time."""

    CROWDED_TRADE = "crowded_trade"
    """Position overlaps materially with other concurrent positions / themes."""

    COUNTER_TREND = "counter_trend"
    """Decision direction opposes prevailing regime — accept higher invalidation risk."""

    UNUSUAL_VOLATILITY = "unusual_volatility"
    """Realized or implied volatility is outside the regime's normal envelope."""


# Locked, operator-authored copy. Tonal range per L.2-E §VII:
# carefully honest. No "confidence" framing; never invert tone.
MARKER_COPY: dict[UncertaintyMarker, str] = {
    UncertaintyMarker.LIMITED_HISTORY: (
        "We've only seen this setup a handful of times — the track "
        "record is thin."
    ),
    UncertaintyMarker.LOW_SIGNAL_STRENGTH: (
        "The trigger barely cleared its threshold. A small move "
        "against us is enough to invalidate the read."
    ),
    UncertaintyMarker.REGIME_TRANSITION: (
        "Market regime has been shifting recently — the backdrop we're "
        "trading against may not last."
    ),
    UncertaintyMarker.PARTIAL_DATA: (
        "One of our inputs was stale or incomplete when we sized this. "
        "Treat the read as provisional."
    ),
    UncertaintyMarker.CROWDED_TRADE: (
        "This position overlaps with other things we're holding. "
        "Correlated drawdowns are possible."
    ),
    UncertaintyMarker.COUNTER_TREND: (
        "We're trading against the prevailing trend. The invalidation "
        "level is tighter than usual."
    ),
    UncertaintyMarker.UNUSUAL_VOLATILITY: (
        "Volatility is running outside its normal envelope. Position "
        "sizing has been pulled in."
    ),
}


def validate_markers(markers: list[UncertaintyMarker | str]) -> list[UncertaintyMarker]:
    """Coerce a list of marker strings / enum members to enum members,
    raising on unknown markers."""
    out: list[UncertaintyMarker] = []
    for m in markers:
        if isinstance(m, UncertaintyMarker):
            out.append(m)
        else:
            try:
                out.append(UncertaintyMarker(m))
            except ValueError as e:
                raise ValueError(f"unknown uncertainty marker: {m!r}") from e
    return out
