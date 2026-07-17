"""Paper surface ownership and public-label regressions (PSEC-T1)."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request


def _request() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/", "headers": []})


class _Portfolio:
    def __init__(self, name: str, portfolio_id: str = "pid"):
        self.id = portfolio_id
        self.name = name
        self.starting_cash = Decimal("100")
        self.cash = Decimal("100")
        self.is_active = True
        self.created_at = None


@pytest.mark.parametrize("uid,name,write,status", [
    (None, "user:me:stock", False, 404),
    ("me", "user:other:stock", False, 404),
    ("me", "user:other:stock", True, 404),
    ("me", "user:me:stock", False, 200),
    ("me", "user:me:stock", True, 200),
    ("me", "Replay Recovery Account", False, 200),
    ("me", "Replay Recovery Account", True, 404),
])
def test_legacy_paper_per_id_gate(monkeypatch, uid, name, write, status):
    from apps.api.src.api import paper

    portfolio = _Portfolio(name)
    monkeypatch.setattr(paper, "get_portfolio", lambda *_: portfolio)
    monkeypatch.setattr(paper, "resolve_identity", lambda *_: uid)
    monkeypatch.setattr(paper, "_request_is_owner", lambda *_: False)
    if status == 404:
        with pytest.raises(HTTPException) as exc:
            paper._require_portfolio_access(_request(), object(), "pid", write=write)
        assert exc.value.status_code == 404
    else:
        assert paper._require_portfolio_access(_request(), object(), "pid", write=write) is portfolio


def test_legacy_paper_list_create_are_owner_only(monkeypatch):
    from apps.api.src.api import paper

    monkeypatch.setattr(paper, "_request_is_owner", lambda *_: False)
    with pytest.raises(HTTPException) as exc:
        paper._require_owner(_request(), object())
    assert exc.value.status_code == 404

    monkeypatch.setattr(paper, "_request_is_owner", lambda *_: True)
    assert paper._require_owner(_request(), object()) is None


def test_legacy_paper_owner_has_full_per_id_access(monkeypatch):
    from apps.api.src.api import paper

    portfolio = _Portfolio("user:other:stock")
    monkeypatch.setattr(paper, "get_portfolio", lambda *_: portfolio)
    monkeypatch.setattr(paper, "resolve_identity", lambda *_: "owner")
    monkeypatch.setattr(paper, "_request_is_owner", lambda *_: True)
    assert paper._require_portfolio_access(_request(), object(), "pid", write=False) is portfolio
    assert paper._require_portfolio_access(_request(), object(), "pid", write=True) is portfolio


def test_public_user_book_label_is_safe_for_non_owner_and_raw_for_owner():
    from apps.api.src.domain.paper_trading.paper_service import public_book_label

    raw = "user:private-user-id:stock"
    assert public_book_label(raw, is_owner=False) == "Your practice book"
    assert "user:" not in public_book_label(raw, is_owner=False)
    assert public_book_label(raw, is_owner=True) == raw


def test_paper_summary_redacts_user_book_name_for_non_owner():
    from apps.api.src.api.paper import _portfolio_summary

    portfolio = _Portfolio("user:private-user-id:stock")
    breakdown = {
        "cash": Decimal("100"), "positions_value": Decimal("0"),
        "total_equity": Decimal("100"), "unrealized_pnl": Decimal("0"),
        "realized_pnl_cumulative": Decimal("0"),
    }
    public = _portfolio_summary(portfolio, breakdown, request_is_owner=False)
    owner = _portfolio_summary(portfolio, breakdown, request_is_owner=True)
    assert public["name"] == "Your practice book"
    assert "user:" not in str(public)
    assert owner["name"] == "user:private-user-id:stock"


def test_live_nav_hides_user_books_for_non_owner_and_keeps_them_for_owner():
    from apps.api.src.api.paper_live import _public_live_nav_payload

    payload = {
        "n_portfolios_active": 2,
        "portfolios": [
            {"id": "demo", "name": "Replay Recovery Account"},
            {"id": "user", "name": "user:private-user-id:stock"},
        ],
    }
    public = _public_live_nav_payload(payload, request_is_owner=False)
    owner = _public_live_nav_payload(payload, request_is_owner=True)
    assert "user:" not in str(public)
    assert public["n_portfolios_active"] == 1
    assert public["portfolios"][0]["name"] == "Demo book"
    assert "user:private-user-id:stock" in str(owner)


class _Result:
    def __init__(self, *, rows=None, scalar=0, first=None):
        self.rows = rows or []
        self.value = scalar
        self.first_value = first

    def mappings(self):
        return self

    def all(self):
        return self.rows

    def fetchall(self):
        return self.rows

    def scalar(self):
        return self.value

    def first(self):
        return self.first_value


class _RiskDb:
    def __init__(self, owner: bool):
        self.owner = owner
        self.sql: list[str] = []
        self.snap_rows = [
            {"portfolio_id": "demo", "portfolio_name": "Replay Recovery Account",
             "snapshot_date": dt.date(2026, 7, 16), "total_equity": Decimal("100"),
             "cash": Decimal("100"), "positions_value": Decimal("0"),
             "unrealized_pnl": Decimal("0"), "realized_pnl_cumulative": Decimal("0")},
            {"portfolio_id": "user", "portfolio_name": "user:private-user-id:stock",
             "snapshot_date": dt.date(2026, 7, 16), "total_equity": Decimal("100"),
             "cash": Decimal("100"), "positions_value": Decimal("0"),
             "unrealized_pnl": Decimal("0"), "realized_pnl_cumulative": Decimal("0")},
        ]

    def execute(self, statement, *_args, **_kwargs):
        sql = str(statement)
        self.sql.append(sql)
        if "SELECT DISTINCT ON (s.portfolio_id)" in sql:
            return _Result(rows=self.snap_rows)
        if "p.id AS portfolio_id, p.name AS portfolio_name" in sql:
            selected = self.snap_rows if self.owner else self.snap_rows[:1]
            rows = [
                {**r, "n_open": 0, "notional_usd": Decimal("0")}
                for r in selected
            ]
            return _Result(rows=rows)
        return _Result()


def test_risk_dashboard_filters_and_redacts_user_books(monkeypatch):
    from apps.api.src.api import performance_paper as mod

    public_db = _RiskDb(owner=False)
    monkeypatch.setattr(mod, "_request_is_owner", lambda *_: False)
    public = mod.paper_risk_dashboard(_request(), public_db)
    assert "user:" not in str(public)
    assert any("p.name NOT LIKE 'user:%'" in sql for sql in public_db.sql)

    owner_db = _RiskDb(owner=True)
    monkeypatch.setattr(mod, "_request_is_owner", lambda *_: True)
    owner = mod.paper_risk_dashboard(_request(), owner_db)
    assert "user:private-user-id:stock" in str(owner)

def test_owner_elevation_ignores_device_header_without_session(monkeypatch):
    from apps.api.src.api import paper

    request = Request({
        "type": "http", "method": "GET", "path": "/",
        "headers": [(b"x-auth-user-id", b"owner")],
    })
    monkeypatch.setattr(paper.ident, "session_user_id", lambda *_: None)
    monkeypatch.setattr(paper, "resolve_identity", lambda *_: "owner")
    assert paper._request_is_owner(request, object()) is False


class _ForeignFunnelDb:
    def execute(self, *_args, **_kwargs):
        return _Result(scalar="user:other:stock")


def test_funnel_by_portfolio_hides_foreign_user_book(monkeypatch):
    from apps.api.src.api import paper_funnel

    monkeypatch.setattr(paper_funnel, "_request_is_owner", lambda *_: False)
    monkeypatch.setattr(paper_funnel, "resolve_identity", lambda *_: "me")
    with pytest.raises(HTTPException) as exc:
        paper_funnel._require_readable_portfolio(_request(), _ForeignFunnelDb(), "foreign")
    assert exc.value.status_code == 404
    assert exc.value.detail == "Not Found"


class _EquityDb:
    def __init__(self):
        self.names = {
            "foreign": "user:other:stock",
            "demo": "Replay Recovery Account",
            "own": "user:me:stock",
        }

    def execute(self, statement, params=None):
        if "SELECT name FROM paper_portfolio" in str(statement):
            return _Result(scalar=self.names.get(params["pid"]))
        return _Result(rows=[])


def test_operator_equity_scopes_user_books(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from apps.api.src.api import operator

    app = FastAPI()
    app.include_router(operator.router)
    app.dependency_overrides[operator.get_session] = lambda: _EquityDb()
    client = TestClient(app)

    monkeypatch.setattr(operator, "_request_is_owner", lambda *_: False)
    monkeypatch.setattr(operator, "resolve_identity", lambda *_: None)
    foreign = client.get("/paper/equity?portfolio_id=foreign")
    assert foreign.status_code == 404
    assert foreign.json() == {"detail": "Not Found"}
    assert client.get("/paper/equity?portfolio_id=demo").status_code == 200

    monkeypatch.setattr(operator, "resolve_identity", lambda *_: "me")
    assert client.get("/paper/equity?portfolio_id=own").status_code == 200

    monkeypatch.setattr(operator, "_request_is_owner", lambda *_: True)
    assert client.get("/paper/equity?portfolio_id=foreign").status_code == 200
