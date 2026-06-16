"""BACKTEST-PAPER-7 — version-scoped replay conviction calibration.

Proves replay outcomes feed a replay-scoped calibration without polluting
live calibration, with honest insufficient-data gating.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from apps.api.src.analytics.calibration import MIN_CALIBRATION_SAMPLES
from apps.api.src.analytics.confidence_outcomes import (
    conviction_calibration_from_pairs,
    replay_conviction_calibration,
    stock_conviction_calibration,
)
from apps.api.src.db.models import (
    Asset,
    PaperPortfolio,
    PaperPosition,
    Recommendation,
)

pytestmark = pytest.mark.integration

LIVE_VER = "0.1.0"
R1_VER = "0.1.0+replay:r1"
R2_VER = "0.1.0+replay:r2"


def _asset_pf(pg_session: Session) -> tuple[str, str]:
    a = Asset(symbol="CAL1", asset_class="equity", exchange="TEST", currency="USD")
    p = PaperPortfolio(name="cal-pf", starting_cash=Decimal("100000"),
                       cash=Decimal("100000"), is_active=True)
    pg_session.add_all([a, p])
    pg_session.flush()
    return a.id, p.id


def _add_closed(pg_session: Session, asset_id: str, portfolio_id: str, *,
                model_version: str, n: int, conviction: float = 70.0) -> None:
    """Add n closed attributed positions under one model_version. Alternating
    win/loss so calibration has both outcomes."""
    for i in range(n):
        rec = Recommendation(
            asset_id=asset_id, action="Buy",
            conviction=Decimal(str(conviction)),
            model_version=model_version, snapshot_hash=f"h{i}",
        )
        pg_session.add(rec)
        pg_session.flush()
        pg_session.add(PaperPosition(
            portfolio_id=portfolio_id, asset_id=asset_id,
            quantity=Decimal("1"), avg_cost=Decimal("100"), is_open=False,
            realized_pnl=Decimal("1") if i % 2 == 0 else Decimal("-1"),
            opened_by_recommendation_id=rec.id,
            opened_at=dt.datetime(2026, 5, 1, tzinfo=dt.timezone.utc),
            closed_at=dt.datetime(2026, 5, 2, tzinfo=dt.timezone.utc),
        ))
    pg_session.flush()


def test_live_calibration_excludes_replay(pg_session: Session) -> None:
    aid, pid = _asset_pf(pg_session)
    _add_closed(pg_session, aid, pid, model_version=LIVE_VER, n=3)
    _add_closed(pg_session, aid, pid, model_version=R1_VER, n=4)
    pg_session.commit()

    res = stock_conviction_calibration(pg_session)
    assert res["sample_count"] == 3          # live only; replay excluded


def test_replay_scoped_filter(pg_session: Session) -> None:
    aid, pid = _asset_pf(pg_session)
    _add_closed(pg_session, aid, pid, model_version=R1_VER, n=4)
    _add_closed(pg_session, aid, pid, model_version=R2_VER, n=2)
    _add_closed(pg_session, aid, pid, model_version=LIVE_VER, n=3)
    pg_session.commit()

    res = replay_conviction_calibration(pg_session, run_label="r1")
    assert res["sample_count"] == 4          # only +replay:r1
    assert res["scope"] == "replay"
    assert res["run_label"] == "r1"


def test_insufficient_gating(pg_session: Session) -> None:
    aid, pid = _asset_pf(pg_session)
    _add_closed(pg_session, aid, pid, model_version=R1_VER, n=5)
    pg_session.commit()

    res = replay_conviction_calibration(pg_session, run_label="r1")
    assert res["sample_count"] == 5
    assert res["status"] == "insufficient_for_calibration"
    assert res["brier_score"] is None
    assert res["expected_calibration_error"] is None


def test_threshold_met_computes_metrics(pg_session: Session) -> None:
    aid, pid = _asset_pf(pg_session)
    n = MIN_CALIBRATION_SAMPLES + 5
    _add_closed(pg_session, aid, pid, model_version=R1_VER, n=n)
    pg_session.commit()

    res = replay_conviction_calibration(pg_session, run_label="r1")
    assert res["sample_count"] == n
    assert res["status"] == "ok"
    assert res["brier_score"] is not None
    assert res["expected_calibration_error"] is not None
    assert res["reliability_bins"]
    assert res["scope"] == "replay" and res["run_label"] == "r1"


def test_calibration_from_pairs_helper(pg_session: Session) -> None:
    n = MIN_CALIBRATION_SAMPLES + 2
    pairs = [(Decimal("70"), Decimal("1") if i % 2 == 0 else Decimal("-1"))
             for i in range(n)]
    res = conviction_calibration_from_pairs(pairs, run_label="rx")
    assert res["sample_count"] == n
    assert res["status"] == "ok"
    assert res["scope"] == "replay" and res["run_label"] == "rx"
