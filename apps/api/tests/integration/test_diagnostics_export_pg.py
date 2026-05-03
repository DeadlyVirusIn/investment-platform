"""Integration: diagnostics export + share-text + CSV format on existing endpoints."""

from __future__ import annotations

import datetime as dt
import io
import json
import zipfile
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
from apps.api.src.domain.stock_engine.scoring import MODEL_VERSION

pytestmark = pytest.mark.integration

TODAY = dt.date(2026, 4, 20)


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


def _portfolio(pg_session: Session) -> PaperPortfolio:
    p = PaperPortfolio(
        name=f"dx-{dt.datetime.now().timestamp()}",
        starting_cash=Decimal("50000"), cash=Decimal("50000"),
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


def _bar(pg_session: Session, asset: Asset, day: dt.date, close: str) -> None:
    ts = dt.datetime.combine(day, dt.time(0, 0, 0, tzinfo=dt.timezone.utc))
    c = Decimal(close)
    pg_session.add(PriceBar(
        asset_id=asset.id, timeframe="1d", ts=ts,
        open=c, close=c, high=c * Decimal("1.005"), low=c * Decimal("0.995"),
        adjusted_close=c, volume=1_000_000, provider="test",
    ))
    pg_session.commit()


def _candidate(
    pg_session: Session, asset: Asset, as_of: dt.date,
    *, status: str, action: str | None = None,
    rejection_reason: str | None = None,
    composite: str = "0.40", confidence: str = "70",
) -> None:
    pg_session.add(CandidateIdea(
        as_of_date=as_of, asset_id=asset.id,
        model_version=MODEL_VERSION, engine="stock_swing",
        status=status, action=action,
        rejection_reason=rejection_reason,
        composite_score=Decimal(composite),
        confidence=Decimal(confidence),
        factor_breakdown={}, regime_snapshot={
            "market_trend": "uptrend", "vol_regime": "normal",
        },
    ))
    pg_session.commit()


def _regime(pg_session: Session, as_of: dt.date) -> None:
    pg_session.add(RegimeSnapshot(
        as_of_date=as_of, benchmark_symbol="SPY",
        market_trend="uptrend", vol_regime="normal",
        breadth_regime=None, sma50_over_sma200=True,
        realized_vol_20d=Decimal("0.15"), atr_pctile_1y=Decimal("0.4"),
    ))
    pg_session.commit()


def _trade(
    pg_session: Session, portfolio: PaperPortfolio, asset: Asset,
    side: str, qty: str, price: str, days_ago: int,
    realized_pnl: str | None = None,
) -> None:
    ts = dt.datetime.combine(
        TODAY - dt.timedelta(days=days_ago),
        dt.time(14, 30, tzinfo=dt.timezone.utc),
    )
    pg_session.add(PaperTrade(
        portfolio_id=portfolio.id, asset_id=asset.id,
        side=side, quantity=Decimal(qty), fill_price=Decimal(price),
        fill_ts=ts, submitted_at=ts,
        realized_pnl=Decimal(realized_pnl) if realized_pnl is not None else None,
        slippage_bps=Decimal("20"), commission=Decimal("0"),
    ))
    pg_session.commit()


def _open_position(
    pg_session: Session, portfolio: PaperPortfolio, asset: Asset,
    qty: str, avg_cost: str,
) -> None:
    pos = PaperPosition(
        portfolio_id=portfolio.id, asset_id=asset.id,
        quantity=Decimal(qty), avg_cost=Decimal(avg_cost),
        is_open=True,
        opened_at=dt.datetime.combine(
            TODAY - dt.timedelta(days=4),
            dt.time(14, 30, tzinfo=dt.timezone.utc),
        ),
    )
    pg_session.add(pos)
    pg_session.commit()


# ---------------------------------------------------------------------------
# Bundle export
# ---------------------------------------------------------------------------


def test_export_bundle_contains_expected_files(pg_session: Session) -> None:
    from apps.api.src.main import app

    p = _portfolio(pg_session)
    _regime(pg_session, TODAY)
    a = _asset(pg_session, "EX_A")
    _bar(pg_session, a, TODAY, close="110")
    _candidate(pg_session, a, TODAY, status="accepted", action="Buy",
               composite="0.40", confidence="70")
    _trade(pg_session, p, a, side="buy", qty="10", price="100", days_ago=4)
    _open_position(pg_session, p, a, qty="10", avg_cost="100")

    client = TestClient(app)
    resp = client.get(
        f"/api/diagnostics/export?from={TODAY.isoformat()}&to={TODAY.isoformat()}"
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"

    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    names = set(zf.namelist())
    for expected in [
        "dashboard_summary.json",
        "pnl_summary.json",
        "pnl_by_symbol.csv",
        "pnl_by_score_bucket.json",
        "pnl_by_regime.json",
        "blocked_alpha_sim.json",
        "candidate_ideas.csv",
        "rejection_summary.json",
        "regime_history.json",
        "paper_trades.csv",
        "job_status.json",
        "factor_snapshots.csv",
    ]:
        assert expected in names, f"missing {expected} in {names}"


def test_export_bundle_respects_include_flags(pg_session: Session) -> None:
    from apps.api.src.main import app

    _regime(pg_session, TODAY)
    client = TestClient(app)
    resp = client.get(
        "/api/diagnostics/export"
        f"?from={TODAY.isoformat()}&to={TODAY.isoformat()}"
        "&include_factors=false&include_candidates=false"
        "&include_pnl=false&include_jobs=false"
    )
    assert resp.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    names = set(zf.namelist())
    # Dashboard + regime history always present
    assert "dashboard_summary.json" in names
    assert "regime_history.json" in names
    # Excluded ones not present
    assert "factor_snapshots.csv" not in names
    assert "candidate_ideas.csv" not in names
    assert "paper_trades.csv" not in names
    assert "job_status.json" not in names


def test_export_bundle_symbols_filter(pg_session: Session) -> None:
    from apps.api.src.main import app

    _regime(pg_session, TODAY)
    a = _asset(pg_session, "FIL_A")
    b = _asset(pg_session, "FIL_B")
    _candidate(pg_session, a, TODAY, status="accepted", action="Buy",
               composite="0.40", confidence="70")
    _candidate(pg_session, b, TODAY, status="accepted", action="Buy",
               composite="0.40", confidence="70")

    client = TestClient(app)
    resp = client.get(
        "/api/diagnostics/export"
        f"?from={TODAY.isoformat()}&to={TODAY.isoformat()}&symbols=FIL_A"
    )
    assert resp.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    body = zf.read("candidate_ideas.csv").decode()
    assert "FIL_A" in body
    assert "FIL_B" not in body


def test_export_rejects_inverted_range(pg_session: Session) -> None:
    from apps.api.src.main import app
    client = TestClient(app)
    resp = client.get(
        "/api/diagnostics/export?from=2026-04-20&to=2026-04-10"
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Share text
# ---------------------------------------------------------------------------


def test_share_text_plain(pg_session: Session) -> None:
    from apps.api.src.main import app

    p = _portfolio(pg_session)
    _regime(pg_session, TODAY)
    a = _asset(pg_session, "STX_A")
    _candidate(pg_session, a, TODAY, status="accepted", action="Buy",
               composite="0.5", confidence="80")
    _bar(pg_session, a, TODAY, close="110")
    _open_position(pg_session, p, a, qty="10", avg_cost="100")

    client = TestClient(app)
    resp = client.get("/api/diagnostics/share-text")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    text = resp.text
    assert "Investment Platform" in text
    assert "Regime" in text
    assert "Portfolio" in text
    assert "STX_A" in text  # appears as top position + top buy


def test_share_text_json(pg_session: Session) -> None:
    from apps.api.src.main import app
    _regime(pg_session, TODAY)
    client = TestClient(app)
    resp = client.get("/api/diagnostics/share-text?format=json")
    assert resp.status_code == 200
    data = json.loads(resp.text)
    assert "candidates" in data
    assert "regime" in data
    assert "portfolio" in data


# ---------------------------------------------------------------------------
# CSV format on existing endpoints
# ---------------------------------------------------------------------------


def test_candidates_csv_format(pg_session: Session) -> None:
    from apps.api.src.main import app

    a = _asset(pg_session, "CC_CSV")
    _candidate(pg_session, a, TODAY, status="accepted", action="Buy",
               composite="0.4", confidence="70")

    client = TestClient(app)
    resp = client.get(
        f"/api/stock-engine/candidates?as_of={TODAY.isoformat()}&format=csv"
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    lines = resp.text.strip().splitlines()
    assert lines[0].startswith("as_of_date,symbol,")
    assert "CC_CSV" in resp.text


def test_pnl_by_symbol_csv(pg_session: Session) -> None:
    from apps.api.src.main import app

    p = _portfolio(pg_session)
    a = _asset(pg_session, "BS_CSV")
    _bar(pg_session, a, TODAY, close="120")
    _open_position(pg_session, p, a, qty="10", avg_cost="100")

    client = TestClient(app)
    resp = client.get("/api/pnl/by-symbol?format=csv")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "BS_CSV" in resp.text


def test_pnl_by_score_bucket_csv(pg_session: Session) -> None:
    from apps.api.src.main import app
    _portfolio(pg_session)
    client = TestClient(app)
    resp = client.get("/api/pnl/by-score-bucket?format=csv")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "bucket" in resp.text


def test_pnl_by_regime_csv(pg_session: Session) -> None:
    from apps.api.src.main import app
    _portfolio(pg_session)
    client = TestClient(app)
    resp = client.get("/api/pnl/by-regime?format=csv")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "market_trend,vol_regime" in resp.text


def test_blocked_alpha_csv(pg_session: Session) -> None:
    from apps.api.src.main import app
    a = _asset(pg_session, "BA_CSV")
    _candidate(pg_session, a, TODAY,
               status="rejected", rejection_reason="regime_off",
               composite="0.4")
    client = TestClient(app)
    resp = client.get(
        "/api/stock-engine/analytics/blocked-alpha"
        f"?from={TODAY.isoformat()}&to={TODAY.isoformat()}&min_score=0.25&format=csv"
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "BA_CSV" in resp.text
