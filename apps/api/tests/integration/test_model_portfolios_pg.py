"""Sprint B — per-user portfolio ownership / isolation (Postgres integration).

Runs only when Docker/testcontainers (or a safe TEST_DATABASE_URL) is available;
skips otherwise. Proves _resolve_user_portfolio gives each user their OWN paper
book and is idempotent per user — the core multi-tenancy guarantee.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from apps.api.src.api.model_portfolios import _resolve_user_portfolio
from apps.api.src.db.models import PaperPortfolio

pytestmark = pytest.mark.integration


def test_resolve_user_portfolio_is_per_user_and_idempotent(pg_session: Session) -> None:
    a1 = _resolve_user_portfolio(pg_session, "userA")
    b1 = _resolve_user_portfolio(pg_session, "userB")
    a2 = _resolve_user_portfolio(pg_session, "userA")   # second call, same user

    # Isolation: distinct users → distinct books.
    assert a1 != b1
    # Idempotent: same user → same book (no duplicate creation).
    assert a1 == a2

    names = {p.name for p in pg_session.scalars(select(PaperPortfolio))}
    assert "user:userA:stock" in names
    assert "user:userB:stock" in names

    # Exactly one book per user (no duplicate on repeated resolve).
    count_a = pg_session.scalar(
        select(func.count()).select_from(PaperPortfolio)
        .where(PaperPortfolio.name == "user:userA:stock")
    )
    assert count_a == 1
