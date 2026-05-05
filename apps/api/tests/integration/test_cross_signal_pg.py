"""Cross-signal stock<->options analytics — read-only integration tests.

Verifies:
  * Pure bucketing (score / gate / trend / iv / strategy).
  * Strategy-map joins stock + options outcomes correctly.
  * Relative edge math: edge = options_avg - stock_avg.
  * Confidence tiers: low (<20), medium (>=20), high (>=50 + multi-h).
  * Recommendation respects edge thresholds + confidence floor.
  * Endpoint contracts: range, vocab, thresholds, notice fields.
  * No write side-effects: paper trade tables untouched, stock
    candidate_idea row counts unchanged.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from apps.api.src.db import get_session
from apps.api.src.db.models import (
    Asset, CandidateIdea, PriceBar, RegimeSnapshot,
)
from apps.api.src.db.options_models import (
    OptionsFeatureDaily, OptionsStrategyOutcome,
)
from apps.api.src.domain.cross_signal.strategy_map import (
    score_bucket, gate_bucket, trend_bucket, iv_bucket,
    strategy_bucket_from_db_name,
    build_strategy_map, build_today_assistant,
)
from apps.api.src.main import app


pytestmark = pytest.mark.integration


@pytest.fixture
def client(pg_engine):
    SessionCls = sessionmaker(
        bind=pg_engine, class_=Session, expire_on_commit=False,
    )

    def _override():
        s = SessionCls()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_session, None)


# ---------------------------------------------------------------------------
# Pure bucketing helpers — no DB
# ---------------------------------------------------------------------------

def test_score_bucket():
    assert score_bucket(0.40) == "strong_buy"
    assert score_bucket(0.30) == "strong_buy"
    assert score_bucket(0.20) == "moderate_buy"
    assert score_bucket(0.10) == "moderate_buy"
    assert score_bucket(0.00) == "neutral"
    assert score_bucket(-0.09) == "neutral"
    assert score_bucket(-0.20) == "moderate_sell"
    assert score_bucket(-0.29) == "moderate_sell"
    assert score_bucket(-0.30) == "strong_sell"
    assert score_bucket(-0.40) == "strong_sell"
    assert score_bucket(None) == "neutral"


def test_gate_bucket():
    assert gate_bucket("accepted", None) == "strict_pass"
    assert gate_bucket(
        "rejected", "extended_from_sma200",
    ) == "soft_gate_relaxed"
    assert gate_bucket("rejected", "regime_off") == "hard_blocked"
    assert gate_bucket("rejected", "stale_data") == "data_blocked"
    assert gate_bucket("rejected", None) == "hard_blocked"


def test_trend_bucket():
    assert trend_bucket("uptrend") == "uptrend"
    assert trend_bucket("BULLISH") == "uptrend"
    assert trend_bucket("downtrend") == "downtrend"
    assert trend_bucket("bear") == "downtrend"
    assert trend_bucket("sideways") == "sideways"
    assert trend_bucket(None) == "sideways"
    assert trend_bucket("unknown_value") == "sideways"


def test_iv_bucket():
    assert iv_bucket(None) == "unknown_iv"
    assert iv_bucket(0.10) == "low_iv"
    assert iv_bucket(0.24) == "low_iv"
    assert iv_bucket(0.25) == "medium_iv"
    assert iv_bucket(0.44) == "medium_iv"
    assert iv_bucket(0.45) == "high_iv"


def test_strategy_bucket_from_db_name():
    assert strategy_bucket_from_db_name("LONG_CALL") == "long_call"
    assert (
        strategy_bucket_from_db_name("BULL_CALL_SPREAD")
        == "bull_call_spread"
    )
    assert (
        strategy_bucket_from_db_name("SHORT_PUT_CREDIT_SPREAD")
        == "credit_spread"
    )
    assert strategy_bucket_from_db_name("IRON_CONDOR") == "iron_condor"
    assert strategy_bucket_from_db_name(None) == "stock_only"
    assert strategy_bucket_from_db_name("UNRECOGNIZED") == "stock_only"


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------

def _mk_asset(symbol: str) -> Asset:
    return Asset(
        symbol=symbol, name=symbol, asset_class="equity",
        sector="tech", currency="USD", is_active=True,
    )


def _seed_stock(
    session: Session, *, symbol: str, as_of: dt.date,
    score: float, status: str = "accepted",
    rejection_reason: str | None = None,
    horizon_days: int = 5,
    fwd_return: float = 0.03,
) -> str:
    """Seed asset, candidate_idea, and `horizon_days+1` daily price
    bars realising `fwd_return`. Returns asset_id."""
    a = _mk_asset(symbol)
    session.add(a)
    session.flush()
    aid = a.id
    entry_px = 100.0
    session.add(PriceBar(
        asset_id=aid, timeframe="1d",
        ts=dt.datetime.combine(
            as_of, dt.time(20, 0), tzinfo=dt.timezone.utc,
        ),
        open=entry_px, high=entry_px * 1.01, low=entry_px * 0.99,
        close=entry_px, adjusted_close=entry_px,
        provider="test",
    ))
    # Forward bars
    for i in range(1, horizon_days + 1):
        px = entry_px * (1 + (fwd_return * i / horizon_days))
        session.add(PriceBar(
            asset_id=aid, timeframe="1d",
            ts=dt.datetime.combine(
                as_of + dt.timedelta(days=i),
                dt.time(20, 0), tzinfo=dt.timezone.utc,
            ),
            open=px, high=px * 1.01, low=px * 0.99,
            close=px, adjusted_close=px,
            provider="test",
        ))
    session.add(CandidateIdea(
        as_of_date=as_of, asset_id=aid,
        model_version="test_v1", engine="stock_swing",
        status=status, action=("Buy" if score > 0 else "Hold"),
        rejection_reason=rejection_reason,
        composite_score=Decimal(str(score)),
        confidence=Decimal("0.7"),
    ))
    session.commit()
    return aid


def _seed_regime(
    session: Session, *, as_of: dt.date, trend: str = "uptrend",
) -> None:
    session.add(RegimeSnapshot(
        as_of_date=as_of, benchmark_symbol="SPY",
        market_trend=trend, vol_regime="normal", breadth_regime="ok",
        sma50_over_sma200=True,
        realized_vol_20d=Decimal("0.15"),
        atr_pctile_1y=Decimal("0.40"),
    ))
    session.commit()


def _seed_iv(
    session: Session, *, as_of: dt.date, underlying: str,
    atm_iv: float = 0.30,
) -> None:
    session.add(OptionsFeatureDaily(
        as_of_date=as_of, underlying=underlying,
        atm_iv=Decimal(str(atm_iv)),
    ))
    session.commit()


def _seed_options_outcome(
    session: Session, *, as_of: dt.date, underlying: str,
    strategy: str = "BULL_CALL_SPREAD", horizon: str = "5D",
    fwd_return: float = 0.05, label: str | None = None,
    submitted_offset_seconds: int = 0,
) -> None:
    submitted = dt.datetime.combine(
        as_of, dt.time(21, 0), tzinfo=dt.timezone.utc,
    ) + dt.timedelta(seconds=submitted_offset_seconds)
    if label is None:
        label = (
            "good" if fwd_return >= 0.01
            else ("bad" if fwd_return <= -0.01 else "neutral")
        )
    session.add(OptionsStrategyOutcome(
        underlying=underlying, strategy_name=strategy,
        legs_json=[{"option_symbol": "X", "action": "buy"}],
        as_of_date=as_of, submitted_at_utc=submitted,
        horizon=horizon,
        entry_reference=Decimal("1.00"),
        exit_reference=Decimal("1.00") + Decimal(str(fwd_return)),
        forward_return_pct=Decimal(str(fwd_return)),
        mfe_pct=Decimal(str(abs(fwd_return))),
        mae_pct=Decimal(str(-abs(fwd_return) * 0.5)),
        outcome_label=label, source="suggestion", mode="strict",
    ))
    session.commit()


# ---------------------------------------------------------------------------
# Strategy-map integration
# ---------------------------------------------------------------------------

def test_strategy_map_basic_join(pg_session):
    """Single (date, underlying) — stock + options edge present."""
    as_of = dt.date(2026, 4, 1)
    _seed_regime(pg_session, as_of=as_of, trend="uptrend")
    _seed_iv(pg_session, as_of=as_of, underlying="AAPL", atm_iv=0.30)
    _seed_stock(
        pg_session, symbol="AAPL", as_of=as_of, score=0.40,
        fwd_return=0.01,
    )
    _seed_options_outcome(
        pg_session, as_of=as_of, underlying="AAPL",
        strategy="BULL_CALL_SPREAD", fwd_return=0.05,
    )
    items = build_strategy_map(
        pg_session, as_of_from=as_of, as_of_to=as_of, horizon="5D",
    )
    bcs = [
        i for i in items
        if i["strategy"] == "bull_call_spread"
        and i["signal_bucket"] == "strong_buy"
    ]
    assert bcs, items
    it = bcs[0]
    assert it["trend_bucket"] == "uptrend"
    assert it["iv_bucket"] == "medium_iv"
    assert it["stock_avg_return_pct"] == pytest.approx(0.01, abs=1e-6)
    assert it["options_avg_return_pct"] == pytest.approx(0.05, abs=1e-6)
    assert it["relative_edge_pct"] == pytest.approx(0.04, abs=1e-6)


def test_strategy_map_low_confidence_when_few_samples(pg_session):
    as_of = dt.date(2026, 4, 1)
    _seed_regime(pg_session, as_of=as_of)
    _seed_iv(pg_session, as_of=as_of, underlying="AAPL")
    _seed_stock(
        pg_session, symbol="AAPL", as_of=as_of, score=0.40,
        fwd_return=0.01,
    )
    _seed_options_outcome(
        pg_session, as_of=as_of, underlying="AAPL",
        fwd_return=0.05,
    )
    items = build_strategy_map(
        pg_session, as_of_from=as_of, as_of_to=as_of, horizon="5D",
    )
    bcs = [
        i for i in items if i["strategy"] == "bull_call_spread"
    ][0]
    assert bcs["confidence"] == "low"
    # Low confidence + insufficient_data recommendation
    assert bcs["recommendation"] == "insufficient_data"


def test_strategy_map_prefer_options_recommendation(pg_session):
    """20+ samples + edge > 0.5%  → prefer_options."""
    base = dt.date(2026, 4, 1)
    for i in range(25):
        as_of = base + dt.timedelta(days=i)
        _seed_regime(pg_session, as_of=as_of)
        sym = f"SYM{i:02d}"
        _seed_iv(pg_session, as_of=as_of, underlying=sym, atm_iv=0.30)
        _seed_stock(
            pg_session, symbol=sym, as_of=as_of, score=0.40,
            fwd_return=0.005,
        )
        _seed_options_outcome(
            pg_session, as_of=as_of, underlying=sym,
            strategy="BULL_CALL_SPREAD", fwd_return=0.05,
        )
    items = build_strategy_map(
        pg_session, as_of_from=base,
        as_of_to=base + dt.timedelta(days=25),
        horizon="5D",
    )
    bcs = [
        i for i in items
        if i["strategy"] == "bull_call_spread"
        and i["signal_bucket"] == "strong_buy"
    ][0]
    assert bcs["sample_count"] >= 20
    assert bcs["confidence"] in ("medium", "high")
    assert bcs["relative_edge_pct"] > 0.005
    assert bcs["recommendation"] == "prefer_options"


def test_strategy_map_prefer_stock_when_options_underperform(pg_session):
    base = dt.date(2026, 4, 1)
    for i in range(25):
        as_of = base + dt.timedelta(days=i)
        _seed_regime(pg_session, as_of=as_of)
        sym = f"SBL{i:02d}"
        _seed_iv(pg_session, as_of=as_of, underlying=sym, atm_iv=0.30)
        _seed_stock(
            pg_session, symbol=sym, as_of=as_of, score=0.40,
            fwd_return=0.04,
        )
        _seed_options_outcome(
            pg_session, as_of=as_of, underlying=sym,
            strategy="LONG_CALL", fwd_return=-0.02,
        )
    items = build_strategy_map(
        pg_session, as_of_from=base,
        as_of_to=base + dt.timedelta(days=25),
        horizon="5D",
    )
    lc = [
        i for i in items
        if i["strategy"] == "long_call"
        and i["signal_bucket"] == "strong_buy"
    ][0]
    assert lc["relative_edge_pct"] < -0.005
    assert lc["recommendation"] == "prefer_stock"


def test_strategy_map_buckets_iv_and_trend(pg_session):
    as_of = dt.date(2026, 4, 1)
    _seed_regime(pg_session, as_of=as_of, trend="downtrend")
    _seed_iv(pg_session, as_of=as_of, underlying="AAPL", atm_iv=0.50)
    _seed_stock(
        pg_session, symbol="AAPL", as_of=as_of, score=-0.40,
        fwd_return=-0.03,
    )
    _seed_options_outcome(
        pg_session, as_of=as_of, underlying="AAPL",
        strategy="LONG_PUT", fwd_return=0.04,
    )
    items = build_strategy_map(
        pg_session, as_of_from=as_of, as_of_to=as_of, horizon="5D",
    )
    lp = [
        i for i in items
        if i["strategy"] == "long_put"
        and i["signal_bucket"] == "strong_sell"
    ][0]
    assert lp["trend_bucket"] == "downtrend"
    assert lp["iv_bucket"] == "high_iv"


# ---------------------------------------------------------------------------
# Today assistant
# ---------------------------------------------------------------------------

def test_today_assistant_attaches_best_strategy(pg_session):
    """Set up enough history that a recommendation is medium-confident."""
    today = dt.date(2026, 4, 30)
    history_start = today - dt.timedelta(days=30)
    for i in range(25):
        d = history_start + dt.timedelta(days=i)
        _seed_regime(pg_session, as_of=d, trend="uptrend")
        sym = f"HST{i:02d}"
        _seed_iv(pg_session, as_of=d, underlying=sym, atm_iv=0.30)
        _seed_stock(
            pg_session, symbol=sym, as_of=d, score=0.40,
            fwd_return=0.005,
        )
        _seed_options_outcome(
            pg_session, as_of=d, underlying=sym,
            strategy="BULL_CALL_SPREAD", fwd_return=0.04,
        )
    # Today's row
    _seed_regime(pg_session, as_of=today, trend="uptrend")
    _seed_iv(pg_session, as_of=today, underlying="AMZN", atm_iv=0.32)
    _seed_stock(
        pg_session, symbol="AMZN", as_of=today, score=0.55,
        fwd_return=0.0,
    )

    items = build_today_assistant(
        pg_session, as_of=today, lookback_days=60, limit=10,
    )
    amzn = [i for i in items if i["underlying"] == "AMZN"]
    assert amzn
    it = amzn[0]
    assert it["stock_signal"] == "strong_buy"
    assert it["iv_bucket"] == "medium_iv"
    # The historical bucket should propose bull_call_spread
    assert it["best_options_strategy"] == "bull_call_spread"
    assert it["decision_hint"] == "prefer_options"
    assert it["historical_edge"]["confidence"] in ("medium", "high")


def test_today_assistant_insufficient_data_default(pg_session):
    today = dt.date(2026, 4, 30)
    _seed_regime(pg_session, as_of=today, trend="uptrend")
    _seed_iv(pg_session, as_of=today, underlying="AAPL", atm_iv=0.30)
    _seed_stock(
        pg_session, symbol="AAPL", as_of=today, score=0.40,
        fwd_return=0.0,
    )
    items = build_today_assistant(
        pg_session, as_of=today, lookback_days=14, limit=5,
    )
    aapl = [i for i in items if i["underlying"] == "AAPL"][0]
    assert aapl["decision_hint"] == "insufficient_data"
    assert aapl["historical_edge"]["confidence"] == "low"


# ---------------------------------------------------------------------------
# Endpoint contracts
# ---------------------------------------------------------------------------

def test_endpoint_strategy_map_shape(client):
    resp = client.get(
        "/api/performance/cross-signal/strategy-map"
        "?as_of_from=2026-04-01&as_of_to=2026-04-30&horizon=5D"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["horizon"] == "5D"
    assert body["date_range"]["from"] == "2026-04-01"
    assert body["date_range"]["to"] == "2026-04-30"
    assert "vocab" in body and "score_buckets" in body["vocab"]
    assert body["thresholds"]["edge_prefer_pct"] == 0.005
    assert "ML_CAN_AFFECT_TRADES" in body["notice"] or "Read-only" in body["notice"]


def test_endpoint_strategy_map_rejects_bad_horizon(client):
    resp = client.get(
        "/api/performance/cross-signal/strategy-map?horizon=99D"
    )
    body = resp.json()
    assert "error" in body


def test_endpoint_strategy_map_rejects_inverted_dates(client):
    resp = client.get(
        "/api/performance/cross-signal/strategy-map"
        "?as_of_from=2026-05-01&as_of_to=2026-04-01"
    )
    body = resp.json()
    assert "error" in body


def test_endpoint_today_default_today(client):
    resp = client.get("/api/performance/cross-signal/today")
    assert resp.status_code == 200
    body = resp.json()
    assert "as_of_date" in body and "items" in body and "notice" in body


def test_endpoint_today_with_limit(client):
    resp = client.get(
        "/api/performance/cross-signal/today?limit=5"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] <= 5


# ---------------------------------------------------------------------------
# Side-effect safety
# ---------------------------------------------------------------------------

def test_strategy_map_makes_no_writes(pg_session):
    as_of = dt.date(2026, 4, 1)
    _seed_regime(pg_session, as_of=as_of)
    _seed_iv(pg_session, as_of=as_of, underlying="AAPL")
    _seed_stock(
        pg_session, symbol="AAPL", as_of=as_of, score=0.40,
        fwd_return=0.01,
    )
    _seed_options_outcome(
        pg_session, as_of=as_of, underlying="AAPL", fwd_return=0.05,
    )
    n_before = pg_session.execute(
        text("SELECT count(*) FROM options_strategy_outcome")
    ).scalar()
    n_paper = pg_session.execute(
        text("SELECT count(*) FROM options_paper_trade")
    ).scalar()
    n_cand = pg_session.execute(
        text("SELECT count(*) FROM candidate_idea")
    ).scalar()
    build_strategy_map(
        pg_session, as_of_from=as_of, as_of_to=as_of, horizon="5D",
    )
    assert pg_session.execute(
        text("SELECT count(*) FROM options_strategy_outcome")
    ).scalar() == n_before
    assert pg_session.execute(
        text("SELECT count(*) FROM options_paper_trade")
    ).scalar() == n_paper
    assert pg_session.execute(
        text("SELECT count(*) FROM candidate_idea")
    ).scalar() == n_cand
