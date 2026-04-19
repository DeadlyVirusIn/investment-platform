"""Postgres integration-test harness via testcontainers.

Session-scoped container + engine; per-test TRUNCATE to keep data isolated.
Run with:
    pytest -m integration apps/api/tests/integration/
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from apps.api.src.db import Base
import apps.api.src.db.models  # noqa: F401 — register ORM classes on Base.metadata

# Mark every test in this dir as integration so it's only run on demand
pytestmark = pytest.mark.integration


@pytest.fixture(scope="session")
def pg_url() -> Iterator[str]:
    """Provide a Postgres URL for integration tests.

    If TEST_DATABASE_URL is set in the environment, use it directly (fast path
    for developers running tests against an existing Postgres container).
    Otherwise, spin up a throwaway Postgres via testcontainers.
    """
    override = os.environ.get("TEST_DATABASE_URL")
    if override:
        yield override
        return

    from testcontainers.postgres import PostgresContainer

    container = PostgresContainer("postgres:17-alpine")
    container.start()
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
    engine = create_engine(pg_url, pool_pre_ping=True, future=True)
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
