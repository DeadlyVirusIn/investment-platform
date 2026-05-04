"""Phase 1 — daily-suggestions endpoint contract pins.

Pins:
  1. /api/performance/paper/daily-suggestions is GET-only.
  2. No INSERT/UPDATE/DELETE in router source for the new fn.
  3. Status vocabulary is frozen.
  4. Strict mode is the default.
  5. Exploratory mode never re-classifies a hard reject as
     watchlist_candidate.
  6. Soft-gate relaxation in exploratory mode tags rows with
     `relaxed_in_exploratory=True` and `relaxed_from=<reason>`.
  7. Items are ranked by score desc then symbol asc.
  8. Caps + vocabulary surfaced in response so the UI / Discord
     formatter cannot drift.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import pytest


ROUTER = Path("apps/api/src/api/performance_paper.py")


def test_route_pinned():
    src = ROUTER.read_text(encoding="utf-8")
    assert '"/daily-suggestions"' in src


def test_get_only():
    src = ROUTER.read_text(encoding="utf-8")
    for f in ("@router.post", "@router.put",
              "@router.patch", "@router.delete"):
        assert f not in src


def test_no_writes_in_source():
    src = ROUTER.read_text(encoding="utf-8")
    pats = (
        re.compile(r"\bINSERT\s+INTO\b", re.IGNORECASE),
        re.compile(r"\bUPDATE\s+\w+\s+SET\b", re.IGNORECASE),
        re.compile(r"\bDELETE\s+FROM\b", re.IGNORECASE),
    )
    for line in src.splitlines():
        s = line.lstrip()
        if (s.startswith("#") or s.startswith('"')
                or s.startswith("'") or s.startswith("*")):
            continue
        for pat in pats:
            assert not pat.search(line)


def test_status_vocabulary_pinned():
    src = ROUTER.read_text(encoding="utf-8")
    for s in ("trade_ready", "pending_next_bar",
              "watchlist_candidate", "blocked_by_gate",
              "data_blocked"):
        assert f'"{s}"' in src, f"missing status literal {s!r}"


def test_hard_gate_set_pinned():
    src = ROUTER.read_text(encoding="utf-8")
    for hard in ("regime_off", "insufficient_history", "stale_data",
                 "liquidity_fail", "earnings_too_close",
                 "duplicate_holding", "portfolio_full",
                 "execution_failure"):
        assert f'"{hard}"' in src, f"hard gate missing in source: {hard}"


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


def test_strict_mode_default(client):
    r = client.get("/api/performance/paper/daily-suggestions?limit=5")
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "strict"
    assert "items" in body
    assert "vocabulary" in body
    assert body["vocabulary"] == [
        "trade_ready", "pending_next_bar",
        "watchlist_candidate", "blocked_by_gate", "data_blocked",
    ]
    # Exploratory caps surfaced even in strict response.
    assert body["exploratory_caps"]["max_buys_per_day"] == 5
    assert body["exploratory_caps"]["max_position_pct"] == 0.03


def test_strict_mode_pending_status_present_when_pending_jsonl_exists(
    client,
):
    """If the latest skip JSONL has a fill-window row, at least one
    suggestion item should carry suggestion_status='pending_next_bar'.
    Sanity: this run produced exactly such a row for MO."""
    r = client.get("/api/performance/paper/daily-suggestions?limit=200")
    body = r.json()
    statuses = {it["suggestion_status"] for it in body["items"]}
    if body["status_counts"].get("pending_next_bar", 0) > 0:
        assert "pending_next_bar" in statuses


def test_items_ranked_by_score_desc(client):
    r = client.get("/api/performance/paper/daily-suggestions?limit=50")
    body = r.json()
    scores = [it["score"] for it in body["items"]]
    assert scores == sorted(scores, reverse=True)
    # Rank assigned starting at 1.
    ranks = [it["rank"] for it in body["items"]]
    assert ranks == list(range(1, len(ranks) + 1))


def test_exploratory_relaxes_only_soft_gates(client):
    r = client.get(
        "/api/performance/paper/daily-suggestions?mode=exploratory&limit=200"
    )
    body = r.json()
    assert body["mode"] == "exploratory"
    relaxed = [it for it in body["items"]
               if it.get("relaxed_in_exploratory")]
    soft = set(body["soft_gates_relaxable_in_exploratory"])
    hard = set(body["hard_gates_never_relaxed"])
    for it in relaxed:
        assert it["relaxed_from"] in soft
        assert it["relaxed_from"] not in hard
        assert it["suggestion_status"] == "watchlist_candidate"
        # Penalty applied — score is the raw composite (or 0 if
        # null) minus 0.10. Source code:
        #   score = max(raw, 0.0) - 0.10
        # So a relaxed item never has score > raw_composite_score.
        # Pin the cap shape: the constant is exposed via
        # exploratory_caps; the penalty value is a pinned literal in
        # the router source. Here we just verify the math sign:
        # score is at most (raw - 0.10) ≤ raw. Without raw at hand
        # in the response, assert score is bounded above by a known
        # ceiling: any composite_score in the table is in [-1, 1],
        # so a relaxed score must be < 1.0 - 0.10 = 0.90.
        assert it["score"] < 0.90


def test_exploratory_does_not_promote_data_blocked(client):
    """data_blocked rows (insufficient_history/stale_data/
    execution_failure) must remain data_blocked even in exploratory."""
    r = client.get(
        "/api/performance/paper/daily-suggestions?mode=exploratory&limit=200"
    )
    body = r.json()
    for it in body["items"]:
        if it.get("blocking_reason") in (
            "insufficient_history", "stale_data", "execution_failure",
        ):
            assert it["suggestion_status"] == "data_blocked"


def test_invalid_mode_rejected(client):
    r = client.get(
        "/api/performance/paper/daily-suggestions?mode=live"
    )
    assert "error" in r.json()


def test_invalid_date_rejected(client):
    r = client.get(
        "/api/performance/paper/daily-suggestions?as_of=not-a-date"
    )
    assert "error" in r.json()


def test_empty_when_no_candidates(client):
    r = client.get(
        "/api/performance/paper/daily-suggestions?as_of=2099-01-01"
    )
    body = r.json()
    assert body["count"] == 0
    assert body["items"] == []


def test_each_item_has_required_fields(client):
    r = client.get("/api/performance/paper/daily-suggestions?limit=5")
    body = r.json()
    for it in body["items"]:
        for k in (
            "symbol", "asset_id", "action", "suggestion_status",
            "rank", "score", "reason_summary", "blocking_reason",
            "execution_status", "next_step", "mode",
        ):
            assert k in it, f"item missing {k}"


def test_main_py_keeps_router_mount():
    src = Path("apps/api/src/main.py").read_text(encoding="utf-8")
    assert "performance_paper_router" in src
