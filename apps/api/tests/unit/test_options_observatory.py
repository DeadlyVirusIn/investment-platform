"""Phase 11G unit tests — observatory pure-fn modules.

Covers:
  * Rule registry shape + frozen criteria codes
  * Eligibility evaluator pass/fail paths (credit spreads + iron condor)
  * Observation id encode/decode round-trip
  * Boundary grep — no V2 / equity / ML / paper-engine-mutation imports
  * No mutating SQL or session calls in any observatory module
  * No recommendation language in user-facing strings
"""

from __future__ import annotations

import datetime as dt
import importlib
import re
from decimal import Decimal
from pathlib import Path

import pytest

from apps.api.src.options.data_provider.base_adapter import OptionChainQuote
from apps.api.src.options.observatory.observations import (
    _decode_observation_id,
    _observation_id,
)
from apps.api.src.options.observatory.rules import (
    DTE_MAX_DAYS,
    DTE_MIN_DAYS,
    RULE_DEFS,
    SHORT_DELTA_MAX_ABS,
    SHORT_DELTA_MIN_ABS,
    evaluate_rules,
    list_rule_defs,
    serialise_evaluation,
)
from apps.api.src.options.paper.strategies import (
    STRATEGY_IRON_CONDOR,
    STRATEGY_SHORT_CALL_CREDIT_SPREAD,
    STRATEGY_SHORT_PUT_CREDIT_SPREAD,
)


def _q(
    *, option_type, strike, expiry, bid=1.50, ask=1.55,
    delta=-0.30, gamma=0.02, iv=0.20, oi=1500, age=2,
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
        volume=100, open_interest=oi,
        delta=Decimal(str(delta)) if delta is not None else None,
        gamma=Decimal(str(gamma)) if gamma is not None else None,
        theta=Decimal("-0.05"), vega=Decimal("0.10"),
        iv=Decimal(str(iv)) if iv is not None else None,
        quote_age_seconds=age, provider="thetadata",
    )


# ===========================================================================
# Rule registry
# ===========================================================================

def test_rule_registry_covers_v1_strategies():
    assert STRATEGY_SHORT_PUT_CREDIT_SPREAD in RULE_DEFS
    assert STRATEGY_SHORT_CALL_CREDIT_SPREAD in RULE_DEFS
    assert STRATEGY_IRON_CONDOR in RULE_DEFS


def test_rule_registry_serialisation_shape():
    out = list_rule_defs()
    assert len(out) == 3
    for rule in out:
        assert {"rule_id", "name", "summary", "criteria"} <= set(rule.keys())
        for c in rule["criteria"]:
            assert {"code", "label", "description"} <= set(c.keys())


def test_rule_thresholds_documented():
    assert DTE_MIN_DAYS == 21
    assert DTE_MAX_DAYS == 45
    assert SHORT_DELTA_MIN_ABS == Decimal("0.20")
    assert SHORT_DELTA_MAX_ABS == Decimal("0.35")


# ===========================================================================
# Eligibility evaluator
# ===========================================================================

def test_short_put_qualifies_with_clean_chain():
    as_of = dt.date(2026, 5, 18)
    e = as_of + dt.timedelta(days=30)
    quotes = [
        _q(option_type="PUT", strike=440, expiry=e, delta=-0.30, oi=2000),
        _q(option_type="PUT", strike=435, expiry=e, delta=-0.18, oi=1500),
    ]
    evals = evaluate_rules(quotes, as_of=as_of)
    by_id = {ev.rule_id: ev for ev in evals}
    spread = by_id[STRATEGY_SHORT_PUT_CREDIT_SPREAD]
    assert spread.qualified is True
    assert spread.candidate is not None
    assert spread.candidate["short_strike"] == "440"
    assert spread.candidate["long_strike"]  == "435"


def test_short_put_rejected_outside_dte_band():
    as_of = dt.date(2026, 5, 18)
    e = as_of + dt.timedelta(days=10)    # too short — fails DTE band
    quotes = [
        _q(option_type="PUT", strike=440, expiry=e, delta=-0.30, oi=2000),
        _q(option_type="PUT", strike=435, expiry=e, delta=-0.18, oi=1500),
    ]
    evals = evaluate_rules(quotes, as_of=as_of)
    spread = next(ev for ev in evals if ev.rule_id == STRATEGY_SHORT_PUT_CREDIT_SPREAD)
    assert spread.qualified is False
    failed_codes = {c.code for c in spread.checks if not c.passed}
    assert "DTE_BAND" in failed_codes


def test_short_put_rejected_when_short_leg_outside_delta_band():
    as_of = dt.date(2026, 5, 18)
    e = as_of + dt.timedelta(days=30)
    quotes = [
        _q(option_type="PUT", strike=440, expiry=e, delta=-0.10, oi=2000),
        _q(option_type="PUT", strike=435, expiry=e, delta=-0.05, oi=1500),
    ]
    evals = evaluate_rules(quotes, as_of=as_of)
    spread = next(ev for ev in evals if ev.rule_id == STRATEGY_SHORT_PUT_CREDIT_SPREAD)
    assert spread.qualified is False
    failed_codes = {c.code for c in spread.checks if not c.passed}
    assert "SHORT_LEG_DELTA_BAND" in failed_codes


def test_short_put_rejected_when_liquidity_fails():
    as_of = dt.date(2026, 5, 18)
    e = as_of + dt.timedelta(days=30)
    quotes = [
        _q(option_type="PUT", strike=440, expiry=e, delta=-0.30, oi=10),    # OI fails
        _q(option_type="PUT", strike=435, expiry=e, delta=-0.18, oi=1500),
    ]
    evals = evaluate_rules(quotes, as_of=as_of)
    spread = next(ev for ev in evals if ev.rule_id == STRATEGY_SHORT_PUT_CREDIT_SPREAD)
    assert spread.qualified is False
    failed_codes = {c.code for c in spread.checks if not c.passed}
    assert "LIQUIDITY" in failed_codes


def test_short_put_rejected_when_no_long_protection():
    as_of = dt.date(2026, 5, 18)
    e = as_of + dt.timedelta(days=30)
    quotes = [
        _q(option_type="PUT", strike=440, expiry=e, delta=-0.30, oi=2000),
        # no further-OTM long put — fails LONG_LEG_PROTECTION
    ]
    evals = evaluate_rules(quotes, as_of=as_of)
    spread = next(ev for ev in evals if ev.rule_id == STRATEGY_SHORT_PUT_CREDIT_SPREAD)
    assert spread.qualified is False
    assert "LONG_LEG_PROTECTION" in {c.code for c in spread.checks if not c.passed}


def test_iron_condor_qualifies_when_both_wings_eligible():
    as_of = dt.date(2026, 5, 18)
    e = as_of + dt.timedelta(days=30)
    quotes = [
        _q(option_type="PUT",  strike=440, expiry=e, delta=-0.30, oi=2000),
        _q(option_type="PUT",  strike=435, expiry=e, delta=-0.18, oi=1500),
        _q(option_type="CALL", strike=460, expiry=e, delta= 0.30, oi=2000),
        _q(option_type="CALL", strike=465, expiry=e, delta= 0.18, oi=1500),
    ]
    evals = evaluate_rules(quotes, as_of=as_of)
    ic = next(ev for ev in evals if ev.rule_id == STRATEGY_IRON_CONDOR)
    assert ic.qualified is True
    assert ic.candidate is not None
    assert "put_wing" in ic.candidate and "call_wing" in ic.candidate


def test_iron_condor_rejected_when_one_wing_fails():
    as_of = dt.date(2026, 5, 18)
    e = as_of + dt.timedelta(days=30)
    quotes = [
        _q(option_type="PUT",  strike=440, expiry=e, delta=-0.30, oi=2000),
        _q(option_type="PUT",  strike=435, expiry=e, delta=-0.18, oi=1500),
        # missing call wing
    ]
    evals = evaluate_rules(quotes, as_of=as_of)
    ic = next(ev for ev in evals if ev.rule_id == STRATEGY_IRON_CONDOR)
    assert ic.qualified is False


# ===========================================================================
# Observation id round-trip
# ===========================================================================

def test_observation_id_round_trip():
    day = dt.date(2026, 5, 18)
    oid = _observation_id("SPY", day, STRATEGY_IRON_CONDOR)
    sym, parsed_day, rid = _decode_observation_id(oid)    # type: ignore[misc]
    assert sym == "SPY"
    assert parsed_day == day
    assert rid == STRATEGY_IRON_CONDOR


def test_observation_id_decode_returns_none_for_garbage():
    assert _decode_observation_id("not-an-id") is None
    assert _decode_observation_id("SPY:not-a-date:rule") is None


# ===========================================================================
# Serialisation shape
# ===========================================================================

def test_serialise_evaluation_includes_per_check_reasons():
    as_of = dt.date(2026, 5, 18)
    e = as_of + dt.timedelta(days=30)
    quotes = [
        _q(option_type="PUT", strike=440, expiry=e, delta=-0.30, oi=2000),
        _q(option_type="PUT", strike=435, expiry=e, delta=-0.18, oi=1500),
    ]
    evals = evaluate_rules(quotes, as_of=as_of)
    out = serialise_evaluation(evals[0])
    assert "checks" in out
    for c in out["checks"]:
        assert "code" in c and "passed" in c and "reason" in c


# ===========================================================================
# Source-static — no mutation, no recommendation language, no V2/equity
# ===========================================================================

_OBS_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "src" / "options" / "observatory"
)


def _obs_files() -> list[Path]:
    return list(_OBS_DIR.rglob("*.py"))


_FORBIDDEN_DECORATORS = (
    r"@router\.post\b", r"@router\.put\b",
    r"@router\.patch\b", r"@router\.delete\b",
)


def test_no_router_decorators_in_observatory_modules():
    for p in _obs_files():
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


def test_no_mutating_sql_in_observatory_modules():
    for p in _obs_files():
        src = p.read_text(encoding="utf-8")
        for line in src.splitlines():
            stripped = line.strip()
            if stripped.startswith(("#", '"', "'")):
                continue
            for pat in _MUTATING_SQL:
                assert not re.search(pat, line), (
                    f"forbidden mutating SQL {pat!r} in {p.name}: {stripped}"
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
    # observatory must NOT import the paper engine mutation entrypoints
    r"options\.paper\.engine\b",
)


def test_no_forbidden_imports_in_observatory():
    for p in _obs_files():
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


def test_observatory_modules_import_in_isolation():
    import sys
    before = set(sys.modules)
    importlib.import_module("apps.api.src.options.observatory.rules")
    importlib.import_module("apps.api.src.options.observatory.performance")
    importlib.import_module("apps.api.src.options.observatory.diagnostics")
    importlib.import_module("apps.api.src.options.observatory.observations")
    importlib.import_module("apps.api.src.options.observatory.replay")
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
            f"observatory indirectly pulled in {f}"
        )


_FORBIDDEN_USER_FACING = (
    r"\bRecommended Trade\b",
    r"\bBest Trade\b",
    r"\bAuto-?trade\b",
    r"\bExecute Trade\b",
    r"\bPlace Order\b",
    r"\bConfidence Score\b",
    r"\bML Signal\b",
    r"\bPromote\b",
)


def test_no_recommendation_language_in_observatory():
    for p in _obs_files():
        src = p.read_text(encoding="utf-8")
        for pat in _FORBIDDEN_USER_FACING:
            assert not re.search(pat, src), (
                f"forbidden user-facing wording {pat!r} in {p.name}"
            )


def test_observation_only_notice_present_in_each_module():
    """Every observatory module that produces user-facing output must
    surface the observation-only notice via the
    `observation_only_notice` JSON field."""
    expected = "Observation only — not investment advice or execution guidance"
    for p in _obs_files():
        if p.name in ("__init__.py", "rules.py"):
            continue
        src = p.read_text(encoding="utf-8")
        assert expected in src, f"observation-only notice missing in {p.name}"
        assert "observation_only_notice" in src, (
            f"`observation_only_notice` key missing in {p.name}"
        )
