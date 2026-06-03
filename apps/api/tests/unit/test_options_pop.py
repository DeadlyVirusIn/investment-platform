"""Phase F2 — Black-Scholes POP unit coverage.

Reproduces the audit reference fixtures (QQQ put-credit-spread ≈76%, SPY iron
condor ≈40%) + null-input paths. Pure math; no DB.
"""

from __future__ import annotations

from apps.api.src.options.opportunities.pop import pop_at_expiry


def test_qqq_put_credit_spread_reference():
    # spot 746.16, breakeven 699.65, T 0.1205, short-leg IV 0.2513 → ~76%
    pop = pop_at_expiry(
        spot=746.159973, be_lower=699.65, be_upper=None, t=0.1205,
        vol_lower=0.2513, vol_upper=None,
    )
    assert pop is not None and 75 <= pop <= 77


def test_spy_iron_condor_reference():
    # spot 759.57, BE 739.435/778.565, T 0.1205, put IV 0.1573, call IV 0.126 → ~40%
    pop = pop_at_expiry(
        spot=759.570007, be_lower=739.435, be_upper=778.565, t=0.1205,
        vol_lower=0.1573, vol_upper=0.126,
    )
    assert pop is not None and 39 <= pop <= 41


def test_call_credit_spread_is_below_breakeven():
    # call spread: profit if S_T < breakeven → uses 1 - N(d2)
    pop = pop_at_expiry(
        spot=100.0, be_lower=None, be_upper=110.0, t=0.1,
        vol_lower=None, vol_upper=0.30,
    )
    assert pop is not None and 60 <= pop <= 95


def test_null_when_inputs_insufficient():
    assert pop_at_expiry(spot=None, be_lower=700, be_upper=None, t=0.1,
                         vol_lower=0.25, vol_upper=None) is None
    assert pop_at_expiry(spot=746, be_lower=700, be_upper=None, t=0.0,
                         vol_lower=0.25, vol_upper=None) is None
    assert pop_at_expiry(spot=746, be_lower=700, be_upper=None, t=0.1,
                         vol_lower=None, vol_upper=None) is None
    assert pop_at_expiry(spot=746, be_lower=None, be_upper=None, t=0.1,
                         vol_lower=None, vol_upper=None) is None
