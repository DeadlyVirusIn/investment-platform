"""Integration tests for per-user paper-portfolio resolution (P0 isolation).

Proves a cold device gets its OWN empty book, read/write resolve the same
portfolio, and no device attaches to the shared Replay-Recovery portfolio.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from apps.api.src.config import settings
from apps.api.src.db.models import PaperPortfolio, PaperPosition
from apps.api.src.domain.paper_trading.paper_service import (
    resolve_user_stock_portfolio,
    user_stock_portfolio_name,
)

pytestmark = pytest.mark.integration


def test_cold_device_gets_own_empty_book(pg_session: Session) -> None:
    pid = resolve_user_stock_portfolio(pg_session, "cold-device-1")
    pg_session.commit()

    pf = pg_session.get(PaperPortfolio, pid)
    assert pf is not None
    assert pf.name == user_stock_portfolio_name("cold-device-1")
    assert float(pf.starting_cash) == 100000.0

    # Never the shared demo / Replay-Recovery portfolio.
    assert pid != settings.CANONICAL_STOCK_PORTFOLIO_ID

    # Empty: zero open positions → onboarding count correctness.
    open_count = pg_session.scalar(
        select(func.count())
        .select_from(PaperPosition)
        .where(PaperPosition.portfolio_id == pid, PaperPosition.is_open.is_(True))
    )
    assert open_count == 0


def test_resolution_is_idempotent_read_equals_write(pg_session: Session) -> None:
    # The SAME resolver backs both the read endpoint and the write endpoints,
    # so repeated resolution of one user always yields the same portfolio id.
    first = resolve_user_stock_portfolio(pg_session, "same-user")
    pg_session.commit()
    second = resolve_user_stock_portfolio(pg_session, "same-user")
    pg_session.commit()
    assert first == second

    # Only one row was created for that user.
    n = pg_session.scalar(
        select(func.count())
        .select_from(PaperPortfolio)
        .where(PaperPortfolio.name == user_stock_portfolio_name("same-user"))
    )
    assert n == 1


def test_distinct_devices_get_distinct_books(pg_session: Session) -> None:
    a = resolve_user_stock_portfolio(pg_session, "device-a")
    b = resolve_user_stock_portfolio(pg_session, "device-b")
    pg_session.commit()
    assert a != b
