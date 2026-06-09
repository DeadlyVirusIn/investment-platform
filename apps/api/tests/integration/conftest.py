"""Postgres integration-test harness via testcontainers.

Session-scoped container + engine; per-test TRUNCATE to keep data isolated.
Run with:
    pytest -m integration apps/api/tests/integration/

SAFETY (Phase 11Z incident response):
  The session fixture below runs `Base.metadata.drop_all` + `create_all`
  unconditionally. Pointing `TEST_DATABASE_URL` at the dev/working db
  destroys ORM-tracked rows. We now refuse to run unless the URL clearly
  identifies a test database — see `_assert_test_database_url`.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import Session, sessionmaker

from apps.api.src.db import Base
import apps.api.src.db.models  # noqa: F401 — register ORM classes on Base.metadata

# Mark every test in this dir as integration so it's only run on demand
pytestmark = pytest.mark.integration


# --------------------------------------------------------------------------
# Phase 11Z incident-response safety guard.
# --------------------------------------------------------------------------
# Hosts that the integration harness is NEVER allowed to run against,
# even via TEST_DATABASE_URL — these point at the running dev/working
# Postgres container behind compose-api-1 / compose-worker-tickloop-1.
_FORBIDDEN_HOSTS: tuple[str, ...] = ("db", "compose-db-1", "compose-db")
# Real production hostnames could be added here over time.
_FORBIDDEN_DB_NAMES: tuple[str, ...] = (
    "investment_platform",   # dev/working db
    "investment_platform_prod",
    "production",
    "prod",
)
# Safe-to-write opt-in. Setting `INTEGRATION_DB_ALLOW_UNSAFE=1` AND
# the test db name still has to look like a test db. This exists so
# CI can override host checks on private runners but cannot override
# the test-name check.
_UNSAFE_OPT_IN_ENV = "INTEGRATION_DB_ALLOW_UNSAFE"


class UnsafeIntegrationDatabaseError(RuntimeError):
    """Raised when TEST_DATABASE_URL points at something that is
    plausibly a real (non-test) database. The integration harness
    drops every ORM-tracked table on session start; running against a
    real DB would destroy data. Hard-fail before any DDL runs."""


def _normalize_url_for_compare(url: str) -> str | None:
    """Return host+port+db tuple as a single comparable string.
    Used to detect the case where TEST_DATABASE_URL points at the
    same connection target as DATABASE_URL — that's the exact
    Phase 11Z incident pattern even if the db name now happens to
    contain 'test'."""
    try:
        u = make_url(url)
    except Exception:  # noqa: BLE001
        return None
    return f"{(u.host or '').lower()}:{u.port or ''}:{(u.database or '').lower()}"


def _assert_test_database_url(url: str) -> None:
    """Phase 11Z guard. Raises if the URL doesn't look like a
    dedicated test database. Rules (incident response — fail-closed):
      * Database name MUST contain the substring 'test' OR
        'integration' (case-insensitive). Names like
        `investment_platform_test` or `app_integration_test` pass;
        `investment_platform` fails.
      * Database name MUST NOT exactly match any of the
        production/dev names in `_FORBIDDEN_DB_NAMES`.
      * Host MUST NOT be in `_FORBIDDEN_HOSTS` unless the explicit
        opt-in env is set.
      * If `DATABASE_URL` is set in the environment, the
        host+port+db tuple of TEST_DATABASE_URL MUST differ from
        DATABASE_URL. This catches the case where someone copies
        the prod/dev URL into TEST_DATABASE_URL with only cosmetic
        changes — the exact incident pattern.
      * Host strings that are well-known production indicators
        (contain 'prod' or 'production') are rejected outright.
    """
    try:
        parsed = make_url(url)
    except Exception as exc:  # noqa: BLE001
        raise UnsafeIntegrationDatabaseError(
            f"TEST_DATABASE_URL is not a valid SQLAlchemy URL: {exc}"
        ) from exc
    db_name = parsed.database or ""
    host = parsed.host or ""

    if db_name.lower() in _FORBIDDEN_DB_NAMES:
        raise UnsafeIntegrationDatabaseError(
            f"TEST_DATABASE_URL database='{db_name}' is on the "
            f"forbidden list {_FORBIDDEN_DB_NAMES}. The integration "
            f"harness drops every ORM table on session start and "
            f"would destroy real data. Use a dedicated test database "
            f"(name containing 'test' or 'integration')."
        )
    if not re.search(r"(test|integration)", db_name, flags=re.IGNORECASE):
        raise UnsafeIntegrationDatabaseError(
            f"TEST_DATABASE_URL database='{db_name}' does not look "
            f"like a test database. The integration harness drops "
            f"every ORM table on session start. Set the URL to a DB "
            f"whose name contains 'test' or 'integration', or unset "
            f"TEST_DATABASE_URL to spin up an ephemeral testcontainer."
        )
    if re.search(r"(prod|production)", host, flags=re.IGNORECASE):
        raise UnsafeIntegrationDatabaseError(
            f"TEST_DATABASE_URL host='{host}' looks like a "
            f"production host. Refusing to run integration tests."
        )
    if (
        host in _FORBIDDEN_HOSTS
        and os.environ.get(_UNSAFE_OPT_IN_ENV, "").strip() != "1"
    ):
        raise UnsafeIntegrationDatabaseError(
            f"TEST_DATABASE_URL host='{host}' is the dev/compose "
            f"Postgres container. Even when the database name "
            f"contains 'test', this is too close to the working DB. "
            f"Run on a separate Postgres or set "
            f"{_UNSAFE_OPT_IN_ENV}=1 if you understand the risk."
        )

    # Cross-check vs DATABASE_URL: refuse identical host+port+db
    # tuples even when the db name contains 'test'. This catches
    # cosmetic-only renames of the production/dev URL.
    prod_url = os.environ.get("DATABASE_URL", "").strip()
    if prod_url:
        prod_norm = _normalize_url_for_compare(prod_url)
        test_norm = _normalize_url_for_compare(url)
        if prod_norm and test_norm and prod_norm == test_norm:
            raise UnsafeIntegrationDatabaseError(
                f"TEST_DATABASE_URL and DATABASE_URL point at the "
                f"same connection target ({test_norm}). Integration "
                f"harness would destroy the dev/prod database. Set "
                f"TEST_DATABASE_URL to a different host/port/db."
            )


@pytest.fixture(scope="session")
def pg_url() -> Iterator[str]:
    """Provide a Postgres URL for integration tests.

    If TEST_DATABASE_URL is set, validate it via the Phase 11Z safety
    guard before yielding. Otherwise, spin up a throwaway Postgres via
    testcontainers (always safe — ephemeral).
    """
    override = os.environ.get("TEST_DATABASE_URL")
    if override:
        _assert_test_database_url(override)
        yield override
        return

    # Graceful skip when Docker / testcontainers is unavailable (local dev
    # without a Docker daemon, or a CI runner without Docker). CI runners that
    # have Docker run these normally; everyone else skips intentionally instead
    # of erroring on collection.
    try:
        from testcontainers.postgres import PostgresContainer
    except ImportError:  # pragma: no cover
        pytest.skip(
            "testcontainers not installed — skipping integration tests",
            allow_module_level=True,
        )

    container = PostgresContainer("postgres:17-alpine")
    try:
        container.start()
    except Exception as exc:  # noqa: BLE001 — Docker daemon unavailable
        pytest.skip(f"Docker unavailable for testcontainers: {exc}")
    try:
        try:
            url = container.get_connection_url(driver="psycopg")
        except TypeError:
            url = container.get_connection_url()
            url = url.replace("postgresql+psycopg2://", "postgresql+psycopg://")
            if "+psycopg" not in url:
                url = url.replace("postgresql://", "postgresql+psycopg://")
        yield url
    finally:
        container.stop()


@pytest.fixture(scope="session")
def pg_engine(pg_url: str) -> Iterator[Engine]:
    """Session-scoped engine. Drops + recreates schema to match current models.

    Note: any data in the target database will be destroyed at session start.
    This is intentional — integration tests require a deterministic starting
    schema and expect a dedicated (or disposable) database.
    """
    engine = create_engine(pg_url, pool_pre_ping=True, future=True)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def pg_session(pg_engine: Engine) -> Iterator[Session]:
    SessionCls = sessionmaker(bind=pg_engine, class_=Session, expire_on_commit=False)
    session = SessionCls()
    try:
        yield session
    finally:
        session.close()
        with pg_engine.begin() as conn:
            table_names = ", ".join(
                f'"{t.name}"' for t in reversed(Base.metadata.sorted_tables)
            )
            conn.execute(text(f"TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE"))
