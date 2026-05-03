"""Phase 11Z — /api/paper/executed/* endpoint contract tests.

Pins:
  1. Module imports without DB.
  2. Endpoints are GET-only (no POST/PUT/DELETE/PATCH on the router).
  3. include_replay defaults to False.
  4. Source code has no INSERT/UPDATE/DELETE statements (read-only).
  5. _exclusion_clause refuses unknown entity types and bad aliases.
  6. _exclusion_clause returns empty when include_replay=True.
  7. _exclusion_clause returns NOT EXISTS fragment when False.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


def test_module_imports():
    import apps.api.src.api.paper_executed as mod  # noqa: F401


def test_router_is_get_only():
    import apps.api.src.api.paper_executed as mod
    bad: list[str] = []
    for r in mod.router.routes:
        methods = getattr(r, "methods", set()) or set()
        for m in methods:
            if m.upper() not in ("GET", "HEAD", "OPTIONS"):
                bad.append(f"{r.path} -> {m}")
    assert not bad, f"non-GET methods registered: {bad}"


def test_router_paths_pinned():
    import apps.api.src.api.paper_executed as mod
    paths = sorted(getattr(r, "path", "") for r in mod.router.routes)
    must_have = (
        "/paper/executed/summary",
        "/paper/executed/trades",
        "/paper/executed/positions",
    )
    for p in must_have:
        assert p in paths, f"missing route: {p}; have {paths}"


def test_no_writes_in_source():
    src = Path(
        "apps/api/src/api/paper_executed.py"
    ).read_text(encoding="utf-8")
    write_patterns = (
        re.compile(r"\bINSERT\s+INTO\b", re.IGNORECASE),
        re.compile(r"\bUPDATE\s+\w+\s+SET\b", re.IGNORECASE),
        re.compile(r"\bDELETE\s+FROM\b", re.IGNORECASE),
    )
    for line in src.splitlines():
        stripped = line.lstrip()
        if (stripped.startswith('"') or stripped.startswith("#")
                or stripped.startswith("'")):
            continue
        for pat in write_patterns:
            assert not pat.search(line), (
                f"write found in read-only endpoint: {line.strip()}"
            )


def test_exclusion_clause_rejects_unknown_entity_type():
    from apps.api.src.api.paper_executed import _exclusion_clause
    with pytest.raises(ValueError):
        _exclusion_clause(False, "orders", "o")


def test_exclusion_clause_rejects_bad_alias():
    from apps.api.src.api.paper_executed import _exclusion_clause
    with pytest.raises(ValueError):
        _exclusion_clause(False, "paper_trade", "pt; DROP TABLE x;")


def test_exclusion_clause_empty_when_include_replay_true():
    from apps.api.src.api.paper_executed import _exclusion_clause
    assert _exclusion_clause(True, "paper_trade", "pt") == ""


def test_exclusion_clause_uses_not_exists_pattern():
    from apps.api.src.api.paper_executed import _exclusion_clause
    sql = _exclusion_clause(False, "paper_trade", "pt")
    assert "NOT EXISTS" in sql
    assert "replay_recovery_manifest" in sql
    assert "pt.id::text" in sql
    assert "'replay'" in sql and "'test'" in sql


def test_response_schema_pinned_in_source():
    """Pin the keys returned by /summary so the WebUI hooks stay in sync."""
    src = Path(
        "apps/api/src/api/paper_executed.py"
    ).read_text(encoding="utf-8")
    # Required keys in summary response.
    for key in (
        '"trades_total"', '"open_positions"', '"distinct_symbols"',
        '"has_replay_recovered_rows"', '"include_replay"',
    ):
        assert key in src, f"summary response missing key: {key}"
    # Trade row keys.
    for key in (
        '"trade_id"', '"symbol"', '"fill_price"', '"notional_usd"',
        '"source"', '"replay_run_id"',
    ):
        assert key in src, f"trade response missing key: {key}"


def test_no_post_added_to_paper_executed():
    src = Path(
        "apps/api/src/api/paper_executed.py"
    ).read_text(encoding="utf-8")
    forbidden = ("@router.post", "@router.put", "@router.delete",
                  "@router.patch")
    for f in forbidden:
        assert f not in src, f"forbidden HTTP verb: {f}"
