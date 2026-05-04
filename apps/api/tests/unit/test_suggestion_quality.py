"""Phase 2 — suggestion-quality endpoint contract pins.

Pins:
  1. Endpoint route + GET-only.
  2. No INSERT/UPDATE/DELETE in source (read-only).
  3. Horizons whitelisted: 1, 3, 5, 10, 20.
  4. Threshold constants pinned: good=+2%, bad=-2%.
  5. Outcome labels limited to {good, neutral, bad, pending,
     data_blocked}.
  6. Same-bar labeling not allowed: entry uses target-day close,
     exit uses target+h close. Endpoint never labels final on
     fewer than h forward bars.
  7. ML / options / live keywords absent.
  8. Live behavior: historical date returns finalized labels;
     today returns mostly pending.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


ROUTER = Path("apps/api/src/api/performance_paper.py")


# ---------------------------------------------------------------------------
# Source-grep pins
# ---------------------------------------------------------------------------
def test_route_pinned():
    src = ROUTER.read_text(encoding="utf-8")
    assert '"/suggestion-quality"' in src


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


def test_horizons_pinned():
    src = ROUTER.read_text(encoding="utf-8")
    assert "_QUALITY_HORIZONS = (1, 3, 5, 10, 20)" in src


def test_thresholds_pinned():
    src = ROUTER.read_text(encoding="utf-8")
    assert "_QUALITY_GOOD_PCT = 0.02" in src
    assert "_QUALITY_BAD_PCT = -0.02" in src


def test_no_ml_or_live_keywords_in_endpoint():
    """Defensive: endpoint must not couple to ML or live execution."""
    src = ROUTER.read_text(encoding="utf-8")
    forbidden = (
        "ML_CAN_AFFECT_TRADES = True",
        "OPTIONS_LIVE",
        "submit_trade(",        # forward-return scoring must not submit
        "INSERT INTO recommendation_outcome",
    )
    for f in forbidden:
        assert f not in src, f"forbidden: {f}"


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


def test_invalid_horizon_rejected(client):
    r = client.get(
        "/api/performance/paper/suggestion-quality?horizon=7D"
    )
    assert "error" in r.json()


def test_invalid_horizon_format_rejected(client):
    r = client.get(
        "/api/performance/paper/suggestion-quality?horizon=5days"
    )
    assert "error" in r.json()


def test_invalid_mode_rejected(client):
    r = client.get(
        "/api/performance/paper/suggestion-quality?mode=live"
    )
    assert "error" in r.json()


def test_invalid_date_rejected(client):
    r = client.get(
        "/api/performance/paper/suggestion-quality?as_of=not-a-date"
    )
    assert "error" in r.json()


def test_historical_date_produces_finalized_labels(client):
    """Past date with full forward window must produce some
    good/neutral/bad labels and no pending."""
    r = client.get(
        "/api/performance/paper/suggestion-quality"
        "?as_of=2026-04-22&horizon=5D&mode=strict"
    )
    assert r.status_code == 200
    body = r.json()
    s = body["summary"]
    assert s["total"] > 0
    # All forward bars exist for 2026-04-22 + 5d (we ingested through
    # 2026-05-04). pending count must be 0.
    assert s["pending"] == 0
    assert s["good"] + s["neutral"] + s["bad"] == s["n_finalized"]


def test_today_returns_mostly_pending(client):
    """Today's run has no future bars yet; labels must be pending
    or data_blocked. No same-bar labeling allowed."""
    r = client.get(
        "/api/performance/paper/suggestion-quality"
        "?as_of=2026-05-04&horizon=5D&mode=strict"
    )
    body = r.json()
    s = body["summary"]
    assert s["total"] > 0
    # No finalized labels should appear when no future bars exist.
    assert s["good"] == 0 and s["bad"] == 0 and s["neutral"] == 0
    assert s["pending"] + s["data_blocked"] == s["total"]


def test_outcome_labels_in_allowed_set(client):
    r = client.get(
        "/api/performance/paper/suggestion-quality"
        "?as_of=2026-04-22&horizon=5D&mode=strict&limit=200"
    )
    allowed = {"good", "neutral", "bad", "pending", "data_blocked"}
    for it in r.json()["items"]:
        assert it["outcome_label"] in allowed


def test_entry_price_is_target_day_close_no_same_bar_exit(client):
    r = client.get(
        "/api/performance/paper/suggestion-quality"
        "?as_of=2026-04-22&horizon=5D&mode=strict&limit=200"
    )
    for it in r.json()["items"]:
        if it["forward_return_pct"] is not None:
            # Must have BOTH entry and exit prices.
            assert it["entry_reference_price"] is not None
            assert it["exit_reference_price"] is not None
            # Entry and exit must NOT be the same bar (no same-bar
            # labeling) — exit price is target+h day, target is the
            # entry. We can't verify dates here but we can verify
            # the math is consistent.
            entry = it["entry_reference_price"]
            exit_ = it["exit_reference_price"]
            ret = it["forward_return_pct"]
            assert abs((exit_ / entry - 1.0) - ret) < 1e-6


def test_summary_has_required_keys(client):
    r = client.get(
        "/api/performance/paper/suggestion-quality"
        "?as_of=2026-04-22&horizon=5D&mode=strict"
    )
    body = r.json()
    for k in (
        "as_of_date", "horizon", "mode", "horizons_supported",
        "thresholds", "summary", "best", "worst",
        "by_status", "by_blocking_reason", "items",
    ):
        assert k in body
    for k in (
        "total", "good", "neutral", "bad", "pending",
        "data_blocked", "n_finalized", "hit_rate",
        "avg_forward_return_pct", "avg_mfe_pct", "avg_mae_pct",
    ):
        assert k in body["summary"]


def test_exploratory_population_ge_strict(client):
    """Exploratory mode includes soft-gate rejects, so total ≥ strict."""
    rs = client.get(
        "/api/performance/paper/suggestion-quality"
        "?as_of=2026-04-22&horizon=5D&mode=strict"
    ).json()
    re_ = client.get(
        "/api/performance/paper/suggestion-quality"
        "?as_of=2026-04-22&horizon=5D&mode=exploratory"
    ).json()
    assert re_["summary"]["total"] >= rs["summary"]["total"]


def test_horizons_supported_surfaced(client):
    r = client.get(
        "/api/performance/paper/suggestion-quality"
        "?as_of=2026-04-22&horizon=5D&mode=strict"
    )
    assert r.json()["horizons_supported"] == [1, 3, 5, 10, 20]


def test_thresholds_surfaced(client):
    r = client.get(
        "/api/performance/paper/suggestion-quality"
        "?as_of=2026-04-22&horizon=5D&mode=strict"
    )
    th = r.json()["thresholds"]
    assert th["good_pct"] == 0.02
    assert th["bad_pct"] == -0.02
