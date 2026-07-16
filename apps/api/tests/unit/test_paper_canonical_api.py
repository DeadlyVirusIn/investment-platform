"""Practice P&L explainability — /paper/canonical/stock contract tests.

Pins the daily_pnl basis (P6D Practice fix): daily_pnl is the equity delta vs
the prior live snapshot, and `daily_pnl_prior_snapshot_date` exposes the date
it is measured against so the Practice page can label the headline honestly
(it is a "since <date>" delta — possibly multi-day — not a same-day mark).
Read-only / GET-only.
"""

from __future__ import annotations

import re
import pytest
from pathlib import Path


def test_module_imports():
    import apps.api.src.api.paper_canonical as mod  # noqa: F401


def test_router_is_get_only():
    import apps.api.src.api.paper_canonical as mod
    bad: list[str] = []
    for r in mod.router.routes:
        for m in (getattr(r, "methods", set()) or set()):
            if m.upper() not in ("GET", "HEAD", "OPTIONS"):
                bad.append(f"{r.path} -> {m}")
    assert not bad, f"non-GET methods registered: {bad}"


def test_daily_pnl_basis_keys_pinned_in_source():
    """The Practice page reconciliation block depends on these keys."""
    src = Path(
        "apps/api/src/api/paper_canonical.py"
    ).read_text(encoding="utf-8")
    for key in (
        '"daily_pnl"',
        '"daily_pnl_prior_snapshot_date"',
        '"unrealized_pnl"',
        '"as_of"',
    ):
        assert key in src, f"canonical response missing key: {key}"


def test_daily_pnl_is_snapshot_delta_not_mark_to_market():
    """Guard the documented semantics: daily_pnl = nav - prior snapshot equity,
    measured against snapshot_date (not an intraday mark)."""
    src = Path(
        "apps/api/src/api/paper_canonical.py"
    ).read_text(encoding="utf-8")
    assert "nav - float(prev_row.total_equity)" in src
    assert "daily_pnl_prior_snapshot_date" in src


def test_snapshot_reads_have_id_tiebreaker():
    """P6D.35A — every latest/prior snapshot ORDER BY must end with id DESC so
    duplicate (portfolio, date, source) rows with equal recorded_at resolve
    deterministically."""
    src = Path(
        "apps/api/src/api/paper_canonical.py"
    ).read_text(encoding="utf-8")
    assert src.count(
        "ORDER BY snapshot_date DESC, recorded_at DESC, id DESC"
    ) == 2, "both canonical snapshot reads need the id DESC tiebreaker"
    # No un-tiebroken recorded_at ordering remains anywhere in the module.
    assert src.count("recorded_at DESC") == src.count(
        "recorded_at DESC, id DESC"
    )


def test_no_writes_in_source():
    src = Path(
        "apps/api/src/api/paper_canonical.py"
    ).read_text(encoding="utf-8")
    for pat in (
        r"\bINSERT\s+INTO\b", r"\bUPDATE\s+\w+\s+SET\b", r"\bDELETE\s+FROM\b",
    ):
        assert not re.search(pat, src, re.IGNORECASE), (
            f"write found in read-only endpoint: {pat}"
        )


def test_book_scope_is_returned_for_both_canonical_stock_branches():
    src = Path("apps/api/src/api/paper_canonical.py").read_text(encoding="utf-8")
    assert src.count('"book_scope": "user" if uid else "shared_demo"') == 2

class _CanonicalResult:
    def __init__(self, first=None, scalar=0):
        self._first, self._scalar = first, scalar
    def first(self): return self._first
    def scalar(self): return self._scalar


class _CanonicalDb:
    def __init__(self): self.calls = 0
    def commit(self): pass
    def execute(self, *_args, **_kwargs):
        self.calls += 1
        if self.calls == 1:
            from types import SimpleNamespace
            return _CanonicalResult(SimpleNamespace(name="book", starting_cash=100000))
        if self.calls == 2:
            return _CanonicalResult(None)
        return _CanonicalResult()


@pytest.mark.parametrize("uid,scope", [(None, "shared_demo"), ("user-id", "user")])
def test_canonical_stock_returns_book_scope(monkeypatch, uid, scope):
    import apps.api.src.api.paper_canonical as mod
    from starlette.requests import Request
    monkeypatch.setattr(mod, "resolve_identity", lambda *_: uid)
    monkeypatch.setattr(mod, "resolve_user_stock_portfolio", lambda *_: "user-pid")
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
    assert mod.canonical_stock(request, _CanonicalDb())["book_scope"] == scope
