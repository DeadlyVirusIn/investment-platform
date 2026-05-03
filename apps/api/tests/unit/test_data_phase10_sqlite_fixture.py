"""Shared SQLite-in-memory fixture for Phase 10 SQL-backed tests.

Uses a temp SQLite DB + sqlalchemy create_all() — avoids coupling to
Postgres for fast unit tests. JSONB columns are handled via the
`JSON().with_variant(JSONB, 'postgresql')` pattern already in models.py.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from apps.api.src.db import Base
# Ensure all ORM models are registered on Base.metadata
from apps.api.src.db import models  # noqa: F401


@pytest.fixture
def sqlite_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = Session(bind=engine, autoflush=False, future=True)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
