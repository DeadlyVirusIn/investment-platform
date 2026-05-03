"""Ingestion-boundary normalizers for execution-layer inputs.

Single source of truth for:
  - confidence scale       (DB stores 0-100 pct; execution expects 0-1)
  - volatility scale       (execution layer EXPECTS ANNUALIZED vol)

Apply these at the boundary where PrimarySignal is constructed. Downstream
sizing functions then consume already-normalized values — NO manual
division / sqrt scattered anywhere else in the codebase.
"""

from __future__ import annotations

import math

# ---------------------------------------------------------------------------
# Invariants
# ---------------------------------------------------------------------------

TRADING_DAYS_PER_YEAR: int = 252

# Validation bounds for annualized vol. Equity upper bound ~200% annualized
# (extremely volatile names); below 0.1% is likely a unit-scale bug.
VOL_MIN: float = 1e-4      # 0.01% annual — below this is degenerate
VOL_MAX: float = 2.0       # 200% annual — above this almost certainly a bug


# ---------------------------------------------------------------------------
# Confidence
# ---------------------------------------------------------------------------


def normalize_confidence(value: float | int | None) -> float:
    """Normalize a confidence value to fractional [0, 1].

    DB stores confidence as a percentage (e.g. 71.2). Execution-layer
    consumers expect fractional (0.712). This helper converts in one place.

    Rules:
      - None / non-numeric → 0.0
      - value > 1.0        → divided by 100.0 (percent → fractional)
      - then clipped to [0, 1]
    """
    if value is None:
        return 0.0
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0
    if v > 1.0:
        v = v / 100.0
    return max(0.0, min(v, 1.0))


# ---------------------------------------------------------------------------
# Volatility
# ---------------------------------------------------------------------------


class VolatilityScaleError(ValueError):
    """Raised when volatility is out of the annualized-scale sanity bounds."""


def ensure_annualized_vol(vol: float | int | None, is_daily: bool) -> float:
    """Return annualized volatility.

    If `is_daily=True`, multiply by sqrt(252). If already annualized, return
    unchanged. Zero or invalid inputs collapse to 0.0 (caller must handle
    downstream — e.g. kelly refuses bet on zero variance).
    """
    if vol is None:
        return 0.0
    try:
        v = float(vol)
    except (TypeError, ValueError):
        return 0.0
    if v <= 0:
        return 0.0
    if is_daily:
        v = v * math.sqrt(TRADING_DAYS_PER_YEAR)
    return v


def validate_annualized_vol(vol: float) -> None:
    """Assert vol is inside annualized-scale sanity bounds.

    Raises VolatilityScaleError if below VOL_MIN or above VOL_MAX.
    """
    if not (VOL_MIN < vol < VOL_MAX):
        raise VolatilityScaleError(
            f"vol={vol!r} outside annualized bounds "
            f"({VOL_MIN}, {VOL_MAX}) — likely a scale bug"
        )
