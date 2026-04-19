"""Integration tests for account creation / listing (Postgres-backed)."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from apps.api.src.domain.ledger.account_service import (
    AccountCreate,
    create_account,
    list_accounts,
)

pytestmark = pytest.mark.integration


def test_create_account_persists(pg_session: Session) -> None:
    out = create_account(
        pg_session,
        AccountCreate(name="Fidelity Brokerage", kind="broker", broker="Fidelity"),
    )
    pg_session.commit()

    assert out.id
    assert out.name == "Fidelity Brokerage"
    assert out.kind == "broker"
    assert out.broker == "Fidelity"
    assert out.currency == "USD"
    assert out.is_active is True


def test_list_accounts_stable_order(pg_session: Session) -> None:
    a = create_account(pg_session, AccountCreate(name="A", kind="exchange", broker="Coinbase"))
    b = create_account(pg_session, AccountCreate(name="B", kind="wallet"))
    c = create_account(pg_session, AccountCreate(name="C", kind="manual"))
    pg_session.commit()

    accounts = list_accounts(pg_session)
    names = [acc.name for acc in accounts]
    assert names == ["A", "B", "C"]
    assert {acc.id for acc in accounts} == {a.id, b.id, c.id}


def test_account_kinds_accepted(pg_session: Session) -> None:
    for kind in ("broker", "exchange", "wallet", "manual"):
        create_account(pg_session, AccountCreate(name=f"acct-{kind}", kind=kind))
    pg_session.commit()
    assert len(list_accounts(pg_session)) == 4
