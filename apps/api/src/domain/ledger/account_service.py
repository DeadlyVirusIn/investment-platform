"""Account creation + listing. Minimal; no edit/delete in this batch."""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.src.db.models import Account

AccountKind = Literal["broker", "exchange", "wallet", "manual"]


class AccountCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    kind: AccountKind
    broker: str | None = Field(default=None, max_length=64)
    currency: str = Field(default="USD", min_length=3, max_length=8)


class AccountOut(BaseModel):
    id: str
    name: str
    kind: str
    broker: str | None
    currency: str
    is_active: bool
    created_at: dt.datetime


def _to_out(row: Account) -> AccountOut:
    return AccountOut(
        id=row.id,
        name=row.name,
        kind=row.account_type,
        broker=row.broker,
        currency=row.currency,
        is_active=row.is_active,
        created_at=row.created_at,
    )


def create_account(session: Session, payload: AccountCreate) -> AccountOut:
    row = Account(
        name=payload.name,
        account_type=payload.kind,
        broker=payload.broker,
        currency=payload.currency,
        is_active=True,
    )
    session.add(row)
    session.flush()
    return _to_out(row)


def list_accounts(session: Session) -> list[AccountOut]:
    stmt = select(Account).order_by(Account.created_at.asc(), Account.id.asc())
    rows = list(session.execute(stmt).scalars())
    return [_to_out(r) for r in rows]


def as_jsonable(out: AccountOut) -> dict[str, Any]:
    return out.model_dump(mode="json")
