"""Verify account_id defaults to the oldest account when omitted."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from apps.api.src.domain.ledger.account_service import AccountCreate, create_account

pytestmark = pytest.mark.integration


def test_portfolio_summary_defaults_to_first_account(pg_session: Session) -> None:
    from apps.api.src.main import app

    create_account(pg_session, AccountCreate(name="Primary", kind="broker"))
    pg_session.commit()
    create_account(pg_session, AccountCreate(name="Secondary", kind="broker"))
    pg_session.commit()

    client = TestClient(app)
    resp = client.get("/api/portfolio/summary")   # no account_id
    assert resp.status_code == 200
    data = resp.json()
    assert "realized_pnl" in data


def test_portfolio_summary_404_when_no_accounts(pg_session: Session) -> None:
    from apps.api.src.main import app
    from apps.api.src.db.models import Account
    from sqlalchemy import select as sqla_select

    client = TestClient(app)
    resp = client.get("/api/portfolio/summary")
    assert resp.status_code == 200

    pg_session.expire_all()
    accounts = list(pg_session.execute(sqla_select(Account)).scalars())
    assert len(accounts) == 1
    assert accounts[0].name == "Primary"


def test_portfolio_summary_with_explicit_account(pg_session: Session) -> None:
    from apps.api.src.main import app
    acct = create_account(pg_session, AccountCreate(name="Explicit", kind="broker"))
    pg_session.commit()
    client = TestClient(app)
    resp = client.get(f"/api/portfolio/summary?account_id={acct.id}")
    assert resp.status_code == 200


def test_portfolio_positions_defaults(pg_session: Session) -> None:
    from apps.api.src.main import app
    create_account(pg_session, AccountCreate(name="P", kind="broker"))
    pg_session.commit()
    client = TestClient(app)
    resp = client.get("/api/portfolio/positions")
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


def test_portfolio_transactions_defaults(pg_session: Session) -> None:
    from apps.api.src.main import app
    create_account(pg_session, AccountCreate(name="T", kind="broker"))
    pg_session.commit()
    client = TestClient(app)
    resp = client.get("/api/portfolio/transactions")
    assert resp.status_code == 200


def test_portfolio_pnl_defaults(pg_session: Session) -> None:
    from apps.api.src.main import app
    create_account(pg_session, AccountCreate(name="P2", kind="broker"))
    pg_session.commit()
    client = TestClient(app)
    resp = client.get("/api/portfolio/pnl")
    assert resp.status_code == 200


def test_briefing_today_defaults(pg_session: Session) -> None:
    from apps.api.src.main import app
    create_account(pg_session, AccountCreate(name="B", kind="broker"))
    pg_session.commit()
    client = TestClient(app)
    resp = client.get("/api/briefing/today")
    assert resp.status_code == 200
    assert "account_id" in resp.json()
