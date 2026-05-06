"""Read-path test: options paper-trades status tab maps to the
correct DB enum set.

Covers the forensic-fix where the UI Open tab requested
status='open' but the runner inserts trades with status='PROPOSED'
— the lower-case UI tab now expands to ('PROPOSED', 'OPEN',
'EXPIRING') so a freshly-submitted trade is visible immediately.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session, sessionmaker

from apps.api.src.db.options_models import (
    OptionsPaperTrade, OptionsPaperTradeLeg,
)
from apps.api.src.options.service_readonly import list_paper_trades


pytestmark = pytest.mark.integration


def _seed_trade(
    session: Session, *, status: str, underlying: str = "AMZN",
    strategy: str = "BULL_CALL_SPREAD",
    opened: dt.datetime | None = None,
) -> int:
    t = OptionsPaperTrade(
        underlying=underlying,
        strategy_name=strategy,
        strategy_version="test",
        status=status,
        opened_at=(
            opened
            or dt.datetime(2026, 5, 4, 21, 0, tzinfo=dt.timezone.utc)
        ),
        max_loss_dollars=Decimal("610"),
        max_profit_dollars=Decimal("890"),
        fees_total_dollars=Decimal("0"),
        fill_model_version="next_bar_v1",
        paper_only=True,
    )
    session.add(t)
    session.flush()
    return t.id


def test_open_tab_includes_proposed(pg_session):
    _seed_trade(pg_session, status="PROPOSED")
    pg_session.commit()
    rows = list_paper_trades(pg_session, status="open")
    assert len(rows) == 1
    assert rows[0]["status"] == "PROPOSED"
    assert rows[0]["underlying"] == "AMZN"


def test_open_tab_includes_open_and_expiring(pg_session):
    _seed_trade(
        pg_session, status="OPEN", underlying="A",
        opened=dt.datetime(2026, 5, 4, 20, tzinfo=dt.timezone.utc),
    )
    _seed_trade(
        pg_session, status="EXPIRING", underlying="B",
        opened=dt.datetime(2026, 5, 4, 21, tzinfo=dt.timezone.utc),
    )
    _seed_trade(
        pg_session, status="CLOSED", underlying="C",
        opened=dt.datetime(2026, 5, 4, 22, tzinfo=dt.timezone.utc),
    )
    pg_session.commit()
    rows = list_paper_trades(pg_session, status="open")
    underlyings = {r["underlying"] for r in rows}
    assert underlyings == {"A", "B"}


def test_closed_tab_excludes_open(pg_session):
    _seed_trade(
        pg_session, status="OPEN", underlying="A",
        opened=dt.datetime(2026, 5, 4, 20, tzinfo=dt.timezone.utc),
    )
    _seed_trade(
        pg_session, status="CLOSED", underlying="B",
        opened=dt.datetime(2026, 5, 4, 22, tzinfo=dt.timezone.utc),
    )
    pg_session.commit()
    rows = list_paper_trades(pg_session, status="closed")
    assert [r["underlying"] for r in rows] == ["B"]


def test_expired_assigned_isolated(pg_session):
    _seed_trade(
        pg_session, status="EXPIRED", underlying="X",
        opened=dt.datetime(2026, 5, 4, 20, tzinfo=dt.timezone.utc),
    )
    _seed_trade(
        pg_session, status="ASSIGNED", underlying="Y",
        opened=dt.datetime(2026, 5, 4, 21, tzinfo=dt.timezone.utc),
    )
    pg_session.commit()
    assert [
        r["underlying"]
        for r in list_paper_trades(pg_session, status="expired")
    ] == ["X"]
    assert [
        r["underlying"]
        for r in list_paper_trades(pg_session, status="assigned")
    ] == ["Y"]


def test_db_enum_value_still_works(pg_session):
    """Backward compatibility: explicit DB enum values still
    filter exactly. Existing API consumers using PROPOSED/OPEN
    are not broken."""
    _seed_trade(
        pg_session, status="PROPOSED", underlying="A",
        opened=dt.datetime(2026, 5, 4, 20, tzinfo=dt.timezone.utc),
    )
    _seed_trade(
        pg_session, status="OPEN", underlying="B",
        opened=dt.datetime(2026, 5, 4, 21, tzinfo=dt.timezone.utc),
    )
    pg_session.commit()
    assert [
        r["underlying"]
        for r in list_paper_trades(pg_session, status="PROPOSED")
    ] == ["A"]
    assert [
        r["underlying"]
        for r in list_paper_trades(pg_session, status="OPEN")
    ] == ["B"]


def test_no_status_returns_all(pg_session):
    _seed_trade(
        pg_session, status="PROPOSED", underlying="A",
        opened=dt.datetime(2026, 5, 4, 20, tzinfo=dt.timezone.utc),
    )
    _seed_trade(
        pg_session, status="CLOSED", underlying="B",
        opened=dt.datetime(2026, 5, 4, 21, tzinfo=dt.timezone.utc),
    )
    pg_session.commit()
    rows = list_paper_trades(pg_session)
    assert len(rows) == 2


def test_underlying_filter_combines_with_status(pg_session):
    _seed_trade(
        pg_session, status="PROPOSED", underlying="AMZN",
        opened=dt.datetime(2026, 5, 4, 20, tzinfo=dt.timezone.utc),
    )
    _seed_trade(
        pg_session, status="PROPOSED", underlying="AAPL",
        opened=dt.datetime(2026, 5, 4, 21, tzinfo=dt.timezone.utc),
    )
    pg_session.commit()
    rows = list_paper_trades(
        pg_session, status="open", underlying="AMZN",
    )
    assert [r["underlying"] for r in rows] == ["AMZN"]
