"""Practice P&L explainability — /paper/canonical/stock contract tests.

Pins the daily_pnl basis (P6D Practice fix): daily_pnl is the equity delta vs
the prior live snapshot, and `daily_pnl_prior_snapshot_date` exposes the date
it is measured against so the Practice page can label the headline honestly
(it is a "since <date>" delta — possibly multi-day — not a same-day mark).
Read-only / GET-only.
"""

from __future__ import annotations

import re
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
