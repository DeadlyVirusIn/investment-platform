"""P0-2A.3 — regression tests for the quote_age_seconds guard.

The 2026-06-12 production regression: quote_age_seconds was selected in
the LATERAL subquery but not projected in the outer SELECT, so row
extraction raised NoSuchColumnError and killed the ENTIRE candidate
generation run. These tests pin the defensive contract:

  * row with the key -> float
  * row without the key / with NULL -> None, never raise
  * shadow diagnostics still computed with the labeled freshness
    degradation when the input is absent
  * candidate.confidence (the v1 constant) is never touched

NOTE: imports the service module (loguru et al.) — runs in the CI /
container environment, like the integration suite.
"""

from __future__ import annotations

import pytest

from apps.api.src.options.strategy_candidates.generator import (
    ChainQuote,
    StrategyCandidate,
)
from apps.api.src.options.strategy_candidates.service import (
    _attach_confidence_v2,
    _extract_quote_age,
)


class _MappingRow(dict):
    """Stand-in for a SQLAlchemy RowMapping (Mapping protocol: .get)."""


class _NoGetRow:
    """Pathological row without .get — guard must still return None."""


def test_extract_present_value():
    assert _extract_quote_age(_MappingRow(quote_age_seconds=180)) == 180.0


def test_extract_null_value():
    assert _extract_quote_age(_MappingRow(quote_age_seconds=None)) is None


def test_extract_missing_key_does_not_raise():
    assert _extract_quote_age(_MappingRow()) is None


def test_extract_object_without_get_does_not_raise():
    assert _extract_quote_age(_NoGetRow()) is None


def _candidate() -> StrategyCandidate:
    return StrategyCandidate(
        rule_id="SHORT_PUT_CREDIT_SPREAD",
        bias="bullish",
        directional_view="x",
        risk_profile="defined",
        confidence=0.70,
        iv_suitability=0.5,
        expiry_suitability=1.0,
        liquidity_suitability=0.75,
        composite_score=0.7,
        why_emitted="t",
        triggering_rule="t",
    )


def _quote(delta=-0.29) -> ChainQuote:
    return ChainQuote(bid=1.0, ask=1.1, mid=1.05, delta=delta, gamma=None,
                      theta=None, vega=None, iv=0.3,
                      open_interest=1000, volume=200)


def test_shadow_runs_with_missing_freshness():
    c = _candidate()
    _attach_confidence_v2(c, _quote(), None)
    d = c.diagnostics
    assert d["confidence_model"] == "v2_shadow"
    assert 0.0 <= d["confidence_v2"] <= 1.0
    assert d["confidence_v2_components"]["freshness_quality"] == 0.50
    assert any("quote age unavailable" in r
               for r in d["confidence_v2_reasons"])
    # v1 constant untouched
    assert c.confidence == 0.70


def test_shadow_runs_with_freshness_present():
    c = _candidate()
    _attach_confidence_v2(c, _quote(), 30.0)
    assert c.diagnostics["confidence_v2_components"][
        "freshness_quality"] == 1.0
    assert c.confidence == 0.70
