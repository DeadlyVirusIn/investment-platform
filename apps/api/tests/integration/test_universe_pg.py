"""Integration: universe_membership helpers + /api/universe endpoint."""

from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from apps.api.src.db.models import Asset, UniverseMembership
from apps.api.src.domain.universe.membership import is_member, list_members

pytestmark = pytest.mark.integration


def _asset(pg_session: Session, symbol: str) -> Asset:
    a = Asset(symbol=symbol, asset_class="equity", exchange="NASDAQ", currency="USD")
    pg_session.add(a)
    pg_session.flush()
    pg_session.commit()
    return a


def _member(
    pg_session: Session,
    asset_id: str,
    universe: str,
    start: dt.date,
    end: dt.date | None = None,
    reason: str | None = "seeded",
) -> UniverseMembership:
    m = UniverseMembership(
        universe_name=universe, asset_id=asset_id,
        start_date=start, end_date=end, reason=reason,
    )
    pg_session.add(m)
    pg_session.commit()
    return m


# ---------------------------------------------------------------------------
# list_members
# ---------------------------------------------------------------------------


def test_list_members_includes_open_row(pg_session: Session) -> None:
    a = _asset(pg_session, "U_OPEN")
    _member(pg_session, a.id, "u1", dt.date(2026, 1, 1))
    rows = list_members(pg_session, "u1", dt.date(2026, 4, 1))
    assert len(rows) == 1
    assert rows[0][1].symbol == "U_OPEN"
    assert rows[0][0].end_date is None


def test_list_members_includes_closed_row_on_boundary(pg_session: Session) -> None:
    a = _asset(pg_session, "U_CLOSED_ON")
    _member(pg_session, a.id, "u1", dt.date(2025, 1, 1), end=dt.date(2026, 4, 1))
    # Inclusive on end_date
    rows = list_members(pg_session, "u1", dt.date(2026, 4, 1))
    assert len(rows) == 1


def test_list_members_excludes_before_start(pg_session: Session) -> None:
    a = _asset(pg_session, "U_FUT")
    _member(pg_session, a.id, "u1", dt.date(2026, 5, 1))
    rows = list_members(pg_session, "u1", dt.date(2026, 1, 1))
    assert rows == []


def test_list_members_excludes_after_end(pg_session: Session) -> None:
    a = _asset(pg_session, "U_END")
    _member(pg_session, a.id, "u1",
            dt.date(2025, 1, 1), end=dt.date(2025, 12, 31))
    rows = list_members(pg_session, "u1", dt.date(2026, 4, 1))
    assert rows == []


def test_list_members_filters_by_universe_name(pg_session: Session) -> None:
    a = _asset(pg_session, "U_OTHER")
    _member(pg_session, a.id, "u2", dt.date(2026, 1, 1))
    assert list_members(pg_session, "u1", dt.date(2026, 4, 1)) == []
    assert len(list_members(pg_session, "u2", dt.date(2026, 4, 1))) == 1


def test_list_members_sorted_by_symbol(pg_session: Session) -> None:
    a1 = _asset(pg_session, "U_BBB")
    a2 = _asset(pg_session, "U_AAA")
    _member(pg_session, a1.id, "u1", dt.date(2026, 1, 1))
    _member(pg_session, a2.id, "u1", dt.date(2026, 1, 1))
    rows = list_members(pg_session, "u1", dt.date(2026, 4, 1))
    assert [r[1].symbol for r in rows] == ["U_AAA", "U_BBB"]


def test_list_members_empty_universe(pg_session: Session) -> None:
    assert list_members(pg_session, "nonexistent", dt.date(2026, 4, 1)) == []


# ---------------------------------------------------------------------------
# is_member
# ---------------------------------------------------------------------------


def test_is_member_true_and_false(pg_session: Session) -> None:
    a = _asset(pg_session, "U_ISM")
    _member(pg_session, a.id, "u1", dt.date(2026, 1, 1))
    assert is_member(pg_session, "u1", a.id, dt.date(2026, 4, 1)) is True
    assert is_member(pg_session, "u1", a.id, dt.date(2025, 12, 1)) is False
    assert is_member(pg_session, "u-other", a.id, dt.date(2026, 4, 1)) is False


# ---------------------------------------------------------------------------
# Partial-unique index: one open row per (universe, asset)
# ---------------------------------------------------------------------------


def test_open_member_uniqueness_enforced(pg_session: Session) -> None:
    a = _asset(pg_session, "U_DUP")
    _member(pg_session, a.id, "u1", dt.date(2026, 1, 1))
    pg_session.add(UniverseMembership(
        universe_name="u1", asset_id=a.id,
        start_date=dt.date(2026, 2, 1), end_date=None,
    ))
    with pytest.raises(IntegrityError):
        pg_session.commit()
    pg_session.rollback()


def test_closed_row_allows_new_open_row(pg_session: Session) -> None:
    a = _asset(pg_session, "U_REOPEN")
    _member(pg_session, a.id, "u1",
            dt.date(2025, 1, 1), end=dt.date(2025, 12, 31))
    # Same (universe, asset) may have new open row once previous is closed
    _member(pg_session, a.id, "u1", dt.date(2026, 1, 1))
    rows = list_members(pg_session, "u1", dt.date(2026, 4, 1))
    assert len(rows) == 1


# ---------------------------------------------------------------------------
# /api/universe/{name} endpoint
# ---------------------------------------------------------------------------


def test_endpoint_returns_members_with_as_of(pg_session: Session) -> None:
    from apps.api.src.main import app

    a = _asset(pg_session, "U_EPT")
    _member(pg_session, a.id, "stock_swing_v1", dt.date(2026, 1, 1))

    client = TestClient(app)
    resp = client.get("/api/universe/stock_swing_v1?as_of=2026-04-01")
    assert resp.status_code == 200
    data = resp.json()
    assert data["universe_name"] == "stock_swing_v1"
    assert data["as_of"] == "2026-04-01"
    assert data["count"] == 1
    m = data["members"][0]
    assert m["symbol"] == "U_EPT"
    assert m["reason"] == "seeded"
    assert m["start_date"] == "2026-01-01"
    assert m["end_date"] is None
    assert m["asset_class"] == "equity"


def test_endpoint_empty_universe_returns_empty(pg_session: Session) -> None:
    from apps.api.src.main import app
    client = TestClient(app)
    resp = client.get("/api/universe/does-not-exist")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 0
    assert data["members"] == []


def test_endpoint_respects_as_of_boundary(pg_session: Session) -> None:
    from apps.api.src.main import app

    a = _asset(pg_session, "U_BOUND")
    _member(pg_session, a.id, "u1",
            dt.date(2025, 1, 1), end=dt.date(2025, 6, 30))

    client = TestClient(app)
    in_window = client.get("/api/universe/u1?as_of=2025-03-15").json()
    assert in_window["count"] == 1
    after = client.get("/api/universe/u1?as_of=2025-07-01").json()
    assert after["count"] == 0


def test_endpoint_defaults_to_today(pg_session: Session) -> None:
    from apps.api.src.main import app

    a = _asset(pg_session, "U_TODAY")
    _member(pg_session, a.id, "u1", dt.date(2020, 1, 1))  # open since 2020

    client = TestClient(app)
    resp = client.get("/api/universe/u1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] >= 1
    # as_of echoes today's date (ISO format)
    dt.date.fromisoformat(data["as_of"])
