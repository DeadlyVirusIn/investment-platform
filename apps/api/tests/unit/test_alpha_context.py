"""SYSTEM-ALPHA-7 — context rec correctness + safety."""

from __future__ import annotations

from apps.api.src.alpha.context_calibration import (
    AUTO_MIN_CONFIDENCE, MIN_MULTIPLIER, MIN_SAMPLE,
    ContextKey, ContextRec, ContextStats, _propose_multiplier,
    _reason_from_stats,
)


def _stats(*, n=30, avg=-0.5, wr=0.4, sharpe=-0.5):
    return ContextStats(
        context=ContextKey(engine="B", regime="directional",
                              mode="exploratory"),
        sample_size=n, win_rate=wr, avg_return=avg,
        median_return=avg, sharpe=sharpe, total_return=avg * n,
    )


# ---------------------------------------------------------------------------
# propose_multiplier
# ---------------------------------------------------------------------------

def test_propose_reduces_on_negative_sharpe_and_return():
    m = _propose_multiplier(_stats(n=50, avg=-0.8, sharpe=-0.4), 1.0)
    assert m is not None
    assert m <= 0.3


def test_propose_floor_enforced():
    m = _propose_multiplier(_stats(n=50, avg=-2.0, sharpe=-2.0), 1.0)
    assert m is not None
    assert m >= MIN_MULTIPLIER


def test_propose_noop_when_positive():
    m = _propose_multiplier(_stats(n=50, avg=0.3, sharpe=0.5, wr=0.55), 1.0)
    assert m is None


def test_propose_reduces_on_low_winrate():
    m = _propose_multiplier(_stats(n=30, avg=0.1, sharpe=0.1, wr=0.35), 1.0)
    assert m is not None
    assert m < 1.0


# ---------------------------------------------------------------------------
# safety — rec never increases
# ---------------------------------------------------------------------------

def test_rec_auto_applicable_gates():
    stats = _stats(n=50, avg=-1.0, sharpe=-0.5)
    r = ContextRec(
        context=stats.context,
        current_multiplier=1.0,
        proposed_multiplier=0.3,
        stats=stats,
        reason="x", confidence=0.85,
    )
    assert r.auto_applicable is True
    # Increase attempt → never auto
    r2 = ContextRec(
        context=stats.context,
        current_multiplier=0.5,
        proposed_multiplier=0.8,      # attacker raises
        stats=stats,
        reason="x", confidence=0.95,
    )
    assert r2.auto_applicable is False


def test_rec_below_min_sample_not_auto():
    s = _stats(n=10)
    r = ContextRec(
        context=s.context, current_multiplier=1.0,
        proposed_multiplier=0.5, stats=s,
        reason="x", confidence=0.99,
    )
    assert r.auto_applicable is False


# ---------------------------------------------------------------------------
# context key stability
# ---------------------------------------------------------------------------

def test_context_key_deterministic():
    a = ContextKey(engine="B", regime="directional", mode="exploratory")
    b = ContextKey(engine="B", regime="directional", mode="exploratory")
    assert a.to_key() == b.to_key()


def test_context_key_differs_on_mode():
    a = ContextKey(engine="B", regime="directional", mode="exploratory")
    b = ContextKey(engine="B", regime="directional", mode="strict")
    assert a.to_key() != b.to_key()


def test_auto_min_confidence_is_tight():
    assert AUTO_MIN_CONFIDENCE >= 0.7
    assert MIN_SAMPLE >= 20
    assert MIN_MULTIPLIER >= 0.2


def test_reason_string_contains_engine_and_regime():
    s = _stats()
    msg = _reason_from_stats(s)
    assert "Engine B" in msg
    assert "directional" in msg
    assert "exploratory" in msg
