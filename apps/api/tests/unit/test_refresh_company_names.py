"""Unit tests for the Phase-2 company-name refresh job + its registration.

Pure (no DB / no network): asserts the job is wired into the worker registry
and that it degrades gracefully (no DB touch) when Polygon is unavailable.
"""

from __future__ import annotations

import asyncio


def test_refresh_company_names_registered() -> None:
    from apps.worker.src.jobs.registry import REGISTRY

    assert "refresh_company_names" in REGISTRY
    assert callable(REGISTRY["refresh_company_names"])
    assert REGISTRY["refresh_company_names"].__name__ == "refresh_company_names"


def test_refresh_company_names_skips_without_key(monkeypatch) -> None:
    """When POLYGON_API_KEY is absent the job must return early — never
    open a DB session or call the network."""
    from apps.api.src.providers import polygon
    from apps.worker.src.jobs import refresh_company_names as job

    monkeypatch.setattr(polygon, "is_available", lambda: False)

    called = {"session": False, "map": False}

    def _boom_session(*a, **k):  # pragma: no cover - must not run
        called["session"] = True
        raise AssertionError("SessionLocal must not be used without a key")

    def _boom_map(*a, **k):  # pragma: no cover - must not run
        called["map"] = True
        raise AssertionError("fetch_ticker_name_map must not run without a key")

    monkeypatch.setattr("apps.api.src.db.SessionLocal", _boom_session, raising=False)
    monkeypatch.setattr(polygon, "fetch_ticker_name_map", _boom_map)

    # Should complete without raising and without touching DB / network.
    asyncio.run(job.refresh_company_names())
    assert called == {"session": False, "map": False}
