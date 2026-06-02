"""Phase C Stage 2B — economics derivation unit coverage.

Pure: compute_economics over fixture leg dicts (no DB). Reuses the real
compute_risk; asserts the money math + the null paths (incomplete, research,
unpriced).
"""

from __future__ import annotations

import datetime as dt

from apps.api.src.options.opportunities.economics import compute_economics

PAF = dt.datetime(2026, 6, 2, 14, 15, 0)
EXP = dt.date(2026, 6, 18)


def _leg(role, side, otype, strike, mid):
    return {
        "role": role, "side": side, "option_type": otype,
        "strike": strike, "expiry": EXP, "option_symbol": "X",
        "entry_mid": mid, "priced_as_of": PAF,
    }


def test_put_credit_spread_economics():
    legs = [
        _leg("short_put", "SELL", "PUT", 720, 6.815),
        _leg("long_put", "BUY", "PUT", 719, 6.565),
    ]
    e = compute_economics("SHORT_PUT_CREDIT_SPREAD", legs)
    assert e is not None
    assert round(e["max_profit"], 2) == 25.00       # credit 0.25 * 100
    assert round(e["max_risk"], 2) == 75.00         # (1 - 0.25) * 100
    assert round(e["capital_at_risk"], 2) == 75.00
    assert round(e["breakeven_lower"], 3) == 719.75
    assert e["breakeven_upper"] is None
    assert round(e["net_credit"], 2) == 25.00
    assert e["net_debit"] is None
    assert e["pop"] is None
    assert e["legs_complete"] is True
    assert e["priced_as_of"].startswith("2026-06-02T14:15")


def test_iron_condor_economics():
    legs = [
        _leg("short_put", "SELL", "PUT", 748, 4.94),
        _leg("long_put", "BUY", "PUT", 747, 4.69),
        _leg("short_call", "SELL", "CALL", 765, 5.165),
        _leg("long_call", "BUY", "CALL", 766, 4.72),
    ]
    e = compute_economics("IRON_CONDOR", legs)
    assert e is not None
    assert round(e["max_profit"], 2) == 69.50       # total credit 0.695 * 100
    assert round(e["max_risk"], 2) == 30.50         # (1 - 0.695) * 100
    assert round(e["breakeven_lower"], 3) == 747.305
    assert round(e["breakeven_upper"], 3) == 765.695


def test_incomplete_returns_none():
    legs = [_leg("short_put", "SELL", "PUT", 720, 6.815)]  # only 1 of 2
    assert compute_economics("SHORT_PUT_CREDIT_SPREAD", legs) is None


def test_research_structure_returns_none():
    legs = [_leg("short_put", "SELL", "PUT", 720, 6.815),
            _leg("long_put", "BUY", "PUT", 719, 6.565)]
    assert compute_economics("LONG_STRADDLE", legs) is None


def test_unpriced_leg_returns_none():
    legs = [
        _leg("short_put", "SELL", "PUT", 720, 6.815),
        _leg("long_put", "BUY", "PUT", 719, None),  # unpriced
    ]
    assert compute_economics("SHORT_PUT_CREDIT_SPREAD", legs) is None
