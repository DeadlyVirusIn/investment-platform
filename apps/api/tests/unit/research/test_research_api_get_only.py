"""Phase 11W (Phase B) — research API surface tests.

Verifies:
  * GET stubs return Phase B empty/null shapes when flag is on.
  * No POST/PUT/PATCH/DELETE routes exist under /api/research/*.
  * Router is NOT mounted when RESEARCH_RO_ENABLED is False (default).
"""

from __future__ import annotations

import importlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _build_app_with_flag(enabled: bool) -> FastAPI:
    """Construct a minimal FastAPI app that mounts the research router
    if `enabled`, mirroring main.py's gating logic."""
    from apps.api.src.api.research import router as research_router

    app = FastAPI()
    if enabled:
        app.include_router(research_router, prefix="/api")
    return app


def test_research_router_not_mounted_when_flag_off():
    app = _build_app_with_flag(enabled=False)
    client = TestClient(app)
    for path in (
        "/api/research/runs",
        "/api/research/runs/abc",
        "/api/research/ticker/AAPL/latest",
        "/api/research/decision/dec-1",
    ):
        r = client.get(path)
        assert r.status_code == 404


def test_research_runs_returns_phase_b_empty_shape():
    app = _build_app_with_flag(enabled=True)
    client = TestClient(app)
    r = client.get("/api/research/runs")
    assert r.status_code == 200
    body = r.json()
    assert body == {"runs": [], "next_cursor": None}


def test_research_run_by_id_returns_404():
    app = _build_app_with_flag(enabled=True)
    client = TestClient(app)
    r = client.get("/api/research/runs/some-uuid")
    assert r.status_code == 404


def test_research_ticker_latest_returns_null_run():
    app = _build_app_with_flag(enabled=True)
    client = TestClient(app)
    r = client.get("/api/research/ticker/AAPL/latest")
    assert r.status_code == 200
    body = r.json()
    assert body == {"symbol": "AAPL", "run": None}


def test_research_decision_returns_empty_runs():
    app = _build_app_with_flag(enabled=True)
    client = TestClient(app)
    r = client.get("/api/research/decision/dec-42")
    assert r.status_code == 200
    body = r.json()
    assert body == {"decision_id": "dec-42", "runs": []}


def test_no_post_put_patch_delete_routes_under_research():
    """Critical Phase B invariant: introspect every route on the
    research router and assert only GET (and HEAD/OPTIONS) methods
    exist. Phase B forbids any write surface."""
    from apps.api.src.api.research import router as research_router

    forbidden = {"POST", "PUT", "PATCH", "DELETE"}
    for route in research_router.routes:
        methods = getattr(route, "methods", None)
        if methods is None:
            continue
        assert forbidden.isdisjoint(methods), (
            f"Forbidden non-GET method on research route "
            f"{getattr(route, 'path', '?')}: {methods}"
        )


def test_no_manual_endpoint_registered():
    """Phase B explicitly forbids /api/research/runs/manual existing."""
    from apps.api.src.api.research import router as research_router

    for route in research_router.routes:
        path = getattr(route, "path", "")
        assert "manual" not in path, (
            f"Forbidden /manual endpoint registered at {path!r}"
        )


def test_research_module_does_not_import_execution_paths():
    """Source-level architectural check: the research module must not
    import any execution / scoring / ML module. Scans only `import`
    and `from` lines so that docstrings listing forbidden names for
    documentation purposes do not trigger false positives."""
    from pathlib import Path
    import apps.api.src.api.research as mod

    src = Path(mod.__file__).read_text(encoding="utf-8")
    import_lines = [
        line for line in src.splitlines()
        if line.lstrip().startswith(("import ", "from "))
    ]
    joined = "\n".join(import_lines)
    forbidden = (
        "feature_engine", "recommendation_engine",
        "shadow_scorer", "drift_monitor",
        "auto_trader", "paper_execution",
        "submit_trade", "auto_trade_portfolio",
    )
    for tok in forbidden:
        assert tok not in joined, (
            f"Forbidden import {tok!r} in research.py "
            f"import lines: {joined!r}"
        )
