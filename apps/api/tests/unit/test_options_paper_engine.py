"""Phase 11E unit tests — paper-trading engine pure functions.

Covers:
  * Fill price logic (BUY=mid+slip, SELL=mid-slip, illiquid reject)
  * Strategy validation: defined-risk only, naked rejected
  * Risk metrics: vertical + iron condor max_loss, max_profit, breakevens
  * Expiration payoff per leg, classification, pin-risk band
  * PnL closed-pre-expiry vs held-to-expiry
  * Greeks aggregation signs by side
  * Boundary grep — no V2 / equity / strategy imports
"""

from __future__ import annotations

import datetime as dt
import importlib
import re
from decimal import Decimal
from pathlib import Path

import pytest

from apps.api.src.options.data_provider.base_adapter import OptionChainQuote
from apps.api.src.options.paper.expiration import (
    CLASSIFICATION_ITM,
    CLASSIFICATION_OTM,
    CLASSIFICATION_PIN_RISK,
    CLASSIFICATION_MISSING,
    FLAG_ASSIGNMENT_SIMPLIFIED_EXIT,
    FLAG_PIN_RISK_UNCERTAIN_OUTCOME,
    expire_legs,
    classify_leg,
)
from apps.api.src.options.paper.fills import (
    DEFAULT_FEE_PER_CONTRACT,
    FILL_MODEL_VERSION,
    REJECT_NO_MID,
    compute_fill,
    fees_for,
    slippage_per_contract,
    total_fees_for_legs,
)
from apps.api.src.options.paper.pnl import (
    GreeksSnapshot,
    aggregate_greeks,
    open_cash_flow_for_leg,
    trade_pnl_closed,
    trade_pnl_expired,
)
from apps.api.src.options.paper.strategies import (
    CONTRACT_MULTIPLIER,
    LegSpec,
    STRATEGY_IRON_CONDOR,
    STRATEGY_SHORT_CALL_CREDIT_SPREAD,
    STRATEGY_SHORT_PUT_CREDIT_SPREAD,
    compute_risk,
    net_credit_dollars,
    validate_defined_risk,
)


def _q(
    *, option_type="CALL", strike=450.0, bid=1.50, ask=1.55,
    volume=100, open_interest=1000, quote_age_seconds=2,
    delta=0.50, gamma=0.02, iv=0.20,
) -> OptionChainQuote:
    expiry = dt.date(2026, 6, 18)
    snap = dt.datetime(2026, 5, 18, 14, 0, tzinfo=dt.timezone.utc)
    mid = (bid + ask) / 2 if (bid is not None and ask is not None) else None
    return OptionChainQuote(
        snapshot_at_utc=snap, underlying="SPY",
        expiry=expiry, strike=Decimal(str(strike)),
        option_type=option_type,
        option_symbol=f"SPY260618{option_type[0]}{int(strike*1000):08d}",
        bid=Decimal(str(bid)) if bid is not None else None,
        ask=Decimal(str(ask)) if ask is not None else None,
        mid=Decimal(str(mid)) if mid is not None else None,
        last=None, volume=volume, open_interest=open_interest,
        delta=Decimal(str(delta)) if delta is not None else None,
        gamma=Decimal(str(gamma)) if gamma is not None else None,
        theta=Decimal("-0.05"), vega=Decimal("0.10"),
        iv=Decimal(str(iv)) if iv is not None else None,
        quote_age_seconds=quote_age_seconds, provider="thetadata",
    )


def _leg(side="SELL", option_type="PUT", strike=440.0, qty=1) -> LegSpec:
    return LegSpec(
        side=side, option_type=option_type,
        strike=Decimal(str(strike)),
        expiry=dt.date(2026, 6, 18),
        qty=qty,
        option_symbol=f"SPY260618{option_type[0]}{int(strike*1000):08d}",
    )


# ===========================================================================
# Fills
# ===========================================================================

def test_buy_fill_is_mid_plus_slip():
    q = _q(bid=1.50, ask=1.55)
    f = compute_fill(q, side="BUY")
    assert f.accepted
    assert f.fill_price == Decimal("1.525") + Decimal("0.025")


def test_sell_fill_is_mid_minus_slip():
    q = _q(bid=1.50, ask=1.55)
    f = compute_fill(q, side="SELL")
    assert f.accepted
    assert f.fill_price == Decimal("1.525") - Decimal("0.025")


def test_sell_fill_floored_at_bid():
    """SELL fill cannot drop below the bid even when mid − slip rounds at it."""
    q = _q(bid=1.50, ask=1.51)
    f = compute_fill(q, side="SELL")
    assert f.accepted
    assert f.fill_price >= q.bid


def test_fill_rejects_low_open_interest():
    q = _q(open_interest=10)
    f = compute_fill(q, side="BUY")
    assert not f.accepted
    assert f.reason == "LOW_OPEN_INTEREST"


def test_fill_rejects_wide_spread():
    q = _q(bid=1.50, ask=2.00)
    f = compute_fill(q, side="BUY")
    assert not f.accepted
    assert f.reason == "WIDE_SPREAD"


def test_fill_rejects_stale_quote():
    q = _q(quote_age_seconds=999)
    f = compute_fill(q, side="BUY")
    assert not f.accepted
    assert f.reason == "STALE_QUOTE"


def test_fill_rejects_missing_mid_when_bypassing_liquidity():
    """If liquidity is forced off but mid is None, still rejects."""
    q = _q(bid=None, ask=None)
    f = compute_fill(q, side="BUY", enforce_liquidity=False)
    assert not f.accepted
    assert f.reason == REJECT_NO_MID


def test_slippage_capped_at_default():
    q = _q(bid=1.50, ask=1.55)
    assert slippage_per_contract(q) == Decimal("0.025")


def test_fees_round_trip_per_leg():
    one_leg_fee = fees_for(2)
    assert one_leg_fee == Decimal("2") * DEFAULT_FEE_PER_CONTRACT
    rt = total_fees_for_legs([2, 2])
    assert rt == Decimal("8") * DEFAULT_FEE_PER_CONTRACT


def test_fill_model_version_is_pinned():
    assert FILL_MODEL_VERSION == "v1.conservative"


# ===========================================================================
# Strategy validation
# ===========================================================================

def test_validate_short_put_credit_spread_ok():
    legs = [
        _leg(side="SELL", option_type="PUT", strike=440),
        _leg(side="BUY",  option_type="PUT", strike=435),
    ]
    validate_defined_risk(STRATEGY_SHORT_PUT_CREDIT_SPREAD, legs)


def test_validate_short_call_credit_spread_ok():
    legs = [
        _leg(side="SELL", option_type="CALL", strike=460),
        _leg(side="BUY",  option_type="CALL", strike=465),
    ]
    validate_defined_risk(STRATEGY_SHORT_CALL_CREDIT_SPREAD, legs)


def test_validate_iron_condor_ok():
    legs = [
        _leg(side="BUY",  option_type="PUT",  strike=430),
        _leg(side="SELL", option_type="PUT",  strike=440),
        _leg(side="SELL", option_type="CALL", strike=460),
        _leg(side="BUY",  option_type="CALL", strike=470),
    ]
    validate_defined_risk(STRATEGY_IRON_CONDOR, legs)


def test_validate_rejects_naked_short_put():
    """Single SELL leg = naked short, rejected."""
    legs = [_leg(side="SELL", option_type="PUT", strike=440)]
    with pytest.raises(ValueError):
        validate_defined_risk(STRATEGY_SHORT_PUT_CREDIT_SPREAD, legs)


def test_validate_rejects_unknown_strategy_name():
    legs = [_leg(side="SELL", option_type="PUT", strike=440)]
    with pytest.raises(ValueError):
        validate_defined_risk("LONG_STRADDLE", legs)


def test_validate_rejects_inverted_credit_spread():
    """Short put strike must be ABOVE long put strike for defined risk."""
    legs = [
        _leg(side="SELL", option_type="PUT", strike=435),
        _leg(side="BUY",  option_type="PUT", strike=440),
    ]
    with pytest.raises(ValueError):
        validate_defined_risk(STRATEGY_SHORT_PUT_CREDIT_SPREAD, legs)


# ===========================================================================
# Risk metrics
# ===========================================================================

def test_risk_short_put_credit_spread_max_loss_and_profit():
    legs = [
        _leg(side="SELL", option_type="PUT", strike=440, qty=2),
        _leg(side="BUY",  option_type="PUT", strike=435, qty=2),
    ]
    fills = [Decimal("1.20"), Decimal("0.50")]   # net credit = 0.70
    r = compute_risk(STRATEGY_SHORT_PUT_CREDIT_SPREAD, legs, fills)
    width = Decimal("5")
    expected_loss = (width - Decimal("0.70")) * Decimal("100") * Decimal("2")
    expected_profit = Decimal("0.70") * Decimal("100") * Decimal("2")
    assert r.max_loss_dollars == expected_loss
    assert r.max_profit_dollars == expected_profit
    assert r.breakeven_lower == Decimal("440") - Decimal("0.70")
    assert r.breakeven_upper is None


def test_risk_iron_condor_max_loss_uses_widest_wing():
    legs = [
        _leg(side="BUY",  option_type="PUT",  strike=425, qty=1),
        _leg(side="SELL", option_type="PUT",  strike=440, qty=1),     # put width=15
        _leg(side="SELL", option_type="CALL", strike=460, qty=1),
        _leg(side="BUY",  option_type="CALL", strike=465, qty=1),     # call width=5
    ]
    fills = [
        Decimal("0.40"),    # long put
        Decimal("1.20"),    # short put
        Decimal("1.10"),    # short call
        Decimal("0.30"),    # long call
    ]
    # net credit per contract = (1.20 + 1.10) − (0.40 + 0.30) = 1.60
    r = compute_risk(STRATEGY_IRON_CONDOR, legs, fills)
    expected_loss = (Decimal("15") - Decimal("1.60")) * Decimal("100")    # widest wing (put=15)
    expected_profit = Decimal("1.60") * Decimal("100")
    assert r.max_loss_dollars == expected_loss
    assert r.max_profit_dollars == expected_profit
    assert r.breakeven_lower == Decimal("440") - Decimal("1.60")
    assert r.breakeven_upper == Decimal("460") + Decimal("1.60")


def test_risk_floors_at_zero_when_credit_exceeds_width():
    """Degenerate input (credit > width) should not produce negative loss."""
    legs = [
        _leg(side="SELL", option_type="PUT", strike=440),
        _leg(side="BUY",  option_type="PUT", strike=435),
    ]
    fills = [Decimal("10"), Decimal("0.50")]   # absurd net credit = 9.50 > width 5
    r = compute_risk(STRATEGY_SHORT_PUT_CREDIT_SPREAD, legs, fills)
    assert r.max_loss_dollars == Decimal("0")


# ===========================================================================
# Expiration payoff + classification
# ===========================================================================

def test_classify_otm_call():
    assert classify_leg(option_type="CALL", side="BUY",
                        strike=Decimal("450"),
                        settlement=Decimal("440")) == CLASSIFICATION_OTM


def test_classify_itm_put():
    assert classify_leg(option_type="PUT", side="SELL",
                        strike=Decimal("450"),
                        settlement=Decimal("440")) == CLASSIFICATION_ITM


def test_classify_pin_risk_within_band():
    assert classify_leg(option_type="CALL", side="SELL",
                        strike=Decimal("450"),
                        settlement=Decimal("450.04")) == CLASSIFICATION_PIN_RISK


def test_classify_missing_settlement():
    assert classify_leg(option_type="CALL", side="SELL",
                        strike=Decimal("450"),
                        settlement=None) == CLASSIFICATION_MISSING


def test_expire_long_call_itm_payoff():
    legs = [_leg(side="BUY", option_type="CALL", strike=450, qty=1)]
    out = expire_legs(legs, settlement_price=Decimal("460"))
    assert out.legs[0].classification == CLASSIFICATION_ITM
    assert out.legs[0].payoff_dollars == Decimal("10") * 100
    assert not out.has_assignment


def test_expire_short_put_itm_assigned():
    legs = [_leg(side="SELL", option_type="PUT", strike=450, qty=1)]
    out = expire_legs(legs, settlement_price=Decimal("445"))
    assert out.legs[0].classification == CLASSIFICATION_ITM
    assert out.legs[0].payoff_dollars == Decimal("-5") * 100
    assert out.legs[0].assigned is True
    assert out.has_assignment is True


def test_expire_iron_condor_in_max_profit_zone():
    """Settlement between short strikes → all 4 legs OTM, payoff = 0."""
    legs = [
        _leg(side="BUY",  option_type="PUT",  strike=435, qty=1),
        _leg(side="SELL", option_type="PUT",  strike=440, qty=1),
        _leg(side="SELL", option_type="CALL", strike=460, qty=1),
        _leg(side="BUY",  option_type="CALL", strike=465, qty=1),
    ]
    out = expire_legs(legs, settlement_price=Decimal("450"))
    assert out.total_payoff_dollars == Decimal("0")
    assert all(l.classification == CLASSIFICATION_OTM for l in out.legs)
    assert not out.has_assignment


def test_expire_credit_spread_max_loss():
    """Settlement past long strike → both legs ITM, net loss = -width*100."""
    legs = [
        _leg(side="SELL", option_type="PUT", strike=440, qty=1),
        _leg(side="BUY",  option_type="PUT", strike=435, qty=1),
    ]
    out = expire_legs(legs, settlement_price=Decimal("420"))
    short_payoff = -Decimal("20") * 100        # short ITM by 20
    long_payoff  = +Decimal("15") * 100        # long ITM by 15
    assert out.total_payoff_dollars == short_payoff + long_payoff   # = -500


def test_expire_missing_settlement_flags_missing_data():
    legs = [_leg(side="SELL", option_type="PUT", strike=440)]
    out = expire_legs(legs, settlement_price=None)
    assert out.has_missing_data is True
    assert out.legs[0].payoff_dollars is None


def test_expire_pin_risk_marks_uncertain_outcome_flag():
    """PIN_RISK leg gets payoff at intrinsic AND is marked uncertain."""
    legs = [_leg(side="SELL", option_type="PUT", strike=450, qty=1)]
    out = expire_legs(legs, settlement_price=Decimal("450.04"))   # within $0.05 band
    assert out.has_pin_risk is True
    assert FLAG_PIN_RISK_UNCERTAIN_OUTCOME in out.flags
    assert out.legs[0].uncertain_outcome is True
    # Payoff still computed at intrinsic (deterministic, but flagged uncertain)
    assert out.legs[0].payoff_dollars is not None


def test_expire_assignment_surfaces_simplified_exit_flag():
    """Any short ITM leg surfaces ASSIGNMENT_SIMPLIFIED_EXIT flag."""
    legs = [_leg(side="SELL", option_type="PUT", strike=450, qty=1)]
    out = expire_legs(legs, settlement_price=Decimal("440"))
    assert out.has_assignment is True
    assert FLAG_ASSIGNMENT_SIMPLIFIED_EXIT in out.flags
    # Final payoff at intrinsic, treated as terminal exit
    assert out.legs[0].payoff_dollars == Decimal("-10") * 100


def test_expire_no_pin_no_assign_no_flags():
    legs = [_leg(side="BUY", option_type="CALL", strike=460, qty=1)]
    out = expire_legs(legs, settlement_price=Decimal("450"))    # OTM, long
    assert out.flags == ()


# ===========================================================================
# PnL — closed pre-expiry
# ===========================================================================

def test_pnl_credit_spread_closed_at_half_credit_profit():
    legs = [
        _leg(side="SELL", option_type="PUT", strike=440, qty=1),
        _leg(side="BUY",  option_type="PUT", strike=435, qty=1),
    ]
    entry = [Decimal("1.20"), Decimal("0.50")]   # net credit = 0.70 → +$70
    exit_ = [Decimal("0.60"), Decimal("0.25")]   # cost-to-close = 0.35 → −$35
    fees = total_fees_for_legs([1, 1])           # round-trip both legs
    p = trade_pnl_closed(legs, entry, exit_, fees_total_dollars=fees)
    # Realized = +70 − 35 − fees
    expected = Decimal("70") - Decimal("35") - fees
    assert p.realized_pnl_dollars == expected


def test_pnl_credit_spread_closed_at_full_credit_breakeven_minus_fees():
    legs = [
        _leg(side="SELL", option_type="PUT", strike=440, qty=1),
        _leg(side="BUY",  option_type="PUT", strike=435, qty=1),
    ]
    entry = [Decimal("1.20"), Decimal("0.50")]
    exit_ = entry            # close at same prices = 0 PnL pre-fees
    fees = total_fees_for_legs([1, 1])
    p = trade_pnl_closed(legs, entry, exit_, fees_total_dollars=fees)
    assert p.realized_pnl_dollars == Decimal("0") - fees


# ===========================================================================
# PnL — held to expiry
# ===========================================================================

def test_pnl_held_to_expiry_iron_condor_full_credit_round_trip_fees():
    """Settlement in profit zone → keep entire credit minus round-trip fees.
    Held-to-expiry now charges close-side fees too (no optimistic advantage)."""
    legs = [
        _leg(side="BUY",  option_type="PUT",  strike=435, qty=1),
        _leg(side="SELL", option_type="PUT",  strike=440, qty=1),
        _leg(side="SELL", option_type="CALL", strike=460, qty=1),
        _leg(side="BUY",  option_type="CALL", strike=465, qty=1),
    ]
    entry = [Decimal("0.30"), Decimal("1.10"), Decimal("1.05"), Decimal("0.25")]
    out = expire_legs(legs, settlement_price=Decimal("450"))
    payoffs = [l.payoff_dollars for l in out.legs]
    rt_fees = total_fees_for_legs([l.qty for l in legs])
    p = trade_pnl_expired(
        legs, entry,
        settlement_payoffs_per_leg=payoffs,
        fees_total_dollars=rt_fees,
    )
    expected_credit = net_credit_dollars(legs, entry)
    assert p.expiration_payoff_dollars == Decimal("0")
    assert p.realized_pnl_dollars == expected_credit - rt_fees


def test_pnl_held_to_expiry_credit_spread_max_loss_round_trip_fees():
    """Settlement past long strike → realized = +credit − width*100 − round_trip_fees."""
    legs = [
        _leg(side="SELL", option_type="PUT", strike=440, qty=1),
        _leg(side="BUY",  option_type="PUT", strike=435, qty=1),
    ]
    entry = [Decimal("1.20"), Decimal("0.50")]    # +$70 credit
    out = expire_legs(legs, settlement_price=Decimal("420"))
    payoffs = [l.payoff_dollars for l in out.legs]    # net −$500
    rt_fees = total_fees_for_legs([l.qty for l in legs])
    p = trade_pnl_expired(
        legs, entry, settlement_payoffs_per_leg=payoffs,
        fees_total_dollars=rt_fees,
    )
    # +70 + (-500) − rt_fees = -430 − rt_fees
    expected = Decimal("70") + Decimal("-500") - rt_fees
    assert p.realized_pnl_dollars == expected


# ===========================================================================
# Greeks aggregation
# ===========================================================================

def test_theta_decay_pnl_grows_monotonically_for_otm_short_premium():
    """Short-premium credit spread held into expiry on an OTM trajectory:
    closing later (mid prices closer to 0) yields strictly higher
    realized PnL than closing earlier (mid still closer to entry).

    This proves the engine's PnL evolves correctly with time-decay —
    holding short-premium gains as theta bleeds the option price down.
    """
    legs = [
        _leg(side="SELL", option_type="PUT", strike=440, qty=1),
        _leg(side="BUY",  option_type="PUT", strike=435, qty=1),
    ]
    entry = [Decimal("1.20"), Decimal("0.50")]    # net credit = $70
    rt_fees = total_fees_for_legs([1, 1])

    # T=0 → T1: half-decayed mids
    early_close = [Decimal("0.60"), Decimal("0.25")]
    # T=0 → T2: deep-decayed mids (later in time)
    late_close  = [Decimal("0.20"), Decimal("0.05")]
    # T=0 → T3: near-zero mids (very close to expiry on OTM path)
    very_late_close = [Decimal("0.05"), Decimal("0.02")]

    p_early = trade_pnl_closed(
        legs, entry, early_close, fees_total_dollars=rt_fees,
    )
    p_late = trade_pnl_closed(
        legs, entry, late_close, fees_total_dollars=rt_fees,
    )
    p_very_late = trade_pnl_closed(
        legs, entry, very_late_close, fees_total_dollars=rt_fees,
    )
    assert p_early.realized_pnl_dollars < p_late.realized_pnl_dollars
    assert p_late.realized_pnl_dollars < p_very_late.realized_pnl_dollars
    # All three should be positive (we collected $70 credit, OTM trajectory)
    assert p_early.realized_pnl_dollars > 0


def test_theta_decay_short_credit_spread_has_positive_net_theta():
    """Aggregate theta on a short credit spread is positive — long side
    bleeds less than short side collects, by construction."""
    legs = [
        _leg(side="SELL", option_type="PUT", strike=440, qty=1),
        _leg(side="BUY",  option_type="PUT", strike=435, qty=1),
    ]
    g = [
        # Short put: theta=-0.04 (option-side theta is negative for long;
        # for short side aggregate inverts → positive contribution)
        GreeksSnapshot(delta=Decimal("-0.30"), gamma=Decimal("0.04"),
                       theta=Decimal("-0.04"), vega=Decimal("0.10")),
        # Long put: theta=-0.02
        GreeksSnapshot(delta=Decimal("-0.18"), gamma=Decimal("0.02"),
                       theta=Decimal("-0.02"), vega=Decimal("0.07")),
    ]
    agg = aggregate_greeks(legs, g)
    # theta = -1*(-0.04) + 1*(-0.02) = 0.04 − 0.02 = 0.02 (positive)
    assert agg.theta == Decimal("0.02")
    assert agg.theta > 0


def test_aggregate_greeks_signed_by_side():
    legs = [
        _leg(side="SELL", option_type="PUT", strike=440, qty=2),
        _leg(side="BUY",  option_type="PUT", strike=435, qty=2),
    ]
    g = [
        GreeksSnapshot(delta=Decimal("-0.40"), gamma=Decimal("0.05"),
                       theta=Decimal("-0.04"), vega=Decimal("0.10")),
        GreeksSnapshot(delta=Decimal("-0.20"), gamma=Decimal("0.03"),
                       theta=Decimal("-0.03"), vega=Decimal("0.08")),
    ]
    agg = aggregate_greeks(legs, g)
    # delta = -1*(-0.40)*2 + 1*(-0.20)*2 = 0.80 − 0.40 = 0.40
    assert agg.delta == Decimal("0.40")
    # gamma = -1*0.05*2 + 1*0.03*2 = -0.10 + 0.06 = -0.04
    assert agg.gamma == Decimal("-0.04")


# ===========================================================================
# Boundary grep
# ===========================================================================

_FORBIDDEN_PATTERNS = [
    r"\bv2_promotion(?!_snapshot)\b",
    r"\bv2_promotion_snapshot\b",
    r"\bv2_oos_monitoring\b",
    r"\bv2_stat_validation\b",
    r"\bb2_v2_comparison\b",
    r"\bengine_b\w*",
    r"\bshadow_strategy\w*",
    r"\bpaper_trade_log\b",
    r"\bdecision_log\b",
    r"\bpaper_shadow_log\b",
    r"\brun_v2_promotion_snapshot\b",
]


def _options_paper_sources() -> list[Path]:
    here = Path(__file__).resolve()
    paper_dir = here.parent.parent.parent / "src" / "options" / "paper"
    return list(paper_dir.rglob("*.py"))


def test_no_forbidden_imports_in_paper_modules():
    for src_path in _options_paper_sources():
        src = src_path.read_text(encoding="utf-8")
        import_lines = [
            ln for ln in src.splitlines()
            if ln.strip().startswith(("import ", "from "))
        ]
        joined = "\n".join(import_lines)
        for pat in _FORBIDDEN_PATTERNS:
            assert not re.search(pat, joined, re.IGNORECASE), (
                f"forbidden pattern {pat!r} in imports of {src_path.name}"
            )


def test_paper_modules_import_in_isolation():
    import sys
    before = set(sys.modules)
    importlib.import_module("apps.api.src.options.paper.fills")
    importlib.import_module("apps.api.src.options.paper.strategies")
    importlib.import_module("apps.api.src.options.paper.expiration")
    importlib.import_module("apps.api.src.options.paper.pnl")
    importlib.import_module("apps.api.src.options.paper.engine")
    after = set(sys.modules)
    new_modules = after - before
    forbidden = (
        "v2_promotion_gates", "v2_promotion_state", "v2_promotion_snapshot",
        "v2_oos_monitoring", "v2_stat_validation", "b2_v2_comparison",
        "engine_b", "shadow_strategy",
    )
    for f in forbidden:
        assert not any(f in m for m in new_modules), \
            f"paper engine indirectly pulled in {f}"


def test_no_api_or_ui_or_ml_imports_in_paper_modules():
    """Scan ONLY import statements — keeps prose docstrings out of scope."""
    bad = (r"\bfastapi\b", r"\bstarlette\b", r"\buvicorn\b",
           r"\bsklearn\b", r"\bxgboost\b", r"\blightgbm\b",
           r"\btorch\b", r"\btensorflow\b", r"\breact\b", r"\bjsx\b")
    for src_path in _options_paper_sources():
        if src_path.name == "__init__.py":
            continue
        src = src_path.read_text(encoding="utf-8")
        import_lines = [
            ln for ln in src.splitlines()
            if ln.strip().startswith(("import ", "from "))
        ]
        joined = "\n".join(import_lines)
        for pat in bad:
            assert not re.search(pat, joined, re.IGNORECASE), (
                f"forbidden import pattern {pat!r} in {src_path.name}"
            )
