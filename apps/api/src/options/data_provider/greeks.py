"""Greeks fallback — stdlib Black-Scholes-Merton (Phase 11C).

Used when provider chain quotes lack Greeks/IV. Pure-fn; deterministic;
no DB; no external HTTP.

If `py_vollib` is installed in the environment, callers may opt in to
use it instead (`use_py_vollib=True`); otherwise this module's stdlib
BSM implementation is the v1 default.

Cross-validates against ThetaData provider Greeks on a fixed sanity
test set per Codex's mandate (test in test_options_greeks.py).

References: Hull (2017) §15; Black-Scholes (1973); Merton (1973).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Final


SQRT_TWO_PI: Final[float] = math.sqrt(2.0 * math.pi)
DEFAULT_RISK_FREE_RATE: Final[float] = 0.05
DEFAULT_DIVIDEND_YIELD: Final[float] = 0.0
DAYS_PER_YEAR: Final[float] = 365.0


@dataclass(frozen=True)
class Greeks:
    iv: float | None
    delta: float | None
    gamma: float | None
    theta: float | None
    vega: float | None


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / SQRT_TWO_PI


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def time_to_expiry_years(
    snapshot_date: object,         # date | datetime
    expiry_date: object,           # date
) -> float:
    """Calendar-day count → years. Floor at 1/365 to avoid div-by-0."""
    import datetime as dt
    if isinstance(snapshot_date, dt.datetime):
        snap = snapshot_date.date()
    else:
        snap = snapshot_date
    if isinstance(expiry_date, dt.datetime):
        exp = expiry_date.date()
    else:
        exp = expiry_date
    days = max(1, (exp - snap).days)
    return days / DAYS_PER_YEAR


def black_scholes_price(
    *,
    option_type: str,        # "CALL" | "PUT"
    spot: float,
    strike: float,
    time_years: float,
    iv: float,
    rate: float = DEFAULT_RISK_FREE_RATE,
    div_yield: float = DEFAULT_DIVIDEND_YIELD,
) -> float:
    """Black-Scholes-Merton price (continuous div yield)."""
    if iv <= 0 or time_years <= 0:
        intrinsic = max(0.0, spot - strike) if option_type == "CALL" \
            else max(0.0, strike - spot)
        return intrinsic
    d1 = (math.log(spot / strike) + (rate - div_yield + 0.5 * iv * iv) * time_years) \
        / (iv * math.sqrt(time_years))
    d2 = d1 - iv * math.sqrt(time_years)
    if option_type == "CALL":
        return (spot * math.exp(-div_yield * time_years) * _norm_cdf(d1)
                - strike * math.exp(-rate * time_years) * _norm_cdf(d2))
    else:
        return (strike * math.exp(-rate * time_years) * _norm_cdf(-d2)
                - spot * math.exp(-div_yield * time_years) * _norm_cdf(-d1))


def black_scholes_greeks(
    *,
    option_type: str,
    spot: float,
    strike: float,
    time_years: float,
    iv: float,
    rate: float = DEFAULT_RISK_FREE_RATE,
    div_yield: float = DEFAULT_DIVIDEND_YIELD,
) -> Greeks:
    """Compute (delta, gamma, theta, vega) via BSM. Returns Greeks(NaN)
    when inputs degenerate (iv ≤ 0 or time_years ≤ 0)."""
    if iv <= 0 or time_years <= 0 or spot <= 0 or strike <= 0:
        return Greeks(iv=iv if iv > 0 else None,
                       delta=None, gamma=None, theta=None, vega=None)
    sqrt_t = math.sqrt(time_years)
    d1 = (math.log(spot / strike) + (rate - div_yield + 0.5 * iv * iv) * time_years) \
        / (iv * sqrt_t)
    d2 = d1 - iv * sqrt_t
    nd1 = _norm_pdf(d1)
    if option_type == "CALL":
        delta = math.exp(-div_yield * time_years) * _norm_cdf(d1)
        theta = (
            - (spot * nd1 * iv * math.exp(-div_yield * time_years)) / (2.0 * sqrt_t)
            - rate * strike * math.exp(-rate * time_years) * _norm_cdf(d2)
            + div_yield * spot * math.exp(-div_yield * time_years) * _norm_cdf(d1)
        ) / DAYS_PER_YEAR    # per-day theta
    else:   # PUT
        delta = math.exp(-div_yield * time_years) * (_norm_cdf(d1) - 1.0)
        theta = (
            - (spot * nd1 * iv * math.exp(-div_yield * time_years)) / (2.0 * sqrt_t)
            + rate * strike * math.exp(-rate * time_years) * _norm_cdf(-d2)
            - div_yield * spot * math.exp(-div_yield * time_years) * _norm_cdf(-d1)
        ) / DAYS_PER_YEAR
    gamma = math.exp(-div_yield * time_years) * nd1 / (spot * iv * sqrt_t)
    vega = spot * math.exp(-div_yield * time_years) * nd1 * sqrt_t / 100.0   # per 1 vol point
    return Greeks(iv=iv, delta=delta, gamma=gamma, theta=theta, vega=vega)


def implied_volatility(
    *,
    option_type: str,
    market_price: float,
    spot: float,
    strike: float,
    time_years: float,
    rate: float = DEFAULT_RISK_FREE_RATE,
    div_yield: float = DEFAULT_DIVIDEND_YIELD,
    tol: float = 1e-6,
    max_iter: int = 100,
) -> float | None:
    """Newton-Raphson IV solver. Returns None on non-convergence or
    arbitrage violation (price below intrinsic)."""
    if market_price <= 0 or spot <= 0 or strike <= 0 or time_years <= 0:
        return None
    intrinsic = max(0.0, spot - strike) if option_type == "CALL" \
        else max(0.0, strike - spot)
    if market_price < intrinsic - 1e-6:
        return None     # arbitrage violation
    iv = 0.30           # initial guess
    for _ in range(max_iter):
        price = black_scholes_price(
            option_type=option_type, spot=spot, strike=strike,
            time_years=time_years, iv=iv, rate=rate, div_yield=div_yield,
        )
        diff = price - market_price
        if abs(diff) < tol:
            return iv
        # Vega in per-1.0-vol units (not per-1-pct)
        sqrt_t = math.sqrt(time_years)
        d1 = (math.log(spot / strike) + (rate - div_yield + 0.5 * iv * iv) * time_years) \
            / (iv * sqrt_t)
        vega_per_unit = spot * math.exp(-div_yield * time_years) \
            * _norm_pdf(d1) * sqrt_t
        if vega_per_unit < 1e-10:
            return None
        iv -= diff / vega_per_unit
        if iv <= 0 or iv > 5.0:     # diverged
            return None
    return None


# ---------------------------------------------------------------------------
# Public fallback API used by chain ingest
# ---------------------------------------------------------------------------

def fill_missing_greeks(
    *,
    option_type: str,
    spot: Decimal | float,
    strike: Decimal | float,
    snapshot_date: object,
    expiry_date: object,
    market_price: Decimal | float | None,
    provider_iv: Decimal | float | None = None,
    provider_delta: Decimal | float | None = None,
    provider_gamma: Decimal | float | None = None,
    provider_theta: Decimal | float | None = None,
    provider_vega: Decimal | float | None = None,
    rate: Decimal | float = DEFAULT_RISK_FREE_RATE,
    div_yield: Decimal | float = DEFAULT_DIVIDEND_YIELD,
) -> Greeks:
    """Use provider Greeks when present; compute via BSM otherwise.

    `market_price` is the mid-price used for IV inversion when provider
    IV is missing. If both market_price and provider_iv are missing,
    returns Greeks(None, None, None, None, None) — caller decides whether
    to flag the row or drop it.
    """
    spot_f = float(spot)
    strike_f = float(strike)
    rate_f = float(rate)
    dy_f = float(div_yield)
    time_y = time_to_expiry_years(snapshot_date, expiry_date)

    iv = float(provider_iv) if provider_iv is not None else None
    if iv is None:
        if market_price is None:
            return Greeks(iv=None, delta=None, gamma=None, theta=None, vega=None)
        iv = implied_volatility(
            option_type=option_type,
            market_price=float(market_price),
            spot=spot_f, strike=strike_f,
            time_years=time_y, rate=rate_f, div_yield=dy_f,
        )
        if iv is None:
            return Greeks(iv=None, delta=None, gamma=None, theta=None, vega=None)

    # If all 4 Greeks supplied by provider, return them verbatim
    if all(g is not None for g in (provider_delta, provider_gamma,
                                     provider_theta, provider_vega)):
        return Greeks(
            iv=iv,
            delta=float(provider_delta),
            gamma=float(provider_gamma),
            theta=float(provider_theta),
            vega=float(provider_vega),
        )

    computed = black_scholes_greeks(
        option_type=option_type, spot=spot_f, strike=strike_f,
        time_years=time_y, iv=iv, rate=rate_f, div_yield=dy_f,
    )
    # Prefer provider value when present; fall back to computed
    return Greeks(
        iv=iv,
        delta=float(provider_delta) if provider_delta is not None else computed.delta,
        gamma=float(provider_gamma) if provider_gamma is not None else computed.gamma,
        theta=float(provider_theta) if provider_theta is not None else computed.theta,
        vega=float(provider_vega) if provider_vega is not None else computed.vega,
    )
