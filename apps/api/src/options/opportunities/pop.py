"""Phase F2 — probability of profit (POP), Black-Scholes at expiry.

Pure math. POP = probability the underlying finishes on the profitable side
of the breakeven(s) at expiry, under lognormal moves at the current implied
volatility, r=0. NO delta approximation.

Structure is inferred from which breakevens are present (no rule_id coupling):
  * both breakevens  → iron condor   : N(d2_lower) − N(d2_upper)
  * lower only       → put credit spread  : N(d2_lower)        [P(S_T > BE)]
  * upper only       → call credit spread : 1 − N(d2_upper)    [P(S_T < BE)]

Returns an int 0–100, or None when any required input is missing/invalid
(honest — never a fabricated number).
"""

from __future__ import annotations

import math


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _d2(spot: float, strike: float, t: float, vol: float, r: float = 0.0) -> float | None:
    if spot <= 0 or strike <= 0 or t <= 0 or vol <= 0:
        return None
    return (math.log(spot / strike) + (r - 0.5 * vol * vol) * t) / (vol * math.sqrt(t))


def pop_at_expiry(
    *,
    spot: float | None,
    be_lower: float | None,
    be_upper: float | None,
    t: float | None,
    vol_lower: float | None,
    vol_upper: float | None,
    r: float = 0.0,
) -> int | None:
    """Whole-percent POP, or None when inputs are insufficient."""
    if spot is None or t is None or t <= 0:
        return None

    has_lo = be_lower is not None and vol_lower is not None and vol_lower > 0
    has_hi = be_upper is not None and vol_upper is not None and vol_upper > 0

    if has_lo and has_hi:
        dl = _d2(spot, be_lower, t, vol_lower, r)
        du = _d2(spot, be_upper, t, vol_upper, r)
        if dl is None or du is None:
            return None
        p = _norm_cdf(dl) - _norm_cdf(du)          # P(BE_lo < S_T < BE_hi)
    elif has_lo:
        dl = _d2(spot, be_lower, t, vol_lower, r)
        if dl is None:
            return None
        p = _norm_cdf(dl)                          # P(S_T > BE_lo)
    elif has_hi:
        du = _d2(spot, be_upper, t, vol_upper, r)
        if du is None:
            return None
        p = 1.0 - _norm_cdf(du)                    # P(S_T < BE_hi)
    else:
        return None

    p = max(0.0, min(1.0, p))
    return round(p * 100)
