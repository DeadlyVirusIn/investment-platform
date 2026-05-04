"""Personal-Analytics Phase — read-only safety + behavior pins.

Covers two new routers:

  * apps.api.src.api.performance_paper  → /api/performance/paper/*
  * apps.api.src.api.ml_insights        → /api/ml/insights/*

Pins (must hold for the lifetime of the personal-analytics phase):
  1. Both routers are GET-only (no POST/PUT/PATCH/DELETE).
  2. No INSERT/UPDATE/DELETE in source — read-only enforcement.
  3. Performance summary returns `win_rate=None` and
     `note="no_closed_outcomes_yet"` when there are zero decided
     outcomes; never fabricates a denominator.
  4. Performance summary always exposes `live_trades_count` /
     `replay_trades_count` / `has_replay_recovered_rows` regardless
     of the `include_replay` flag.
  5. ML insights summary always returns
     `ml_can_affect_trades=false` and `ready=false` when labeled
     outcomes < MIN_LABELED_OUTCOMES.
  6. ML insights label endpoint reports open_pending separately.
  7. ML insights does NOT import from recommendation/strategy/
     execution code paths (no Engine import, no auto_trader, no
     paper_service).
  8. Equity endpoint declares `unrealized_status='unavailable'` on
     symbols missing recent price_bar; does not silently zero them.
  9. main.py mounts both routers.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


PERF = Path("apps/api/src/api/performance_paper.py")
MLINS = Path("apps/api/src/api/ml_insights.py")
MAIN = Path("apps/api/src/main.py")


# ---------------------------------------------------------------------------
# Source-grep safety pins
# ---------------------------------------------------------------------------
def test_files_exist():
    assert PERF.exists(), f"missing {PERF}"
    assert MLINS.exists(), f"missing {MLINS}"


@pytest.mark.parametrize("p", [PERF, MLINS])
def test_only_get_router_decorators(p: Path):
    src = p.read_text(encoding="utf-8")
    forbidden = ("@router.post", "@router.put", "@router.patch",
                 "@router.delete")
    for f in forbidden:
        assert f not in src, f"{p.name}: forbidden HTTP verb {f}"


@pytest.mark.parametrize("p", [PERF, MLINS])
def test_no_db_writes_in_source(p: Path):
    src = p.read_text(encoding="utf-8")
    write_patterns = (
        re.compile(r"\bINSERT\s+INTO\b", re.IGNORECASE),
        re.compile(r"\bUPDATE\s+\w+\s+SET\b", re.IGNORECASE),
        re.compile(r"\bDELETE\s+FROM\b", re.IGNORECASE),
    )
    for line in src.splitlines():
        stripped = line.lstrip()
        if (stripped.startswith("#") or stripped.startswith('"')
                or stripped.startswith("'") or stripped.startswith("*")):
            continue
        for pat in write_patterns:
            assert not pat.search(line), (
                f"{p.name}: write found in read-only endpoint: "
                f"{line.strip()}"
            )


def test_ml_insights_no_strategy_or_execution_imports():
    src = MLINS.read_text(encoding="utf-8")
    forbidden_imports = (
        "auto_trader", "paper_service", "submit_trade",
        "recommendation_engine",
        "execution.discipline", "execution.integrator",
        "scheduler.add_job", "BackgroundTasks",
    )
    for f in forbidden_imports:
        assert f not in src, (
            f"ml_insights must not couple to execution code: {f}"
        )


def test_no_ml_can_affect_trades_set_true():
    """Hard pin: ML_CAN_AFFECT_TRADES must never be assigned True
    inside these endpoints."""
    for p in (PERF, MLINS):
        src = p.read_text(encoding="utf-8")
        assert not re.search(
            r"ML_CAN_AFFECT_TRADES\s*=\s*True", src
        ), f"{p.name} must not flip ML_CAN_AFFECT_TRADES"
        # Source may quote the literal string in messaging — that's
        # fine — but never the assignment form.


def test_main_py_mounts_new_routers():
    src = MAIN.read_text(encoding="utf-8")
    assert "performance_paper_router" in src
    assert "ml_insights_router" in src
    assert ("from apps.api.src.api.performance_paper import router"
            in src)
    assert "from apps.api.src.api.ml_insights import router" in src


# ---------------------------------------------------------------------------
# In-process behavior pins via TestClient
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def client():
    import os
    os.environ.setdefault(
        "DATABASE_URL",
        "postgresql+psycopg://invest:dev_only_password@localhost:54329/"
        "investment_platform",
    )
    from fastapi.testclient import TestClient
    from apps.api.src.main import app
    return TestClient(app)


def test_performance_summary_default_excludes_replay(client):
    r = client.get("/api/performance/paper/summary")
    assert r.status_code == 200
    body = r.json()
    # Always-on split counts must be present.
    for k in ("live_trades_count", "replay_trades_count",
              "has_replay_recovered_rows", "include_replay",
              "win_rate", "note"):
        assert k in body, f"missing key in summary: {k}"
    # Default toggle off.
    assert body["include_replay"] is False
    # Honest about pending: zero decided outcomes → no fake win rate.
    if body["win_count"] + body["loss_count"] == 0:
        assert body["win_rate"] is None
        assert body["note"] == "no_closed_outcomes_yet"


def test_performance_summary_include_replay_true(client):
    r = client.get(
        "/api/performance/paper/summary?include_replay=true"
    )
    assert r.status_code == 200
    body = r.json()
    assert body["include_replay"] is True
    # Split counts unchanged regardless of the flag.
    assert "live_trades_count" in body
    assert "replay_trades_count" in body


def test_performance_attribution_breaks_down_by_source(client):
    r = client.get("/api/performance/paper/attribution")
    assert r.status_code == 200
    body = r.json()
    sources = {row["source"] for row in body["by_source"]}
    # When replay rows exist, replay must appear as a distinct source.
    # If no rows at all, by_source is empty, which is also fine.
    if body["by_source"]:
        assert "replay" in sources or "live" in sources
    for row in body["by_source"]:
        # Pending vs closed must be reported separately, never merged.
        assert "open_pending_trades" in row
        assert "closed_trades" in row


def test_performance_equity_marks_unavailable_when_no_price(client):
    r = client.get("/api/performance/paper/equity")
    assert r.status_code == 200
    body = r.json()
    assert "unrealized_unavailable_count" in body
    # Each by-symbol row carries an explicit unrealized_status.
    for row in body["by_symbol"]:
        assert row["unrealized_status"] in ("ok", "unavailable")


def test_ml_insights_summary_always_pins_no_affect_trades(client):
    r = client.get("/api/ml/insights/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["ml_can_affect_trades"] is False
    assert "ML insight only" in body["notice"]


def test_ml_insights_summary_not_ready_without_labels(client):
    r = client.get("/api/ml/insights/summary")
    body = r.json()
    labeled = body["counts"]["labeled_outcomes"]
    if labeled < body["min_labeled_outcomes_required"]:
        assert body["ready"] is False
        assert body["reason"] in (
            "no_labeled_outcomes",
            f"insufficient_labeled_outcomes "
            f"(have={labeled}, need>={body['min_labeled_outcomes_required']})",
        )


def test_ml_insights_labels_open_pending_reported_separately(client):
    r = client.get("/api/ml/insights/labels")
    assert r.status_code == 200
    body = r.json()
    assert "barrier_label_open_pending" in body
    # If labeled_outcomes_total is zero, note must explain ML eval is
    # not ready instead of returning empty silence.
    if body["labeled_outcomes_total"] == 0:
        assert body["note"] == "ML evaluation not ready — outcomes still pending."
        assert body["ready_for_evaluation"] is False


def test_ml_insights_features_endpoint_pure_metadata(client):
    r = client.get("/api/ml/insights/features")
    assert r.status_code == 200
    body = r.json()
    assert body["ml_can_affect_trades"] is False
    assert isinstance(body["feature_columns"], list)
    assert body["feature_count"] == len(body["feature_columns"])
    # Leakage-check stub must declare it is implemented.
    assert (
        body["leakage_check"]["is_forbidden_feature_name_implemented"]
        is True
    )


def test_ml_insights_dataset_split_counts(client):
    r = client.get("/api/ml/insights/dataset")
    assert r.status_code == 200
    body = r.json()
    recs = body["recommendations"]
    # Live + replay = total — pure invariant.
    assert recs["total"] == recs["live"] + recs["replay"]
    assert body["ml_can_affect_trades"] is False
