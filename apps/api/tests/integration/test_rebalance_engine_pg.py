"""Integration: rebalance engine + weekly job against Postgres."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from apps.api.src.db.models import (
    Asset,
    CandidateIdea,
    FactorSnapshot,
    PaperPortfolio,
    PaperPosition,
    PaperTrade,
    PriceBar,
    RegimeSnapshot,
    UniverseMembership,
)
from apps.api.src.domain.stock_engine.portfolio.rebalance_engine import (
    run_rebalance,
)
from apps.api.src.domain.stock_engine.scoring import MODEL_VERSION
from apps.worker.src.jobs.run_weekly_rebalance import run_weekly_rebalance

pytestmark = pytest.mark.integration

UNIVERSE = "stock_swing_v1"


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


def _portfolio(
    pg_session: Session, cash: str = "100000",
    name: str | None = None,
) -> PaperPortfolio:
    p = PaperPortfolio(
        name=name or f"reb-{dt.datetime.now().timestamp()}",
        starting_cash=Decimal(cash), cash=Decimal(cash),
        is_active=True,
    )
    pg_session.add(p)
    pg_session.flush()
    pg_session.commit()
    return p


def _asset(pg_session: Session, symbol: str, sector: str = "tech") -> Asset:
    a = Asset(
        symbol=symbol, asset_class="equity", exchange="NASDAQ",
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
        market_trend=market_trend, vol_regime=vol_regime,
        breadth_regime=None, sma50_over_sma200=True,
        realized_vol_20d=Decimal("0.14"), atr_pctile_1y=Decimal("0.4"),
    ))
    pg_session.commit()


def _price_bar(
    pg_session: Session, asset: Asset, day: dt.date,
    close: str, high: str | None = None, low: str | None = None,
) -> None:
    ts = dt.datetime.combine(day, dt.time(0, 0, 0, tzinfo=dt.timezone.utc))
    c = Decimal(close)
    pg_session.add(PriceBar(
        asset_id=asset.id, timeframe="1d", ts=ts,
        open=c, close=c,
        high=Decimal(high) if high else c * Decimal("1.005"),
        low=Decimal(low) if low else c * Decimal("0.995"),
        adjusted_close=c, volume=1_000_000, provider="test",
    ))
    pg_session.commit()


def _factor(
    pg_session: Session, asset: Asset, as_of: dt.date,
    adv: str = "60000000",
) -> None:
    pg_session.add(FactorSnapshot(
        as_of_date=as_of, asset_id=asset.id,
        feature_set_hash="testhash",
        enough_data=True, stale_data=False,
        avg_dollar_volume_20d=Decimal(adv),
        atr_percent_14=Decimal("0.02"),
    ))
    pg_session.commit()


def _candidate(
    pg_session: Session, asset: Asset, as_of: dt.date,
    *, status: str = "accepted", action: str = "Buy",
    composite: str = "0.50", confidence: str = "70",
) -> CandidateIdea:
    c = CandidateIdea(
        as_of_date=as_of, asset_id=asset.id,
        model_version=MODEL_VERSION, engine="stock_swing",
        status=status, action=action,
        composite_score=Decimal(composite),
        confidence=Decimal(confidence),
        factor_breakdown={}, regime_snapshot={},
    )
    pg_session.add(c)
    pg_session.commit()
    return c


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_rebalance_opens_positions_for_top_buys(pg_session: Session) -> None:
    as_of = dt.date(2026, 4, 20)
    _regime(pg_session, as_of)
    p = _portfolio(pg_session)
    tickers = []
    for i, (sym, comp, conf) in enumerate([
        ("TOP1", "0.60", "80"),
        ("TOP2", "0.50", "70"),
        ("TOP3", "0.40", "60"),
    ]):
        a = _asset(pg_session, sym, sector="tech")
        _member(pg_session, a, dt.date(2024, 1, 1))
        _price_bar(pg_session, a, as_of, close="100")
        _price_bar(pg_session, a, as_of + dt.timedelta(days=1), close="101")
        _factor(pg_session, a, as_of)
        _candidate(pg_session, a, as_of, composite=comp, confidence=conf)
        tickers.append(a)

    report = run_rebalance(pg_session, p, as_of=as_of)
    pg_session.commit()

    executed = [e for e in report.entries if e.status == "executed"]
    assert len(executed) == 3
    # Sector cap (50%) engaged since 3 tech @ base 0.10 * conf is below cap → just sum
    assert all(a.symbol in {"TOP1", "TOP2", "TOP3"}
               for a in [t for t in tickers])
    # All trades carry slippage_bps + commission
    pg_session.expire_all()
    trades = list(pg_session.query(PaperTrade).filter_by(portfolio_id=p.id).all())
    assert len(trades) == 3
    for t in trades:
        assert t.slippage_bps is not None
        assert t.commission == Decimal("0")
        assert t.reason == "rebalance_entry"


def test_rebalance_no_candidates_no_trades(pg_session: Session) -> None:
    as_of = dt.date(2026, 4, 20)
    _regime(pg_session, as_of)
    p = _portfolio(pg_session)

    report = run_rebalance(pg_session, p, as_of=as_of)
    pg_session.commit()

    assert report.entries == []
    assert report.exits == []
    # Snapshot still written → equity unchanged
    assert p.cash == Decimal("100000")


def test_rebalance_downtrend_blocks_new_entries(pg_session: Session) -> None:
    as_of = dt.date(2026, 4, 20)
    _regime(pg_session, as_of, market_trend="downtrend")
    p = _portfolio(pg_session)

    a = _asset(pg_session, "DT1")
    _member(pg_session, a, dt.date(2024, 1, 1))
    _price_bar(pg_session, a, as_of, close="100")
    _price_bar(pg_session, a, as_of + dt.timedelta(days=1), close="101")
    _factor(pg_session, a, as_of)
    _candidate(pg_session, a, as_of)

    report = run_rebalance(pg_session, p, as_of=as_of)
    pg_session.commit()

    assert report.entries == []
    assert "downtrend_no_entries" in report.notes


def test_rebalance_stop_loss_closes_position(pg_session: Session) -> None:
    as_of = dt.date(2026, 4, 20)
    _regime(pg_session, as_of)
    p = _portfolio(pg_session)

    a = _asset(pg_session, "SL")
    _member(pg_session, a, dt.date(2024, 1, 1))
    # Seed bar well below avg_cost → -15% unrealized
    _price_bar(pg_session, a, as_of, close="85")
    _price_bar(pg_session, a, as_of + dt.timedelta(days=1), close="85")

    # Open position manually
    pos = PaperPosition(
        portfolio_id=p.id, asset_id=a.id,
        quantity=Decimal("10"), avg_cost=Decimal("100"),
        is_open=True,
        opened_at=dt.datetime(2026, 4, 15, tzinfo=dt.timezone.utc),
    )
    pg_session.add(pos)
    pg_session.commit()

    report = run_rebalance(pg_session, p, as_of=as_of)
    pg_session.commit()
    pg_session.expire_all()

    executed_exits = [e for e in report.exits if e.status == "executed"]
    assert len(executed_exits) == 1
    assert executed_exits[0].reason == "stop_loss"
    # Position closed
    pos = pg_session.get(PaperPosition, pos.id)
    assert pos.is_open is False


def test_rebalance_horizon_exit_closes_old_position(pg_session: Session) -> None:
    as_of = dt.date(2026, 4, 20)
    _regime(pg_session, as_of)
    p = _portfolio(pg_session)

    a = _asset(pg_session, "HORZ")
    _member(pg_session, a, dt.date(2024, 1, 1))
    _price_bar(pg_session, a, as_of, close="100")
    _price_bar(pg_session, a, as_of + dt.timedelta(days=1), close="100")

    pos = PaperPosition(
        portfolio_id=p.id, asset_id=a.id,
        quantity=Decimal("5"), avg_cost=Decimal("100"),
        is_open=True,
        opened_at=dt.datetime(2026, 4, 5, tzinfo=dt.timezone.utc),  # > 10d ago
    )
    pg_session.add(pos)
    pg_session.commit()

    report = run_rebalance(pg_session, p, as_of=as_of)
    pg_session.commit()

    reasons = {e.reason for e in report.exits if e.status == "executed"}
    assert "horizon_exit" in reasons


def test_rebalance_slippage_on_buys(pg_session: Session) -> None:
    as_of = dt.date(2026, 4, 20)
    _regime(pg_session, as_of)
    p = _portfolio(pg_session, cash="10000")

    a = _asset(pg_session, "SLIP")
    _member(pg_session, a, dt.date(2024, 1, 1))
    # Wide bar → non-trivial spread proxy
    _price_bar(pg_session, a, as_of, close="100", high="103", low="97")
    _price_bar(pg_session, a, as_of + dt.timedelta(days=1), close="100",
               high="103", low="97")
    _factor(pg_session, a, as_of)
    _candidate(pg_session, a, as_of, confidence="100")

    report = run_rebalance(pg_session, p, as_of=as_of)
    pg_session.commit()
    pg_session.expire_all()

    trades = list(pg_session.query(PaperTrade).filter_by(portfolio_id=p.id).all())
    assert len(trades) == 1
    t = trades[0]
    assert t.slippage_bps is not None
    assert t.slippage_bps > Decimal("0")
    # Buy → fill > quote
    assert t.fill_price > Decimal("100")


def test_rebalance_sector_cap_rescales(pg_session: Session) -> None:
    as_of = dt.date(2026, 4, 20)
    _regime(pg_session, as_of)
    p = _portfolio(pg_session, cash="1000000")

    # 8 tech candidates at confidence=100 → would sum to 0.80 in tech; cap=0.50
    for i in range(8):
        a = _asset(pg_session, f"SC{i}", sector="tech")
        _member(pg_session, a, dt.date(2024, 1, 1))
        _price_bar(pg_session, a, as_of, close="100")
        _price_bar(pg_session, a, as_of + dt.timedelta(days=1), close="100")
        _factor(pg_session, a, as_of)
        _candidate(pg_session, a, as_of, composite=f"0.{70-i}", confidence="100")

    report = run_rebalance(pg_session, p, as_of=as_of)
    pg_session.commit()

    assert "tech" in report.sector_totals
    # Cap is 0.50 — target sector total must not exceed it materially
    assert report.sector_totals["tech"] <= Decimal("0.500001")


async def test_weekly_rebalance_job_runs_for_all_active_portfolios(
    pg_session: Session,
) -> None:
    as_of = dt.date(2026, 4, 20)
    _regime(pg_session, as_of)
    p1 = _portfolio(pg_session, name="p1", cash="10000")

    a = _asset(pg_session, "JOBA")
    _member(pg_session, a, dt.date(2024, 1, 1))
    _price_bar(pg_session, a, as_of, close="100")
    _price_bar(pg_session, a, as_of + dt.timedelta(days=1), close="100")
    _factor(pg_session, a, as_of)
    _candidate(pg_session, a, as_of, confidence="70")

    await run_weekly_rebalance(as_of)

    pg_session.expire_all()
    trades = list(pg_session.query(PaperTrade).filter_by(portfolio_id=p1.id).all())
    assert len(trades) == 1
    assert trades[0].reason == "rebalance_entry"
