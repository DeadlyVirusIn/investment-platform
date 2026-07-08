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


def test_known_device_resolution_is_stable_and_never_shared_fallback(
    pg_session: Session,
) -> None:
    """Guardrail (2026-06-19 demo-clone repair).

    Regression protection for the trust incident where the owner/demo device's
    visible portfolio silently changed. The invariant: once a device owns a
    per-device book, the resolver must keep returning THAT book. A future change
    to the resolver must NOT silently repoint a known device to the shared
    Replay-Recovery fallback (``CANONICAL_STOCK_PORTFOLIO_ID``), to a fresh
    empty book, or to anything else.
    """
    device = "305fcf0b-bc89-4d9d-ba47-b6de6810dfd6"  # owner/demo device

    # The per-device name formula is load-bearing: it is what maps a device to
    # its portfolio. Changing it silently changes which book the device sees.
    assert user_stock_portfolio_name(device) == f"user:{device}:stock"

    # First resolution materialises the device's own book...
    pid_first = resolve_user_stock_portfolio(pg_session, device)
    pg_session.commit()

    # ...which is the per-device book, never the shared demo fallback.
    assert pid_first != settings.CANONICAL_STOCK_PORTFOLIO_ID
    pf = pg_session.get(PaperPortfolio, pid_first)
    assert pf is not None
    assert pf.name == user_stock_portfolio_name(device)

    # Re-resolving the SAME known device is stable — no silent swap.
    pid_again = resolve_user_stock_portfolio(pg_session, device)
    pg_session.commit()
    assert pid_again == pid_first


def test_engine_selector_never_returns_user_books(pg_session: Session) -> None:
    """P1 incident 2026-07-08: the nightly auto-trader drained user books.

    The engine job selector must return active ENGINE portfolios only —
    a per-user book (``user:<id>:stock``) must never be auto-traded,
    rebalanced, or exit-cycled by scheduled jobs."""
    from apps.api.src.domain.paper_trading.paper_service import (
        create_portfolio,
        engine_tradable_portfolio_ids,
    )
    from apps.api.src.domain.paper_trading.paper_service import PortfolioCreate

    user_pid = resolve_user_stock_portfolio(pg_session, "engine-guard-user")
    engine_pf = create_portfolio(
        pg_session, PortfolioCreate(name="engine-guard-book")
    )
    pg_session.commit()

    ids = engine_tradable_portfolio_ids(pg_session)
    assert engine_pf.id in ids
    assert user_pid not in ids
