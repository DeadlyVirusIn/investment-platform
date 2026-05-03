"""Integration: dashboard summary + PnL + attribution + blocked-alpha sim."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from apps.api.src.db.models import (
    Asset,
    CandidateIdea,
    PaperPortfolio,
    PaperPosition,
    PaperTrade,
    PriceBar,
    RegimeSnapshot,
)
from apps.api.src.domain.pnl.attribution import (
    attribution_by_regime,
    attribution_by_score_bucket,
    blocked_alpha_sim,
)
from apps.api.src.domain.pnl.engine import portfolio_pnl
from apps.api.src.domain.stock_engine.scoring import MODEL_VERSION

pytestmark = pytest.mark.integration

TODAY = dt.date(2026, 4, 20)


def _portfolio(
    pg_session: Session, cash: str = "100000", name: str | None = None,
) -> PaperPortfolio:
    p = PaperPortfolio(
        name=name or f"pd-{dt.datetime.now().timestamp()}",
        starting_cash=Decimal(cash), cash=Decimal(cash),
        is_active=True,
    )
    pg_session.add(p)
    pg_session.flush()
    pg_session.commit()
    return p


def _asset(
    pg_session: Session, symbol: str, sector: str = "tech",
) -> Asset:
    a = Asset(
        symbol=symbol, asset_class="equity", exchange="NASDAQ",
        currency="USD", sector=sector,
    )
    pg_session.add(a)
    pg_session.flush()
    pg_session.commit()
    return a


def _bar(
    pg_session: Session, asset: Asset, day: dt.date, close: str,
) -> None:
    ts = dt.datetime.combine(day, dt.time(0, 0, 0, tzinfo=dt.timezone.utc))
    c = Decimal(close)
    pg_session.add(PriceBar(
        asset_id=asset.id, timeframe="1d", ts=ts,
        open=c, close=c, high=c * Decimal("1.005"),
        low=c * Decimal("0.995"), adjusted_close=c,
        volume=1_000_000, provider="test",
    ))
    pg_session.commit()


def _candidate(
    pg_session: Session, asset: Asset, as_of: dt.date,
    *, status: str, action: str | None = None,
    rejection_reason: str | None = None,
    composite: str = "0.40", confidence: str = "70",
    market_trend: str = "uptrend", vol_regime: str = "normal",
) -> None:
    pg_session.add(CandidateIdea(
        as_of_date=as_of, asset_id=asset.id,
        model_version=MODEL_VERSION, engine="stock_swing",
        status=status, action=action,
        rejection_reason=rejection_reason,
        composite_score=Decimal(composite),
        confidence=Decimal(confidence),
        factor_breakdown={},
        regime_snapshot={"market_trend": market_trend, "vol_regime": vol_regime},
    ))
    pg_session.commit()


def _open_position(
    pg_session: Session, portfolio: PaperPortfolio, asset: Asset,
    qty: str, avg_cost: str, opened_days_ago: int = 3,
) -> PaperPosition:
    pos = PaperPosition(
        portfolio_id=portfolio.id, asset_id=asset.id,
        quantity=Decimal(qty), avg_cost=Decimal(avg_cost),
        is_open=True,
        opened_at=dt.datetime.combine(
            TODAY - dt.timedelta(days=opened_days_ago),
            dt.time(0, 0, 0, tzinfo=dt.timezone.utc),
        ),
    )
    pg_session.add(pos)
    pg_session.commit()
    return pos


def _trade(
    pg_session: Session, portfolio: PaperPortfolio, asset: Asset,
    *, side: str, qty: str, price: str,
    fill_days_ago: int, realized_pnl: str | None = None,
    slippage_bps: str | None = None,
) -> None:
    ts = dt.datetime.combine(
        TODAY - dt.timedelta(days=fill_days_ago),
        dt.time(14, 30, 0, tzinfo=dt.timezone.utc),
    )
    pg_session.add(PaperTrade(
        portfolio_id=portfolio.id, asset_id=asset.id,
        side=side, quantity=Decimal(qty), fill_price=Decimal(price),
        fill_ts=ts, submitted_at=ts,
        realized_pnl=Decimal(realized_pnl) if realized_pnl is not None else None,
        slippage_bps=Decimal(slippage_bps) if slippage_bps is not None else None,
        commission=Decimal("0"),
    ))
    pg_session.commit()


def _regime(
    pg_session: Session, as_of: dt.date,
    market_trend: str = "uptrend", vol_regime: str = "normal",
) -> None:
    pg_session.add(RegimeSnapshot(
        as_of_date=as_of, benchmark_symbol="SPY",
        market_trend=market_trend, vol_regime=vol_regime, breadth_regime=None,
        sma50_over_sma200=True, realized_vol_20d=Decimal("0.15"),
        atr_pctile_1y=Decimal("0.40"),
    ))
    pg_session.commit()


# ---------------------------------------------------------------------------
# Dashboard summary
# ---------------------------------------------------------------------------


def test_dashboard_summary_happy_path(pg_session: Session) -> None:
    from apps.api.src.main import app

    p = _portfolio(pg_session, cash="90000")
    _regime(pg_session, TODAY)

    # Accepted Buy
    a1 = _asset(pg_session, "DBA1", sector="tech")
    _candidate(pg_session, a1, TODAY,
               status="accepted", action="Buy",
               composite="0.50", confidence="80")
    # Rejected high composite → blocked alpha
    a2 = _asset(pg_session, "DBA2", sector="tech")
    _candidate(pg_session, a2, TODAY,
               status="rejected", rejection_reason="high_vol_topn_overflow",
               composite="0.40")
    # Open position with mark above cost
    a3 = _asset(pg_session, "DBA3", sector="tech")
    _bar(pg_session, a3, TODAY, close="110")
    _open_position(pg_session, p, a3, qty="100", avg_cost="100")

    client = TestClient(app)
    resp = client.get("/api/dashboard/summary")
    assert resp.status_code == 200
    data = resp.json()

    assert data["as_of_date"] == TODAY.isoformat()
    assert data["regime"]["market_trend"] == "uptrend"
    assert data["candidates"]["accepted_buys"] == 1
    assert data["candidates"]["rejected_total"] == 1
    assert data["blocked_alpha"]["count"] == 1
    assert data["top_buys"][0]["symbol"] == "DBA1"
    assert data["portfolio"]["open_positions_count"] == 1
    assert data["portfolio"]["top_positions"][0]["symbol"] == "DBA3"
    # NAV = 90000 + 100*110 = 101000
    assert Decimal(data["portfolio"]["nav"]) == Decimal("101000")
    # No "no_buys_today" alert (we have 1 Buy)
    codes = {a["code"] for a in data["alerts"]}
    assert "no_buys_today" not in codes


def test_dashboard_summary_emits_no_buys_alert(pg_session: Session) -> None:
    from apps.api.src.main import app

    p = _portfolio(pg_session)
    _regime(pg_session, TODAY)
    a = _asset(pg_session, "DB_NO")
    _candidate(pg_session, a, TODAY,
               status="rejected", rejection_reason="regime_off",
               composite="0.30")

    client = TestClient(app)
    resp = client.get("/api/dashboard/summary")
    data = resp.json()
    codes = {a["code"] for a in data["alerts"]}
    assert "no_buys_today" in codes
    assert "all_blocked_one_reason" in codes


# ---------------------------------------------------------------------------
# PnL summary
# ---------------------------------------------------------------------------


def test_pnl_summary_open_and_closed(pg_session: Session) -> None:
    from apps.api.src.main import app

    p = _portfolio(pg_session, cash="50000")
    a = _asset(pg_session, "PNL_A")
    _bar(pg_session, a, TODAY, close="120")
    _open_position(pg_session, p, a, qty="100", avg_cost="100")

    # Closed winning trade
    b = _asset(pg_session, "PNL_B")
    _trade(pg_session, p, b, side="buy", qty="10", price="50",
           fill_days_ago=8)
    _trade(pg_session, p, b, side="sell", qty="10", price="60",
           fill_days_ago=2, realized_pnl="100")

    # Closed losing trade
    c = _asset(pg_session, "PNL_C")
    _trade(pg_session, p, c, side="buy", qty="5", price="80",
           fill_days_ago=6)
    _trade(pg_session, p, c, side="sell", qty="5", price="70",
           fill_days_ago=1, realized_pnl="-50")

    pnl = portfolio_pnl(pg_session, p)
    # Unrealized: 100 * (120-100) = 2000
    assert pnl.unrealized_pnl == Decimal("2000")
    assert pnl.realized_pnl == Decimal("50")    # 100 - 50
    assert pnl.closed_trade_count == 2
    assert pnl.wins == 1
    assert pnl.losses == 1
    assert pnl.win_rate == Decimal("0.5")
    assert pnl.avg_win == Decimal("100")
    assert pnl.avg_loss == Decimal("-50")
    # NAV = cash + invested; cash unchanged since we didn't debit trades via
    # real engine. invested = 100 * 120 = 12000.
    assert pnl.invested == Decimal("12000")

    client = TestClient(app)
    resp = client.get("/api/pnl/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert Decimal(data["realized_pnl"]) == Decimal("50")
    assert Decimal(data["unrealized_pnl"]) == Decimal("2000")
    assert data["wins"] == 1
    assert data["losses"] == 1


def test_pnl_by_symbol_links_entry_candidate(pg_session: Session) -> None:
    from apps.api.src.main import app

    p = _portfolio(pg_session)
    a = _asset(pg_session, "SYM_LINK")
    # Candidate row existed 5 days ago with composite=0.50
    _candidate(pg_session, a, TODAY - dt.timedelta(days=5),
               status="accepted", action="Buy",
               composite="0.50", confidence="80",
               market_trend="uptrend", vol_regime="normal")
    # Buy + open position
    _trade(pg_session, p, a, side="buy", qty="10", price="100",
           fill_days_ago=4)
    _bar(pg_session, a, TODAY, close="105")
    _open_position(pg_session, p, a, qty="10", avg_cost="100", opened_days_ago=4)

    client = TestClient(app)
    resp = client.get("/api/pnl/by-symbol")
    data = resp.json()
    row = next(r for r in data["items"] if r["symbol"] == "SYM_LINK")
    assert Decimal(row["entry_composite_score"]) == Decimal("0.50")
    assert row["entry_market_trend"] == "uptrend"
    assert row["entry_vol_regime"] == "normal"
    assert row["status"] == "open"


# ---------------------------------------------------------------------------
# Score-bucket attribution
# ---------------------------------------------------------------------------


def test_score_bucket_attribution(pg_session: Session) -> None:
    from apps.api.src.main import app

    p = _portfolio(pg_session)
    # Asset with entry score 0.30 → bucket 0.25-0.35
    a = _asset(pg_session, "SB_LOW")
    _candidate(pg_session, a, TODAY - dt.timedelta(days=5),
               status="accepted", action="Buy", composite="0.30", confidence="60")
    _trade(pg_session, p, a, side="buy", qty="10", price="100", fill_days_ago=4)
    _trade(pg_session, p, a, side="sell", qty="10", price="105",
           fill_days_ago=1, realized_pnl="50")

    # Asset with entry score 0.50 → bucket 0.45+
    b = _asset(pg_session, "SB_HI")
    _candidate(pg_session, b, TODAY - dt.timedelta(days=5),
               status="accepted", action="Buy", composite="0.50", confidence="80")
    _trade(pg_session, p, b, side="buy", qty="5", price="200", fill_days_ago=4)
    _trade(pg_session, p, b, side="sell", qty="5", price="220",
           fill_days_ago=1, realized_pnl="100")

    buckets = attribution_by_score_bucket(pg_session, p)
    by_name = {b.bucket: b for b in buckets}
    assert by_name["0.25-0.35"].trade_count == 1
    assert by_name["0.25-0.35"].total_pnl == Decimal("50")
    assert by_name["0.45+"].trade_count == 1
    assert by_name["0.45+"].total_pnl == Decimal("100")

    client = TestClient(app)
    resp = client.get("/api/pnl/by-score-bucket")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Regime attribution
# ---------------------------------------------------------------------------


def test_regime_attribution(pg_session: Session) -> None:
    from apps.api.src.main import app

    p = _portfolio(pg_session)
    # uptrend/normal winner
    a = _asset(pg_session, "RG_UN")
    _candidate(pg_session, a, TODAY - dt.timedelta(days=5),
               status="accepted", action="Buy", composite="0.4",
               market_trend="uptrend", vol_regime="normal")
    _trade(pg_session, p, a, side="buy", qty="10", price="100", fill_days_ago=4)
    _trade(pg_session, p, a, side="sell", qty="10", price="108",
           fill_days_ago=1, realized_pnl="80")

    # uptrend/high loser
    b = _asset(pg_session, "RG_UH")
    _candidate(pg_session, b, TODAY - dt.timedelta(days=5),
               status="accepted", action="Buy", composite="0.4",
               market_trend="uptrend", vol_regime="high")
    _trade(pg_session, p, b, side="buy", qty="10", price="100", fill_days_ago=4)
    _trade(pg_session, p, b, side="sell", qty="10", price="95",
           fill_days_ago=1, realized_pnl="-50")

    stats = attribution_by_regime(pg_session, p)
    by_key = {(s.market_trend, s.vol_regime): s for s in stats}
    assert by_key[("uptrend", "normal")].trade_count == 1
    assert by_key[("uptrend", "normal")].total_pnl == Decimal("80")
    assert by_key[("uptrend", "high")].trade_count == 1
    assert by_key[("uptrend", "high")].total_pnl == Decimal("-50")

    client = TestClient(app)
    resp = client.get("/api/pnl/by-regime")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Blocked-alpha simulation
# ---------------------------------------------------------------------------


def test_blocked_alpha_sim_computes_returns(pg_session: Session) -> None:
    from apps.api.src.main import app

    # One rejected candidate 20 days ago. Entry (next day close) and
    # exit 14 days later. Return = +10%.
    a = _asset(pg_session, "BA_WIN")
    as_of = TODAY - dt.timedelta(days=20)
    _bar(pg_session, a, as_of + dt.timedelta(days=1), close="100")
    _bar(pg_session, a, as_of + dt.timedelta(days=15), close="110")
    _candidate(pg_session, a, as_of,
               status="rejected", rejection_reason="regime_off",
               composite="0.35")

    # Another rejected with negative return
    b = _asset(pg_session, "BA_LOSE")
    _bar(pg_session, b, as_of + dt.timedelta(days=1), close="200")
    _bar(pg_session, b, as_of + dt.timedelta(days=15), close="180")
    _candidate(pg_session, b, as_of,
               status="rejected", rejection_reason="high_vol_topn_overflow",
               composite="0.30")

    report = blocked_alpha_sim(
        pg_session, min_score=Decimal("0.25"), horizon_days=14,
        from_date=as_of - dt.timedelta(days=1),
        to_date=as_of + dt.timedelta(days=1),
    )
    assert report.simulated_count == 2
    assert report.wins == 1
    assert report.losses == 1
    assert report.avg_return is not None
    # 0.10 + (-0.10) = 0 average
    assert abs(report.avg_return) < Decimal("0.01")

    client = TestClient(app)
    resp = client.get(
        f"/api/pnl/blocked-alpha-sim?from={(as_of - dt.timedelta(days=1)).isoformat()}"
        f"&to={(as_of + dt.timedelta(days=1)).isoformat()}"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["simulated_count"] == 2


def test_blocked_alpha_sim_skips_when_no_prices(pg_session: Session) -> None:
    a = _asset(pg_session, "BA_NOP")
    as_of = TODAY - dt.timedelta(days=20)
    _candidate(pg_session, a, as_of,
               status="rejected", rejection_reason="regime_off",
               composite="0.40")
    report = blocked_alpha_sim(
        pg_session, min_score=Decimal("0.25"), horizon_days=14,
        from_date=as_of, to_date=as_of,
    )
    assert report.simulated_count == 0
    assert report.skipped_count == 1


def test_blocked_alpha_sim_respects_min_score(pg_session: Session) -> None:
    a = _asset(pg_session, "BA_LOW")
    as_of = TODAY - dt.timedelta(days=20)
    _bar(pg_session, a, as_of + dt.timedelta(days=1), close="100")
    _bar(pg_session, a, as_of + dt.timedelta(days=15), close="105")
    _candidate(pg_session, a, as_of,
               status="rejected", rejection_reason="regime_off",
               composite="0.10")  # below default min_score
    report = blocked_alpha_sim(
        pg_session, min_score=Decimal("0.25"), horizon_days=14,
        from_date=as_of, to_date=as_of,
    )
    assert report.simulated_count == 0
    assert report.skipped_count == 0
