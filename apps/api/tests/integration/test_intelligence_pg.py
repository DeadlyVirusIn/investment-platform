"""Integration: Phase 2 Intelligence Console — decision review,
portfolio intelligence, tuning advisor, news analyzer."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from apps.api.src.db.models import (
    Asset,
    CandidateIdea,
    NewsItem,
    NewsSymbolMap,
    PaperPortfolio,
    PaperPosition,
    PaperTrade,
    PriceBar,
)
from apps.api.src.domain.intelligence.decision_review import review_decisions
from apps.api.src.domain.intelligence.news_analyzer import analyze_news
from apps.api.src.domain.intelligence.portfolio_intelligence import (
    analyze_portfolio,
)
from apps.api.src.domain.intelligence.tuning_advisor import advise
from apps.api.src.domain.stock_engine.scoring import MODEL_VERSION

pytestmark = pytest.mark.integration

TODAY = dt.date(2026, 4, 20)


# ---------------------------------------------------------------------------
# Seeders
# ---------------------------------------------------------------------------


def _portfolio(
    pg_session: Session, cash: str = "50000",
) -> PaperPortfolio:
    p = PaperPortfolio(
        name=f"intel-{dt.datetime.now().timestamp()}",
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


def _bar(
    pg_session: Session, asset: Asset, day: dt.date, close: str,
) -> None:
    ts = dt.datetime.combine(day, dt.time(0, 0, 0, tzinfo=dt.timezone.utc))
    c = Decimal(close)
    pg_session.add(PriceBar(
        asset_id=asset.id, timeframe="1d", ts=ts,
        open=c, close=c, high=c * Decimal("1.005"), low=c * Decimal("0.995"),
        adjusted_close=c, volume=1_000_000, provider="test",
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
            dt.time(14, 30, tzinfo=dt.timezone.utc),
        ),
    )
    pg_session.add(pos)
    pg_session.commit()
    return pos


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


def _trade_slip(
    pg_session: Session, portfolio: PaperPortfolio, asset: Asset,
    slippage_bps: str,
) -> None:
    pg_session.add(PaperTrade(
        portfolio_id=portfolio.id, asset_id=asset.id,
        side="buy", quantity=Decimal("1"), fill_price=Decimal("100"),
        fill_ts=dt.datetime.now(dt.timezone.utc),
        submitted_at=dt.datetime.now(dt.timezone.utc),
        slippage_bps=Decimal(slippage_bps), commission=Decimal("0"),
    ))
    pg_session.commit()


def _news(
    pg_session: Session, asset: Asset, title: str,
    sentiment: str, sscore: str, category: str,
    published_at: dt.datetime,
) -> None:
    url = f"https://example.com/{title.replace(' ', '-')}"
    import hashlib
    uh = hashlib.sha1(url.encode()).hexdigest()
    item = NewsItem(
        source="test", url=url, url_hash=uh, title=title, summary="",
        published_at=published_at, category=category,
        sentiment=sentiment, sentiment_score=Decimal(sscore),
        impact_level="medium", impact_score=2,
        raw_payload={},
    )
    pg_session.add(item)
    pg_session.flush()
    pg_session.add(NewsSymbolMap(news_id=item.id, symbol=asset.symbol))
    pg_session.commit()


# ---------------------------------------------------------------------------
# Decision Review
# ---------------------------------------------------------------------------


def test_decision_review_builds_with_positions(pg_session: Session) -> None:
    p = _portfolio(pg_session)
    a = _asset(pg_session, "DR_A")
    _bar(pg_session, a, TODAY, close="110")
    _open_position(pg_session, p, a, qty="10", avg_cost="100")

    out = review_decisions(pg_session)
    assert out.accepted_vs_blocked is not None
    assert out.accepted_vs_blocked.accepted_count == 1
    assert out.accepted_vs_blocked.accepted_avg_return_pct == Decimal("0.1")
    assert "accepted_sample_small" in out.sample_notes


def test_decision_review_populates_rejection_quality(pg_session: Session) -> None:
    p = _portfolio(pg_session)
    a = _asset(pg_session, "DR_B")
    _candidate(pg_session, a, TODAY,
               status="rejected", rejection_reason="regime_off",
               composite="0.30")
    _candidate(pg_session, a, TODAY - dt.timedelta(days=1),
               status="rejected", rejection_reason="regime_off",
               composite="0.40")

    out = review_decisions(pg_session, portfolio_id=p.id)
    reasons = {rq.reason for rq in out.rejection_quality}
    assert "regime_off" in reasons


# ---------------------------------------------------------------------------
# Portfolio Intelligence
# ---------------------------------------------------------------------------


def test_portfolio_intelligence_flags_high_concentration(
    pg_session: Session,
) -> None:
    p = _portfolio(pg_session, cash="10000")
    a = _asset(pg_session, "CONC", sector="tech")
    _bar(pg_session, a, TODAY, close="600")
    _open_position(pg_session, p, a, qty="100", avg_cost="500")

    out = analyze_portfolio(pg_session, p.id)
    # 100 * 600 = 60000; cash=10000 → top1 ~0.857
    assert out.top1_weight is not None
    assert out.top1_weight > Decimal("0.30")
    assert any("high_single_position_weight" in f for f in out.flags)


def test_portfolio_intelligence_idle_cash_flag(pg_session: Session) -> None:
    p = _portfolio(pg_session, cash="10000")  # 100% cash
    out = analyze_portfolio(pg_session, p.id)
    assert any("idle_cash" in f for f in out.flags)


def test_portfolio_intelligence_slippage(pg_session: Session) -> None:
    p = _portfolio(pg_session)
    a = _asset(pg_session, "SLP")
    _trade_slip(pg_session, p, a, "50")
    _trade_slip(pg_session, p, a, "80")
    out = analyze_portfolio(pg_session, p.id)
    assert out.avg_slippage_bps is not None
    assert out.avg_slippage_bps > Decimal("30")
    assert any("high_avg_slippage" in f for f in out.flags)


def test_portfolio_regime_mix(pg_session: Session) -> None:
    p = _portfolio(pg_session)
    a = _asset(pg_session, "RM")
    _bar(pg_session, a, TODAY, close="110")
    _open_position(pg_session, p, a, qty="5", avg_cost="100", opened_days_ago=4)
    _candidate(pg_session, a, TODAY - dt.timedelta(days=5),
               status="accepted", action="Buy",
               market_trend="uptrend", vol_regime="high")
    # trade buy needed so entry_context_map resolves
    _trade_slip(pg_session, p, a, "10")

    out = analyze_portfolio(pg_session, p.id)
    keys = {(r.market_trend, r.vol_regime) for r in out.regime_mix}
    assert ("uptrend", "high") in keys or ("unknown", "unknown") in keys


# ---------------------------------------------------------------------------
# Tuning Advisor
# ---------------------------------------------------------------------------


def test_tuning_advises_idle_cash(pg_session: Session) -> None:
    p = _portfolio(pg_session, cash="10000")
    a = _asset(pg_session, "TA_IDLE")
    _candidate(pg_session, a, TODAY,
               status="accepted", action="Buy", composite="0.5")
    suggestions = advise(pg_session, portfolio_id=p.id)
    codes = {s.code for s in suggestions}
    assert "increase_capital_utilization" in codes


def test_tuning_advises_concentration(pg_session: Session) -> None:
    p = _portfolio(pg_session, cash="5000")
    a = _asset(pg_session, "TA_CONC")
    _bar(pg_session, a, TODAY, close="200")
    _open_position(pg_session, p, a, qty="100", avg_cost="100")
    suggestions = advise(pg_session, portfolio_id=p.id)
    codes = {s.code for s in suggestions}
    assert "review_concentration" in codes


def test_tuning_no_action_when_healthy(pg_session: Session) -> None:
    # Empty system: no candidates, no positions, no news
    p = _portfolio(pg_session, cash="100")
    suggestions = advise(pg_session, portfolio_id=p.id)
    codes = {s.code for s in suggestions}
    # Either no_action or only very safe info-level items
    assert any(c in codes for c in ("no_action", "expand_universe"))


# ---------------------------------------------------------------------------
# News Analyzer
# ---------------------------------------------------------------------------


def test_news_analyzer_buckets_by_sentiment(pg_session: Session) -> None:
    p = _portfolio(pg_session)
    a = _asset(pg_session, "NA_A")
    _bar(pg_session, a, TODAY, close="110")
    _open_position(pg_session, p, a, qty="10", avg_cost="100", opened_days_ago=3)
    opened = dt.datetime.combine(
        TODAY - dt.timedelta(days=3), dt.time(12, 0, tzinfo=dt.timezone.utc),
    )
    _news(pg_session, a, "Strong beat", sentiment="positive", sscore="1",
          category="earnings",
          published_at=opened - dt.timedelta(days=1))
    _news(pg_session, a, "Upgrade", sentiment="positive", sscore="1",
          category="analyst",
          published_at=opened - dt.timedelta(days=2))

    out = analyze_news(pg_session, p.id)
    assert out.trades_analyzed == 1
    sent_keys = {b.key for b in out.by_sentiment}
    assert "positive" in sent_keys
    # Alignment: positive sentiment + positive return → 100%
    assert out.alignment_pct == Decimal("1")


def test_news_analyzer_small_sample_flag(pg_session: Session) -> None:
    p = _portfolio(pg_session)
    out = analyze_news(pg_session, p.id)
    assert "no_positions_to_analyze" in out.sample_notes


# ---------------------------------------------------------------------------
# HTTP endpoints
# ---------------------------------------------------------------------------


def test_summary_endpoint_aggregates_modules(pg_session: Session) -> None:
    from apps.api.src.main import app

    p = _portfolio(pg_session, cash="5000")
    a = _asset(pg_session, "EPT")
    _bar(pg_session, a, TODAY, close="110")
    _open_position(pg_session, p, a, qty="10", avg_cost="100")

    client = TestClient(app)
    resp = client.get("/api/intelligence/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert "decision_review" in data
    assert "portfolio" in data
    assert "news" in data
    assert "tuning_advice" in data


def test_tuning_advice_endpoint(pg_session: Session) -> None:
    from apps.api.src.main import app
    p = _portfolio(pg_session, cash="10000")
    a = _asset(pg_session, "EPT2")
    _candidate(pg_session, a, TODAY,
               status="accepted", action="Buy", composite="0.5")

    client = TestClient(app)
    resp = client.get("/api/intelligence/tuning-advice")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] >= 1
    codes = {s["code"] for s in data["suggestions"]}
    assert "increase_capital_utilization" in codes


def test_portfolio_intelligence_endpoint(pg_session: Session) -> None:
    from apps.api.src.main import app
    _portfolio(pg_session, cash="10000")
    client = TestClient(app)
    resp = client.get("/api/intelligence/portfolio")
    assert resp.status_code == 200
    data = resp.json()
    assert "flags" in data


def test_decision_review_endpoint(pg_session: Session) -> None:
    from apps.api.src.main import app
    _portfolio(pg_session)
    client = TestClient(app)
    resp = client.get("/api/intelligence/decision-review")
    assert resp.status_code == 200
    assert "bucket_performance" in resp.json()


def test_news_analysis_endpoint(pg_session: Session) -> None:
    from apps.api.src.main import app
    _portfolio(pg_session)
    client = TestClient(app)
    resp = client.get("/api/intelligence/news-analysis")
    assert resp.status_code == 200
    data = resp.json()
    assert "by_sentiment" in data
    assert "by_category" in data
