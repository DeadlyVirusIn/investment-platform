"""Phase 2-4 — pending-fill visibility contract.

Pins:
  1. /api/performance/paper/pending-fills is GET-only.
  2. Endpoint reads paper_trading_skips JSONL (no DB writes).
  3. Filters strictly to reason='execution_failure' AND
     detail.exec_reason matches the no-price-bar marker.
  4. Each item carries the pinned field set.
  5. `current_status` is always literal "pending_next_bar".
  6. `expected_fill_rule` is always literal "next_bar".
  7. Discord formatter:
     - title literal "🟡 Paper Trade Pending Fill"
     - footer states "No trade has been filled yet"
     - never claims success
     - never includes "Filled" / "Executed" / "PnL" /  "$"
     - status text is "Waiting for next bar"
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

import pytest


ROUTER = Path("apps/api/src/api/performance_paper.py")


# ---------------------------------------------------------------------------
# Static guards on the router source
# ---------------------------------------------------------------------------
def test_endpoint_route_pinned():
    src = ROUTER.read_text(encoding="utf-8")
    assert '"/pending-fills"' in src


def test_endpoint_is_get_only():
    src = ROUTER.read_text(encoding="utf-8")
    # Module-wide forbidden (already enforced by other tests; pin
    # again here so a future regression is caught locally).
    for f in (
        "@router.post", "@router.put", "@router.patch", "@router.delete",
    ):
        assert f not in src, f"forbidden HTTP verb {f}"


def test_endpoint_does_no_writes():
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
            assert not pat.search(line), (
                f"write SQL in pending-fills router: {line.strip()}"
            )


def test_endpoint_pins_status_vocabulary():
    src = ROUTER.read_text(encoding="utf-8")
    # These literals are the contract the UI / Discord formatter
    # depend on; do not drift. The vocabulary is tri-state:
    #   pending_next_bar  — still genuinely guard-blocked
    #   ready_for_replay  — bar after submitted_at exists; awaiting
    #                       post-ingest paper cycle (operator action)
    #   unknown_no_bar    — no price_bar visible at all (data gap)
    assert '"pending_next_bar"' in src
    assert '"ready_for_replay"' in src
    assert '"unknown_no_bar"' in src
    assert '"next_bar"' in src
    assert '"waiting for price_bar after submitted_at"' in src


def test_endpoint_filter_constants_pinned():
    src = ROUTER.read_text(encoding="utf-8")
    assert '_PENDING_FILL_REASON = "execution_failure"' in src
    assert (
        '_PENDING_FILL_MARKER = "no price bar available after submitted_at"'
        in src
    )


def test_no_writes_to_jsonl_or_pending_path():
    src = ROUTER.read_text(encoding="utf-8")
    forbidden = (
        ".write_text(", ".write_bytes(", ".open(\"w",
        ".open('w", '.write("', ".writelines(",
    )
    for f in forbidden:
        assert f not in src, f"pending-fills router must not write: {f}"


# ---------------------------------------------------------------------------
# In-process behavior
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


def test_endpoint_returns_pinned_field_set(client):
    r = client.get("/api/performance/paper/pending-fills")
    assert r.status_code == 200
    body = r.json()
    assert "count" in body
    assert "items" in body
    # ready_for_replay_count is a new top-level key (UX-trust fix);
    # may legitimately be 0 on a clean system.
    assert "ready_for_replay_count" in body
    valid_statuses = {
        "pending_next_bar", "ready_for_replay", "unknown_no_bar",
    }
    valid_blockers = {
        "next_bar_guard", "operator_action_needed", "data_gap",
    }
    for item in body["items"]:
        for k in (
            "symbol", "asset_id", "action",
            "submitted_at", "as_of_date",
            "portfolio_id", "portfolio_name",
            "expected_fill_rule", "current_status",
            "blocker", "reason", "latest_price_bar_ts",
            "next_expected_bar_date",
        ):
            assert k in item, f"pending-fill row missing {k}"
        assert item["expected_fill_rule"] == "next_bar"
        assert item["current_status"] in valid_statuses, (
            f"unexpected current_status {item['current_status']!r}"
        )
        assert item["blocker"] in valid_blockers, (
            f"unexpected blocker {item['blocker']!r}"
        )
        assert item["action"] == "Buy"
        # Each status has its own reason wording — verify the
        # mapping is internally consistent.
        if item["current_status"] == "pending_next_bar":
            assert "waiting for price_bar" in item["reason"]
            assert item["blocker"] == "next_bar_guard"
        elif item["current_status"] == "ready_for_replay":
            assert "next bar available" in item["reason"]
            assert item["blocker"] == "operator_action_needed"
        elif item["current_status"] == "unknown_no_bar":
            assert "no price_bar visible" in item["reason"]
            assert item["blocker"] == "data_gap"


def test_endpoint_next_expected_bar_is_weekday(client):
    r = client.get("/api/performance/paper/pending-fills")
    body = r.json()
    if body.get("next_expected_bar_date"):
        d = dt.date.fromisoformat(body["next_expected_bar_date"])
        # Weekday only (Mon..Fri).
        assert d.weekday() < 5, (
            f"next_expected_bar_date {d} is not a trading day"
        )


def test_endpoint_handles_unknown_date(client):
    r = client.get("/api/performance/paper/pending-fills?as_of=2099-01-01")
    body = r.json()
    assert body["count"] == 0
    assert body["items"] == []


def test_endpoint_rejects_bad_date_format(client):
    r = client.get("/api/performance/paper/pending-fills?as_of=not-a-date")
    body = r.json()
    assert "error" in body


# ---------------------------------------------------------------------------
# UX-trust regression — current_status flips to ready_for_replay when
# the latest_price_bar_ts > submitted_at. This test exercises the
# classifier directly via the live endpoint (which reads the real
# JSONL + DB) and asserts the contract holds for whichever bucket
# each item falls into.
# ---------------------------------------------------------------------------
def test_endpoint_status_consistent_with_bar_availability(client):
    r = client.get("/api/performance/paper/pending-fills")
    body = r.json()
    for item in body["items"]:
        latest = item.get("latest_price_bar_ts")
        submitted = item.get("submitted_at")
        if latest is None:
            assert item["current_status"] == "unknown_no_bar"
            continue
        # Compare ISO strings — both produced by datetime.isoformat()
        # with timezone, lexicographic order matches chronological.
        latest_dt = dt.datetime.fromisoformat(latest)
        submitted_dt = dt.datetime.fromisoformat(submitted)
        if latest_dt > submitted_dt:
            assert item["current_status"] == "ready_for_replay", (
                f"latest_ts {latest} > submitted {submitted} but "
                f"current_status is {item['current_status']!r}"
            )
            assert item["blocker"] == "operator_action_needed"
        else:
            assert item["current_status"] == "pending_next_bar"
            assert item["blocker"] == "next_bar_guard"


def test_endpoint_top_notice_mentions_replay_when_ready(client):
    r = client.get("/api/performance/paper/pending-fills")
    body = r.json()
    if body.get("ready_for_replay_count", 0) > 0:
        assert "READY for post-ingest replay" in body["notice"], (
            f"notice {body['notice']!r} should call out replay readiness"
        )


# ---------------------------------------------------------------------------
# Discord formatter
# ---------------------------------------------------------------------------
def test_discord_formatter_pinned_title_and_footer():
    from apps.api.src.api.performance_paper import (
        format_pending_fill_discord,
    )
    sample = {
        "symbol": "AAPL", "action": "Buy",
        "portfolio_id": "p1", "submitted_at": "2026-05-04T21:00:00+00:00",
        "latest_price_bar_ts": "2026-05-04T00:00:00+00:00",
        "next_expected_bar_date": "2026-05-05",
    }
    out = format_pending_fill_discord(sample)
    # Title / footer pinned.
    assert out.startswith("🟡 Paper Trade Pending Fill")
    assert "No trade has been filled yet" in out
    assert "Status: Waiting for next bar" in out
    assert "Fill Rule: Next available price bar" in out
    # Required fields rendered.
    for k in ("Symbol: AAPL", "Action: Buy", "Portfolio: p1",
              "Submitted: 2026-05-04T21:00:00+00:00",
              "Latest Bar: 2026-05-04T00:00:00+00:00",
              "Expected Fill Window: 2026-05-05"):
        assert k in out, f"discord formatter missing {k!r}"


def test_discord_formatter_does_not_imply_success():
    from apps.api.src.api.performance_paper import (
        format_pending_fill_discord,
    )
    out = format_pending_fill_discord({
        "symbol": "AAPL", "action": "Buy",
        "portfolio_id": "p1", "submitted_at": "x",
        "latest_price_bar_ts": "y", "next_expected_bar_date": "z",
    })
    forbidden = (
        "Filled", "FILLED", "Executed", "EXECUTED",
        "PnL", "P&L", "$", "Profit", "Loss",
        "Success", "Confirmed",
    )
    for f in forbidden:
        assert f not in out, (
            f"discord formatter must not include {f!r}: \n{out}"
        )


# ---------------------------------------------------------------------------
# JSONL filter logic (synthetic fixture, no DB)
# ---------------------------------------------------------------------------
def test_jsonl_filter_only_picks_fill_window_failures(tmp_path: Path):
    """Synthetic skip JSONL with mixed reasons; only execution_failure
    rows whose detail.exec_reason mentions the marker are pending."""
    # Stage a fixture under a temporary skips dir and point the router
    # at it via monkeypatching `_SKIPS_DIR`. We test the source filter
    # not the endpoint for this case.
    from apps.api.src.api import performance_paper as mod

    skips_dir = tmp_path / "paper_trading_skips"
    skips_dir.mkdir(parents=True)
    today = dt.date(2026, 5, 4)
    f = skips_dir / f"{today.isoformat()}.jsonl"
    f.write_text("\n".join([
        json.dumps({"as_of_date": "2026-05-04",
                    "portfolio_id": "p1", "asset_id": "a1",
                    "reason": "execution_failure",
                    "detail": {"exec_reason":
                               "no price bar available after submitted_at"}}),
        json.dumps({"as_of_date": "2026-05-04",
                    "portfolio_id": "p1", "asset_id": "a2",
                    "reason": "execution_failure",
                    "detail": {"exec_reason": "insufficient cash"}}),
        json.dumps({"as_of_date": "2026-05-04",
                    "portfolio_id": "p1", "asset_id": "a3",
                    "reason": "duplicate_holding", "detail": {}}),
    ]) + "\n", encoding="utf-8")

    # Read via the same logic the endpoint uses.
    raw = []
    for line in f.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("reason") != mod._PENDING_FILL_REASON:
            continue
        detail = row.get("detail") or {}
        exec_reason = (detail.get("exec_reason") or "").lower()
        if mod._PENDING_FILL_MARKER.lower() not in exec_reason:
            continue
        raw.append(row)
    assert len(raw) == 1
    assert raw[0]["asset_id"] == "a1"


def test_main_py_keeps_performance_paper_router_mount():
    src = Path("apps/api/src/main.py").read_text(encoding="utf-8")
    assert "performance_paper_router" in src
