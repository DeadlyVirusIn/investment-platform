"""Tests for reliability FallbackChain.

Critical invariants:
  * chain NEVER raises
  * first successful provider wins
  * missing critical field flagged
  * stale data annotated but returned
"""

from __future__ import annotations

import datetime as dt

import pytest

from apps.api.src.data.reliability.chain import (
    FallbackChain, MissingData, ProviderError, ProviderResult, StaleData,
)
from apps.api.src.data.reliability.types import ReliableBundle


def _fresh(val: float) -> ProviderResult[float]:
    return ProviderResult(
        value=val, as_of=dt.datetime.now(dt.timezone.utc), confidence=1.0,
    )


def test_first_provider_wins():
    chain = FallbackChain[float]("x")
    chain.add("yahoo",   lambda: _fresh(1.0))
    chain.add("finnhub", lambda: _fresh(2.0))
    rv = chain.execute()
    assert rv.usable
    assert rv.value == 1.0
    assert rv.source == "yahoo"


def test_falls_through_on_provider_error():
    chain = FallbackChain[float]("x")
    chain.add("yahoo",   lambda: (_ for _ in ()).throw(ProviderError("oops")))
    chain.add("finnhub", lambda: _fresh(2.0))
    rv = chain.execute()
    assert rv.source == "finnhub"
    assert rv.value == 2.0


def test_missing_data_is_not_fatal():
    chain = FallbackChain[float]("x", critical=True)
    chain.add("yahoo",   lambda: (_ for _ in ()).throw(MissingData("none")))
    chain.add("finnhub", lambda: (_ for _ in ()).throw(MissingData("none")))
    rv = chain.execute()
    assert rv.missing
    assert not rv.usable
    assert rv.critical is True


def test_unexpected_crash_is_swallowed():
    chain = FallbackChain[float]("x")
    def explode(): raise RuntimeError("boom")
    chain.add("bad",     explode)
    chain.add("finnhub", lambda: _fresh(5.0))
    rv = chain.execute()
    assert rv.usable
    assert rv.source == "finnhub"


def test_stale_flag_degrades_confidence():
    old = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=5)
    chain = FallbackChain[float]("x", max_age=dt.timedelta(days=1))
    chain.add("yahoo", lambda: ProviderResult(value=1.0, as_of=old, confidence=1.0))
    rv = chain.execute()
    assert rv.usable
    assert rv.stale is True
    assert rv.confidence < 1.0


def test_bundle_confidence_caps_to_zero_on_critical_missing():
    chain_ok = FallbackChain[float]("feature_ok")
    chain_ok.add("yahoo", lambda: _fresh(1.0))
    chain_bad = FallbackChain[float]("feature_critical", critical=True)
    chain_bad.add("y", lambda: (_ for _ in ()).throw(MissingData("gone")))
    bundle = ReliableBundle()
    bundle.put(chain_ok.execute())
    bundle.put(chain_bad.execute())
    q = bundle.quality()
    assert q.confidence == 0.0
    assert "feature_critical" in q.missing_fields
    assert "feature_critical" in bundle.critical_missing()


def test_staledata_triggers_fallthrough_not_use():
    chain = FallbackChain[float]("x")
    chain.add("old",   lambda: (_ for _ in ()).throw(StaleData("too old")))
    chain.add("fresh", lambda: _fresh(7.0))
    rv = chain.execute()
    assert rv.value == 7.0
    assert rv.source == "fresh"


def test_empty_chain_returns_missing():
    chain = FallbackChain[float]("x")
    rv = chain.execute()
    assert rv.missing
    assert rv.source == "none"


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
