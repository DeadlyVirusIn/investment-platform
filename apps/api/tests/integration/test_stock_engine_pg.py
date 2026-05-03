"""Integration: decision engine job + /api/stock-engine endpoints."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from apps.api.src.db.models import (
    Asset,
    CandidateIdea,
    FactorSnapshot,
    RegimeSnapshot,
    UniverseMembership,
)
from apps.api.src.domain.stock_engine.scoring import MODEL_VERSION
from apps.worker.src.jobs.generate_stock_candidates import generate_stock_candidates

pytestmark = pytest.mark.integration

UNIVERSE = "stock_swing_v1"


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


def _asset(
    pg_session: Session, symbol: str, sector: str = "tech",
    asset_class: str = "equity",
) -> Asset:
    a = Asset(
        symbol=symbol, asset_class=asset_class, exchange="NASDAQ",
        currency="USD", sector=sector,
    )
    pg_session.add(a)
    pg_session.flush()
    pg_session.commit()
    return a


def _member(pg_session: Session, asset: Asset, start: dt.date) -> None:
    pg_session.add(UniverseMembership(
        universe_name=UNIVERSE, asset_id=asset.id,
        start_date=start, reason="seeded",
    ))
    pg_session.commit()


def _regime(
    pg_session: Session, as_of: dt.date,
    market_trend: str = "uptrend", vol_regime: str = "normal",
) -> None:
    pg_session.add(RegimeSnapshot(
        as_of_date=as_of, benchmark_symbol="SPY",
        market_trend=market_trend, vol_regime=vol_regime, breadth_regime=None,
        sma50_over_sma200=True, realized_vol_20d=Decimal("0.14"),
        atr_pctile_1y=Decimal("0.4"),
    ))
    pg_session.commit()


def _factor(
    pg_session: Session, asset: Asset, as_of: dt.date,
    *,
    enough_data: bool = True, stale_data: bool = False,
    rm60: Decimal | None = Decimal("1.0"),
    rm20: Decimal | None = Decimal("0.5"),
    sector_rank: Decimal | None = Decimal("0.7"),
    trend_20d: Decimal | None = Decimal("1.0"),
    price_vs_200: Decimal | None = Decimal("0.05"),
    atr_pct: Decimal | None = Decimal("0.02"),
    adv: Decimal | None = Decimal("60000000"),
    earnings_days: int | None = None,
) -> None:
    pg_session.add(FactorSnapshot(
        as_of_date=as_of, asset_id=asset.id,
        residual_momentum_60d=rm60,
        residual_momentum_20d=rm20,
        sector_relative_rank=sector_rank,
        trend_strength_20d=trend_20d,
        price_vs_200sma=price_vs_200,
        atr_percent_14=atr_pct,
        avg_dollar_volume_20d=adv,
        earnings_proximity_days=earnings_days,
        feature_set_hash="testhash",
        enough_data=enough_data, stale_data=stale_data,
    ))
    pg_session.commit()


# ---------------------------------------------------------------------------
# Job tests
# ---------------------------------------------------------------------------


async def test_job_writes_one_row_per_asset(pg_session: Session) -> None:
    as_of = dt.date(2026, 4, 17)
    _regime(pg_session, as_of)

    a1 = _asset(pg_session, "BUY1")
    a2 = _asset(pg_session, "HOLD1")
    _member(pg_session, a1, dt.date(2024, 1, 1))
    _member(pg_session, a2, dt.date(2024, 1, 1))

    _factor(pg_session, a1, as_of, rm60=Decimal("3"), rm20=Decimal("3"),
            sector_rank=Decimal("1"), trend_20d=Decimal("2"))
    _factor(pg_session, a2, as_of, rm60=Decimal("0"), rm20=Decimal("0"),
            sector_rank=Decimal("0.5"), trend_20d=Decimal("0"))

    await generate_stock_candidates(as_of)

    pg_session.expire_all()
    rows = list(pg_session.query(CandidateIdea).filter_by(as_of_date=as_of).all())
    assert len(rows) == 2
    by_asset = {r.asset_id: r for r in rows}
    assert by_asset[a1.id].status == "accepted"
    assert by_asset[a1.id].action == "Buy"
    assert by_asset[a2.id].status == "accepted"
    assert by_asset[a2.id].action == "Hold"
    # Model version stable
    assert all(r.model_version == MODEL_VERSION for r in rows)


async def test_job_logs_every_asset_including_rejects(pg_session: Session) -> None:
    as_of = dt.date(2026, 4, 17)
    _regime(pg_session, as_of)

    # Four assets covering different rejection reasons
    ok = _asset(pg_session, "OK")
    no_hist = _asset(pg_session, "NOHIST")
    stale = _asset(pg_session, "STALE")
    illiq = _asset(pg_session, "ILLIQ")
    earn = _asset(pg_session, "EARN")
    trendbad = _asset(pg_session, "TRENDBAD")
    for a in (ok, no_hist, stale, illiq, earn, trendbad):
        _member(pg_session, a, dt.date(2024, 1, 1))

    _factor(pg_session, ok, as_of)
    _factor(pg_session, no_hist, as_of, enough_data=False)
    _factor(pg_session, stale, as_of, stale_data=True)
    _factor(pg_session, illiq, as_of, adv=Decimal("1000000"))
    _factor(pg_session, earn, as_of, earnings_days=2)
    _factor(pg_session, trendbad, as_of, price_vs_200=Decimal("-0.10"))

    await generate_stock_candidates(as_of)

    pg_session.expire_all()
    rows = list(pg_session.query(CandidateIdea).filter_by(as_of_date=as_of).all())
    assert len(rows) == 6
    reasons = {r.asset_id: r.rejection_reason for r in rows}
    assert reasons[ok.id] is None
    assert reasons[no_hist.id] == "insufficient_history"
    assert reasons[stale.id] == "stale_data"
    assert reasons[illiq.id] == "liquidity_fail"
    assert reasons[earn.id] == "earnings_too_close"
    assert reasons[trendbad.id] == "below_long_trend"


async def test_job_regime_off_on_downtrend_rejects_all(pg_session: Session) -> None:
    """Downtrend is still a HARD regime block — every asset rejected."""
    as_of = dt.date(2026, 4, 17)
    _regime(pg_session, as_of, market_trend="downtrend")

    a = _asset(pg_session, "DNTRND")
    _member(pg_session, a, dt.date(2024, 1, 1))
    _factor(pg_session, a, as_of)

    await generate_stock_candidates(as_of)

    pg_session.expire_all()
    rows = list(pg_session.query(CandidateIdea).filter_by(as_of_date=as_of).all())
    assert len(rows) == 1
    assert rows[0].status == "rejected"
    assert rows[0].rejection_reason == "regime_off"


async def test_job_missing_regime_rejects_all(pg_session: Session) -> None:
    """Missing regime row still a HARD block."""
    as_of = dt.date(2026, 4, 17)
    # Intentionally no _regime() call.
    a = _asset(pg_session, "NOREGIME")
    _member(pg_session, a, dt.date(2024, 1, 1))
    _factor(pg_session, a, as_of)

    await generate_stock_candidates(as_of)

    pg_session.expire_all()
    rows = list(pg_session.query(CandidateIdea).filter_by(as_of_date=as_of).all())
    assert len(rows) == 1
    assert rows[0].rejection_reason == "regime_off"


async def test_job_high_vol_soft_cap_allows_top_3_buys(pg_session: Session) -> None:
    """Under vol_regime='high', the decision engine caps daily Buys at 3.
    Excess Buy-scored assets become status='rejected' with
    rejection_reason='high_vol_topn_overflow' — not the old blanket
    regime_off rejection."""
    as_of = dt.date(2026, 4, 17)
    _regime(pg_session, as_of, market_trend="uptrend", vol_regime="high")

    # 6 Buy-scored assets — only top 3 should be accepted as Buys.
    for i in range(6):
        a = _asset(pg_session, f"HV{i}", sector="tech")
        _member(pg_session, a, dt.date(2024, 1, 1))
        # Strictly decreasing composite so rank is deterministic.
        _factor(
            pg_session, a, as_of,
            rm60=Decimal(str(3 - i * 0.001)),
            rm20=Decimal("3"),
            sector_rank=Decimal("1"),
            trend_20d=Decimal("2"),
        )

    await generate_stock_candidates(as_of)

    pg_session.expire_all()
    rows = list(pg_session.query(CandidateIdea).filter_by(as_of_date=as_of).all())
    accepted_buys = [
        r for r in rows
        if r.status == "accepted" and r.action == "Buy" and r.rejection_reason is None
    ]
    soft_overflow = [r for r in rows if r.rejection_reason == "high_vol_topn_overflow"]
    assert len(accepted_buys) == 3
    assert len(soft_overflow) == 3
    for r in soft_overflow:
        # Rejected status, no action, explicit reason
        assert r.status == "rejected"
        assert r.action is None
        assert r.rejection_reason == "high_vol_topn_overflow"


async def test_job_low_vol_preserves_default_topn_behavior(
    pg_session: Session,
) -> None:
    """Low/normal vol regime MUST preserve existing Batch-4 behavior:
    cap = 10, overflow stays 'accepted' with action='Hold' and
    rejection_reason='topn_overflow'."""
    as_of = dt.date(2026, 4, 17)
    _regime(pg_session, as_of, market_trend="uptrend", vol_regime="normal")

    for i in range(12):  # > 10
        a = _asset(pg_session, f"NV{i}", sector="tech")
        _member(pg_session, a, dt.date(2024, 1, 1))
        _factor(
            pg_session, a, as_of,
            rm60=Decimal(str(3 - i * 0.001)),
            rm20=Decimal("3"),
            sector_rank=Decimal("1"),
            trend_20d=Decimal("2"),
        )

    await generate_stock_candidates(as_of)

    pg_session.expire_all()
    rows = list(pg_session.query(CandidateIdea).filter_by(as_of_date=as_of).all())
    accepted_buys = [
        r for r in rows
        if r.status == "accepted" and r.action == "Buy" and r.rejection_reason is None
    ]
    overflow = [r for r in rows if r.rejection_reason == "topn_overflow"]
    assert len(accepted_buys) == 10
    assert len(overflow) == 2
    for r in overflow:
        assert r.status == "accepted"
        assert r.action == "Hold"


async def test_job_idempotent_upserts(pg_session: Session) -> None:
    as_of = dt.date(2026, 4, 17)
    _regime(pg_session, as_of)
    a = _asset(pg_session, "IDEM")
    _member(pg_session, a, dt.date(2024, 1, 1))
    _factor(pg_session, a, as_of)

    await generate_stock_candidates(as_of)
    await generate_stock_candidates(as_of)

    pg_session.expire_all()
    rows = list(pg_session.query(CandidateIdea).filter_by(as_of_date=as_of).all())
    assert len(rows) == 1


async def test_job_topn_overflow_forces_hold(pg_session: Session) -> None:
    """When more than TOP_N Buys are accepted, overflow stays 'accepted'
    with action=Hold and rejection_reason='topn_overflow'."""
    as_of = dt.date(2026, 4, 17)
    _regime(pg_session, as_of)

    buys = []
    for i in range(12):                  # > TOP_N (10)
        a = _asset(pg_session, f"TOPN{i}", sector="tech")
        _member(pg_session, a, dt.date(2024, 1, 1))
        # Slight decreasing composite so rank is deterministic
        _factor(
            pg_session, a, as_of,
            rm60=Decimal(str(3 - i * 0.001)),
            rm20=Decimal("3"),
            sector_rank=Decimal("1"),
            trend_20d=Decimal("2"),
        )
        buys.append(a)

    await generate_stock_candidates(as_of)

    pg_session.expire_all()
    rows = list(pg_session.query(CandidateIdea).filter_by(as_of_date=as_of).all())
    by_reason = [
        r for r in rows if r.rejection_reason == "topn_overflow"
    ]
    buys_rows = [r for r in rows if r.action == "Buy" and r.rejection_reason is None]
    assert len(buys_rows) == 10
    assert len(by_reason) == 2
    # Overflow rows keep status='accepted' with Hold action
    for r in by_reason:
        assert r.status == "accepted"
        assert r.action == "Hold"


async def test_job_records_factor_breakdown_and_regime(pg_session: Session) -> None:
    as_of = dt.date(2026, 4, 17)
    _regime(pg_session, as_of)
    a = _asset(pg_session, "BRK")
    _member(pg_session, a, dt.date(2024, 1, 1))
    _factor(pg_session, a, as_of)

    await generate_stock_candidates(as_of)

    pg_session.expire_all()
    row = (
        pg_session.query(CandidateIdea)
        .filter_by(as_of_date=as_of, asset_id=a.id).first()
    )
    assert row is not None
    assert "weights" in row.factor_breakdown
    assert "contributions" in row.factor_breakdown
    assert row.regime_snapshot["market_trend"] == "uptrend"


async def test_job_handles_asset_with_no_factor_snapshot(pg_session: Session) -> None:
    """Universe member with no factor row still gets a candidate row with
    insufficient_history rejection — never silently dropped."""
    as_of = dt.date(2026, 4, 17)
    _regime(pg_session, as_of)
    a = _asset(pg_session, "GHOST")
    _member(pg_session, a, dt.date(2024, 1, 1))
    # Deliberately no _factor() call

    await generate_stock_candidates(as_of)

    pg_session.expire_all()
    row = (
        pg_session.query(CandidateIdea)
        .filter_by(as_of_date=as_of, asset_id=a.id).first()
    )
    assert row is not None
    assert row.status == "rejected"
    assert row.rejection_reason == "insufficient_history"


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------


def _seed_candidate(
    pg_session: Session, as_of: dt.date, asset: Asset,
    status: str, action: str | None = None,
    rejection_reason: str | None = None,
    composite: Decimal | None = None,
) -> None:
    pg_session.add(CandidateIdea(
        as_of_date=as_of, asset_id=asset.id,
        model_version=MODEL_VERSION, engine="stock_swing",
        status=status, action=action,
        rejection_reason=rejection_reason,
        composite_score=composite,
        factor_breakdown={}, regime_snapshot={},
    ))
    pg_session.commit()


def test_candidates_endpoint_empty_when_no_rows(pg_session: Session) -> None:
    from apps.api.src.main import app
    client = TestClient(app)
    resp = client.get("/api/stock-engine/candidates")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 0


def test_candidates_endpoint_filters_by_status(pg_session: Session) -> None:
    from apps.api.src.main import app
    as_of = dt.date(2026, 4, 17)
    a1 = _asset(pg_session, "CA")
    a2 = _asset(pg_session, "CB")
    _seed_candidate(pg_session, as_of, a1, "accepted", action="Buy",
                    composite=Decimal("0.5"))
    _seed_candidate(pg_session, as_of, a2, "rejected",
                    rejection_reason="liquidity_fail")

    client = TestClient(app)
    resp = client.get("/api/stock-engine/candidates?status=rejected")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["candidates"][0]["symbol"] == "CB"
    assert data["candidates"][0]["rejection_reason"] == "liquidity_fail"


def test_candidates_endpoint_filters_by_action(pg_session: Session) -> None:
    from apps.api.src.main import app
    as_of = dt.date(2026, 4, 17)
    a1 = _asset(pg_session, "BX")
    a2 = _asset(pg_session, "HX")
    _seed_candidate(pg_session, as_of, a1, "accepted", action="Buy",
                    composite=Decimal("0.5"))
    _seed_candidate(pg_session, as_of, a2, "accepted", action="Hold",
                    composite=Decimal("0.0"))

    client = TestClient(app)
    data = client.get("/api/stock-engine/candidates?action=Buy").json()
    assert data["count"] == 1
    assert data["candidates"][0]["symbol"] == "BX"


def test_rejections_summary_endpoint(pg_session: Session) -> None:
    from apps.api.src.main import app
    as_of = dt.date(2026, 4, 17)
    a = _asset(pg_session, "RA")
    b = _asset(pg_session, "RB")
    c = _asset(pg_session, "RC")
    _seed_candidate(pg_session, as_of, a, "accepted", action="Buy",
                    composite=Decimal("0.4"))
    _seed_candidate(pg_session, as_of, b, "rejected",
                    rejection_reason="liquidity_fail")
    _seed_candidate(pg_session, as_of, c, "rejected",
                    rejection_reason="liquidity_fail")

    client = TestClient(app)
    resp = client.get("/api/stock-engine/rejections/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["as_of_date"] == as_of.isoformat()
    assert data["total_evaluated"] == 3
    assert data["accepted"] == 1
    assert data["rejected"] == 2
    assert data["reasons"]["liquidity_fail"] == 2


def test_top_endpoint_returns_buys_sorted(pg_session: Session) -> None:
    from apps.api.src.main import app
    as_of = dt.date(2026, 4, 17)
    low = _asset(pg_session, "LOW")
    high = _asset(pg_session, "HIGH")
    mid = _asset(pg_session, "MID")
    _seed_candidate(pg_session, as_of, low, "accepted", action="Buy",
                    composite=Decimal("0.30"))
    _seed_candidate(pg_session, as_of, high, "accepted", action="Buy",
                    composite=Decimal("0.70"))
    _seed_candidate(pg_session, as_of, mid, "accepted", action="Buy",
                    composite=Decimal("0.50"))
    # A hold that must be excluded
    hold = _asset(pg_session, "HOLDX")
    _seed_candidate(pg_session, as_of, hold, "accepted", action="Hold",
                    composite=Decimal("0.10"))

    client = TestClient(app)
    resp = client.get("/api/stock-engine/top?n=2")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2
    symbols = [c["symbol"] for c in data["candidates"]]
    assert symbols == ["HIGH", "MID"]


def test_rejections_summary_empty(pg_session: Session) -> None:
    from apps.api.src.main import app
    client = TestClient(app)
    data = client.get("/api/stock-engine/rejections/summary").json()
    assert data["as_of_date"] is None
    assert data["total_evaluated"] == 0
