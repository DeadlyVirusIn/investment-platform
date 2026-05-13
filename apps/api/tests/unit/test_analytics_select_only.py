"""Phase 6b-1 — discipline test: analytics_queries.py is SELECT-only.

Static-analysis test that grep-verifies the analytics module has no
mutation paths. Catches regressions where someone adds INSERT/UPDATE/
DELETE/MERGE/TRUNCATE inside an analytics handler.
"""

from __future__ import annotations

import re
from pathlib import Path


_FILES = [
    "apps/api/src/options/analytics_queries.py",
    "apps/api/src/options/routes_analytics.py",
]

# Forbidden tokens (case-insensitive). Any literal SQL fragment OR
# Python ORM mutation API in these files fails the test.
_FORBIDDEN_SQL = [
    "INSERT INTO", "UPDATE ", "DELETE FROM",
    "MERGE INTO", "TRUNCATE ",
    "DROP TABLE", "ALTER TABLE",
    "CREATE TABLE", "CREATE INDEX",
]
_FORBIDDEN_ORM = [
    "session.add(", "session.merge(", "session.commit(",
    "session.flush(", "session.delete(", ".bulk_insert",
    ".bulk_update",
]
_FORBIDDEN_HTTP = [
    '@router.post(', '@router.put(', '@router.patch(',
    '@router.delete(',
]


def _read(rel: str) -> str:
    # apps/api/tests/unit/test_X.py → repo root is parents[4]
    base = Path(__file__).resolve().parents[4]
    return (base / rel).read_text(encoding="utf-8")


def test_analytics_queries_no_mutation_sql():
    src = _read("apps/api/src/options/analytics_queries.py")
    upper = src.upper()
    for kw in _FORBIDDEN_SQL:
        assert kw.upper() not in upper, (
            f"forbidden SQL keyword present in analytics_queries.py: {kw!r}")


def test_analytics_queries_no_orm_mutation_calls():
    src = _read("apps/api/src/options/analytics_queries.py")
    for needle in _FORBIDDEN_ORM:
        assert needle not in src, (
            f"forbidden ORM mutation call in analytics_queries.py: {needle!r}")


def test_routes_analytics_only_get_decorators():
    src = _read("apps/api/src/options/routes_analytics.py")
    for needle in _FORBIDDEN_HTTP:
        assert needle not in src, (
            f"non-GET HTTP decorator in routes_analytics.py: {needle!r}")
    # at least one @router.get must exist (sanity)
    assert "@router.get(" in src


def test_routes_analytics_no_mutation_sql():
    src = _read("apps/api/src/options/routes_analytics.py")
    upper = src.upper()
    for kw in _FORBIDDEN_SQL:
        assert kw.upper() not in upper, (
            f"forbidden SQL keyword in routes_analytics.py: {kw!r}")


def test_routes_analytics_no_orm_mutation():
    src = _read("apps/api/src/options/routes_analytics.py")
    for needle in _FORBIDDEN_ORM:
        assert needle not in src, (
            f"forbidden ORM mutation call in routes_analytics.py: {needle!r}")
