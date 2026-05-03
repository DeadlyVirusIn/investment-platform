"""Integration test — end-to-end runner against Postgres."""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from apps.api.src.db.models import (
    Asset,
    PriceBar,
    Signal,
    SignalOutcome,
)
from apps.api.src.domain.signal_evaluator.runner import evaluate_pending_signals

pytestmark = pytest.mark.integration


def _seed_asset(session: Session, symbol: str = "AAPL") -> Asset:
    a = Asset(
        id=str(uuid.uuid4()), symbol=symbol,
        asset_class="equity", sector="tech", exchange="NASDAQ",
    )
    session.add(a)
    session.commit()
    return a


def _seed_signal(
    session: Session, *, asset: Asset, as_of: dt.date,
    direction: str = "long", holding: int = 5,
    signal_id: str | None = None,
) -> Signal:
    s = Signal(
        signal_id=signal_id or str(uuid.uuid4()),
        as_of_date=as_of,
        asset_id=asset.id, symbol=asset.symbol, timeframe="1d",
        strategy_id="deterministic_v1", model_family="deterministic",
        model_version="test:abc", features_version="v1",
        signal_direction=direction,
        signal_strength=Decimal("0.8"),
        confidence=Decimal("0.7"),
        holding_period_bars=holding,
        generated_at=dt.datetime.combine(as_of, dt.time(15, 0), tzinfo=dt.timezone.utc),
    )
    session.add(s)
    session.commit()
    return s


def _seed_price(
    session: Session, *, asset_id: str, date: dt.date, close: Decimal,
) -> None:
    ts = dt.datetime.combine(date, dt.time(20, 0), tzinfo=dt.timezone.utc)
    session.add(PriceBar(
        id=str(uuid.uuid4()), asset_id=asset_id, timeframe="1d", ts=ts,
        open=close, high=close, low=close, close=close, adjusted_close=close,
        volume=1_000_000, provider="test",
    ))
    session.commit()


def _seed_price_series(
    session: Session, asset: Asset, start: dt.date, closes: list[Decimal],
) -> None:
    for i, c in enumerate(closes):
        _seed_price(session, asset_id=asset.id, date=start + dt.timedelta(days=i), close=c)


# ---------------------------------------------------------------------------


def test_signal_produces_win_outcome(pg_session: Session):
    asset = _seed_asset(pg_session, "AAPL")
    entry_date = dt.date(2026, 1, 5)
    # 6 bars: entry + 5 forward (holding=5)
    _seed_price_series(pg_session, asset, entry_date, [
        Decimal("100"), Decimal("102"), Decimal("104"),
        Decimal("103"), Decimal("105"), Decimal("110"),
    ])
    sig = _seed_signal(pg_session, asset=asset, as_of=entry_date, direction="long", holding=5)

    report = evaluate_pending_signals(pg_session, today=entry_date + dt.timedelta(days=6))
    assert report.signals_total == 1
    assert report.signals_evaluated == 1
    assert report.signals_skipped == 0

    row = pg_session.query(SignalOutcome).filter_by(signal_id=sig.signal_id).one()
    assert row.outcome_label == "win"
    assert row.signal_direction == "long"
    assert Decimal(row.entry_price) == Decimal("100")
    # Realized = (110 - 100) / 100 = 0.10
    assert Decimal(row.realized_return) == Decimal("0.1")


def test_idempotent_does_not_overwrite(pg_session: Session):
    asset = _seed_asset(pg_session, "MSFT")
    entry_date = dt.date(2026, 2, 3)
    _seed_price_series(pg_session, asset, entry_date, [
        Decimal("200"), Decimal("201"), Decimal("195"), Decimal("210"),
    ])
    _seed_signal(pg_session, asset=asset, as_of=entry_date, direction="long", holding=3)

    r1 = evaluate_pending_signals(pg_session, today=entry_date + dt.timedelta(days=4))
    r2 = evaluate_pending_signals(pg_session, today=entry_date + dt.timedelta(days=4))
    assert r1.signals_evaluated == 1
    assert r2.signals_total == 0     # excluded because outcome exists
    assert r2.signals_evaluated == 0
    assert pg_session.query(SignalOutcome).count() == 1


def test_insufficient_forward_data_skips(pg_session: Session):
    asset = _seed_asset(pg_session, "NVDA")
    entry_date = dt.date(2026, 3, 2)
    # Only 2 bars, holding=5 → insufficient
    _seed_price_series(pg_session, asset, entry_date, [Decimal("100"), Decimal("101")])
    _seed_signal(pg_session, asset=asset, as_of=entry_date, direction="long", holding=5)

    # Advance 'today' enough that as_of+holding_period_bars <= today (required by query)
    report = evaluate_pending_signals(pg_session, today=entry_date + dt.timedelta(days=6))
    assert report.signals_total == 1
    assert report.signals_evaluated == 0
    assert report.signals_skipped == 1
    assert "insufficient_forward_bars" in report.skip_reasons
    assert pg_session.query(SignalOutcome).count() == 0


def test_timeout_is_labeled(pg_session: Session):
    asset = _seed_asset(pg_session, "TSLA")
    entry_date = dt.date(2026, 4, 1)
    # One entry bar so evaluator can record entry_price
    _seed_price(pg_session, asset_id=asset.id, date=entry_date, close=Decimal("250"))
    _seed_signal(pg_session, asset=asset, as_of=entry_date, direction="long", holding=5)

    # Age far beyond MAX_WAIT (2 × 5 = 10) — use 30 days later
    report = evaluate_pending_signals(
        pg_session, today=entry_date + dt.timedelta(days=30),
    )
    assert report.signals_timeout == 1
    row = pg_session.query(SignalOutcome).one()
    assert row.outcome_label == "timeout"
    assert Decimal(row.entry_price) == Decimal("250")


def test_breakeven_threshold_applied(pg_session: Session):
    asset = _seed_asset(pg_session, "VZ")
    entry_date = dt.date(2026, 5, 4)
    # Entry 100, exit 100.15 → 0.15% < 0.2% threshold → breakeven
    _seed_price_series(pg_session, asset, entry_date, [
        Decimal("100"), Decimal("100.05"), Decimal("100.10"),
        Decimal("100.12"), Decimal("100.14"), Decimal("100.15"),
    ])
    _seed_signal(pg_session, asset=asset, as_of=entry_date, direction="long", holding=5)
    r = evaluate_pending_signals(pg_session, today=entry_date + dt.timedelta(days=6))
    assert r.signals_evaluated == 1
    row = pg_session.query(SignalOutcome).one()
    assert row.outcome_label == "breakeven"
