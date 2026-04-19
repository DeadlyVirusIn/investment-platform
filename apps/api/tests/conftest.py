"""Pytest fixtures for the API test suite – Phase 0 placeholders."""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# TODO Phase 1: replace with a real async test DB session using
# pytest-asyncio + SQLAlchemy async engine pointed at a test database.
# ---------------------------------------------------------------------------

@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
