"""Unit tests — Opt-B credit-mode generator.

Covers the engine-aligned credit taxonomy: bias→structure mapping
(decision 3, bias passed in — never inferred from contract type),
engine rule_id names (decision: canonical vocabulary), IV-rank NULL
neutral handling (decision 4), and the underlying-level IRON_CONDOR
builder (decision 2). Pure — no DB, no clock.
"""

from __future__ import annotations

import datetime as dt

from apps.api.src.options.strategy_candidates.generator import (
    ChainQuote, ShadowObservation, UnderlyingFeature,
    build_iron_condor, generate,
)

ENGINE_SUPPORTED = {
    "SHORT_PUT_CREDIT_SPREAD", "SHORT_CALL_CREDIT_SPREAD", "IRON_CONDOR",
}

_RUN = dt.date(2026, 6, 1)
_EXP = dt.date(2026, 7, 2)  # ~31 DTE


def _obs(option_type: str, *, would_trade: bool = True) -> ShadowObservation:
    return ShadowObservation(
        observation_id=1, run_date=_RUN, underlying="SPY",
        option_symbol="SPY260702X", expiration=_EXP, strike=500.0,
        option_type=option_type, side="sell", would_trade=would_trade,
        liquidity_pass=True, spread_pass=True, open_interest_pass=True,
        volume_pass=True, greeks_pass=True, iv_rank_pass=True,
        risk_pass=True, score=0.8, diagnostics={},
    )


def _quote(delta: float) -> ChainQuote:
    return ChainQuote(bid=1.0, ask=1.1, mid=1.05, delta=delta, gamma=0.01,
                      theta=-0.02, vega=0.1, iv=0.20, open_interest=5000,
                      volume=1000)


def _feat(iv_rank=None) -> UnderlyingFeature:
    return UnderlyingFeature(iv_rank_252d=iv_rank, atm_iv=0.20,
                             realized_vol_30d=0.15)


# --- bias → structure mapping (decision 3) -----------------------------

def test_bullish_put_emits_short_put_credit_spread():
    out = generate(obs=_obs("put"), quote=_quote(-0.30), feat=_feat(),
                   structures="credit", bias="bullish")
    assert [c.rule_id for c in out] == ["SHORT_PUT_CREDIT_SPREAD"]
    assert out[0].bias == "bullish"
    assert out[0].rule_id in ENGINE_SUPPORTED


def test_bearish_call_emits_short_call_credit_spread():
    out = generate(obs=_obs("call"), quote=_quote(0.30), feat=_feat(),
                   structures="credit", bias="bearish")
    assert [c.rule_id for c in out] == ["SHORT_CALL_CREDIT_SPREAD"]
    assert out[0].bias == "bearish"


def test_bias_not_inferred_from_contract_type():
    # A bullish bias on a CALL contract must NOT emit (bullish credit
    # anchors on a PUT). Confirms bias drives structure, not option_type.
    out = generate(obs=_obs("call"), quote=_quote(0.30), feat=_feat(),
                   structures="credit", bias="bullish")
    assert out == []


def test_neutral_bias_emits_nothing_per_contract():
    # IC is composed at the underlying level, not per-contract.
    out = generate(obs=_obs("put"), quote=_quote(-0.30), feat=_feat(),
                   structures="credit", bias="neutral")
    assert out == []


def test_out_of_delta_zone_emits_nothing():
    # |delta| 0.05 is below the 0.20–0.35 short-leg band.
    out = generate(obs=_obs("put"), quote=_quote(-0.05), feat=_feat(),
                   structures="credit", bias="bullish")
    assert out == []


# --- IV-rank NULL handling (decision 4) --------------------------------

def test_iv_rank_null_is_neutral_with_building_message():
    out = generate(obs=_obs("put"), quote=_quote(-0.30), feat=_feat(None),
                   structures="credit", bias="bullish")
    c = out[0]
    assert abs(c.iv_suitability - 0.5) < 1e-9
    assert "IV-rank history building" in (c.iv_fit_reason or "")
    assert "IV-rank history building" in c.why_emitted


def test_width_recorded_in_diagnostics():
    out = generate(obs=_obs("put"), quote=_quote(-0.30), feat=_feat(),
                   structures="credit", bias="bullish")
    assert out[0].diagnostics["width_strikes"] == 1
    assert out[0].diagnostics["bias_source"] == "recommendation_signal"


# --- underlying-level IRON_CONDOR (decision 2) -------------------------

def test_build_iron_condor_no_signal_messaging():
    ic = build_iron_condor(obs=_obs("put"), quote=_quote(-0.30),
                           feat=_feat(), catalyst=None,
                           has_directional_signal=False)
    assert ic.rule_id == "IRON_CONDOR"
    assert ic.bias == "neutral"
    assert "No directional recommendation signal" in ic.why_emitted


def test_build_iron_condor_hold_messaging():
    ic = build_iron_condor(obs=_obs("put"), quote=_quote(-0.30),
                           feat=_feat(), catalyst=None,
                           has_directional_signal=True)
    assert "Neutral/hold recommendation" in ic.why_emitted


# --- directional mode untouched ----------------------------------------

def test_directional_mode_still_emits_legacy_structures():
    out = generate(obs=_obs("call"), quote=_quote(0.60), feat=_feat(),
                   structures="directional")
    rule_ids = {c.rule_id for c in out}
    assert rule_ids  # emitted something
    assert "LONG_CALL" in rule_ids  # legacy debit/long family


def test_would_trade_false_emits_nothing_either_mode():
    assert generate(obs=_obs("put", would_trade=False), quote=_quote(-0.30),
                    feat=_feat(), structures="credit", bias="bullish") == []
