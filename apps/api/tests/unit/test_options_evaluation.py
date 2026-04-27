"""Phase 11H unit tests — pure-fn deterministic scoring model.

Covers:
  * Determinism — same inputs → same score
  * Bounds — total always 0-100
  * Reconciliation — components + capped penalty = total (pre-clamp)
  * Per-penalty firing for every flag in spec
  * Boundary import scan — no V2 / equity / ML / paper-engine-mutation
  * No mutating SQL or session calls in evaluation modules
  * No recommendation language in serialised output
"""

from __future__ import annotations

import datetime as dt
import importlib
import re
from decimal import Decimal
from pathlib import Path

import pytest

from apps.api.src.options.data_provider.base_adapter import OptionChainQuote
from apps.api.src.options.evaluation.score_model import (
    PENALTY_ASSIGNMENT_SIMPLIFIED_EXIT,
    PENALTY_CAP,
    PENALTY_INSUFFICIENT_IV_HISTORY,
    PENALTY_INSUFFICIENT_REALIZED_VOL,
    PENALTY_MISSING_GREEKS,
    PENALTY_MISSING_IV,
    PENALTY_MISSING_SETTLEMENT,
    PENALTY_NAIVE_GEX,
    PENALTY_PIN_RISK,
    SCORE_MODEL_VERSION,
    ScoringInputs,
    compute_score,
    serialise,
)
from apps.api.src.options.paper.expiration import (
    FLAG_ASSIGNMENT_SIMPLIFIED_EXIT,
    FLAG_MISSING_SETTLEMENT,
    FLAG_PIN_RISK_UNCERTAIN_OUTCOME,
)
from apps.api.src.options.paper.strategies import (
    STRATEGY_IRON_CONDOR,
    STRATEGY_SHORT_PUT_CREDIT_SPREAD,
)


def _q(
    *, option_type, strike, expiry, bid=1.20, ask=1.25,
    delta=-0.30, gamma=0.02, iv=0.20, oi=2000, vol=200, age=2,
) -> OptionChainQuote:
    snap = dt.datetime(2026, 5, 18, 14, 0, tzinfo=dt.timezone.utc)
    mid = (bid + ask) / 2
    return OptionChainQuote(
        snapshot_at_utc=snap, underlying="SPY",
        expiry=expiry, strike=Decimal(str(strike)),
        option_type=option_type,
        option_symbol=f"SPY{expiry.strftime('%y%m%d')}{option_type[0]}{int(strike*1000):08d}",
        bid=Decimal(str(bid)), ask=Decimal(str(ask)),
        mid=Decimal(str(mid)), last=None,
        volume=vol, open_interest=oi,
        delta=Decimal(str(delta)) if delta is not None else None,
        gamma=Decimal(str(gamma)) if gamma is not None else None,
        theta=Decimal("-0.05"), vega=Decimal("0.10"),
        iv=Decimal(str(iv)) if iv is not None else None,
        quote_age_seconds=age, provider="thetadata",
    )


def _good_credit_spread_inputs(*, flags: tuple[str, ...] = ()) -> ScoringInputs:
    as_of = dt.date(2026, 5, 18)
    expiry = as_of + dt.timedelta(days=30)
    short = _q(option_type="PUT", strike=440, expiry=expiry,
               bid=1.20, ask=1.25, delta=-0.30, oi=2000)
    long_ = _q(option_type="PUT", strike=435, expiry=expiry,
               bid=0.50, ask=0.55, delta=-0.18, oi=1500)
    candidate = {
        "side": "PUT",
        "short_strike": "440",
        "short_delta": "-0.30",
        "long_strike": "435",
        "expiry": expiry.isoformat(),
        "short_symbol": short.option_symbol,
        "long_symbol":  long_.option_symbol,
    }
    feature = {
        "iv_rank_252d": "0.55",
        "iv_percentile_252d": "0.60",
        "vrp_30d": "0.05",
        "realized_vol_20d": "0.15",
        "data_quality_flags": [],
    }
    return ScoringInputs(
        rule_id=STRATEGY_SHORT_PUT_CREDIT_SPREAD,
        underlying="SPY",
        as_of_date=as_of,
        qualified=True,
        candidate=candidate,
        accepted_quotes=(short, long_),
        feature_row=feature,
        flags=flags,
    )


# ===========================================================================
# Determinism
# ===========================================================================

def test_score_is_deterministic():
    a = compute_score(_good_credit_spread_inputs())
    b = compute_score(_good_credit_spread_inputs())
    assert a.total_score == b.total_score
    assert a.components == b.components
    assert a.penalties == b.penalties
    assert a.inputs == b.inputs


def test_score_model_version_is_pinned():
    s = compute_score(_good_credit_spread_inputs())
    assert s.model_version == SCORE_MODEL_VERSION
    assert SCORE_MODEL_VERSION == "v1.frozen"


# ===========================================================================
# Bounds
# ===========================================================================

def test_score_is_bounded_to_0_100():
    # Force everything failing → total clamps to 0, not negative
    bad = ScoringInputs(
        rule_id="SHORT_PUT_CREDIT_SPREAD",
        underlying="SPY",
        as_of_date=dt.date(2026, 5, 18),
        qualified=False,
        candidate=None,
        accepted_quotes=(),
        feature_row=None,
        flags=(FLAG_PIN_RISK_UNCERTAIN_OUTCOME,
               FLAG_ASSIGNMENT_SIMPLIFIED_EXIT,
               FLAG_MISSING_SETTLEMENT),
    )
    s = compute_score(bad)
    assert 0 <= s.total_score <= 100
    assert s.total_score == 0


def test_score_clamps_at_100_on_fully_qualifying_inputs():
    s = compute_score(_good_credit_spread_inputs())
    assert 0 <= s.total_score <= 100


# ===========================================================================
# Reconciliation
# ===========================================================================

def test_components_plus_capped_penalty_reconcile_to_total_pre_clamp():
    s = compute_score(_good_credit_spread_inputs(
        flags=(FLAG_PIN_RISK_UNCERTAIN_OUTCOME,
               FLAG_ASSIGNMENT_SIMPLIFIED_EXIT,
               FLAG_MISSING_SETTLEMENT),
    ))
    component_sum = sum(c.score for c in s.components)
    raw_pre_clamp = component_sum + s.inputs["capped_penalty"]
    assert s.inputs["raw_total_pre_clamp"] == raw_pre_clamp
    assert s.total_score == max(0, min(100, raw_pre_clamp))


def test_penalty_cap_enforced():
    """Three big flags + many missing-data flags should cap at -PENALTY_CAP."""
    inp = _good_credit_spread_inputs(
        flags=(FLAG_PIN_RISK_UNCERTAIN_OUTCOME,
               FLAG_ASSIGNMENT_SIMPLIFIED_EXIT,
               FLAG_MISSING_SETTLEMENT),
    )
    feat = dict(inp.feature_row or {})
    feat["data_quality_flags"] = [
        "INSUFFICIENT_VOLUME_HISTORY", "NO_PRICE_HISTORY",
        "INSUFFICIENT_IV_HISTORY", "NO_OPEN_INTEREST",
    ]
    inp = ScoringInputs(
        rule_id=inp.rule_id,
        underlying=inp.underlying,
        as_of_date=inp.as_of_date,
        qualified=inp.qualified,
        candidate=inp.candidate,
        accepted_quotes=inp.accepted_quotes,
        feature_row=feat,
        flags=inp.flags,
    )
    s = compute_score(inp)
    assert s.inputs["raw_penalty_sum"] < -PENALTY_CAP   # raw was huge
    assert s.inputs["capped_penalty"] == -PENALTY_CAP    # cap kicks in


# ===========================================================================
# Per-penalty firing
# ===========================================================================

def _penalty_codes(s) -> set[str]:
    return {p.code for p in s.penalties}


def test_pin_risk_penalty_applied_when_flag_present():
    s = compute_score(_good_credit_spread_inputs(
        flags=(FLAG_PIN_RISK_UNCERTAIN_OUTCOME,),
    ))
    assert FLAG_PIN_RISK_UNCERTAIN_OUTCOME in _penalty_codes(s)
    pen = next(p for p in s.penalties if p.code == FLAG_PIN_RISK_UNCERTAIN_OUTCOME)
    assert pen.points == PENALTY_PIN_RISK


def test_assignment_simplified_exit_penalty_applied():
    s = compute_score(_good_credit_spread_inputs(
        flags=(FLAG_ASSIGNMENT_SIMPLIFIED_EXIT,),
    ))
    assert FLAG_ASSIGNMENT_SIMPLIFIED_EXIT in _penalty_codes(s)


def test_missing_settlement_penalty_applied():
    s = compute_score(_good_credit_spread_inputs(
        flags=(FLAG_MISSING_SETTLEMENT,),
    ))
    pen = next(p for p in s.penalties if p.code == FLAG_MISSING_SETTLEMENT)
    assert pen.points == PENALTY_MISSING_SETTLEMENT


def test_missing_greeks_penalty_applied():
    inp = _good_credit_spread_inputs()
    # Replace short leg with missing greeks
    no_greeks = OptionChainQuote(
        snapshot_at_utc=inp.accepted_quotes[0].snapshot_at_utc,
        underlying="SPY",
        expiry=inp.accepted_quotes[0].expiry,
        strike=inp.accepted_quotes[0].strike,
        option_type=inp.accepted_quotes[0].option_type,
        option_symbol=inp.accepted_quotes[0].option_symbol,
        bid=inp.accepted_quotes[0].bid,
        ask=inp.accepted_quotes[0].ask,
        mid=inp.accepted_quotes[0].mid,
        last=inp.accepted_quotes[0].last,
        volume=inp.accepted_quotes[0].volume,
        open_interest=inp.accepted_quotes[0].open_interest,
        delta=None, gamma=None, theta=None, vega=None,
        iv=inp.accepted_quotes[0].iv,
        quote_age_seconds=inp.accepted_quotes[0].quote_age_seconds,
        provider=inp.accepted_quotes[0].provider,
    )
    inp2 = ScoringInputs(
        rule_id=inp.rule_id,
        underlying=inp.underlying,
        as_of_date=inp.as_of_date,
        qualified=inp.qualified,
        candidate=inp.candidate,
        accepted_quotes=(no_greeks, inp.accepted_quotes[1]),
        feature_row=inp.feature_row,
        flags=inp.flags,
    )
    s = compute_score(inp2)
    assert "MISSING_GREEKS" in _penalty_codes(s)
    pen = next(p for p in s.penalties if p.code == "MISSING_GREEKS")
    assert pen.points == PENALTY_MISSING_GREEKS


def test_insufficient_realized_vol_penalty_applied():
    inp = _good_credit_spread_inputs()
    feat = dict(inp.feature_row or {})
    feat["data_quality_flags"] = ["NO_PRICE_HISTORY"]
    inp2 = ScoringInputs(
        rule_id=inp.rule_id, underlying=inp.underlying,
        as_of_date=inp.as_of_date, qualified=inp.qualified,
        candidate=inp.candidate, accepted_quotes=inp.accepted_quotes,
        feature_row=feat, flags=inp.flags,
    )
    s = compute_score(inp2)
    pen = next(p for p in s.penalties if p.code == "NO_PRICE_HISTORY")
    assert pen.points == PENALTY_INSUFFICIENT_REALIZED_VOL


def test_missing_iv_penalty_applied():
    inp = _good_credit_spread_inputs()
    no_iv = OptionChainQuote(
        snapshot_at_utc=inp.accepted_quotes[0].snapshot_at_utc,
        underlying="SPY",
        expiry=inp.accepted_quotes[0].expiry,
        strike=inp.accepted_quotes[0].strike,
        option_type=inp.accepted_quotes[0].option_type,
        option_symbol=inp.accepted_quotes[0].option_symbol,
        bid=inp.accepted_quotes[0].bid,
        ask=inp.accepted_quotes[0].ask,
        mid=inp.accepted_quotes[0].mid,
        last=None,
        volume=200, open_interest=2000,
        delta=Decimal("-0.30"), gamma=Decimal("0.02"),
        theta=Decimal("-0.05"), vega=Decimal("0.10"),
        iv=None,
        quote_age_seconds=2, provider="thetadata",
    )
    inp2 = ScoringInputs(
        rule_id=inp.rule_id, underlying=inp.underlying,
        as_of_date=inp.as_of_date, qualified=inp.qualified,
        candidate=inp.candidate,
        accepted_quotes=(no_iv, inp.accepted_quotes[1]),
        feature_row=inp.feature_row, flags=inp.flags,
    )
    s = compute_score(inp2)
    pen = next(p for p in s.penalties if p.code == "MISSING_IV")
    assert pen.points == PENALTY_MISSING_IV


def test_naive_gex_penalty_applied():
    inp = _good_credit_spread_inputs()
    feat = dict(inp.feature_row or {})
    feat["data_quality_flags"] = ["NO_OPEN_INTEREST"]
    inp2 = ScoringInputs(
        rule_id=inp.rule_id, underlying=inp.underlying,
        as_of_date=inp.as_of_date, qualified=inp.qualified,
        candidate=inp.candidate, accepted_quotes=inp.accepted_quotes,
        feature_row=feat, flags=inp.flags,
    )
    s = compute_score(inp2)
    pen = next(p for p in s.penalties if p.code == "NO_OPEN_INTEREST")
    assert pen.points == PENALTY_NAIVE_GEX


def test_insufficient_iv_history_penalty_applied():
    inp = _good_credit_spread_inputs()
    feat = dict(inp.feature_row or {})
    feat["data_quality_flags"] = ["INSUFFICIENT_IV_HISTORY"]
    inp2 = ScoringInputs(
        rule_id=inp.rule_id, underlying=inp.underlying,
        as_of_date=inp.as_of_date, qualified=inp.qualified,
        candidate=inp.candidate, accepted_quotes=inp.accepted_quotes,
        feature_row=feat, flags=inp.flags,
    )
    s = compute_score(inp2)
    pen = next(p for p in s.penalties if p.code == "INSUFFICIENT_IV_HISTORY")
    assert pen.points == PENALTY_INSUFFICIENT_IV_HISTORY


# ===========================================================================
# Component sanity
# ===========================================================================

def test_components_emit_explanations_with_reasons():
    s = compute_score(_good_credit_spread_inputs())
    codes = {c.component for c in s.components}
    assert codes == {"liquidity", "risk_reward", "vol_context", "structure"}
    for c in s.components:
        assert c.explanation
        assert 0 <= c.score <= c.weight_max


def test_serialisation_shape():
    s = compute_score(_good_credit_spread_inputs())
    j = serialise(s)
    assert "total_score" in j
    assert "components" in j
    assert "penalties" in j
    assert "flags" in j
    assert "inputs" in j
    for c in j["components"]:
        assert {"component", "weight_max", "score", "explanation"} <= set(c)


# ===========================================================================
# Source-static — no mutation, no V2/ML/paper-engine-mutation
# ===========================================================================

_EVAL_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "src" / "options" / "evaluation"
)


def _eval_files() -> list[Path]:
    return list(_EVAL_DIR.rglob("*.py"))


_FORBIDDEN_DECORATORS = (
    r"@router\.post\b", r"@router\.put\b",
    r"@router\.patch\b", r"@router\.delete\b",
)


def test_no_router_decorators_in_evaluation_modules():
    for p in _eval_files():
        src = p.read_text(encoding="utf-8")
        for pat in _FORBIDDEN_DECORATORS:
            assert not re.search(pat, src), (
                f"forbidden decorator {pat!r} in {p.name}"
            )


_MUTATING_SQL = (
    r"\bINSERT\s+INTO\b",
    r"\bUPDATE\s+\w+\s+SET\b",
    r"\bDELETE\s+FROM\b",
    r"session\.add\b",
    r"session\.commit\b",
    r"session\.delete\b",
    r"session\.flush\b",
    r"session\.merge\b",
)


def test_no_mutating_sql_in_evaluation_modules():
    for p in _eval_files():
        src = p.read_text(encoding="utf-8")
        for line in src.splitlines():
            stripped = line.strip()
            if stripped.startswith(("#", '"', "'")):
                continue
            for pat in _MUTATING_SQL:
                assert not re.search(pat, line), (
                    f"forbidden mutating SQL/session call {pat!r} "
                    f"in {p.name}: {stripped}"
                )


_FORBIDDEN_IMPORTS = (
    r"\bv2_promotion(?!_snapshot)\b",
    r"\bv2_promotion_snapshot\b",
    r"\bv2_oos_monitoring\b",
    r"\bv2_stat_validation\b",
    r"\bb2_v2_comparison\b",
    r"\bengine_b\w*",
    r"\bshadow_strategy\w*",
    r"\bml_hybrid\b", r"\bml_research\b", r"\bml_replay\b",
    # Evaluation must NOT import paper engine MUTATION endpoints
    r"options\.paper\.engine\b",
)


def test_no_forbidden_imports_in_evaluation():
    for p in _eval_files():
        src = p.read_text(encoding="utf-8")
        import_lines = [
            ln for ln in src.splitlines()
            if ln.strip().startswith(("import ", "from "))
        ]
        joined = "\n".join(import_lines)
        for pat in _FORBIDDEN_IMPORTS:
            assert not re.search(pat, joined, re.IGNORECASE), (
                f"forbidden import pattern {pat!r} in {p.name}"
            )


def test_evaluation_modules_import_in_isolation():
    import sys
    before = set(sys.modules)
    importlib.import_module("apps.api.src.options.evaluation.score_model")
    importlib.import_module("apps.api.src.options.evaluation.score_service")
    after = set(sys.modules)
    new_modules = after - before
    forbidden = (
        "v2_promotion_gates", "v2_promotion_state", "v2_promotion_snapshot",
        "v2_oos_monitoring", "v2_stat_validation", "b2_v2_comparison",
        "engine_b", "shadow_strategy",
        "ml_hybrid", "ml_research", "ml_replay",
        "options.paper.engine",
    )
    for f in forbidden:
        assert not any(f in m for m in new_modules), (
            f"evaluation indirectly pulled in {f}"
        )


_FORBIDDEN_USER_FACING = (
    r"\bRecommended\b", r"\bRecommendation\b",
    r"\bBest Trade\b", r"\bTop pick\b", r"\bTrade now\b",
    r"\bAuto-?trade\b",
    r"\bExecute Trade\b", r"\bPlace Order\b",
    r"\bConfidence Score\b", r"\bML Signal\b",
    r"\bPromote\b",
)


def test_no_recommendation_language_in_evaluation():
    for p in _eval_files():
        src = p.read_text(encoding="utf-8")
        for pat in _FORBIDDEN_USER_FACING:
            assert not re.search(pat, src), (
                f"forbidden user-facing wording {pat!r} in {p.name}"
            )
