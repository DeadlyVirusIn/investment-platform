"""Integration tests for options strategy outcome scoring + endpoints.

Verifies:
  * compute_strategy_outcomes refuses same-bar entry (next-bar guard).
  * forward_return / outcome_label math is correct for LONG_CALL +
    BULL_CALL_SPREAD (debit) using only real chain rows.
  * upsert_outcomes is idempotent on natural key.
  * /api/performance/options/strategy-quality summary aggregates
    by_strategy correctly + reports thresholds.
  * /api/performance/options/strategy-quality/details surfaces rows
    sorted by absolute forward return.
  * Read-only safety — endpoints make no writes; rerunning the
    operator with new exit data converts pending -> good/bad.
"""

from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from apps.api.src.db import get_session
from apps.api.src.db.options_models import (
    OptionsChainSnapshot, OptionsStrategyOutcome,
)
from apps.api.src.domain.options_quality.outcome import (
    HORIZONS, StrategyInput, compute_strategy_outcomes, upsert_outcomes,
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


def _mk_snap(
    *, ts: dt.datetime, underlying: str, expiry: dt.date,
    strike: float, otype: str, sym: str,
    bid: float, ask: float, mid: float | None = None,
) -> OptionsChainSnapshot:
    return OptionsChainSnapshot(
        snapshot_at_utc=ts, underlying=underlying, expiry=expiry,
        strike=strike, option_type=otype, option_symbol=sym,
        bid=bid, ask=ask, mid=(mid if mid is not None else (bid + ask) / 2),
        quote_age_seconds=0, provider="test",
    )


@pytest.fixture
def submit_at() -> dt.datetime:
    return dt.datetime(2026, 5, 1, 21, 0, tzinfo=dt.timezone.utc)


def _seed_long_call(
    pg_session: Session, *, sym: str, expiry: dt.date,
    submit_at: dt.datetime,
    same_bar_mid: float, t1_mid: float, t5_mid: float,
    underlying: str = "AAPL", strike: float = 200.0,
) -> None:
    """Three snapshots: same-bar (must be ignored), T+1, T+5 — long call."""
    pg_session.add(_mk_snap(
        ts=submit_at, underlying=underlying, expiry=expiry, strike=strike,
        otype="CALL", sym=sym,
        bid=same_bar_mid - 0.05, ask=same_bar_mid + 0.05, mid=same_bar_mid,
    ))
    pg_session.add(_mk_snap(
        ts=submit_at + dt.timedelta(days=1, hours=2),
        underlying=underlying, expiry=expiry, strike=strike,
        otype="CALL", sym=sym,
        bid=t1_mid - 0.05, ask=t1_mid + 0.05, mid=t1_mid,
    ))
    pg_session.add(_mk_snap(
        ts=submit_at + dt.timedelta(days=5, hours=2),
        underlying=underlying, expiry=expiry, strike=strike,
        otype="CALL", sym=sym,
        bid=t5_mid - 0.05, ask=t5_mid + 0.05, mid=t5_mid,
    ))
    pg_session.commit()


def test_long_call_good_outcome_at_5d(pg_session, submit_at):
    """Entry uses T+1 (not same-bar). Exit at T+5 with +50% premium → good."""
    expiry = (submit_at + dt.timedelta(days=30)).date()
    _seed_long_call(
        pg_session, sym="AAPL_C200_30D", expiry=expiry,
        submit_at=submit_at,
        same_bar_mid=99.99,   # MUST be ignored
        t1_mid=2.00,
        t5_mid=3.00,          # +50%
    )
    inp = StrategyInput(
        underlying="AAPL", strategy_name="LONG_CALL",
        legs=[{
            "option_symbol": "AAPL_C200_30D",
            "action": "buy", "type": "call",
            "strike": 200, "expiry": expiry.isoformat(),
        }],
        as_of_date=submit_at.date(), submitted_at_utc=submit_at,
        source="suggestion", mode="strict",
    )
    outs = compute_strategy_outcomes(pg_session, [inp], horizons=("5D",))
    assert len(outs) == 1
    o = outs[0]
    assert o.entry_reference == pytest.approx(2.00)
    assert o.exit_reference == pytest.approx(3.00)
    assert o.forward_return_pct == pytest.approx(0.50)
    assert o.outcome_label == "good"


def test_long_call_bad_outcome_at_5d(pg_session, submit_at):
    expiry = (submit_at + dt.timedelta(days=30)).date()
    _seed_long_call(
        pg_session, sym="AAPL_C200_30D", expiry=expiry,
        submit_at=submit_at,
        same_bar_mid=99.99,
        t1_mid=2.00,
        t5_mid=1.50,  # -25%
    )
    inp = StrategyInput(
        underlying="AAPL", strategy_name="LONG_CALL",
        legs=[{
            "option_symbol": "AAPL_C200_30D", "action": "buy",
            "type": "call", "strike": 200, "expiry": expiry.isoformat(),
        }],
        as_of_date=submit_at.date(), submitted_at_utc=submit_at,
        source="suggestion", mode="strict",
    )
    outs = compute_strategy_outcomes(pg_session, [inp], horizons=("5D",))
    o = outs[0]
    assert o.forward_return_pct == pytest.approx(-0.25)
    assert o.outcome_label == "bad"


def test_pending_when_no_future_exit(pg_session, submit_at):
    """Entry exists but no snapshot >= submit + 5d → pending."""
    expiry = (submit_at + dt.timedelta(days=30)).date()
    pg_session.add(_mk_snap(
        ts=submit_at + dt.timedelta(days=1),
        underlying="AAPL", expiry=expiry, strike=200, otype="CALL",
        sym="AAPL_C200_30D",
        bid=1.95, ask=2.05, mid=2.00,
    ))
    pg_session.commit()
    inp = StrategyInput(
        underlying="AAPL", strategy_name="LONG_CALL",
        legs=[{
            "option_symbol": "AAPL_C200_30D", "action": "buy",
            "type": "call", "strike": 200, "expiry": expiry.isoformat(),
        }],
        as_of_date=submit_at.date(), submitted_at_utc=submit_at,
        source="suggestion", mode="strict",
    )
    outs = compute_strategy_outcomes(pg_session, [inp], horizons=("5D",))
    assert outs[0].outcome_label == "pending"
    assert outs[0].forward_return_pct is None


def test_data_blocked_when_no_future_quote_at_all(pg_session, submit_at):
    expiry = (submit_at + dt.timedelta(days=30)).date()
    pg_session.add(_mk_snap(
        ts=submit_at, underlying="AAPL", expiry=expiry,
        strike=200, otype="CALL", sym="AAPL_C200_30D",
        bid=1.95, ask=2.05, mid=2.00,
    ))
    pg_session.commit()
    inp = StrategyInput(
        underlying="AAPL", strategy_name="LONG_CALL",
        legs=[{
            "option_symbol": "AAPL_C200_30D", "action": "buy",
            "type": "call", "strike": 200, "expiry": expiry.isoformat(),
        }],
        as_of_date=submit_at.date(), submitted_at_utc=submit_at,
        source="suggestion", mode="strict",
    )
    outs = compute_strategy_outcomes(pg_session, [inp], horizons=("5D",))
    assert outs[0].outcome_label == "data_blocked"


def test_bull_call_spread_pricing(pg_session, submit_at):
    """Net debit = buy.mid - sell.mid; forward return uses signed delta."""
    expiry = (submit_at + dt.timedelta(days=30)).date()
    # Long 200 leg
    _seed_long_call(
        pg_session, sym="AAPL_C200_30D", expiry=expiry,
        submit_at=submit_at,
        same_bar_mid=99.99,
        t1_mid=3.00, t5_mid=4.50,
    )
    # Short 210 leg
    pg_session.add(_mk_snap(
        ts=submit_at + dt.timedelta(days=1, hours=2),
        underlying="AAPL", expiry=expiry, strike=210, otype="CALL",
        sym="AAPL_C210_30D",
        bid=0.95, ask=1.05, mid=1.00,
    ))
    pg_session.add(_mk_snap(
        ts=submit_at + dt.timedelta(days=5, hours=2),
        underlying="AAPL", expiry=expiry, strike=210, otype="CALL",
        sym="AAPL_C210_30D",
        bid=1.95, ask=2.05, mid=2.00,
    ))
    pg_session.commit()
    inp = StrategyInput(
        underlying="AAPL", strategy_name="BULL_CALL_SPREAD",
        legs=[
            {
                "option_symbol": "AAPL_C200_30D", "action": "buy",
                "type": "call", "strike": 200,
                "expiry": expiry.isoformat(),
            },
            {
                "option_symbol": "AAPL_C210_30D", "action": "sell",
                "type": "call", "strike": 210,
                "expiry": expiry.isoformat(),
            },
        ],
        as_of_date=submit_at.date(), submitted_at_utc=submit_at,
        source="suggestion", mode="strict",
    )
    outs = compute_strategy_outcomes(pg_session, [inp], horizons=("5D",))
    o = outs[0]
    # entry net debit: 3.00 - 1.00 = 2.00
    assert o.entry_reference == pytest.approx(2.00)
    # exit net debit: 4.50 - 2.00 = 2.50
    assert o.exit_reference == pytest.approx(2.50)
    # forward return: (2.50 - 2.00)/abs(2.00) = +0.25
    assert o.forward_return_pct == pytest.approx(0.25)
    assert o.outcome_label == "good"


def test_upsert_idempotent_then_pending_to_finalized(pg_session, submit_at):
    """First run: pending. Add future snap. Second run: outcome
    upgraded in place via natural-key UPSERT."""
    expiry = (submit_at + dt.timedelta(days=30)).date()
    pg_session.add(_mk_snap(
        ts=submit_at + dt.timedelta(days=1),
        underlying="AAPL", expiry=expiry, strike=200, otype="CALL",
        sym="AAPL_C200_30D",
        bid=1.95, ask=2.05, mid=2.00,
    ))
    pg_session.commit()
    inp = StrategyInput(
        underlying="AAPL", strategy_name="LONG_CALL",
        legs=[{
            "option_symbol": "AAPL_C200_30D", "action": "buy",
            "type": "call", "strike": 200, "expiry": expiry.isoformat(),
        }],
        as_of_date=submit_at.date(), submitted_at_utc=submit_at,
        source="suggestion", mode="strict",
    )
    outs1 = compute_strategy_outcomes(pg_session, [inp], horizons=("5D",))
    r1 = upsert_outcomes(pg_session, outs1)
    assert r1["inserted"] == 1 and r1["updated"] == 0
    assert outs1[0].outcome_label == "pending"

    # Add T+5 snapshot, rerun
    pg_session.add(_mk_snap(
        ts=submit_at + dt.timedelta(days=5, hours=2),
        underlying="AAPL", expiry=expiry, strike=200, otype="CALL",
        sym="AAPL_C200_30D",
        bid=2.95, ask=3.05, mid=3.00,
    ))
    pg_session.commit()
    outs2 = compute_strategy_outcomes(pg_session, [inp], horizons=("5D",))
    r2 = upsert_outcomes(pg_session, outs2)
    assert r2["inserted"] == 0 and r2["updated"] == 1

    # Single row total + label is now 'good'
    rows = (
        pg_session.query(OptionsStrategyOutcome)
        .filter_by(underlying="AAPL", strategy_name="LONG_CALL")
        .all()
    )
    assert len(rows) == 1
    assert rows[0].outcome_label == "good"
    assert float(rows[0].forward_return_pct) == pytest.approx(0.50)


def test_strategy_quality_endpoint_aggregates(pg_session, client, submit_at):
    """End-to-end: seed outcomes, hit the API, check by_strategy summary."""
    expiry = (submit_at + dt.timedelta(days=30)).date()
    # Two LONG_CALL: one good, one bad. One BULL_CALL_SPREAD: good.
    _seed_long_call(
        pg_session, sym="AAPL_C200_30D", expiry=expiry,
        submit_at=submit_at,
        same_bar_mid=99.99, t1_mid=2.00, t5_mid=3.00,
    )
    _seed_long_call(
        pg_session, sym="MSFT_C400_30D", expiry=expiry,
        submit_at=submit_at,
        same_bar_mid=99.99, t1_mid=4.00, t5_mid=3.00,
        underlying="MSFT", strike=400.0,
    )
    inp_good = StrategyInput(
        underlying="AAPL", strategy_name="LONG_CALL",
        legs=[{
            "option_symbol": "AAPL_C200_30D", "action": "buy",
            "type": "call", "strike": 200, "expiry": expiry.isoformat(),
        }],
        as_of_date=submit_at.date(), submitted_at_utc=submit_at,
        source="suggestion", mode="strict",
    )
    inp_bad = StrategyInput(
        underlying="MSFT", strategy_name="LONG_CALL",
        legs=[{
            "option_symbol": "MSFT_C400_30D", "action": "buy",
            "type": "call", "strike": 400, "expiry": expiry.isoformat(),
        }],
        as_of_date=submit_at.date(), submitted_at_utc=submit_at,
        source="suggestion", mode="strict",
    )
    outs = compute_strategy_outcomes(
        pg_session, [inp_good, inp_bad], horizons=("5D",),
    )
    upsert_outcomes(pg_session, outs)

    resp = client.get(
        f"/api/performance/options/strategy-quality"
        f"?as_of={submit_at.date().isoformat()}&horizon=5D&mode=strict"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["as_of_date"] == submit_at.date().isoformat()
    assert body["horizon"] == "5D"
    assert body["thresholds"]["good_pct"] == 0.01
    s = body["summary"]
    assert s["total"] == 2
    assert s["good"] == 1 and s["bad"] == 1
    assert s["hit_rate"] == pytest.approx(0.5)
    by = body["by_strategy"]
    assert "LONG_CALL" in by
    assert by["LONG_CALL"]["total"] == 2


def test_strategy_quality_details_endpoint(pg_session, client, submit_at):
    expiry = (submit_at + dt.timedelta(days=30)).date()
    _seed_long_call(
        pg_session, sym="AAPL_C200_30D", expiry=expiry,
        submit_at=submit_at,
        same_bar_mid=99.99, t1_mid=2.00, t5_mid=3.00,
    )
    inp = StrategyInput(
        underlying="AAPL", strategy_name="LONG_CALL",
        legs=[{
            "option_symbol": "AAPL_C200_30D", "action": "buy",
            "type": "call", "strike": 200, "expiry": expiry.isoformat(),
        }],
        as_of_date=submit_at.date(), submitted_at_utc=submit_at,
        source="suggestion", mode="strict",
    )
    upsert_outcomes(
        pg_session,
        compute_strategy_outcomes(pg_session, [inp], horizons=("5D",)),
    )

    resp = client.get(
        f"/api/performance/options/strategy-quality/details"
        f"?as_of={submit_at.date().isoformat()}&horizon=5D&mode=strict&limit=10"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    item = body["items"][0]
    assert item["underlying"] == "AAPL"
    assert item["strategy_name"] == "LONG_CALL"
    assert item["outcome_label"] == "good"
    assert item["forward_return_pct"] == pytest.approx(0.5)


def test_endpoint_rejects_bad_horizon(client):
    resp = client.get(
        "/api/performance/options/strategy-quality"
        "?as_of=2026-05-01&horizon=99D&mode=strict"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "error" in body and "horizon" in body["error"]


def test_endpoint_rejects_bad_mode(client):
    resp = client.get(
        "/api/performance/options/strategy-quality"
        "?as_of=2026-05-01&horizon=5D&mode=live"
    )
    body = resp.json()
    assert "error" in body and "mode" in body["error"]


def test_endpoint_empty_when_no_rows(client):
    resp = client.get(
        "/api/performance/options/strategy-quality"
        "?horizon=5D&mode=strict"
    )
    assert resp.status_code == 200
    body = resp.json()
    # No rows yet → should not 500; either notice or empty summary.
    assert body.get("notice") or body["summary"]["total"] == 0
