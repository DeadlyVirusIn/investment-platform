"""ML-2.6 — dedupe keys, rate limit, provider failure tolerance,
coverage scoring, readiness gate transitions, dataset safety guard.

DB-free. Stub sessions used where SQL would execute.
"""

from __future__ import annotations

import datetime as dt

import pytest

from apps.api.src.data.catalysts.backfill.base import (
    BackfillProviderError, EarningsRecord, NewsRecord,
    ProviderFetchResult,
)
from apps.api.src.data.catalysts.backfill.dedupe import (
    earnings_dedupe_key, news_dedupe_key,
)
from apps.api.src.data.catalysts.backfill.rate_limit import RateLimiter
from apps.api.src.data.catalysts.backfill.coverage import (
    SymbolCoverage, _tier_for_coverage,
)
from apps.api.src.ml.replay.validation_harness import (
    ReplayReadiness, _recommendation_and_cfg,
)


# ---------------------------------------------------------------------------
# Dedupe keys
# ---------------------------------------------------------------------------

def test_news_dedupe_key_stable_for_identical_inputs():
    t = dt.datetime(2025, 3, 1, 12, 0, tzinfo=dt.timezone.utc)
    a = news_dedupe_key(symbol="AAPL", provider="finnhub",
                         url="http://x/article", title="Apple beats",
                         published_at=t)
    b = news_dedupe_key(symbol="AAPL", provider="finnhub",
                         url="http://x/article", title="APPLE   BEATS",
                         published_at=t)
    assert a == b                          # whitespace + case normalized


def test_news_dedupe_key_differs_on_provider():
    t = dt.datetime(2025, 3, 1, tzinfo=dt.timezone.utc)
    a = news_dedupe_key(symbol="AAPL", provider="finnhub",
                         url="u", title="Apple beats", published_at=t)
    b = news_dedupe_key(symbol="AAPL", provider="yahoo",
                         url="u", title="Apple beats", published_at=t)
    assert a != b


def test_earnings_dedupe_key_stable():
    a = earnings_dedupe_key(symbol="AAPL", provider="finnhub",
                              event_date=dt.date(2025, 4, 30),
                              fiscal_period="Q2")
    b = earnings_dedupe_key(symbol="AAPL", provider="finnhub",
                              event_date=dt.date(2025, 4, 30),
                              fiscal_period="Q2")
    assert a == b
    assert "AAPL" in a


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

def test_rate_limiter_allows_up_to_budget():
    rl = RateLimiter(max_per_minute=5, max_wait_secs=0.0)
    for _ in range(5):
        assert rl.wait() is True
    # 6th should fail since max_wait_secs=0
    assert rl.wait() is False


# ---------------------------------------------------------------------------
# NewsRecord / EarningsRecord validation
# ---------------------------------------------------------------------------

def test_news_record_requires_tz_aware_published_at():
    bad = NewsRecord(
        symbol="AAPL", source="s", provider="finnhub",
        title="t", url="http://x",
        published_at=dt.datetime(2025, 3, 1, 12, 0),  # naive
    )
    with pytest.raises(BackfillProviderError):
        bad.validate()


def test_earnings_record_warns_missing_known_at_is_ok_but_typed():
    rec = EarningsRecord(
        symbol="AAPL", provider="finnhub",
        event_date=dt.date(2025, 4, 30),
        known_at=None,
    )
    rec.validate()              # no exception — known_at None permitted


# ---------------------------------------------------------------------------
# Coverage tiers
# ---------------------------------------------------------------------------

def test_coverage_tier_thresholds():
    assert _tier_for_coverage(0.9, 0.8) == "excellent"
    assert _tier_for_coverage(0.9, 0.2) == "usable"      # known_at low
    assert _tier_for_coverage(0.6, 0.0) == "usable"
    assert _tier_for_coverage(0.2, 0.0) == "weak"


def test_symbol_coverage_to_dict_stable():
    c = SymbolCoverage(
        symbol="AAPL", months_covered=10, news_count_total=100,
        earnings_events=4, earnings_known_at_count=2,
        confidence=0.75, quality_tier="usable",
    )
    d = c.to_dict()
    assert d["symbol"] == "AAPL"
    assert abs(d["earnings_known_at_rate"] - 0.5) < 1e-9


# ---------------------------------------------------------------------------
# Readiness recommendations
# ---------------------------------------------------------------------------

def test_readiness_leakage_never_allows_replay():
    _, cfg = _recommendation_and_cfg(
        ReplayReadiness.NOT_READY_LEAKAGE_RISK,
    )
    assert cfg["ML_DATASET_INCLUDE_REPLAY"] is False
    assert cfg["ML_REPLAY_WEIGHT"] == 0.0


def test_readiness_calibration_only_keeps_replay_excluded():
    _, cfg = _recommendation_and_cfg(ReplayReadiness.CALIBRATION_ONLY)
    assert cfg["ML_DATASET_INCLUDE_REPLAY"] is False


def test_readiness_ready_for_weighted_test_limits_weight():
    _, cfg = _recommendation_and_cfg(
        ReplayReadiness.READY_FOR_WEIGHTED_TEST,
    )
    assert cfg["ML_DATASET_INCLUDE_REPLAY"] is True
    assert cfg["ML_REPLAY_WEIGHT"] == 0.25


# ---------------------------------------------------------------------------
# Dataset safety guard (replay silent drop)
# ---------------------------------------------------------------------------

class _FakeSessionEmpty:
    """Session stub that always returns no rows."""
    def execute(self, *_a, **_kw):
        class R:
            def mappings(self): return self
            def all(self):       return []
            def first(self):     return None
            def fetchone(self):  return None
            def scalar(self):    return 0
        return R()
    def commit(self):  pass
    def close(self):   pass


def test_dataset_combined_silently_drops_replay_when_not_ready(monkeypatch):
    from apps.api.src.config import settings
    monkeypatch.setattr(settings, "ML_DATASET_INCLUDE_REPLAY", False)
    from apps.api.src.ml.dataset import build_dataset
    r = build_dataset(_FakeSessionEmpty(), source="combined")
    assert "replay_blocked_reason" in r.diagnostics
    # No crash, no frame
    assert r.n_rows == 0


def test_dataset_combined_allowed_with_explicit_run_ids(monkeypatch):
    from apps.api.src.config import settings
    monkeypatch.setattr(settings, "ML_DATASET_INCLUDE_REPLAY", False)
    from apps.api.src.ml.dataset import build_dataset
    r = build_dataset(
        _FakeSessionEmpty(), source="combined",
        replay_run_ids=["run-1"],
    )
    # Explicit run id bypasses env flag; diagnostics shouldn't have block
    assert "replay_blocked_reason" not in r.diagnostics


# ---------------------------------------------------------------------------
# Provider fetch result shape
# ---------------------------------------------------------------------------

def test_provider_fetch_result_default_empty():
    pfr = ProviderFetchResult()
    assert pfr.news == []
    assert pfr.earnings == []
    assert pfr.warnings == []
