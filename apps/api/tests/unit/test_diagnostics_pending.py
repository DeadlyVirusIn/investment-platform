"""Phase 11Q - "Pending T+1 Decisions" diagnostic tests.

Read-only API contract + boundary scans. NEVER triggers fills.
NEVER mutates DB.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.src.api import diagnostics_pending as dp_mod
from apps.api.src.api.diagnostics_pending import (
    DEFAULT_LOOKBACK_DAYS,
    EXPECTED_FILL_OFFSET_DAYS,
    FILL_STATUS,
    MAX_LOOKBACK_DAYS,
    SKIP_REASON_REGEX,
    SKIPS_DIR,
    _expected_fill_run_utc,
    _next_ingest_eta_utc,
    _read_skip_lines,
    router,
)


REPO_ROOT = Path(__file__).resolve().parents[4]


def _build_app(session_factory=None) -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    if session_factory is not None:
        from apps.api.src.db import get_session

        def _override():
            with session_factory() as s:
                yield s

        app.dependency_overrides[get_session] = _override
    return app


# ---------------------------------------------------------------------------
# Pure-fn helpers
# ---------------------------------------------------------------------------

def test_frozen_constants():
    assert DEFAULT_LOOKBACK_DAYS == 5
    assert MAX_LOOKBACK_DAYS == 30
    assert EXPECTED_FILL_OFFSET_DAYS == 1
    assert FILL_STATUS == "waiting_for_next_bar"
    assert SKIP_REASON_REGEX == r"no price bar available after submitted_at"


def test_expected_fill_run_is_t_plus_one():
    out = _expected_fill_run_utc(dt.date(2026, 4, 28))
    assert out == dt.datetime(
        2026, 4, 29, 3, 30, tzinfo=dt.timezone.utc,
    )


def test_next_ingest_eta_is_t_plus_one_at_2_utc():
    out = _next_ingest_eta_utc(dt.date(2026, 4, 28))
    assert out == dt.datetime(
        2026, 4, 29, 2, 0, tzinfo=dt.timezone.utc,
    )


def test_read_skip_lines_missing_file_returns_empty(tmp_path):
    out = _read_skip_lines(tmp_path / "missing.jsonl")
    assert out == []


def test_read_skip_lines_skips_malformed(tmp_path):
    p = tmp_path / "x.jsonl"
    p.write_text(
        "{\"a\":1}\n"
        "not-json\n"
        "{\"b\":2}\n",
        encoding="utf-8",
    )
    rows = _read_skip_lines(p)
    assert rows == [{"a": 1}, {"b": 2}]


# ---------------------------------------------------------------------------
# Boundary scans
# ---------------------------------------------------------------------------

def test_diagnostic_module_has_no_forbidden_imports():
    src = Path(dp_mod.__file__).read_text(encoding="utf-8")
    for tok in (
        "from broker_", "import broker_",
        "from live_", "import live_",
        "from execution_", "import execution_",
        "order_router",
    ):
        assert tok not in src, f"forbidden token {tok!r}"


def test_diagnostic_module_does_not_import_strict_engine():
    """Read-only: must not pull in engine_a, engine_b, selector,
    options paper engine, eval_runner."""
    src = Path(dp_mod.__file__).read_text(encoding="utf-8")
    for tok in (
        "data.strategy.engine_a", "data.strategy.engine_b",
        "data.strategy.selector",
        "options.paper.engine",
        "options.paper.eval_runner",
        "data.context.production",
    ):
        assert tok not in src, (
            f"diagnostic must not import strict-engine module: {tok!r}"
        )


def test_diagnostic_module_has_no_db_writes():
    src = Path(dp_mod.__file__).read_text(encoding="utf-8")
    for tok in (
        "INSERT INTO", "UPDATE ", "DELETE FROM",
        "session.execute(text(\"INSERT",
        "session.commit()",
        ".commit()",
    ):
        assert tok not in src, (
            f"diagnostic must not write to DB: {tok!r}"
        )


def test_diagnostic_module_does_not_register_into_REGISTRY():
    from apps.worker.src.jobs.registry import REGISTRY
    assert "pending_t1" not in [k.lower() for k in REGISTRY.keys()]
    assert all(
        "diagnostic" not in k.lower() for k in REGISTRY.keys()
    )


def test_diagnostic_module_no_recommendation_language():
    src = Path(dp_mod.__file__).read_text(encoding="utf-8")
    forbidden = (
        r"\brecommend\w*",
        r"\bbest\s+trade\b",
        r"\btop\s+pick\b",
        r"\btrade\s+now\b",
        r"\bplace\s+order\b",
        r"\bauto-?trade\b",
        r"\bpromote\b",
    )
    for pat in forbidden:
        assert not re.search(pat, src, flags=re.IGNORECASE), (
            f"forbidden token {pat!r}"
        )


def test_frontend_page_exists_and_is_read_only():
    """Static check on the React page: no buttons, no onClick, no
    forms, no mutation hooks."""
    page = (
        REPO_ROOT / "apps" / "web" / "src" / "pages" / "diagnostics"
        / "PendingT1.tsx"
    )
    assert page.exists()
    src = page.read_text(encoding="utf-8")
    for tok in (
        "<button", "<input", "<select", "<form",
        "onClick", "onChange", "onSubmit",
        "useMutation(", "apiPost(", "apiPut(", "apiPatch(",
        "apiDelete(",
    ):
        assert tok not in src, (
            f"frontend must be read-only: {tok!r}"
        )


def test_frontend_page_has_required_banner_text():
    page = (
        REPO_ROOT / "apps" / "web" / "src" / "pages" / "diagnostics"
        / "PendingT1.tsx"
    )
    src = page.read_text(encoding="utf-8")
    assert "Decisions waiting for next-bar fill (T+1 model)" in src
    assert "Read-only" in src or "READ-ONLY" in src


# ---------------------------------------------------------------------------
# HTTP contract — empty state (no DB, no skip artifacts)
# ---------------------------------------------------------------------------

class _FakeSession:
    """Minimal session stub: returns empty result for every execute."""

    def execute(self, sql, params=None):
        class _R:
            def all(self_inner):
                return []

            def first(self_inner):
                return None

        return _R()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_endpoint_returns_empty_when_no_artifacts(
    monkeypatch, tmp_path,
):
    monkeypatch.setattr(dp_mod, "SKIPS_DIR", tmp_path)

    def fake_factory():
        return _FakeSession()

    app = _build_app(session_factory=fake_factory)
    with TestClient(app) as client:
        r = client.get("/api/diagnostics/pending-t1")
    assert r.status_code == 200
    body = r.json()
    assert body["n_pending"] == 0
    assert body["pending"] == []
    assert "fill_model_note" in body
    assert FILL_STATUS not in body  # status is per-row only


def test_endpoint_clamps_lookback_days(monkeypatch, tmp_path):
    monkeypatch.setattr(dp_mod, "SKIPS_DIR", tmp_path)

    def fake_factory():
        return _FakeSession()

    app = _build_app(session_factory=fake_factory)
    with TestClient(app) as client:
        # Below 1
        r1 = client.get("/api/diagnostics/pending-t1?lookback_days=0")
        assert r1.status_code == 422
        # Above max
        r2 = client.get(
            "/api/diagnostics/pending-t1?lookback_days=999",
        )
        assert r2.status_code == 422
        # Valid edge
        r3 = client.get(
            "/api/diagnostics/pending-t1?lookback_days=30",
        )
        assert r3.status_code == 200


def test_endpoint_with_skip_artifact_surfaces_pending(
    monkeypatch, tmp_path,
):
    today = dt.date(2026, 4, 28)
    artifact = tmp_path / f"{today.isoformat()}.jsonl"
    artifact.write_text(
        json.dumps({
            "submitted_at": "2026-04-28T15:00:00Z",
            "as_of_date": "2026-04-28",
            "symbol": "ES",
            "engine": "A",
            "rule": "stress_mean_reversion_v1",
            "kind": "open_buy",
            "reason":
                "no price bar available after submitted_at; cannot fill",
        }) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(dp_mod, "SKIPS_DIR", tmp_path)

    def fake_factory():
        return _FakeSession()

    app = _build_app(session_factory=fake_factory)
    with TestClient(app) as client:
        r = client.get(
            "/api/diagnostics/pending-t1"
            f"?as_of_date={today.isoformat()}"
        )
    assert r.status_code == 200
    body = r.json()
    assert body["n_pending"] == 1
    row = body["pending"][0]
    assert row["symbol"] == "ES"
    assert row["fill_status"] == FILL_STATUS
    assert row["source"] == "skip_artifact"
    assert "next price_bar not available" in row["reason"]


def test_endpoint_response_no_recommendation_language(
    monkeypatch, tmp_path,
):
    today = dt.date(2026, 4, 28)
    artifact = tmp_path / f"{today.isoformat()}.jsonl"
    artifact.write_text(
        json.dumps({
            "submitted_at": "2026-04-28T15:00:00Z",
            "symbol": "SPY",
            "kind": "open_buy",
            "reason":
                "no price bar available after submitted_at; cannot fill",
        }) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(dp_mod, "SKIPS_DIR", tmp_path)

    def fake_factory():
        return _FakeSession()

    app = _build_app(session_factory=fake_factory)
    with TestClient(app) as client:
        r = client.get(
            "/api/diagnostics/pending-t1"
            f"?as_of_date={today.isoformat()}"
        )
    body_text = r.text.lower()
    for tok in (
        "recommend",
        "best trade",
        "top pick",
        "trade now",
        "place order",
        "auto-trade",
        "promote",
    ):
        assert tok not in body_text, f"forbidden token {tok!r}"


def test_endpoint_does_not_modify_skip_artifact(
    monkeypatch, tmp_path,
):
    today = dt.date(2026, 4, 28)
    artifact = tmp_path / f"{today.isoformat()}.jsonl"
    payload = json.dumps({
        "submitted_at": "2026-04-28T15:00:00Z",
        "symbol": "ES", "kind": "open_buy",
        "reason":
            "no price bar available after submitted_at; cannot fill",
    }) + "\n"
    artifact.write_text(payload, encoding="utf-8")
    mtime_before = artifact.stat().st_mtime
    monkeypatch.setattr(dp_mod, "SKIPS_DIR", tmp_path)

    def fake_factory():
        return _FakeSession()

    app = _build_app(session_factory=fake_factory)
    with TestClient(app) as client:
        client.get(
            "/api/diagnostics/pending-t1"
            f"?as_of_date={today.isoformat()}"
        )
    assert artifact.read_text(encoding="utf-8") == payload
    assert artifact.stat().st_mtime == mtime_before
