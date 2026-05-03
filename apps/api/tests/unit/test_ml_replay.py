"""Phase ML-2.5 tests — PIT + leakage + universe + outcome math + helpers.

DB-free: uses minimal stub objects for the Session-dependent paths.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import pytest

from apps.api.src.ml.replay.point_in_time import PITError
from apps.api.src.ml.replay.universe import resolve_universe
from apps.api.src.ml.replay.leakage import (
    FORBIDDEN_KEYS_IN_FEATURES, ReplayLeakageReport,
)
from apps.api.src.ml.replay.replayer import (
    _compute_pit_features, _regime_from_features, _replay_selector,
    _business_days,
)
from apps.api.src.data.catalysts.types import (
    CatalystSummary, TradePolicy, UpcomingEvent,
)


# ---------------------------------------------------------------------------
# Universe
# ---------------------------------------------------------------------------

def test_resolve_universe_uses_explicit_list():
    u = resolve_universe(explicit=["aapl", "msft", "aapl"])
    assert u.symbols == ("AAPL", "MSFT")
    # Survivorship warning always present
    assert any("survivorship" in w.lower() for w in u.warnings)


def test_resolve_universe_caps_max_symbols():
    u = resolve_universe(
        explicit=["A", "B", "C", "D", "E"], max_symbols=3,
    )
    assert len(u.symbols) == 3
    assert any("capped" in w for w in u.warnings)


def test_resolve_universe_empty_warning():
    u = resolve_universe(explicit=[])
    # Empty explicit falls through to env / default so symbols shouldn't be empty
    # unless env var also empty. Just ensure warnings are attached.
    assert len(u.warnings) >= 1


# ---------------------------------------------------------------------------
# Business-day iteration
# ---------------------------------------------------------------------------

def test_business_days_skips_weekends():
    start = dt.date(2025, 1, 3)          # Friday
    end   = dt.date(2025, 1, 8)          # Wednesday
    days = _business_days(start, end)
    # Fri 3, Mon 6, Tue 7, Wed 8
    assert days == [
        dt.date(2025, 1, 3),
        dt.date(2025, 1, 6),
        dt.date(2025, 1, 7),
        dt.date(2025, 1, 8),
    ]


# ---------------------------------------------------------------------------
# PIT features
# ---------------------------------------------------------------------------

def _synth_bars(n=80, start="2025-01-01"):
    dates = pd.bdate_range(start, periods=n)
    rng = np.random.default_rng(0)
    closes = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    return pd.DataFrame({
        "date": dates,
        "open": closes,
        "high": closes * 1.01,
        "low":  closes * 0.99,
        "close": closes,
        "volume": 1_000_000,
        "symbol": "SPY",
    })


def test_compute_pit_features_basic():
    bars = _synth_bars(80)
    feats, ts_max = _compute_pit_features(bars)
    assert ts_max == bars["date"].iloc[-1].date() \
           or ts_max == bars["date"].iloc[-1]
    assert "z_score" in feats
    assert "atr_ratio" in feats
    assert "vol_20d" in feats
    assert feats["vol_20d"] > 0


def test_compute_pit_features_returns_empty_when_too_short():
    bars = _synth_bars(10)
    feats, _ = _compute_pit_features(bars)
    assert feats == {}


# ---------------------------------------------------------------------------
# Replay selector
# ---------------------------------------------------------------------------

def _neutral_catalyst(policy: TradePolicy = TradePolicy.NEUTRAL) -> CatalystSummary:
    return CatalystSummary(
        symbol="SPY",
        as_of=dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc),
        next_event=None,
        days_to_earnings=None,
        has_earnings_soon=False,
        headlines=[],
        catalyst_score=0.0,
        event_risk_score=0.0,
        trade_policy=policy,
        short_reason="n/a",
        data_confidence=0.0,
        providers_used=[],
        partial=True,
    )


def test_selector_skips_when_catalyst_blocks():
    dec, conf, eng, skip = _replay_selector(
        feats={"z_score": -2.0, "range_loose": 1, "vol_elevated": 1,
                "mean_20d_ret": 0.0},
        regime={"stress_regime": True, "directional_regime": False,
                "neutral_regime": False, "gates_favorable": 2},
        catalyst=_neutral_catalyst(TradePolicy.BLOCK_NEW_ENTRY),
    )
    assert dec == "skip"
    assert eng == "none"
    assert skip is not None


def test_selector_fires_engine_a_on_stress_oversold():
    dec, conf, eng, skip = _replay_selector(
        feats={"z_score": -1.5, "range_loose": 1, "vol_elevated": 1,
                "mean_20d_ret": 0.0},
        regime={"stress_regime": True, "directional_regime": False,
                "neutral_regime": False, "gates_favorable": 2},
        catalyst=_neutral_catalyst(),
    )
    assert dec == "enter_long"
    assert eng == "A"
    assert skip is None


def test_selector_fires_engine_b_on_positive_directional():
    dec, conf, eng, skip = _replay_selector(
        feats={"z_score": 0.1, "mean_20d_ret": 0.002},
        regime={"stress_regime": False, "directional_regime": True,
                "neutral_regime": False, "gates_favorable": 3},
        catalyst=_neutral_catalyst(),
    )
    assert dec == "enter_long"
    assert eng == "B"


def test_regime_from_features_neutral_when_mild():
    r = _regime_from_features({
        "vol_elevated": 0, "vol_expanding": 0,
        "range_loose": 0, "mean_20d_ret": 0.0,
    })
    assert r["neutral_regime"] is True


# ---------------------------------------------------------------------------
# Leakage guard
# ---------------------------------------------------------------------------

def test_forbidden_keys_catch_outcome_blobs():
    # Simulate a features blob that accidentally contains an outcome
    bad_key = "forward_return"
    assert any(p in bad_key for p in FORBIDDEN_KEYS_IN_FEATURES)


def test_leakage_report_ok_shape():
    r = ReplayLeakageReport(
        ok=True, run_id="abc", n_decisions=10, n_outcomes=40,
    )
    d = r.to_dict()
    assert d["ok"] is True
    assert d["run_id"] == "abc"
    assert d["n_decisions"] == 10
    assert "violations" in d
    assert "label_start_on_or_before_decision" in d


# ---------------------------------------------------------------------------
# PIT accessor future-guard
# ---------------------------------------------------------------------------

class _StubSession:
    """Minimal session that records queries without executing them."""
    def execute(self, *_a, **_kw):
        raise RuntimeError("stub cannot execute")


def test_pit_get_bars_rejects_future():
    from apps.api.src.ml.replay.point_in_time import PointInTimeDataAccessor
    pit = PointInTimeDataAccessor(_StubSession())  # type: ignore[arg-type]
    with pytest.raises(PITError):
        pit.get_bars("SPY", as_of=dt.date.today() + dt.timedelta(days=1))


def test_pit_get_forward_bars_requires_positive_horizon():
    from apps.api.src.ml.replay.point_in_time import PointInTimeDataAccessor
    pit = PointInTimeDataAccessor(_StubSession())  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        pit.get_forward_bars("SPY", after=dt.date(2024, 1, 1), horizon_days=0)


# ---------------------------------------------------------------------------
# Replay dry_run doesn't attempt persistence
# ---------------------------------------------------------------------------

@dataclass
class _NoPersistSession:
    """Stub that explodes if anything is executed — validates dry_run path."""
    def execute(self, *_, **__):
        raise AssertionError("dry_run should not execute SQL")

    def commit(self):
        raise AssertionError("dry_run should not commit")


def test_replayer_dry_run_handles_no_universe_gracefully():
    from apps.api.src.ml.replay.replayer import Replayer, ReplayRunConfig
    # With empty universe + dry_run there should be no SQL calls.
    cfg = ReplayRunConfig(
        replay_name="unit-dry-run",
        start_date=dt.date(2025, 1, 6),
        end_date=dt.date(2025, 1, 10),
        universe=tuple(),           # empty → nothing to replay
        dry_run=True,
    )
    r = Replayer(_NoPersistSession())  # type: ignore[arg-type]
    result = r.run(cfg)
    assert result.persisted is False
    assert result.n_decisions == 0
